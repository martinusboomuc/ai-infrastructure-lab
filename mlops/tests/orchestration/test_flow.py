"""Tests for the drift-triggered retraining flow (Phase 5's exit criterion: injecting synthetic
drift raises an alert and triggers a retraining run, which is then blocked or promoted by the
gate on its own merits). Every dependency (the drift job, the gated training pipeline) is
mocked — these test the *wiring*, not drift detection or the gate itself, which already have
their own tests.
"""

from __future__ import annotations

from unittest.mock import patch

from bankml.orchestration.flow import drift_check_and_retrain


def _drift_result(input_drift: bool, prediction_drift: bool) -> dict:
    return {
        "status": "ok",
        "input_drift": {"dataset_drift": input_drift},
        "prediction_drift": {"dataset_drift": prediction_drift},
    }


def test_retraining_is_triggered_when_input_drift_is_detected():
    with (
        patch("bankml.monitoring.drift.run_drift_job", return_value=_drift_result(True, False)),
        patch("bankml.monitoring.drift.log_drift_run") as mock_log,
        patch("bankml.orchestration.flow.train_and_evaluate_task") as mock_train,
    ):
        drift_check_and_retrain(domain="credit")

    mock_log.assert_called_once()
    mock_train.assert_called_once()


def test_retraining_is_triggered_when_prediction_drift_is_detected():
    with (
        patch("bankml.monitoring.drift.run_drift_job", return_value=_drift_result(False, True)),
        patch("bankml.monitoring.drift.log_drift_run"),
        patch("bankml.orchestration.flow.train_and_evaluate_task") as mock_train,
    ):
        drift_check_and_retrain(domain="credit")

    mock_train.assert_called_once()


def test_retraining_is_not_triggered_when_no_drift_is_detected():
    with (
        patch("bankml.monitoring.drift.run_drift_job", return_value=_drift_result(False, False)),
        patch("bankml.monitoring.drift.log_drift_run") as mock_log,
        patch("bankml.orchestration.flow.train_and_evaluate_task") as mock_train,
    ):
        drift_check_and_retrain(domain="credit")

    # a clean drift check still gets logged (there's a real run to record), it just doesn't
    # cascade into retraining
    mock_log.assert_called_once()
    mock_train.assert_not_called()


def test_nothing_happens_when_the_drift_job_has_no_data_to_compare():
    with (
        patch(
            "bankml.monitoring.drift.run_drift_job",
            return_value={
                "status": "no_data",
                "domain": "credit",
                "message": "no logged predictions found",
            },
        ),
        patch("bankml.monitoring.drift.log_drift_run") as mock_log,
        patch("bankml.orchestration.flow.train_and_evaluate_task") as mock_train,
    ):
        drift_check_and_retrain(domain="credit")

    mock_log.assert_not_called()
    mock_train.assert_not_called()


def test_push_drift_metrics_is_called_when_pushgateway_is_configured(monkeypatch):
    monkeypatch.setenv("BANKML_PUSHGATEWAY_URL", "http://fake-gateway:9091")
    with (
        patch("bankml.monitoring.drift.run_drift_job", return_value=_drift_result(False, False)),
        patch("bankml.monitoring.drift.log_drift_run"),
        patch("bankml.monitoring.drift.push_drift_metrics") as mock_push,
        patch("bankml.orchestration.flow.train_and_evaluate_task"),
    ):
        drift_check_and_retrain(domain="credit")

    mock_push.assert_called_once()


def test_push_drift_metrics_is_skipped_when_no_pushgateway_is_configured(monkeypatch):
    monkeypatch.delenv("BANKML_PUSHGATEWAY_URL", raising=False)
    with (
        patch("bankml.monitoring.drift.run_drift_job", return_value=_drift_result(False, False)),
        patch("bankml.monitoring.drift.log_drift_run"),
        patch("bankml.monitoring.drift.push_drift_metrics") as mock_push,
        patch("bankml.orchestration.flow.train_and_evaluate_task"),
    ):
        drift_check_and_retrain(domain="credit")

    mock_push.assert_not_called()
