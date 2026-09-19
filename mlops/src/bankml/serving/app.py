"""FastAPI serving for Credit Risk (Phase 4, ARCHITECTURE.md §6).

Every request builds features through the same code training uses
(`bankml.features.credit.pipeline.assemble_features`, `bankml.features.credit.prepare`) and
scores through the same model object training fit — see ADR-0009 for why the request carries
the applicant's own historical rows rather than looking features up from an online store
(ADR-0006 defers that store).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import mlflow.artifacts
import mlflow.pyfunc
import pandas as pd
import pandera.errors
from fastapi import FastAPI, HTTPException
from mlflow import MlflowClient
from pydantic import BaseModel, Field

from bankml.evaluation.explain import compute_reason_codes
from bankml.features.credit.pipeline import assemble_features
from bankml.features.credit.prepare import feature_columns, prepare_features
from bankml.serving.prediction_log import write_prediction_record
from bankml.validation.credit.bureau import BureauSchema
from bankml.validation.credit.bureau_balance import BureauBalanceSchema
from bankml.validation.credit.credit_card_balance import CreditCardBalanceSchema
from bankml.validation.credit.installments_payments import InstallmentsPaymentsSchema
from bankml.validation.credit.pos_cash_balance import PosCashBalanceSchema
from bankml.validation.credit.previous_application import PreviousApplicationSchema
from bankml.validation.credit.request import ApplicationRequestSchema

logger = logging.getLogger("bankml.serving")

REGISTERED_MODEL_NAME = "credit-champion"
MODEL_ALIAS = "production"
DOMAIN = "credit"

# Every historical table a request may attach, validated against the exact same Pandera
# contract training's raw ingestion boundary uses — zero new schema code for these six.
HISTORY_SCHEMAS: dict[str, type] = {
    "bureau": BureauSchema,
    "bureau_balance": BureauBalanceSchema,
    "previous_application": PreviousApplicationSchema,
    "POS_CASH_balance": PosCashBalanceSchema,
    "installments_payments": InstallmentsPaymentsSchema,
    "credit_card_balance": CreditCardBalanceSchema,
}


def _log_event(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str))


class CreditApplicant(BaseModel):
    CODE_GENDER: str
    DAYS_BIRTH: int
    DAYS_EMPLOYED: int
    AMT_INCOME_TOTAL: float
    AMT_CREDIT: float
    AMT_ANNUITY: float | None = None
    NAME_EDUCATION_TYPE: str
    NAME_FAMILY_STATUS: str
    NAME_HOUSING_TYPE: str
    CNT_CHILDREN: int
    EXT_SOURCE_1: float | None = None
    EXT_SOURCE_2: float | None = None
    EXT_SOURCE_3: float | None = None


class CreditPredictionRequest(BaseModel):
    applicant_id: int
    decision_date: datetime | None = None
    applicant: CreditApplicant
    bureau: list[dict[str, Any]] = Field(default_factory=list)
    bureau_balance: list[dict[str, Any]] = Field(default_factory=list)
    previous_application: list[dict[str, Any]] = Field(default_factory=list)
    POS_CASH_balance: list[dict[str, Any]] = Field(default_factory=list)
    installments_payments: list[dict[str, Any]] = Field(default_factory=list)
    credit_card_balance: list[dict[str, Any]] = Field(default_factory=list)


class ModelState:
    model: Any = None
    model_type: str = ""
    model_version: str = ""
    threshold: float = 0.0
    categories: dict[str, list] = {}


state = ModelState()


def load_production_model() -> None:
    """Load the credit-champion production model and the threshold the gate actually evaluated
    (`test_alert_threshold`, computed in `evaluation/metrics.py` and logged by `tracking.py`) —
    never recomputed here, it must be the exact number the promoted run was gated on.
    """
    client = MlflowClient()
    version = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, MODEL_ALIAS)
    run = client.get_run(version.run_id)

    loaded = mlflow.pyfunc.load_model(f"models:/{REGISTERED_MODEL_NAME}@{MODEL_ALIAS}")
    # unwrap_python_model() reaches past pyfunc's uniform predict(X) to the actual
    # ScorecardModel/LGBMClassifier (see registry/pyfunc_model.py) — reason codes need the real
    # object's own SHAP explainer, not just a probability.
    state.model = loaded.unwrap_python_model().model
    state.model_type = run.data.params["model_type"]
    state.model_version = version.version
    state.threshold = run.data.metrics["test_alert_threshold"]
    # Same category levels this run was fit on (tracking.py logs this alongside the model) —
    # required for a tree model's categorical encoding to match at predict time; see
    # features/credit/prepare.py::capture_categories's docstring.
    state.categories = mlflow.artifacts.load_dict(f"runs:/{version.run_id}/categorical_levels.json")
    _log_event(
        "model_loaded",
        model_name=REGISTERED_MODEL_NAME,
        model_version=state.model_version,
        model_type=state.model_type,
        threshold=state.threshold,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_production_model()
    yield


app = FastAPI(title="BankML Credit Risk Serving", lifespan=lifespan)


def _validate_history_table(name: str, rows: list[dict[str, Any]], schema: type) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=list(schema.to_schema().columns.keys()))
    df = pd.DataFrame(rows)
    try:
        return schema.validate(df)
    except (pandera.errors.SchemaError, pandera.errors.SchemaErrors) as exc:
        raise HTTPException(status_code=422, detail=f"{name}: {exc}") from exc


def _build_raw_tables(payload: CreditPredictionRequest) -> dict[str, pd.DataFrame]:
    applicant_row = {"SK_ID_CURR": payload.applicant_id, **payload.applicant.model_dump()}
    application_df = pd.DataFrame([applicant_row])
    try:
        application_df = ApplicationRequestSchema.validate(application_df)
    except (pandera.errors.SchemaError, pandera.errors.SchemaErrors) as exc:
        raise HTTPException(status_code=422, detail=f"applicant: {exc}") from exc

    raw_tables = {"application_train": application_df}
    for name, schema in HISTORY_SCHEMAS.items():
        raw_tables[name] = _validate_history_table(name, getattr(payload, name), schema)
    return raw_tables


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": state.model_version}


@app.post("/predict/credit")
def predict_credit(payload: CreditPredictionRequest) -> dict:
    request_id = str(uuid.uuid4())
    decision_date = payload.decision_date or datetime.now(UTC)

    raw_tables = _build_raw_tables(payload)
    application_dates = pd.Series({payload.applicant_id: pd.Timestamp(decision_date)})
    application_dates.index.name = "SK_ID_CURR"

    features_df = assemble_features(raw_tables, application_dates)
    columns = feature_columns(features_df)
    X = prepare_features(features_df, columns, categories=state.categories)

    score = float(state.model.predict_proba(X)[:, 1][0])
    decision = "flag" if score >= state.threshold else "pass"
    reason_codes = compute_reason_codes(state.model, state.model_type, X, sample_size=1)
    contributions = reason_codes[0]["contributions"] if reason_codes else []

    record = {
        "request_id": request_id,
        "applicant_id": payload.applicant_id,
        "model_name": REGISTERED_MODEL_NAME,
        "model_version": state.model_version,
        "score": score,
        "decision": decision,
        "threshold": state.threshold,
        "feature_vector": X.iloc[0].to_dict(),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    write_prediction_record(record, domain=DOMAIN)
    _log_event(
        "prediction",
        request_id=request_id,
        applicant_id=payload.applicant_id,
        model_version=state.model_version,
        score=score,
        decision=decision,
    )

    return {
        "request_id": request_id,
        "model_version": state.model_version,
        "score": score,
        "decision": decision,
        "threshold": state.threshold,
        "reason_codes": contributions,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bankml.serving.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
