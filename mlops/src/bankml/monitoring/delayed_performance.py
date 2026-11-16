"""Production performance once outcomes arrive (ADR-0021, ARCHITECTURE.md's "Delayed
performance" row: "Once labels mature, was the model actually right?").

Drift (`monitoring/drift.py`) needs no labels, so it runs on today's traffic. This job answers
the direct question: on predictions whose outcome is now known, how well did the production
model rank and decide?

Outcomes exist only for replayed traffic (ADR-0016): every replayed applicant is a real held-out
applicant, and `monitoring/outcomes.py` publishes their outcomes. A real credit outcome matures
after `label.maturity_days` (540), which would leave nothing to measure for 18 months, so a
replayed prediction's outcome counts as known `label.replay_outcome_delay_days` after it was
served. That delay is a simulation, stated as one; live traffic has no outcome feed and is not
measured here.

Like drift (ADR-0018), the job measures only the production version's own predictions, inside a
window: served between `window_days + delay` and `delay` days ago. It compares the live ROC-AUC
with the same version's test ROC-AUC, which is threshold-free and does not move with the base
rate (ADR-0020); a drop beyond `MAX_ROC_AUC_DROP` is what the Grafana rule alerts on.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import mlflow
import pandas as pd
from mlflow import MlflowClient
from sklearn.metrics import average_precision_score, roc_auc_score

from bankml.monitoring.outcomes import load_domain_config, load_outcomes
from bankml.serving.prediction_log import read_all_records
from bankml.tracking import experiment_name

DEFAULT_WINDOW_DAYS = 30
# Below these, an AUC on replayed traffic is too noisy to alert on: with about 8% defaults,
# 500 predictions carry about 40 defaults.
DEFAULT_MIN_LABELED = 500
DEFAULT_MIN_POSITIVES = 25
# Same size as the slice tolerance (ADR-0020): a drop this large is a change in ranking quality,
# not sampling noise.
MAX_ROC_AUC_DROP = 0.05


def select_window(
    records: list[dict],
    model_version: str,
    as_of: datetime,
    delay_days: int,
    window_days: int,
) -> list[dict]:
    """Replayed predictions by `model_version` whose outcome is known by `as_of`, served in the
    `window_days` before the delay cut-off."""
    cutoff = as_of - timedelta(days=delay_days)
    start = cutoff - timedelta(days=window_days)
    return [
        r
        for r in records
        if r.get("traffic_source") == "replay"
        and str(r.get("model_version")) == str(model_version)
        and start <= datetime.fromisoformat(r["timestamp"]) < cutoff
    ]


def compute_performance(
    records: list[dict],
    outcomes: pd.Series,
    reference: dict[str, float],
    min_labeled: int = DEFAULT_MIN_LABELED,
    min_positives: int = DEFAULT_MIN_POSITIVES,
) -> dict[str, Any]:
    """Ranking and decision quality of `records` against `outcomes`.

    `reference` holds the version's test metrics (`roc_auc`, `pr_auc`), the numbers it was
    promoted on.
    """
    labeled = [r for r in records if r["applicant_id"] in outcomes.index]
    y_true = pd.Series([int(outcomes[r["applicant_id"]]) for r in labeled], dtype=int)
    result: dict[str, Any] = {
        "n_in_window": len(records),
        "n_labeled": len(labeled),
        "n_positive": int(y_true.sum()),
    }
    if len(labeled) < min_labeled or result["n_positive"] < min_positives:
        result["status"] = "insufficient_outcomes"
        result["reason"] = (
            f"{len(labeled)} predictions with outcomes and {result['n_positive']} defaults; "
            f"at least {min_labeled} and {min_positives} needed"
        )
        return result

    y_score = pd.Series([r["score"] for r in labeled])
    flagged = pd.Series([r["decision"] == "flag" for r in labeled])
    positive = y_true == 1
    tp = int((positive & flagged).sum())
    fp = int((~positive & flagged).sum())
    fn = int((positive & ~flagged).sum())
    tn = int((~positive & ~flagged).sum())

    roc_auc = float(roc_auc_score(y_true, y_score))
    result.update(
        {
            "status": "ok",
            "positive_rate": float(y_true.mean()),
            "roc_auc": roc_auc,
            "pr_auc": float(average_precision_score(y_true, y_score)),
            "alert_rate": float(flagged.mean()),
            "recall": tp / (tp + fn),
            "precision": tp / (tp + fp) if tp + fp else None,
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "test_roc_auc": reference["roc_auc"],
            "test_pr_auc": reference["pr_auc"],
            "roc_auc_drop": reference["roc_auc"] - roc_auc,
        }
    )
    result["degraded"] = result["roc_auc_drop"] > MAX_ROC_AUC_DROP
    return result


def production_reference(registered_model_name: str) -> tuple[str, dict[str, float]]:
    client = MlflowClient()
    version = client.get_model_version_by_alias(registered_model_name, "production")
    metrics = client.get_run(version.run_id).data.metrics
    return str(version.version), {
        "roc_auc": metrics["test_roc_auc"],
        "pr_auc": metrics["test_pr_auc"],
    }


def run_performance_job(
    domain: str,
    window_days: int = DEFAULT_WINDOW_DAYS,
    delay_days: int | None = None,
    model_version: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = as_of or datetime.now(UTC)
    if delay_days is None:
        delay_days = load_domain_config(domain)["label"]["replay_outcome_delay_days"]
    registered_model_name = f"{domain}-champion"
    production_version, reference = production_reference(registered_model_name)
    if model_version is not None and model_version != production_version:
        version = MlflowClient().get_model_version(registered_model_name, model_version)
        metrics = MlflowClient().get_run(version.run_id).data.metrics
        reference = {"roc_auc": metrics["test_roc_auc"], "pr_auc": metrics["test_pr_auc"]}
    model_version = model_version or production_version

    since = as_of - timedelta(days=delay_days + window_days)
    records = select_window(
        read_all_records(domain, since=since), model_version, as_of, delay_days, window_days
    )
    window = {
        "domain": domain,
        "model_version": model_version,
        "delay_days": delay_days,
        "window_days": window_days,
        "window_start": since.isoformat(),
        "as_of": as_of.isoformat(),
    }
    if not records:
        return {**window, "status": "insufficient_outcomes", "n_in_window": 0}
    return {**window, **compute_performance(records, load_outcomes(domain), reference)}


def log_performance_run(domain: str, result: dict[str, Any]) -> str:
    mlflow.set_experiment(experiment_name(domain, "monitoring"))
    with mlflow.start_run(run_name=f"{domain}-performance") as run:
        mlflow.log_params(
            {
                k: result[k]
                for k in ("model_version", "delay_days", "window_days", "window_start", "as_of")
            }
        )
        for key, value in result.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                mlflow.log_metric(key, value)
        mlflow.log_metric("degraded", int(result["degraded"]))
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "performance_report.json"
            report_path.write_text(json.dumps(result, indent=2, default=str))
            mlflow.log_artifact(str(report_path))
        return run.info.run_id


def push_performance_metrics(domain: str, result: dict[str, Any], pushgateway_url: str) -> None:
    """Replace the job's metric group, like drift's full push. Every gauge carries the model
    version, so a promotion starts a new series rather than continuing the old one."""
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

    registry = CollectorRegistry()
    labels = {"domain": domain, "model_version": result["model_version"]}
    for name, description in (
        ("roc_auc", "ROC-AUC on replayed predictions with known outcomes"),
        ("pr_auc", "PR-AUC on replayed predictions with known outcomes"),
        ("test_roc_auc", "The production version's test ROC-AUC"),
        ("roc_auc_drop", "Test ROC-AUC minus live ROC-AUC"),
        ("recall", "Share of defaults the model flagged"),
        ("alert_rate", "Share of applicants the model flagged"),
        ("positive_rate", "Share of applicants that defaulted"),
        ("n_labeled", "Predictions with a known outcome in the window"),
    ):
        gauge = Gauge(f"bankml_performance_{name}", description, list(labels), registry=registry)
        gauge.labels(**labels).set(result[name])
    _last_run_gauge(registry, domain).set_to_current_time()
    push_to_gateway(pushgateway_url, job=f"bankml_performance_{domain}", registry=registry)


def push_performance_heartbeat(domain: str, pushgateway_url: str) -> None:
    """Merge only the timestamp into the group, so a run without enough outcomes proves the job
    ran without erasing the last measured values (same reason as drift's heartbeat)."""
    from prometheus_client import CollectorRegistry, pushadd_to_gateway

    registry = CollectorRegistry()
    _last_run_gauge(registry, domain).set_to_current_time()
    pushadd_to_gateway(pushgateway_url, job=f"bankml_performance_{domain}", registry=registry)


def _last_run_gauge(registry, domain: str):
    from prometheus_client import Gauge

    return Gauge(
        "bankml_performance_last_run_timestamp_seconds",
        "When the performance job last ran, with or without enough outcomes",
        ["domain"],
        registry=registry,
    ).labels(domain=domain)


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure production performance on outcomes.")
    parser.add_argument("--domain", default="credit")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument(
        "--delay-days",
        type=int,
        default=None,
        help="Overrides label.replay_outcome_delay_days, for a run by hand.",
    )
    parser.add_argument(
        "--model-version",
        default=None,
        help="Measure this version instead of production, for a run by hand.",
    )
    args = parser.parse_args()

    result = run_performance_job(args.domain, args.window_days, args.delay_days, args.model_version)
    print(json.dumps(result, indent=2, default=str))

    # A run by hand with an override is not the scheduled measurement, so it never reaches the
    # gauges the alert reads. It is still logged to MLflow, with the override as a param.
    pushgateway_url = os.environ.get("BANKML_PUSHGATEWAY_URL")
    if args.model_version is not None or args.delay_days is not None:
        pushgateway_url = None
    if result["status"] != "ok":
        if pushgateway_url:
            push_performance_heartbeat(args.domain, pushgateway_url)
            print(f"Pushed heartbeat to {pushgateway_url}")
        return

    run_id = log_performance_run(args.domain, result)
    print(f"\nLogged performance run {run_id}")
    if pushgateway_url:
        push_performance_metrics(args.domain, result, pushgateway_url)
        print(f"Pushed metrics to {pushgateway_url}")


if __name__ == "__main__":
    main()
