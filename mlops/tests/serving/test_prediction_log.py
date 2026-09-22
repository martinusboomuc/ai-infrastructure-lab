"""Tests for the prediction log's two sinks (Phase 5) — a local JSON-lines file always, and an
Azure Blob append blob when `AZURE_STORAGE_CONNECTION_STRING` is set. The Azure SDK is mocked;
these never touch a real network.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from bankml.serving.prediction_log import write_prediction_record


def _record(request_id: str = "abc-123") -> dict:
    return {
        "request_id": request_id,
        "applicant_id": 1,
        "model_name": "credit-champion",
        "model_version": "1",
        "score": 0.1,
        "decision": "pass",
        "threshold": 0.2,
        "feature_vector": {"AMT_CREDIT": 500000.0},
        "timestamp": "2026-01-01T00:00:00+00:00",
    }


def test_writes_locally_regardless_of_azure_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)

    log_path = write_prediction_record(_record(), domain="credit")

    lines = log_path.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["request_id"] == "abc-123"


def test_also_appends_to_azure_blob_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-connection-string")

    mock_client = MagicMock()
    mock_client.exists.return_value = False
    with patch("azure.storage.blob.BlobClient.from_connection_string", return_value=mock_client):
        write_prediction_record(_record(), domain="credit")

    mock_client.create_append_blob.assert_called_once()
    mock_client.append_block.assert_called_once()
    appended = json.loads(mock_client.append_block.call_args[0][0])
    assert appended["request_id"] == "abc-123"


def test_a_failed_azure_write_does_not_raise_or_lose_the_local_copy(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-connection-string")

    with patch(
        "azure.storage.blob.BlobClient.from_connection_string",
        side_effect=RuntimeError("network unreachable"),
    ):
        log_path = write_prediction_record(_record(), domain="credit")

    assert len(log_path.read_text().splitlines()) == 1


def test_does_not_create_a_new_append_blob_if_todays_already_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "fake-connection-string")

    mock_client = MagicMock()
    mock_client.exists.return_value = True
    with patch("azure.storage.blob.BlobClient.from_connection_string", return_value=mock_client):
        write_prediction_record(_record(), domain="credit")

    mock_client.create_append_blob.assert_not_called()
    mock_client.append_block.assert_called_once()
