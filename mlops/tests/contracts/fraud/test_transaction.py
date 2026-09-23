"""Contract tests for fraudTrain.csv/fraudTest.csv's schema.

Base valid row built generically from the schema's own declared dtype/nullability per column
(int -> 0, float -> 0.0, str -> "x"), then the semantically-important columns overridden
explicitly — same convention as tests/contracts/credit/test_application.py.
"""

import pandas as pd
import pandera.errors
import pytest

from bankml.validation.fraud.transaction import TransactionSchema


def _generic_valid_row():
    row = {}
    for name, column in TransactionSchema.to_schema().columns.items():
        dtype = str(column.dtype)
        if "int" in dtype:
            row[name] = 0
        elif "float" in dtype:
            row[name] = 0.0
        else:
            row[name] = "x"
    return row


def _valid_row(trans_num, is_fraud=0):
    row = _generic_valid_row()
    row.update(
        {
            "trans_num": trans_num,
            "is_fraud": is_fraud,
            "gender": "F",
            "lat": 36.0788,
            "long": -81.1781,
            "merch_lat": 36.011293,
            "merch_long": -82.048315,
            "amt": 4.97,
            "city_pop": 3495,
        }
    )
    return row


def test_accepts_valid_rows():
    df = pd.DataFrame([_valid_row("t1"), _valid_row("t2", is_fraud=1)])
    TransactionSchema.validate(df, lazy=True)


def test_rejects_duplicate_trans_num():
    df = pd.DataFrame([_valid_row("t1"), _valid_row("t1")])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        TransactionSchema.validate(df, lazy=True)


def test_rejects_is_fraud_outside_zero_one():
    df = pd.DataFrame([_valid_row("t1", is_fraud=2)])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        TransactionSchema.validate(df, lazy=True)


def test_rejects_gender_outside_f_m():
    row = _valid_row("t1")
    row["gender"] = "X"
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        TransactionSchema.validate(df, lazy=True)


def test_rejects_latitude_outside_valid_range():
    row = _valid_row("t1")
    row["lat"] = 200.0
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        TransactionSchema.validate(df, lazy=True)


def test_rejects_negative_amount():
    row = _valid_row("t1")
    row["amt"] = -5.0
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        TransactionSchema.validate(df, lazy=True)
