import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.installments_payments import InstallmentsPaymentsSchema


def _valid_row(sk_id_prev, sk_id_curr):
    return {
        "SK_ID_PREV": sk_id_prev,
        "SK_ID_CURR": sk_id_curr,
        "NUM_INSTALMENT_VERSION": 1.0,
        "NUM_INSTALMENT_NUMBER": 3,
        "DAYS_INSTALMENT": -1180.0,
        "DAYS_ENTRY_PAYMENT": -1187.0,
        "AMT_INSTALMENT": 6948.36,
        "AMT_PAYMENT": 6948.36,
    }


def test_accepts_valid_rows():
    df = pd.DataFrame([_valid_row(1000001, 1), _valid_row(1000002, 2)])
    InstallmentsPaymentsSchema.validate(df, lazy=True)


def test_accepts_null_in_days_entry_payment_and_amt_payment():
    # Real full-file scan found nulls here (unpaid installments) — must stay accepted.
    row = _valid_row(1000001, 1)
    row["DAYS_ENTRY_PAYMENT"] = None
    row["AMT_PAYMENT"] = None
    df = pd.DataFrame([row])
    InstallmentsPaymentsSchema.validate(df, lazy=True)


def test_rejects_null_in_required_column():
    row = _valid_row(1000001, 1)
    row["AMT_INSTALMENT"] = None
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        InstallmentsPaymentsSchema.validate(df, lazy=True)
