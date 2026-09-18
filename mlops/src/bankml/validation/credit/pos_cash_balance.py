"""Pandera contract for POS_CASH_balance.csv.

Columns and nullability cross-checked against a full-file null scan (all 10,001,358
rows) — consistent with the 20,000-row sample, no new nulls found.
"""

import pandera.pandas as pa
from pandera.typing import Series


class PosCashBalanceSchema(pa.DataFrameModel):
    SK_ID_PREV: Series[int] = pa.Field(nullable=False)
    SK_ID_CURR: Series[int] = pa.Field(nullable=False)
    MONTHS_BALANCE: Series[int] = pa.Field(nullable=False)
    CNT_INSTALMENT: Series[float] = pa.Field(nullable=True)
    CNT_INSTALMENT_FUTURE: Series[float] = pa.Field(nullable=True)
    NAME_CONTRACT_STATUS: Series[str] = pa.Field(nullable=False)
    SK_DPD: Series[int] = pa.Field(nullable=False)
    SK_DPD_DEF: Series[int] = pa.Field(nullable=False)

    class Config:
        strict = True
        coerce = True
