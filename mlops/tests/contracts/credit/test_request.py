"""Contract tests for the serving-time applicant request schema (Phase 4, ADR-0009)."""

import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.request import ApplicationRequestSchema


def _valid_row(sk_id_curr=1):
    return {
        "SK_ID_CURR": sk_id_curr,
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


def test_accepts_a_valid_applicant():
    df = pd.DataFrame([_valid_row()])
    ApplicationRequestSchema.validate(df, lazy=True)


def test_accepts_the_days_employed_sentinel():
    row = _valid_row()
    row["DAYS_EMPLOYED"] = 365243  # "not employed" — must be accepted, same as training
    df = pd.DataFrame([row])
    ApplicationRequestSchema.validate(df, lazy=True)


def test_accepts_null_amt_annuity_and_ext_sources():
    row = _valid_row()
    row["AMT_ANNUITY"] = None
    row["EXT_SOURCE_1"] = None
    df = pd.DataFrame([row])
    ApplicationRequestSchema.validate(df, lazy=True)


def test_rejects_a_column_outside_the_serving_contract():
    row = _valid_row()
    row["APARTMENTS_AVG"] = 0.5  # not part of BASE_APPLICANT_COLUMNS — strict schema rejects it
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        ApplicationRequestSchema.validate(df, lazy=True)


def test_rejects_null_code_gender():
    row = _valid_row()
    row["CODE_GENDER"] = None
    df = pd.DataFrame([row])
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        ApplicationRequestSchema.validate(df, lazy=True)
