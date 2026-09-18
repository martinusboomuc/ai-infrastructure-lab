import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.credit_card_balance import CreditCardBalanceSchema


def _valid_row(sk_id_prev, sk_id_curr):
    return {
        "SK_ID_PREV": sk_id_prev,
        "SK_ID_CURR": sk_id_curr,
        "MONTHS_BALANCE": -1,
        "AMT_BALANCE": 56.97,
        "AMT_CREDIT_LIMIT_ACTUAL": 135000,
        "AMT_DRAWINGS_ATM_CURRENT": 0.0,
        "AMT_DRAWINGS_CURRENT": 877.5,
        "AMT_DRAWINGS_OTHER_CURRENT": 0.0,
        "AMT_DRAWINGS_POS_CURRENT": 877.5,
        "AMT_INST_MIN_REGULARITY": 1700.325,
        "AMT_PAYMENT_CURRENT": 1800.0,
        "AMT_PAYMENT_TOTAL_CURRENT": 1800.0,
        "AMT_RECEIVABLE_PRINCIPAL": 0.0,
        "AMT_RECIVABLE": 0.0,
        "AMT_TOTAL_RECEIVABLE": 0.0,
        "CNT_DRAWINGS_ATM_CURRENT": 0.0,
        "CNT_DRAWINGS_CURRENT": 1,
        "CNT_DRAWINGS_OTHER_CURRENT": 0.0,
        "CNT_DRAWINGS_POS_CURRENT": 1.0,
        "CNT_INSTALMENT_MATURE_CUM": 1.0,
        "NAME_CONTRACT_STATUS": "Active",
        "SK_DPD": 0,
        "SK_DPD_DEF": 0,
    }


def test_accepts_valid_rows():
    df = pd.DataFrame([_valid_row(1000001, 1), _valid_row(1000002, 2)])
    CreditCardBalanceSchema.validate(df, lazy=True)


def test_rejects_null_in_required_column():
    row = _valid_row(1000001, 1)
    row["AMT_BALANCE"] = None
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        CreditCardBalanceSchema.validate(df, lazy=True)
