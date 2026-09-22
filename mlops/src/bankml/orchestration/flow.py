"""Prefect flows for the Credit Risk pipeline (ROADMAP Phase 4: "Prefect introduced for the
end-to-end flow"). Thin orchestration only — wraps the existing feature, training and drift
entrypoints as tasks; none of their own behavior changes. `make` plus GitHub Actions was
sufficient while the pipeline was linear (ARCHITECTURE.md's stack rationale); this is the first
point retries and a visible run history earn their keep.
"""

from __future__ import annotations

import argparse
import os

from prefect import flow, task

from bankml.features.credit import pipeline as feature_pipeline
from bankml.monitoring import drift as drift_module
from bankml.training import pipeline as training_pipeline


@task(name="build-credit-features", retries=1)
def build_features_task() -> None:
    feature_pipeline.main()


@task(name="train-and-evaluate-credit", retries=0)
def train_and_evaluate_task() -> None:
    # No retry: a training run that fails partway shouldn't silently re-run and double-log to
    # MLflow — a failure here should surface, not be papered over.
    training_pipeline.main(domain="credit")


@flow(name="bankml-credit-pipeline")
def credit_pipeline() -> None:
    """Build features, then train + evaluate + gate + (maybe) promote, as one tracked run."""
    build_features_task()
    train_and_evaluate_task()


@task(name="check-credit-drift", retries=0)
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


@flow(name="bankml-credit-drift-check-and-retrain")
def drift_check_and_retrain(domain: str = "credit") -> None:
    """Phase 5's exit criterion: injecting synthetic drift raises an alert (Session 017's Grafana
    rules fire off the metrics `check_drift_task` pushes) and triggers a retraining run, which is
    then blocked or promoted by the gate on its own merits — drift is what *decides to retrain*,
    never what decides to *promote*. A clean drift check does nothing further;
    `train_and_evaluate_task` only runs when either input or prediction drift actually crossed
    its threshold.

    Retrains against the existing feature set (`train_and_evaluate_task` alone), not
    `credit_pipeline`'s full build-features-then-train — deliberately, not an oversight.
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
        train_and_evaluate_task()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--flow",
        choices=["credit-pipeline", "drift-check-and-retrain"],
        default="credit-pipeline",
    )
    parser.add_argument("--domain", default="credit")
    args = parser.parse_args()

    if args.flow == "credit-pipeline":
        credit_pipeline()
    else:
        drift_check_and_retrain(domain=args.domain)
