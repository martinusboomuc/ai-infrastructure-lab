"""Prefect flows for BankML's lifecycle (ROADMAP Phase 4: "Prefect introduced for the end-to-end
flow"). Thin orchestration only — wraps the existing feature, training and drift entrypoints as
tasks; none of their own behavior changes.

Domain-agnostic (ADR-0002): every task and flow here takes `domain` explicitly, and the feature
pipeline to run is resolved dynamically via `bankml.features.<domain>.pipeline` — the same
dispatch pattern `bankml.training.pipeline` already uses for its own feature-preparation import.
This file used to hardcode Credit Risk throughout (a module-level
`from bankml.features.credit import pipeline`, a flow named `credit_pipeline`, `domain="credit"`
baked into `train_and_evaluate_task` itself) with only Credit Risk ever having run through it;
Phase 6 generalized it once Fraud Detection existed to actually exercise the gap.
"""

from __future__ import annotations

import argparse
import importlib
import os
from types import ModuleType

from prefect import flow, task

from bankml.monitoring import drift as drift_module
from bankml.training import pipeline as training_pipeline


def _load_feature_pipeline(domain: str) -> ModuleType:
    return importlib.import_module(f"bankml.features.{domain}.pipeline")


@task(name="build-features", retries=1)
def build_features_task(domain: str) -> None:
    _load_feature_pipeline(domain).main()


@task(name="train-and-evaluate", retries=0)
def train_and_evaluate_task(domain: str) -> None:
    # No retry: a training run that fails partway shouldn't silently re-run and double-log to
    # MLflow — a failure here should surface, not be papered over.
    training_pipeline.main(domain=domain)


@flow(name="bankml-pipeline")
def bankml_pipeline(domain: str = "credit") -> None:
    """Build features, then train + evaluate + gate + (maybe) promote, as one tracked run."""
    build_features_task(domain)
    train_and_evaluate_task(domain)


@task(name="check-drift", retries=0)
def check_drift_task(domain: str) -> dict:
    """Run the drift job (Phase 5) and log/push it exactly as `make drift` does — this task
    *is* `make drift`'s own logic, not a separate copy of it, so a drift-triggered retraining run
    and a hand-run drift check always agree on what counts as drifted.
    """
    result = drift_module.run_drift_job(domain)
    if result["status"] == "no_data":
        return result

    drift_module.log_drift_run(domain, result)
    pushgateway_url = os.environ.get("BANKML_PUSHGATEWAY_URL")
    if pushgateway_url:
        drift_module.push_drift_metrics(domain, result, pushgateway_url)
    return result


@flow(name="bankml-drift-check-and-retrain")
def drift_check_and_retrain(domain: str = "credit") -> None:
    """Phase 5's exit criterion: injecting synthetic drift raises an alert (Session 017's Grafana
    rules fire off the metrics `check_drift_task` pushes) and triggers a retraining run, which is
    then blocked or promoted by the gate on its own merits — drift is what *decides to retrain*,
    never what decides to *promote*. A clean drift check does nothing further;
    `train_and_evaluate_task` only runs when either input or prediction drift actually crossed
    its threshold.

    Retrains against the existing feature set (`train_and_evaluate_task` alone), not
    `bankml_pipeline`'s full build-features-then-train — deliberately, not an oversight.
    ARCHITECTURE.md's own known simplifications: "Datasets are public, historical and static;
    there is no live transaction stream," so re-running `build_features_task` here would rebuild
    byte-identical features from the same static raw tables every time, at real cost (it loads
    every relational table — several with millions of rows — into memory at once, found the hard
    way: it OOM-killed a real drift-triggered retrain on `docker-01`'s 4GB, something
    `train_and_evaluate_task` alone never comes close to). If this project ever gains a live
    ingestion pipeline, this is exactly where `build_features_task` would need to come back.
    """
    result = check_drift_task(domain)
    if result["status"] == "no_data":
        return
    if result["input_drift"]["dataset_drift"] or result["prediction_drift"]["dataset_drift"]:
        train_and_evaluate_task(domain)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flow",
        choices=["pipeline", "drift-check-and-retrain"],
        default="pipeline",
    )
    parser.add_argument("--domain", default="credit")
    args = parser.parse_args()

    if args.flow == "pipeline":
        bankml_pipeline(domain=args.domain)
    else:
        drift_check_and_retrain(domain=args.domain)
