"""Pandera contract for bureau_balance.csv.

Columns and nullability cross-checked against a full-file null scan (all 27,299,925
rows) — consistent with the 20,000-row sample, genuinely zero nulls anywhere. This
table has no SK_ID_CURR at all — it's keyed by SK_ID_BUREAU only, joined to the
customer indirectly through bureau.csv.
"""

import pandera.pandas as pa
from pandera.typing import Series


class BureauBalanceSchema(pa.DataFrameModel):
    SK_ID_BUREAU: Series[int] = pa.Field(nullable=False)
    MONTHS_BALANCE: Series[int] = pa.Field(nullable=False)
    STATUS: Series[str] = pa.Field(nullable=False)

    class Config:
        strict = True
        coerce = True
