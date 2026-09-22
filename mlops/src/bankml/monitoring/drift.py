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

**Known gap, not fixed here**: the deployed Azure Container App's prediction log lives at
`BANKML_PREDICTION_LOG_DIR=/data/predictions` *inside the container's own filesystem* (baked
into the Dockerfile), with no persistent volume mounted — every prediction it serves is lost on
restart, redeploy, or scale-to-zero. This job reads whatever prediction log actually exists
(e.g. from local runs), but there is currently no durable log of real production traffic to run
it against. Fixing that (a durable sink — Azure Blob, a database, anything outside the
container) is separate work, not something a drift job can paper over.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import mlflow
import mlflow.artifacts
import mlflow.pyfunc
import pandas as pd
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset
from mlflow import MlflowClient

from bankml.features.credit.prepare import feature_columns, prepare_features
from bankml.serving.prediction_log import AZURE_CONTAINER as AZURE_PREDICTION_CONTAINER
from bankml.serving.prediction_log import prediction_log_dir

DEFAULT_PSI_THRESHOLD = (
    0.2  # industry-standard cutoff: <0.1 stable, 0.1-0.2 moderate, >0.2 significant
)


def _iter_azure_blob_records(domain: str) -> list[dict[str, Any]]:
    """The durable copy of the prediction log (`serving/prediction_log.py`'s Blob sink) — the
    one that actually has real production traffic, since the deployed Azure app's local
    filesystem doesn't survive a restart. A no-op, not an error, when
    `AZURE_STORAGE_CONNECTION_STRING` isn't set (e.g. running this locally against only
    locally-logged predictions).
    """
    connection_string = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connection_string:
        return []

    from azure.storage.blob import ContainerClient

    container = ContainerClient.from_connection_string(
        connection_string, container_name=AZURE_PREDICTION_CONTAINER
    )
    if not container.exists():
        return []

    records: list[dict[str, Any]] = []
    for blob in container.list_blobs(name_starts_with=f"{domain}/"):
        content = container.download_blob(blob.name).readall().decode("utf-8")
        for line in content.splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def load_current_from_prediction_log(domain: str) -> pd.DataFrame:
    """Reconstruct one row per logged prediction — the feature vector plus the score the model
    actually produced — from every local `*.jsonl` file under the domain's prediction log
    directory, merged with the durable Azure Blob copy when configured. Deduped by
    `request_id` (the same record can legitimately exist in both sinks). Empty DataFrame if
    nothing has been logged anywhere yet.
    """
    log_dir = prediction_log_dir(domain)
    by_request_id: dict[str, dict[str, Any]] = {}
    for path in sorted(log_dir.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            by_request_id[rec["request_id"]] = rec
    for rec in _iter_azure_blob_records(domain):
        by_request_id.setdefault(rec["request_id"], rec)

    records = []
    for rec in by_request_id.values():
        row = dict(rec["feature_vector"])
        row["score"] = rec["score"]
        records.append(row)
    return pd.DataFrame(records)


def load_reference_features(domain: str) -> pd.DataFrame:
    """The `SPLIT="train"` rows of the domain's own processed feature set."""
    data_root = Path(os.environ["BANKML_DATA_ROOT"])
    features_path = data_root / "processed" / domain / "features.parquet"
    df = pd.read_parquet(features_path)
    return df[df["SPLIT"] == "train"]


def score_reference_with_production_model(
    reference: pd.DataFrame, registered_model_name: str
) -> pd.Series:
    """What the currently-deployed production model predicts on its own training population —
    the baseline prediction drift is measured against.
    """
    client = MlflowClient()
    version = client.get_model_version_by_alias(registered_model_name, "production")
    loaded = mlflow.pyfunc.load_model(f"models:/{registered_model_name}@production")
    model = loaded.unwrap_python_model().model
    categories = mlflow.artifacts.load_dict(f"runs:/{version.run_id}/categorical_levels.json")

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
    domain: str = "credit", threshold: float = DEFAULT_PSI_THRESHOLD
) -> dict[str, Any]:
    reference = load_reference_features(domain)
    current = load_current_from_prediction_log(domain)

    if current.empty:
        return {"status": "no_data", "domain": domain, "message": "no logged predictions found"}

    columns = feature_columns(reference)
    input_drift = compute_drift(reference[columns], current[columns], threshold=threshold)

    reference_scores = score_reference_with_production_model(reference, f"{domain}-champion")
    prediction_drift = compute_drift(
        pd.DataFrame({"score": reference_scores}), current[["score"]], threshold=threshold
    )

    return {
        "status": "ok",
        "domain": domain,
        "threshold": threshold,
        "n_reference": len(reference),
        "n_current": len(current),
        "input_drift": input_drift,
        "prediction_drift": prediction_drift,
    }


def log_drift_run(domain: str, result: dict[str, Any]) -> str:
    """Log the drift job's result to MLflow — its own experiment, separate from training runs,
    so a drift history is queryable on its own timeline.
    """
    mlflow.set_experiment(f"{domain}-monitoring")
    with mlflow.start_run(run_name=f"{domain}-drift") as run:
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


def main(domain: str = "credit", threshold: float = DEFAULT_PSI_THRESHOLD) -> None:
    result = run_drift_job(domain, threshold=threshold)
    print(json.dumps(result, indent=2, default=str))

    if result["status"] == "no_data":
        return

    run_id = log_drift_run(domain, result)
    print(f"\nLogged drift run {run_id}")

    pushgateway_url = os.environ.get("BANKML_PUSHGATEWAY_URL")
    if pushgateway_url:
        push_drift_metrics(domain, result, pushgateway_url)
        print(f"Pushed metrics to {pushgateway_url}")

    if result["input_drift"]["dataset_drift"] or result["prediction_drift"]["dataset_drift"]:
        print("ALERT: drift detected — see logged run for per-feature PSI.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="credit")
    parser.add_argument("--threshold", type=float, default=DEFAULT_PSI_THRESHOLD)
    args = parser.parse_args()
    main(domain=args.domain, threshold=args.threshold)
