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


def _fake_models() -> dict:
    return {
        "credit": app_module.DomainModel(
            model=_FakeModel(),
            model_type="lightgbm",
            model_version="1",
            threshold=0.5,
            categories={"NAME_EDUCATION_TYPE": ["Higher education", "Secondary"]},
        ),
        "fraud": app_module.DomainModel(
            model=_FakeModel(),
            model_type="lightgbm",
            model_version="4",
            threshold=0.1,
            categories={"category": ["grocery_pos", "misc_net"]},
        ),
    }


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


REPLAY_KEY = "r" * 40
PROMETHEUS_KEY = "p" * 40
AUTH = {"Authorization": f"Bearer {REPLAY_KEY}"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("BANKML_PREDICTION_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("BANKML_API_KEYS", f"replay:{REPLAY_KEY},prometheus:{PROMETHEUS_KEY}")

    def _fake_load_production_model(domain):
        return _fake_models()[domain]

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
    assert response.json() == {
        "status": "ok",
        "model_version": "1",
        "models": {"credit": "1", "fraud": "4"},
    }


def test_predict_scores_an_applicant_with_no_history(client):
    response = client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": _valid_applicant()},
        headers=AUTH,
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
        headers=AUTH,
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
        headers=AUTH,
    )
    assert response.status_code == 422


def _logged_records(tmp_path):
    import json

    return [
        json.loads(line)
        for path in sorted((tmp_path / "credit").glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def test_predict_logs_live_traffic_by_default(client, tmp_path):
    client.post(
        "/predict/credit", json={"applicant_id": 1, "applicant": _valid_applicant()}, headers=AUTH
    )

    assert _logged_records(tmp_path)[-1]["traffic_source"] == "live"


def test_predict_logs_replayed_traffic_as_replay(client, tmp_path):
    response = client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": _valid_applicant()},
        headers={**AUTH, "X-Traffic-Source": "replay"},
    )

    assert response.status_code == 200
    assert _logged_records(tmp_path)[-1]["traffic_source"] == "replay"


def test_predict_rejects_an_unknown_traffic_source(client):
    response = client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": _valid_applicant()},
        headers={**AUTH, "X-Traffic-Source": "something-else"},
    )

    assert response.status_code == 422


def test_predict_refuses_a_request_without_a_key(client):
    response = client.post(
        "/predict/credit", json={"applicant_id": 1, "applicant": _valid_applicant()}
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_predict_refuses_a_wrong_key(client):
    response = client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": _valid_applicant()},
        headers={"Authorization": "Bearer " + "x" * 40},
    )

    assert response.status_code == 401


def test_predict_logs_which_client_made_the_request(client, tmp_path):
    client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": _valid_applicant()},
        headers={"Authorization": f"Bearer {PROMETHEUS_KEY}"},
    )

    assert _logged_records(tmp_path)[-1]["client"] == "prometheus"


def test_metrics_needs_a_key_and_health_does_not(client):
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers=AUTH).status_code == 200
    assert client.get("/health").status_code == 200


def test_protected_endpoints_fail_closed_without_configured_keys(client):
    app_module.require_client.keys = {}

    response = client.post(
        "/predict/credit",
        json={"applicant_id": 1, "applicant": _valid_applicant()},
        headers=AUTH,
    )

    assert response.status_code == 503


def _fraud_payload(**overrides):
    payload = {
        "transaction_id": "t-100",
        "card_id": 42,
        "transaction": {
            "trans_date_trans_time": "2020-07-10T12:00:00",
            "category": "misc_net",
            "amt": 250.0,
            "lat": 36.0,
            "long": -81.0,
            "merch_lat": 36.5,
            "merch_long": -81.5,
        },
        "history": [
            {
                "trans_date_trans_time": "2020-07-10T11:30:00",
                "category": "misc_net",
                "amt": 20.0,
                "merch_lat": 36.1,
                "merch_long": -81.1,
            },
            {
                "trans_date_trans_time": "2020-07-01T09:00:00",
                "category": "grocery_pos",
                "amt": 40.0,
                "merch_lat": 36.2,
                "merch_long": -81.2,
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_predict_fraud_scores_a_transaction_with_its_card_history(client, tmp_path):
    import json

    response = client.post("/predict/fraud", json=_fraud_payload(), headers=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "4"
    assert body["decision"] == "flag"  # score 0.2 >= fraud threshold 0.1

    (log_file,) = (tmp_path / "fraud").glob("*.jsonl")
    record = json.loads(log_file.read_text().splitlines()[-1])
    assert record["transaction_id"] == "t-100"
    assert record["card_id"] == 42
    assert record["model_name"] == "fraud-champion"
    # Built from the two history rows, not from the transaction itself.
    features = record["feature_vector"]
    assert features["CC_TXN_COUNT_1H"] == 1
    assert features["CC_AMT_AVG_30D"] == pytest.approx(30.0)


def test_predict_fraud_rejects_history_at_or_after_the_transaction(client):
    payload = _fraud_payload()
    payload["history"][0]["trans_date_trans_time"] = "2020-07-10T12:00:00"

    response = client.post("/predict/fraud", json=payload, headers=AUTH)

    assert response.status_code == 422


def test_predict_fraud_rejects_a_timestamp_with_a_zone(client):
    payload = _fraud_payload()
    payload["transaction"]["trans_date_trans_time"] = "2020-07-10T12:00:00+00:00"

    response = client.post("/predict/fraud", json=payload, headers=AUTH)

    assert response.status_code == 422


def test_predict_fraud_rejects_a_negative_amount(client):
    payload = _fraud_payload()
    payload["transaction"]["amt"] = -1.0

    response = client.post("/predict/fraud", json=payload, headers=AUTH)

    assert response.status_code == 422


def test_a_domain_without_a_production_model_answers_503(client):
    del app_module.models["fraud"]

    response = client.post("/predict/fraud", json=_fraud_payload(), headers=AUTH)

    assert response.status_code == 503
    assert client.get("/health").json()["models"] == {"credit": "1"}


def test_an_optional_domain_without_a_model_does_not_stop_the_api(monkeypatch):
    from mlflow.exceptions import MlflowException

    def _load(domain):
        if domain == "fraud":
            raise MlflowException("Registered model alias production not found.")
        return _fake_models()[domain]

    monkeypatch.setattr(app_module, "load_production_model", _load)
    app_module.load_models()

    assert set(app_module.models) == {"credit"}


def test_the_api_does_not_start_without_a_credit_model(monkeypatch):
    from mlflow.exceptions import MlflowException

    def _load(domain):
        raise MlflowException("Registered model alias production not found.")

    monkeypatch.setattr(app_module, "load_production_model", _load)

    with pytest.raises(MlflowException):
        app_module.load_models()
