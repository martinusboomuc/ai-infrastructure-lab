import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.pos_cash_balance import PosCashBalanceSchema


def _valid_row(sk_id_prev, sk_id_curr):
    return {
        "SK_ID_PREV": sk_id_prev,
        "SK_ID_CURR": sk_id_curr,
        "MONTHS_BALANCE": -1,
        "CNT_INSTALMENT": 24.0,
        "CNT_INSTALMENT_FUTURE": 20.0,
        "NAME_CONTRACT_STATUS": "Active",
        "SK_DPD": 0,
        "SK_DPD_DEF": 0,
    }


def test_accepts_valid_rows():
    df = pd.DataFrame([_valid_row(1000001, 1), _valid_row(1000002, 2)])
    PosCashBalanceSchema.validate(df, lazy=True)


def test_rejects_wrong_dtype_in_required_column():
    df = pd.DataFrame([_valid_row(1000001, 1)])
    df["MONTHS_BALANCE"] = "not-a-number"
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        PosCashBalanceSchema.validate(df, lazy=True)
