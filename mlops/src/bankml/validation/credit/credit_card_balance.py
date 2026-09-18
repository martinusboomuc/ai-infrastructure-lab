"""Pandera contract for credit_card_balance.csv.

Columns and nullability cross-checked against a full-file null scan (all 3,840,312
rows) — consistent with the 20,000-row sample, no new nulls found.
"""

import pandera.pandas as pa
from pandera.typing import Series


class CreditCardBalanceSchema(pa.DataFrameModel):
    SK_ID_PREV: Series[int] = pa.Field(nullable=False)
    SK_ID_CURR: Series[int] = pa.Field(nullable=False)
    MONTHS_BALANCE: Series[int] = pa.Field(nullable=False)
    AMT_BALANCE: Series[float] = pa.Field(nullable=False)
    AMT_CREDIT_LIMIT_ACTUAL: Series[int] = pa.Field(nullable=False)
    AMT_DRAWINGS_ATM_CURRENT: Series[float] = pa.Field(nullable=True)
    AMT_DRAWINGS_CURRENT: Series[float] = pa.Field(nullable=False)
    AMT_DRAWINGS_OTHER_CURRENT: Series[float] = pa.Field(nullable=True)
    AMT_DRAWINGS_POS_CURRENT: Series[float] = pa.Field(nullable=True)
    AMT_INST_MIN_REGULARITY: Series[float] = pa.Field(nullable=True)
    AMT_PAYMENT_CURRENT: Series[float] = pa.Field(nullable=True)
    AMT_PAYMENT_TOTAL_CURRENT: Series[float] = pa.Field(nullable=False)
    AMT_RECEIVABLE_PRINCIPAL: Series[float] = pa.Field(nullable=False)
    AMT_RECIVABLE: Series[float] = pa.Field(nullable=False)
    AMT_TOTAL_RECEIVABLE: Series[float] = pa.Field(nullable=False)
    CNT_DRAWINGS_ATM_CURRENT: Series[float] = pa.Field(nullable=True)
    CNT_DRAWINGS_CURRENT: Series[int] = pa.Field(nullable=False)
    CNT_DRAWINGS_OTHER_CURRENT: Series[float] = pa.Field(nullable=True)
    CNT_DRAWINGS_POS_CURRENT: Series[float] = pa.Field(nullable=True)
    CNT_INSTALMENT_MATURE_CUM: Series[float] = pa.Field(nullable=True)
    NAME_CONTRACT_STATUS: Series[str] = pa.Field(nullable=False)
    SK_DPD: Series[int] = pa.Field(nullable=False)
    SK_DPD_DEF: Series[int] = pa.Field(nullable=False)

    class Config:
        strict = True
        coerce = True
