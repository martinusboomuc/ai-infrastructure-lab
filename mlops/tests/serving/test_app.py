"""FastAPI serving tests (Phase 4). The MLflow model load is mocked — these exercise the request
validation, feature-assembly and scoring wiring, not the registry itself.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import bankml.serving.app as app_module


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


def test_health_reports_the_loaded_model_version(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_version": "1"}


def test_predict_scores_an_applicant_with_no_history(client):
    response = client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": _valid_applicant()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "1"
    assert body["score"] == pytest.approx(0.2)
    assert body["decision"] == "pass"  # score 0.2 < threshold 0.5
    assert body["threshold"] == pytest.approx(0.5)
    assert body["reason_codes"] == [{"feature": "AMT_CREDIT", "shap_value": 0.1}]
    assert "request_id" in body


def test_predict_rejects_an_applicant_outside_the_request_contract(client):
    bad_applicant = _valid_applicant()
    del bad_applicant["CODE_GENDER"]
    response = client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": bad_applicant},
    )
    assert response.status_code == 422


def test_predict_rejects_a_malformed_history_row(client):
    response = client.post(
        "/predict/credit",
        json={
            "applicant_id": 1,
            "applicant": _valid_applicant(),
            "bureau": [{"SK_ID_CURR": 1, "SK_ID_BUREAU": 10}],  # missing required columns
        },
    )
    assert response.status_code == 422
