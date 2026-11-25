"""Evidently-based drift monitoring (Phase 5, ARCHITECTURE.md §7).

Two comparisons, both against the `SPLIT="train"` rows of the domain's own processed feature
set — the population the currently-deployed model was actually fit on, not the full historical
dataset, so a drift alert genuinely means "the world has moved since training," not "the test
split looks a little different from the train split" (which would always be at least somewhat
true and isn't the question this job answers):

- **Input drift**: per-feature PSI between the training population's own feature values and the
  values BankML's serving app has actually logged for real requests (`serving/prediction_log.py`).
- **Prediction drift**: PSI on the model's *score*, comparing what the currently-deployed model
  predicts on its own training population against what it has actually predicted for real
  requests — isolating "the model's own behavior shifted" from "raw feature values shifted."

Credit-specific for now (imports `bankml.features.credit.prepare` directly), matching how
`serving/app.py` and `training/pipeline.py` already hardcode the one domain that's actually
built end to end (ADR-0002's vertical-slice-first) — not a deliberate limitation to work around,
just not generalized past one domain yet.

Reads `serving/prediction_log.py`'s merged record set (`read_all_records`) — the local file plus
the durable Azure Blob copy, deduped by `request_id` — so this sees real production traffic, not
just whatever happens to still be on the deployed container's own ephemeral filesystem.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import mlflow
import mlflow.artifacts
import mlflow.pyfunc
import pandas as pd
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

from bankml.features.credit.prepare import feature_columns, prepare_features
from bankml.serving.prediction_log import read_all_records
from bankml.tracking import REFERENCE_ARTIFACT_PATH, experiment_name

DEFAULT_PSI_THRESHOLD = (
    0.2  # industry-standard cutoff: <0.1 stable, 0.1-0.2 moderate, >0.2 significant
)
# Fewest logged predictions PSI is computed on. PSI bins each column into ten buckets; below
# roughly 50 observations per bucket the per-bucket shares are noise, and the job reports drift
# on almost every column. Found running it on the real prediction log, which held 2 records:
# 95% of features "drifted". Below this, the run counts as having nothing to compare.
DEFAULT_MIN_CURRENT = 500
# How far back the comparison looks (ADR-0018). Reading every record ever logged lets months of
# old traffic dilute a shift that started this week. Seven days of the daily replay (200 a day)
# is about 1,400 records, comfortably above DEFAULT_MIN_CURRENT.
DEFAULT_WINDOW_DAYS = 7


def load_current_from_prediction_log(
    domain: str, since: datetime | None = None, model_version: str | None = None
) -> pd.DataFrame:
    """Reconstruct one row per logged prediction — the feature vector plus the score the model
    actually produced — from every prediction record `read_all_records` returns (merged across
    both sinks, deduped by `request_id`). Empty DataFrame if nothing has been logged anywhere yet.

    `since` keeps only records served from then on. `model_version` keeps only predictions made
    by that version: after a promotion, scores from the previous model are not this model's
    behaviour, and comparing them would report the model change itself as prediction drift.

    Requests from the Nexus test bench (`traffic_source` "test", ADR-0025) are skipped: they are
    applicants someone typed or edited, not the population the model serves.
    """
    records = []
    for rec in read_all_records(domain, since=since):
        if model_version is not None and str(rec.get("model_version")) != str(model_version):
            continue
        if rec.get("traffic_source") == "test":
            continue
        row = dict(rec["feature_vector"])
        row["score"] = rec["score"]
        records.append(row)
    return pd.DataFrame(records)


def load_reference_features(domain: str, run_id: str) -> pd.DataFrame:
    """The `SPLIT="train"` rows the production model was fit on, read from its own MLflow run
    (`bankml.tracking.REFERENCE_ARTIFACT_PATH`, ADR-0015). This is what lets the job run on the
    k3s cluster, which has no copy of the processed feature set.

    Falls back to the local processed feature set under `BANKML_DATA_ROOT` only when the run has
    no such artifact, which is true of models trained before it existed and not yet backfilled.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = mlflow.artifacts.download_artifacts(
                run_id=run_id, artifact_path=REFERENCE_ARTIFACT_PATH, dst_path=tmp_dir
            )
            return pd.read_parquet(path)
    except (MlflowException, OSError):
        if "BANKML_DATA_ROOT" not in os.environ:
            raise
    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    features_path = data_root / "processed" / domain / "features.parquet"
    df = pd.read_parquet(features_path)
    return df[df["SPLIT"] == "train"]


def score_reference_with_production_model(
    reference: pd.DataFrame, registered_model_name: str, run_id: str
) -> pd.Series:
    """What the currently-deployed production model predicts on its own training population —
    the baseline prediction drift is measured against.
    """
    loaded = mlflow.pyfunc.load_model(f"models:/{registered_model_name}@production")
    model = loaded.unwrap_python_model().model
    categories = mlflow.artifacts.load_dict(f"runs:/{run_id}/categorical_levels.json")

    columns = feature_columns(reference)
    X = prepare_features(reference, columns, categories=categories)
    return pd.Series(model.predict_proba(X)[:, 1], index=reference.index)


def compute_drift(
    reference: pd.DataFrame, current: pd.DataFrame, threshold: float = DEFAULT_PSI_THRESHOLD
) -> dict[str, Any]:
    """Per-column PSI drift between two DataFrames sharing at least one column.

    Returns `{"dataset_drift": bool, "drifted_share": float, "threshold": float,
    "features": {column: {"psi": float, "drifted": bool}}, "skipped_columns": [...]}`.
    `dataset_drift` is True once at least half the compared columns individually exceed
    `threshold` — Evidently's own default `drift_share` semantics for `DataDriftPreset`.

    A column that's entirely null in `current` (e.g. a relational aggregate for an applicant
    with no history in that table at all — expected, not a data quality bug) is excluded rather
    than passed to Evidently, which raises instead of treating an empty column as "no drift
    computable" — found running this against a real, small prediction log where exactly that
    happened for a `CREDIT_CARD_AMT_BALANCE_MEAN`-shaped column.

    Column types (numerical vs. categorical) are declared explicitly from `reference`'s own
    dtypes, not left to Evidently's automatic inference — on a small `current` sample (a handful
    of logged predictions, not thousands), a string column can look like free-text to the
    inference heuristic rather than categorical, and PSI has no text-column implementation.
    """
    shared_columns = [c for c in reference.columns if c in current.columns]
    comparable_columns = [c for c in shared_columns if current[c].notna().any()]
    skipped_columns = [c for c in shared_columns if c not in comparable_columns]
    if not comparable_columns:
        raise ValueError("reference and current share no columns with any non-null current data")

    # `is_numeric_dtype` rather than enumerating dtype names — pandas has several distinct
    # non-numeric dtype spellings for the same "this is text" concept (classic `object`,
    # `category`, and the newer PyArrow-backed `str`, which `read_parquet` produces and which
    # Evidently's numeric-stats path can't handle if a column ends up misclassified into it).
    # Booleans pass `is_numeric_dtype` too, but Evidently's numeric-stats quantile computation
    # can't subtract two `bool`s — treated as categorical instead, which is also the more
    # natural reading of a binary flag column like `DAYS_EMPLOYED_IS_SENTINEL`.
    numerical_columns = [
        c
        for c in comparable_columns
        if pd.api.types.is_numeric_dtype(reference[c])
        and not pd.api.types.is_bool_dtype(reference[c])
    ]
    categorical_columns = [c for c in comparable_columns if c not in numerical_columns]
    definition = DataDefinition(
        numerical_columns=numerical_columns, categorical_columns=categorical_columns
    )

    ref_dataset = Dataset.from_pandas(reference[comparable_columns], data_definition=definition)
    cur_dataset = Dataset.from_pandas(current[comparable_columns], data_definition=definition)
    report = Report(metrics=[DataDriftPreset(method="psi", threshold=threshold)])
    result = report.run(current_data=cur_dataset, reference_data=ref_dataset).dict()

    # `bool(...)` explicitly — `psi > threshold` on Evidently's numpy-float PSI value produces
    # `numpy.bool_`, not Python's own `bool`. Both are truthy/falsy correctly, but `numpy.bool_`
    # fails an `is True` identity check (a different type, not just a different representation)
    # and json.dumps can't serialize it without a `default=` fallback — a real footgun for any
    # caller, not just this module's own tests.
    features: dict[str, dict[str, Any]] = {}
    drifted_share = 0.0
    for metric in result["metrics"]:
        name = metric["metric_name"]
        if name.startswith("ValueDrift"):
            column = metric["config"]["column"]
            psi = float(metric["value"])
            features[column] = {"psi": psi, "drifted": bool(psi > threshold)}
        elif name.startswith("DriftedColumnsCount"):
            drifted_share = float(metric["value"]["share"])

    return {
        "dataset_drift": bool(drifted_share >= 0.5),
        "drifted_share": drifted_share,
        "threshold": threshold,
        "features": features,
        "skipped_columns": skipped_columns,
    }


def run_drift_job(
    domain: str = "credit",
    threshold: float = DEFAULT_PSI_THRESHOLD,
    min_current: int = DEFAULT_MIN_CURRENT,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> dict[str, Any]:
    registered_model_name = f"{domain}-champion"
    version = MlflowClient().get_model_version_by_alias(registered_model_name, "production")
    window_start = datetime.now(UTC) - timedelta(days=window_days)
    window = {
        "window_days": window_days,
        "window_start": window_start.isoformat(),
        "model_version": str(version.version),
    }

    current = load_current_from_prediction_log(
        domain, since=window_start, model_version=version.version
    )
    if len(current) < min_current:
        return {
            "status": "no_data",
            "domain": domain,
            "n_current": len(current),
            **window,
            "message": (
                f"{len(current)} predictions by {registered_model_name} v{version.version} in the "
                f"last {window_days} days; at least {min_current} needed"
            ),
        }

    reference = load_reference_features(domain, version.run_id)

    columns = feature_columns(reference)
    input_drift = compute_drift(reference[columns], current[columns], threshold=threshold)

    reference_scores = score_reference_with_production_model(
        reference, registered_model_name, version.run_id
    )
    prediction_drift = compute_drift(
        pd.DataFrame({"score": reference_scores}), current[["score"]], threshold=threshold
    )

    return {
        "status": "ok",
        "domain": domain,
        "threshold": threshold,
        "n_reference": len(reference),
        "n_current": len(current),
        **window,
        "input_drift": input_drift,
        "prediction_drift": prediction_drift,
    }


def log_drift_run(domain: str, result: dict[str, Any]) -> str:
    """Log the drift job's result to MLflow — its own experiment, separate from training runs,
    so a drift history is queryable on its own timeline.
    """
    mlflow.set_experiment(experiment_name(domain, "monitoring"))
    with mlflow.start_run(run_name=f"{domain}-drift") as run:
        mlflow.log_params(
            {k: result[k] for k in ("window_days", "window_start", "model_version") if k in result}
        )
        mlflow.log_metric("n_reference", result["n_reference"])
        mlflow.log_metric("n_current", result["n_current"])
        mlflow.log_metric("input_dataset_drift", int(result["input_drift"]["dataset_drift"]))
        mlflow.log_metric("input_drifted_share", result["input_drift"]["drifted_share"])
        mlflow.log_metric(
            "prediction_dataset_drift", int(result["prediction_drift"]["dataset_drift"])
        )
        mlflow.log_metric("prediction_psi", result["prediction_drift"]["features"]["score"]["psi"])
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = Path(tmp_dir) / "drift_report.json"
            report_path.write_text(json.dumps(result, indent=2, default=str))
            mlflow.log_artifact(str(report_path))
        return run.info.run_id


def push_drift_metrics(domain: str, result: dict[str, Any], pushgateway_url: str) -> None:
    """Push this run's drift metrics to a Prometheus Pushgateway — the bridge a one-shot batch
    job needs, since Prometheus's own pull model has nothing to scrape between runs (see
    infrastructure/homelab/monitoring/docker-compose.yml's comment on the gateway itself).

    A fresh `CollectorRegistry` per call, pushed with `push_to_gateway`'s default replace
    semantics (not `pushadd_to_gateway`) — every metric this job currently has is included every
    push, so a feature that stops existing in a later run doesn't linger as a stale value
    forever; the whole job's metric group is replaced, not merged into.

    `bankml_drift_last_run_timestamp_seconds` exists specifically so an alert rule can check
    staleness — a Pushgateway metric has no concept of "the job that pushed it stopped running,"
    it just keeps returning the last-pushed value indefinitely otherwise.
    """
    from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

    registry = CollectorRegistry()
    dataset_drift = Gauge(
        "bankml_drift_dataset_drift",
        "1 if dataset-level drift was detected on the most recent run, else 0",
        ["domain", "kind"],
        registry=registry,
    )
    drifted_share = Gauge(
        "bankml_drift_drifted_share",
        "Share of compared columns flagged individually drifted",
        ["domain", "kind"],
        registry=registry,
    )
    feature_psi = Gauge(
        "bankml_drift_feature_psi",
        "Per-feature PSI value from the most recent input-drift run",
        ["domain", "feature"],
        registry=registry,
    )
    last_run_timestamp = Gauge(
        "bankml_drift_last_run_timestamp_seconds",
        "Unix timestamp of the most recent successful drift run",
        ["domain"],
        registry=registry,
    )

    dataset_drift.labels(domain=domain, kind="input").set(
        int(result["input_drift"]["dataset_drift"])
    )
    dataset_drift.labels(domain=domain, kind="prediction").set(
        int(result["prediction_drift"]["dataset_drift"])
    )
    drifted_share.labels(domain=domain, kind="input").set(result["input_drift"]["drifted_share"])
    drifted_share.labels(domain=domain, kind="prediction").set(
        result["prediction_drift"]["drifted_share"]
    )
    for feature, values in result["input_drift"]["features"].items():
        feature_psi.labels(domain=domain, feature=feature).set(values["psi"])
    last_run_timestamp.labels(domain=domain).set(time.time())

    push_to_gateway(pushgateway_url, job=f"bankml_drift_{domain}", registry=registry)


def push_drift_heartbeat(domain: str, pushgateway_url: str) -> None:
    """Record that the job ran when there was no logged traffic to compare.

    A run with nothing to compare is still a successful run. Without this, the staleness alert
    ("BankML drift job has not run recently") fires whenever the API sees no traffic for two
    days, which cannot be told apart from the job itself having stopped. Uses
    `pushadd_to_gateway`, which merges into the job's metric group instead of replacing it, so
    the last real drift values stay in place rather than vanishing because traffic stopped.
    """
    from prometheus_client import CollectorRegistry, Gauge, pushadd_to_gateway

    registry = CollectorRegistry()
    Gauge(
        "bankml_drift_last_run_timestamp_seconds",
        "Unix timestamp of the most recent successful drift run",
        ["domain"],
        registry=registry,
    ).labels(domain=domain).set(time.time())
    pushadd_to_gateway(pushgateway_url, job=f"bankml_drift_{domain}", registry=registry)


def main(
    domain: str = "credit",
    threshold: float = DEFAULT_PSI_THRESHOLD,
    min_current: int = DEFAULT_MIN_CURRENT,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> None:
    result = run_drift_job(
        domain, threshold=threshold, min_current=min_current, window_days=window_days
    )
    print(json.dumps(result, indent=2, default=str))

    pushgateway_url = os.environ.get("BANKML_PUSHGATEWAY_URL")
    if result["status"] == "no_data":
        if pushgateway_url:
            push_drift_heartbeat(domain, pushgateway_url)
            print(f"Pushed heartbeat to {pushgateway_url}")
        return

    run_id = log_drift_run(domain, result)
    print(f"\nLogged drift run {run_id}")

    if pushgateway_url:
        push_drift_metrics(domain, result, pushgateway_url)
        print(f"Pushed metrics to {pushgateway_url}")

    if result["input_drift"]["dataset_drift"] or result["prediction_drift"]["dataset_drift"]:
        print("ALERT: drift detected — see logged run for per-feature PSI.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="credit")
    parser.add_argument("--threshold", type=float, default=DEFAULT_PSI_THRESHOLD)
    parser.add_argument("--min-current", type=int, default=DEFAULT_MIN_CURRENT)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    args = parser.parse_args()
    main(
        domain=args.domain,
        threshold=args.threshold,
        min_current=args.min_current,
        window_days=args.window_days,
    )
