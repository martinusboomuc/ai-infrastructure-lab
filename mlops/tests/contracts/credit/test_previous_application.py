import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.previous_application import PreviousApplicationSchema


def _valid_row(sk_id_prev, sk_id_curr):
    return {
        "SK_ID_PREV": sk_id_prev,
        "SK_ID_CURR": sk_id_curr,
        "NAME_CONTRACT_TYPE": "Consumer loans",
        "AMT_ANNUITY": 1730.43,
        "AMT_APPLICATION": 17145.0,
        "AMT_CREDIT": 17145.0,
        "AMT_DOWN_PAYMENT": 0.0,
        "AMT_GOODS_PRICE": 17145.0,
        "WEEKDAY_APPR_PROCESS_START": "SATURDAY",
        "HOUR_APPR_PROCESS_START": 15,
        "FLAG_LAST_APPL_PER_CONTRACT": "Y",
        "NFLAG_LAST_APPL_IN_DAY": 1,
        "RATE_DOWN_PAYMENT": 0.0,
        "RATE_INTEREST_PRIMARY": None,
        "RATE_INTEREST_PRIVILEGED": None,
        "NAME_CASH_LOAN_PURPOSE": "XAP",
        "NAME_CONTRACT_STATUS": "Approved",
        "DAYS_DECISION": -73,
        "NAME_PAYMENT_TYPE": "Cash through the bank",
        "CODE_REJECT_REASON": "XAP",
        "NAME_TYPE_SUITE": None,
        "NAME_CLIENT_TYPE": "Repeater",
        "NAME_GOODS_CATEGORY": "Mobile",
        "NAME_PORTFOLIO": "POS",
        "NAME_PRODUCT_TYPE": "XNA",
        "CHANNEL_TYPE": "Country-wide",
        "SELLERPLACE_AREA": 35,
        "NAME_SELLER_INDUSTRY": "Connectivity",
        "CNT_PAYMENT": 12.0,
        "NAME_YIELD_GROUP": "middle",
        "PRODUCT_COMBINATION": "POS mobile with interest",
        # 365243 sentinel per ADR/config, real distinct rows below exercise it.
        "DAYS_FIRST_DRAWING": 365243.0,
        "DAYS_FIRST_DUE": -42.0,
        "DAYS_LAST_DUE_1ST_VERSION": 300.0,
        "DAYS_LAST_DUE": -37.0,
        "DAYS_TERMINATION": -37.0,
        "NFLAG_INSURED_ON_APPROVAL": 0.0,
    }


def test_accepts_valid_rows():
    df = pd.DataFrame([_valid_row(2000001, 1), _valid_row(2000002, 1), _valid_row(2000003, 2)])
    PreviousApplicationSchema.validate(df, lazy=True)


def test_accepts_the_365243_sentinel_and_nulls_in_the_days_columns():
    row = _valid_row(2000001, 1)
    row["DAYS_FIRST_DRAWING"] = 365243.0
    row["DAYS_FIRST_DUE"] = 365243.0
    row["DAYS_LAST_DUE_1ST_VERSION"] = 365243.0
    row["DAYS_LAST_DUE"] = None
    row["DAYS_TERMINATION"] = None
    row["NFLAG_INSURED_ON_APPROVAL"] = None
    df = pd.DataFrame([row])
    PreviousApplicationSchema.validate(df, lazy=True)


def test_rejects_null_in_required_column():
    row = _valid_row(2000001, 1)
    row["DAYS_DECISION"] = None
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        PreviousApplicationSchema.validate(df, lazy=True)


def test_rejects_duplicate_primary_key():
    df = pd.DataFrame([_valid_row(2000001, 1), _valid_row(2000001, 2)])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        PreviousApplicationSchema.validate(df, lazy=True)
