"""Contract tests for application_train.csv's schema.

122 columns makes a fully hand-typed fixture error-prone and not worth it structurally
— the base valid row is built generically from the schema's own declared dtype/
nullability per column (a bool -> False, int -> 0, float -> 0.0, str -> "x"), then the
handful of semantically-important columns are overridden explicitly. This keeps the
fixture in sync automatically if a column is ever added to the schema.
"""

import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.application import ApplicationTrainSchema


def _generic_valid_row():
    row = {}
    for name, column in ApplicationTrainSchema.to_schema().columns.items():
        dtype = str(column.dtype)
        if "int" in dtype:
            row[name] = 0
        elif "float" in dtype:
            row[name] = 0.0
        else:
            row[name] = "x"
    return row


def _valid_row(sk_id_curr, target=0):
    row = _generic_valid_row()
    row.update(
        {
            "SK_ID_CURR": sk_id_curr,
            "TARGET": target,
            "DAYS_BIRTH": -12005,
            "DAYS_EMPLOYED": -2000,
            "AMT_ANNUITY": 24700.5,
            "CNT_FAM_MEMBERS": 2.0,
        }
    )
    return row


def test_accepts_valid_rows():
    df = pd.DataFrame([_valid_row(1), _valid_row(2, target=1)])
    ApplicationTrainSchema.validate(df, lazy=True)


def test_accepts_the_days_employed_sentinel():
    row = _valid_row(1)
    row["DAYS_EMPLOYED"] = 365243  # means "not employed" — must be accepted, not rejected
    df = pd.DataFrame([row])
    ApplicationTrainSchema.validate(df, lazy=True)


def test_accepts_null_in_amt_annuity_and_cnt_fam_members():
    # Real full-file scan found nulls here — must stay accepted.
    row = _valid_row(1)
    row["AMT_ANNUITY"] = None
    row["CNT_FAM_MEMBERS"] = None
    df = pd.DataFrame([row])
    ApplicationTrainSchema.validate(df, lazy=True)


def test_rejects_duplicate_sk_id_curr():
    df = pd.DataFrame([_valid_row(1), _valid_row(1)])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        ApplicationTrainSchema.validate(df, lazy=True)


def test_rejects_target_outside_zero_one():
    df = pd.DataFrame([_valid_row(1, target=2)])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        ApplicationTrainSchema.validate(df, lazy=True)


def test_rejects_null_in_target():
    row = _valid_row(1)
    row["TARGET"] = None
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        ApplicationTrainSchema.validate(df, lazy=True)
