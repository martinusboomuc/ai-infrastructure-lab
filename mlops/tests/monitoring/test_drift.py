"""Drift detection tests (Phase 5). Synthetic fixtures only (ADR-0007's pattern) — these exercise
`compute_drift` directly, not `run_drift_job`, so they need no real data, MLflow server, or
registered model. ROADMAP's Phase 5 exit criterion in one sentence: injecting synthetic drift
into the input stream raises an alert.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from bankml.monitoring.drift import (
    compute_drift,
    load_current_from_prediction_log,
    push_drift_metrics,
)


@pytest.fixture
def stable_population():
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 1_000),
            "education": rng.choice(["Higher", "Secondary"], 1_000, p=[0.4, 0.6]),
            "children": rng.integers(0, 4, 1_000),
        }
    )


def test_a_shifted_numeric_feature_is_flagged_drifted(stable_population):
    rng = np.random.default_rng(1)
    drifted = pd.DataFrame(
        {
            "income": rng.normal(400_000, 20_000, 200),  # far outside the reference distribution
            "education": rng.choice(["Higher", "Secondary"], 200, p=[0.4, 0.6]),  # unchanged
            "children": rng.integers(0, 4, 200),  # unchanged
        }
    )

    result = compute_drift(stable_population, drifted)

    assert result["features"]["income"]["drifted"] is True
    assert result["features"]["education"]["drifted"] is False
    assert result["features"]["children"]["drifted"] is False
    # only 1 of 3 columns drifted, below Evidently's own 0.5 drift_share default for a
    # dataset-wide alert — a single unstable feature shouldn't read as "everything moved"
    assert result["dataset_drift"] is False


def test_a_shifted_categorical_feature_is_flagged_drifted(stable_population):
    rng = np.random.default_rng(2)
    drifted = pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 200),  # unchanged
            "education": rng.choice(["Higher", "Secondary"], 200, p=[0.95, 0.05]),  # flipped
        }
    )

    result = compute_drift(stable_population, drifted)

    assert result["features"]["education"]["drifted"] is True
    assert result["features"]["income"]["drifted"] is False


def test_no_drift_when_current_matches_the_reference_distribution(stable_population):
    rng = np.random.default_rng(3)
    same_distribution = pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 200),
            "education": rng.choice(["Higher", "Secondary"], 200, p=[0.4, 0.6]),
        }
    )

    result = compute_drift(stable_population, same_distribution)

    assert result["dataset_drift"] is False
    assert all(not f["drifted"] for f in result["features"].values())


def test_a_column_entirely_null_in_current_is_skipped_not_a_crash(stable_population):
    rng = np.random.default_rng(4)
    current = pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 50),
            "education": [None] * 50,
        }
    )

    result = compute_drift(stable_population, current)

    assert "education" in result["skipped_columns"]
    assert "education" not in result["features"]
    assert "income" in result["features"]


def test_boolean_columns_do_not_crash_the_numeric_stats_path():
    reference = pd.DataFrame({"flag": [True, False, True, False, True] * 20})
    current = pd.DataFrame({"flag": [True] * 20})

    result = compute_drift(reference, current)

    assert "flag" in result["features"]


def test_raises_when_reference_and_current_share_no_comparable_columns():
    reference = pd.DataFrame({"a": [1, 2, 3]})
    current = pd.DataFrame({"b": [1, 2, 3]})

    with pytest.raises(ValueError, match="no columns"):
        compute_drift(reference, current)


def _prediction_record(request_id: str, amt_credit: float) -> dict:
    return {
        "request_id": request_id,
        "score": 0.1,
        "feature_vector": {"AMT_CREDIT": amt_credit},
    }


def test_load_current_reads_local_records_when_azure_is_not_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    log_dir = tmp_path / "credit"
    log_dir.mkdir()
    (log_dir / "2026-01-01.jsonl").write_text(
        json.dumps(_prediction_record("local-1", 100.0)) + "\n"
    )

    result = load_current_from_prediction_log("credit")

    assert len(result) == 1
    assert result.iloc[0]["AMT_CREDIT"] == 100.0


def test_load_current_merges_local_and_azure_blob_records(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-connection-string")
    log_dir = tmp_path / "credit"
    log_dir.mkdir()
    (log_dir / "2026-01-01.jsonl").write_text(
        json.dumps(_prediction_record("local-1", 100.0)) + "\n"
    )

    mock_blob = MagicMock()
    mock_blob.name = "credit/2026-01-01.jsonl"
    mock_download = MagicMock()
    mock_download.readall.return_value = (
        json.dumps(_prediction_record("blob-1", 200.0)) + "\n"
    ).encode()

    mock_container = MagicMock()
    mock_container.exists.return_value = True
    mock_container.list_blobs.return_value = [mock_blob]
    mock_container.download_blob.return_value = mock_download

    with patch(
        "azure.storage.blob.ContainerClient.from_connection_string", return_value=mock_container
    ):
        result = load_current_from_prediction_log("credit")

    # two distinct request_ids, one from each sink — both present, not deduplicated away
    assert sorted(result["AMT_CREDIT"]) == [100.0, 200.0]


def test_load_current_does_not_double_count_a_record_present_in_both_sinks(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-connection-string")
    log_dir = tmp_path / "credit"
    log_dir.mkdir()
    (log_dir / "2026-01-01.jsonl").write_text(
        json.dumps(_prediction_record("shared-1", 100.0)) + "\n"
    )

    mock_blob = MagicMock()
    mock_blob.name = "credit/2026-01-01.jsonl"
    mock_download = MagicMock()
    # same request_id as the local record — this is expected (both sinks get every write)
    mock_download.readall.return_value = (
        json.dumps(_prediction_record("shared-1", 100.0)) + "\n"
    ).encode()

    mock_container = MagicMock()
    mock_container.exists.return_value = True
    mock_container.list_blobs.return_value = [mock_blob]
    mock_container.download_blob.return_value = mock_download

    with patch(
        "azure.storage.blob.ContainerClient.from_connection_string", return_value=mock_container
    ):
        result = load_current_from_prediction_log("credit")

    assert len(result) == 1


def _drift_result(input_drift: bool, prediction_drift: bool) -> dict:
    return {
        "input_drift": {
            "dataset_drift": input_drift,
            "drifted_share": 0.6 if input_drift else 0.1,
            "features": {
                "income": {"psi": 0.5, "drifted": True},
                "age": {"psi": 0.02, "drifted": False},
            },
        },
        "prediction_drift": {
            "dataset_drift": prediction_drift,
            "drifted_share": 1.0 if prediction_drift else 0.0,
            "features": {
                "score": {"psi": 0.9 if prediction_drift else 0.01, "drifted": prediction_drift}
            },
        },
    }


def test_push_drift_metrics_sends_dataset_drift_and_per_feature_psi():
    with patch("prometheus_client.push_to_gateway") as mock_push:
        push_drift_metrics("credit", _drift_result(True, False), "http://fake-gateway:9091")

    mock_push.assert_called_once()
    _, kwargs = mock_push.call_args
    registry = kwargs["registry"]
    samples = {
        (m.name, tuple(sorted(s.labels.items()))): s.value
        for m in registry.collect()
        for s in m.samples
        if s.name.endswith(("_dataset_drift", "_feature_psi"))
    }
    assert samples[("bankml_drift_dataset_drift", (("domain", "credit"), ("kind", "input")))] == 1.0
    assert (
        samples[("bankml_drift_dataset_drift", (("domain", "credit"), ("kind", "prediction")))]
        == 0.0
    )
    assert (
        samples[("bankml_drift_feature_psi", (("domain", "credit"), ("feature", "income")))] == 0.5
    )


def test_push_drift_metrics_pushes_to_the_configured_gateway_url():
    with patch("prometheus_client.push_to_gateway") as mock_push:
        push_drift_metrics("credit", _drift_result(False, False), "http://fake-gateway:9091")

    args, kwargs = mock_push.call_args
    assert (
        args[0] == "http://fake-gateway:9091" or kwargs.get("gateway") == "http://fake-gateway:9091"
    )
    assert kwargs["job"] == "bankml_drift_credit"
