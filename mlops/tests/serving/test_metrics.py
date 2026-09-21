"""Tests for the /metrics endpoint and its instrumentation (Phase 5)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import bankml.serving.app as app_module
import bankml.serving.metrics as metrics_module


class _FakeModel:
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        score = np.full(len(X), 0.2)
        return np.column_stack([1 - score, score])


def _valid_applicant():
    return {
        "CODE_GENDER": "F",
        "DAYS_BIRTH": -12000,
        "DAYS_EMPLOYED": -2000,
        "AMT_INCOME_TOTAL": 150000.0,
        "AMT_CREDIT": 500000.0,
        "AMT_ANNUITY": 25000.0,
        "NAME_EDUCATION_TYPE": "Higher education",
        "NAME_FAMILY_STATUS": "Married",
        "NAME_HOUSING_TYPE": "House / apartment",
        "CNT_CHILDREN": 1,
        "EXT_SOURCE_1": 0.5,
        "EXT_SOURCE_2": 0.6,
        "EXT_SOURCE_3": 0.7,
    }


@pytest.fixture(autouse=True)
def _reset_metrics():
    # The Counter/Histogram objects in bankml.serving.metrics are module-level singletons shared
    # across the whole test session, so without this, later tests would inherit earlier tests'
    # counts and see values they never produced themselves.
    metrics_module.REQUEST_COUNT._metrics.clear()
    metrics_module.REQUEST_LATENCY._metrics.clear()
    metrics_module.PREDICTIONS._metrics.clear()
    yield


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))

    def _fake_load_production_model():
        app_module.state.model = _FakeModel()
        app_module.state.model_type = "lightgbm"
        app_module.state.model_version = "1"
        app_module.state.threshold = 0.5
        app_module.state.categories = {"NAME_EDUCATION_TYPE": ["Higher education", "Secondary"]}

    monkeypatch.setattr(app_module, "load_production_model", _fake_load_production_model)
    monkeypatch.setattr(
        app_module,
        "compute_reason_codes",
        lambda model, model_type, X, sample_size=1: [
            {"row_index": 0, "contributions": [{"feature": "AMT_CREDIT", "shap_value": 0.1}]}
        ],
    )

    with TestClient(app_module.app) as test_client:
        yield test_client


def test_metrics_endpoint_exposes_prometheus_text_format(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")


def test_metrics_count_requests_by_path_method_and_status(client):
    client.get("/health")
    client.get("/health")
    body = client.get("/metrics").text
    assert 'bankml_requests_total{method="GET",path="/health",status_code="200"} 2.0' in body


def test_metrics_count_predictions_by_domain_and_decision(client):
    client.post("/predict/credit", json={"applicant_id": 1, "applicant": _valid_applicant()})
    body = client.get("/metrics").text
    assert 'bankml_predictions_total{decision="pass",domain="credit"} 1.0' in body


def test_metrics_scrape_is_not_reflected_in_its_own_response_body(client):
    # The middleware increments REQUEST_COUNT *after* call_next returns, so /metrics's own
    # snapshot (rendered inside call_next) can never include the very request that fetched it —
    # only a later scrape would show it.
    body = client.get("/metrics").text
    assert 'path="/metrics"' not in body
