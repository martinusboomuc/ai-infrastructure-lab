"""FastAPI serving for Credit Risk and Fraud Detection (Phase 4, ARCHITECTURE.md §6, ADR-0023).

Every request builds features through the same code training uses (each domain's
`features/<domain>/pipeline.assemble_features` and `prepare`) and scores through the same model
object training fit. See ADR-0009 for why a request carries its own history rather than looking
features up from an online store (ADR-0006 defers that store).

One process serves both domains (ADR-0023): the libraries are most of the memory, and they are
loaded once. Each domain loads its own `<domain>-champion@production` at startup. Credit Risk is
required; a domain without a production version yet answers 503 instead of stopping the API.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import mlflow.artifacts
import mlflow.pyfunc
import pandas as pd
import pandera.errors
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from pydantic import BaseModel, Field, NaiveDatetime

from bankml.evaluation.explain import compute_reason_codes
from bankml.features.credit import prepare as credit_prepare
from bankml.features.credit.pipeline import assemble_features
from bankml.features.fraud import pipeline as fraud_pipeline
from bankml.features.fraud import prepare as fraud_prepare
from bankml.serving.auth import ApiKeyAuth, load_api_keys
from bankml.serving.metrics import PREDICTIONS, metrics_middleware, render_metrics
from bankml.serving.prediction_log import write_prediction_record
from bankml.validation.credit.bureau import BureauSchema
from bankml.validation.credit.bureau_balance import BureauBalanceSchema
from bankml.validation.credit.credit_card_balance import CreditCardBalanceSchema
from bankml.validation.credit.installments_payments import InstallmentsPaymentsSchema
from bankml.validation.credit.pos_cash_balance import PosCashBalanceSchema
from bankml.validation.credit.previous_application import PreviousApplicationSchema
from bankml.validation.credit.request import ApplicationRequestSchema
from bankml.validation.fraud.request import TransactionRequestSchema

logger = logging.getLogger("bankml.serving")

MODEL_ALIAS = "production"
TrafficSource = Literal["live", "replay", "test"]
DOMAINS = ("credit", "fraud")
# A domain the API cannot start without. Fraud joins once it has served for a while.
REQUIRED_DOMAINS = {"credit"}

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


class FraudTransaction(BaseModel):
    # Local time without a zone, as the card network records it and as the model was trained.
    trans_date_trans_time: NaiveDatetime
    category: str
    amt: float
    lat: float
    long: float
    merch_lat: float
    merch_long: float


class CardTransaction(BaseModel):
    trans_date_trans_time: NaiveDatetime
    category: str
    amt: float
    merch_lat: float
    merch_long: float


class FraudPredictionRequest(BaseModel):
    transaction_id: str
    card_id: int
    transaction: FraudTransaction
    # The card's earlier transactions from the last `velocity.HISTORY_DAYS` days. Older ones are
    # accepted and ignored: no feature looks further back.
    history: list[CardTransaction] = Field(default_factory=list)


@dataclass
class DomainModel:
    model: Any
    model_type: str
    model_version: str
    threshold: float
    categories: dict[str, list] = field(default_factory=dict)


models: dict[str, DomainModel] = {}
require_client = ApiKeyAuth()


def registered_model_name(domain: str) -> str:
    return f"{domain}-champion"


def load_production_model(domain: str) -> DomainModel:
    """Load a domain's production model and the threshold the gate actually evaluated
    (`test_alert_threshold`, computed in `evaluation/metrics.py` and logged by `tracking.py`) —
    never recomputed here, it must be the exact number the promoted run was gated on.
    """
    name = registered_model_name(domain)
    client = MlflowClient()
    version = client.get_model_version_by_alias(name, MODEL_ALIAS)
    run = client.get_run(version.run_id)

    loaded = mlflow.pyfunc.load_model(f"models:/{name}@{MODEL_ALIAS}")
    # unwrap_python_model() reaches past pyfunc's uniform predict(X) to the actual
    # ScorecardModel/LGBMClassifier (see registry/pyfunc_model.py) — reason codes need the real
    # object's own SHAP explainer, not just a probability.
    loaded_model = DomainModel(
        model=loaded.unwrap_python_model().model,
        model_type=run.data.params["model_type"],
        model_version=version.version,
        threshold=run.data.metrics["test_alert_threshold"],
        # Same category levels this run was fit on (tracking.py logs this alongside the model) —
        # required for a tree model's categorical encoding to match at predict time; see
        # features/credit/prepare.py::capture_categories's docstring.
        categories=mlflow.artifacts.load_dict(f"runs:/{version.run_id}/categorical_levels.json"),
    )
    _log_event(
        "model_loaded",
        model_name=name,
        model_version=loaded_model.model_version,
        model_type=loaded_model.model_type,
        threshold=loaded_model.threshold,
    )
    return loaded_model


def load_models() -> None:
    models.clear()
    for domain in DOMAINS:
        try:
            models[domain] = load_production_model(domain)
        except MlflowException as exc:
            if domain in REQUIRED_DOMAINS:
                raise
            # No registered model or no production alias yet: the endpoint answers 503.
            _log_event("model_not_loaded", model_name=registered_model_name(domain), error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Before the models: a malformed key table should stop startup before anything is served.
    require_client.keys = load_api_keys()
    if not require_client.keys:
        logger.warning("BANKML_API_KEYS is empty: protected endpoints will answer 503")
    load_models()
    yield


app = FastAPI(title="BankML Serving", lifespan=lifespan)
app.middleware("http")(metrics_middleware)


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


def _build_fraud_frame(payload: FraudPredictionRequest) -> pd.DataFrame:
    """The transaction and its card history as raw rows, in the shape `assemble_features` reads
    from the Sparkov files. A history row only feeds the scored transaction's features through
    its time, category, amount and merchant location, so it borrows the cardholder's location
    from the transaction.
    """
    transaction = payload.transaction
    scored_at = transaction.trans_date_trans_time
    if any(row.trans_date_trans_time >= scored_at for row in payload.history):
        raise HTTPException(
            status_code=422,
            detail="history: every row must be strictly before the transaction",
        )

    shared = {
        "cc_num": payload.card_id,
        "lat": transaction.lat,
        "long": transaction.long,
    }
    rows = [
        {"trans_num": f"{payload.transaction_id}/history/{i}", **shared, **row.model_dump()}
        for i, row in enumerate(payload.history)
    ]
    rows.append({"trans_num": payload.transaction_id, **shared, **transaction.model_dump()})
    try:
        return TransactionRequestSchema.validate(pd.DataFrame(rows))
    except (pandera.errors.SchemaError, pandera.errors.SchemaErrors) as exc:
        raise HTTPException(status_code=422, detail=f"transaction: {exc}") from exc


def _production_model(domain: str) -> DomainModel:
    loaded = models.get(domain)
    if loaded is None:
        raise HTTPException(
            status_code=503, detail=f"{registered_model_name(domain)} has no production version"
        )
    return loaded


def _score(
    domain: str,
    loaded: DomainModel,
    X: pd.DataFrame,
    entity: dict[str, Any],
    traffic_source: str,
    client: str,
) -> dict:
    """Score one prepared row, log it, and build the response. `entity` names what was scored
    (`applicant_id` for Credit Risk, `transaction_id` and `card_id` for Fraud) and is copied into
    the log record and the log event.
    """
    request_id = str(uuid.uuid4())
    score = float(loaded.model.predict_proba(X)[:, 1][0])
    decision = "flag" if score >= loaded.threshold else "pass"
    reason_codes = compute_reason_codes(loaded.model, loaded.model_type, X, sample_size=1)
    contributions = reason_codes[0]["contributions"] if reason_codes else []

    record = {
        "request_id": request_id,
        **entity,
        "model_name": registered_model_name(domain),
        "model_version": loaded.model_version,
        "score": score,
        "decision": decision,
        "threshold": loaded.threshold,
        "feature_vector": X.iloc[0].to_dict(),
        "traffic_source": traffic_source,
        "client": client,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    write_prediction_record(record, domain=domain)
    PREDICTIONS.labels(domain=domain, decision=decision).inc()
    _log_event(
        "prediction",
        domain=domain,
        request_id=request_id,
        **entity,
        model_version=loaded.model_version,
        score=score,
        decision=decision,
        traffic_source=traffic_source,
        client=client,
    )

    return {
        "request_id": request_id,
        "model_version": loaded.model_version,
        "score": score,
        "decision": decision,
        "threshold": loaded.threshold,
        "reason_codes": contributions,
    }


@app.get("/health")
def health() -> dict:
    versions = {domain: loaded.model_version for domain, loaded in models.items()}
    # `model_version` is Credit Risk's, kept for the callers that read it before Fraud was served.
    return {"status": "ok", "model_version": versions.get("credit", ""), "models": versions}


@app.get("/metrics", dependencies=[Depends(require_client)])
def metrics() -> Response:
    return render_metrics()


@app.post("/predict/credit")
def predict_credit(
    payload: CreditPredictionRequest,
    # Set to "replay" by bankml.monitoring.replay (ADR-0016), and to "test" by the Nexus test
    # bench (ADR-0025). Logged with the prediction so neither is mistaken for real traffic by
    # drift or performance; anything else is refused.
    x_traffic_source: Annotated[TrafficSource, Header()] = "live",
    client: str = Depends(require_client),
) -> dict:
    loaded = _production_model("credit")
    decision_date = payload.decision_date or datetime.now(UTC)

    raw_tables = _build_raw_tables(payload)
    application_dates = pd.Series({payload.applicant_id: pd.Timestamp(decision_date)})
    application_dates.index.name = "SK_ID_CURR"

    features_df = assemble_features(raw_tables, application_dates)
    columns = credit_prepare.feature_columns(features_df)
    X = credit_prepare.prepare_features(features_df, columns, categories=loaded.categories)

    entity = {"applicant_id": payload.applicant_id}
    return _score("credit", loaded, X, entity, x_traffic_source, client)


@app.post("/predict/fraud")
def predict_fraud(
    payload: FraudPredictionRequest,
    x_traffic_source: Annotated[TrafficSource, Header()] = "live",
    client: str = Depends(require_client),
) -> dict:
    loaded = _production_model("fraud")

    features_df = fraud_pipeline.assemble_features(_build_fraud_frame(payload))
    scored = features_df[features_df["trans_num"] == payload.transaction_id]
    columns = fraud_prepare.feature_columns(scored)
    X = fraud_prepare.prepare_features(scored, columns, categories=loaded.categories)

    entity = {"transaction_id": payload.transaction_id, "card_id": payload.card_id}
    return _score("fraud", loaded, X.reset_index(drop=True), entity, x_traffic_source, client)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("bankml.serving.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
