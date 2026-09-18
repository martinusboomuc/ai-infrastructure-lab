"""Pandera contract for bureau.csv.

Columns and nullability cross-checked against a full-file null scan (all 1,716,428
rows), not just the initial sample: AMT_CREDIT_SUM (13 nulls) turned out nullable
despite showing zero nulls in the first 20,000-row sample.

SK_ID_CURR is a plain foreign key here (not unique — one customer has many bureau
records), unlike in application_train where it is the primary key.
"""

import pandera.pandas as pa
from pandera.typing import Series


class BureauSchema(pa.DataFrameModel):
    SK_ID_CURR: Series[int] = pa.Field(nullable=False)
    SK_ID_BUREAU: Series[int] = pa.Field(nullable=False, unique=True)
    CREDIT_ACTIVE: Series[str] = pa.Field(nullable=False)
    CREDIT_CURRENCY: Series[str] = pa.Field(nullable=False)
    DAYS_CREDIT: Series[int] = pa.Field(nullable=False)
    CREDIT_DAY_OVERDUE: Series[int] = pa.Field(nullable=False)
    DAYS_CREDIT_ENDDATE: Series[float] = pa.Field(nullable=True)
    DAYS_ENDDATE_FACT: Series[float] = pa.Field(nullable=True)
    AMT_CREDIT_MAX_OVERDUE: Series[float] = pa.Field(nullable=True)
    CNT_CREDIT_PROLONG: Series[int] = pa.Field(nullable=False)
    AMT_CREDIT_SUM: Series[float] = pa.Field(nullable=True)
    AMT_CREDIT_SUM_DEBT: Series[float] = pa.Field(nullable=True)
    AMT_CREDIT_SUM_LIMIT: Series[float] = pa.Field(nullable=True)
    AMT_CREDIT_SUM_OVERDUE: Series[float] = pa.Field(nullable=False)
    CREDIT_TYPE: Series[str] = pa.Field(nullable=False)
    DAYS_CREDIT_UPDATE: Series[int] = pa.Field(nullable=False)
    AMT_ANNUITY: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True
