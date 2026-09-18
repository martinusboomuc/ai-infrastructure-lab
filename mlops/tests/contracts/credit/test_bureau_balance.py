import pandas as pd
import pandera.errors
import pytest

from bankml.validation.credit.bureau_balance import BureauBalanceSchema


def test_accepts_valid_rows():
    df = pd.DataFrame(
        {
            "SK_ID_BUREAU": [100001, 100001, 100002],
            "MONTHS_BALANCE": [0, -1, 0],
            "STATUS": ["C", "0", "X"],
        }
    )
    BureauBalanceSchema.validate(df, lazy=True)


def test_rejects_null_in_required_column():
    df = pd.DataFrame(
        {
            "SK_ID_BUREAU": [100001, None],
            "MONTHS_BALANCE": [0, -1],
            "STATUS": ["C", "0"],
        }
    )
    with pytest.raises((pandera.errors.SchemaError, pandera.errors.SchemaErrors)):
        BureauBalanceSchema.validate(df, lazy=True)
