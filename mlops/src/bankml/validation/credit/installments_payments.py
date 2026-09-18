"""Pandera contract for installments_payments.csv.

The initial 20,000-row sample showed zero nulls anywhere in this table — but a
full-file null scan (all 13,605,401 rows) found 2,905 nulls each in
DAYS_ENTRY_PAYMENT and AMT_PAYMENT, corrected here. Exactly the failure mode a
sample-only schema risks: confirms checking the full file matters, not just noting
the caveat.
"""

import pandera.pandas as pa
from pandera.typing import Series


class InstallmentsPaymentsSchema(pa.DataFrameModel):
    SK_ID_PREV: Series[int] = pa.Field(nullable=False)
    SK_ID_CURR: Series[int] = pa.Field(nullable=False)
    NUM_INSTALMENT_VERSION: Series[float] = pa.Field(nullable=False)
    NUM_INSTALMENT_NUMBER: Series[int] = pa.Field(nullable=False)
    DAYS_INSTALMENT: Series[float] = pa.Field(nullable=False)
    DAYS_ENTRY_PAYMENT: Series[float] = pa.Field(nullable=True)
    AMT_INSTALMENT: Series[float] = pa.Field(nullable=False)
    AMT_PAYMENT: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True
