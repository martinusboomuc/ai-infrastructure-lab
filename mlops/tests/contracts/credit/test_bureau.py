import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.bureau import BureauSchema


def _valid_row(sk_id_bureau, sk_id_curr):
    return {
        "SK_ID_CURR": sk_id_curr,
        "SK_ID_BUREAU": sk_id_bureau,
        "CREDIT_ACTIVE": "Closed",
        "CREDIT_CURRENCY": "currency 1",
        "DAYS_CREDIT": -857,
        "CREDIT_DAY_OVERDUE": 0,
        "DAYS_CREDIT_ENDDATE": -492.0,
        "DAYS_ENDDATE_FACT": -553.0,
        "AMT_CREDIT_MAX_OVERDUE": 0.0,
        "CNT_CREDIT_PROLONG": 0,
        "AMT_CREDIT_SUM": 91323.0,
        "AMT_CREDIT_SUM_DEBT": 0.0,
        "AMT_CREDIT_SUM_LIMIT": 0.0,
        "AMT_CREDIT_SUM_OVERDUE": 0.0,
        "CREDIT_TYPE": "Consumer credit",
        "DAYS_CREDIT_UPDATE": -155,
        "AMT_ANNUITY": None,
    }


def test_accepts_valid_rows():
    df = pd.DataFrame([_valid_row(100001, 1), _valid_row(100002, 1), _valid_row(100003, 2)])
    BureauSchema.validate(df, lazy=True)


def test_rejects_duplicate_primary_key():
    df = pd.DataFrame([_valid_row(100001, 1), _valid_row(100001, 2)])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        BureauSchema.validate(df, lazy=True)
