"""Pandera contract for previous_application.csv.

Columns and nullability determined from a 20,000-row sample of the real file.

Surprise found during inspection, not previously documented in docs/datasets/README.md
or configs/credit.yaml (which only mention the sentinel on application_train's
DAYS_EMPLOYED): the 365243 "not applicable" sentinel also appears in FIVE columns
here — DAYS_FIRST_DRAWING, DAYS_FIRST_DUE, DAYS_LAST_DUE_1ST_VERSION, DAYS_LAST_DUE,
and DAYS_TERMINATION — all with nontrivial occurrence counts in just the sample. As
in application.py, the sentinel is deliberately not rejected or coerced here; it's a
feature-pipeline concern for a later stage.

Nullability also cross-checked against a full-file null scan (all 1,670,214 rows):
AMT_CREDIT (1 null) turned out nullable despite showing zero nulls in the sample.
"""

import pandera.pandas as pa
from pandera.typing import Series


class PreviousApplicationSchema(pa.DataFrameModel):
    SK_ID_PREV: Series[int] = pa.Field(nullable=False, unique=True)
    SK_ID_CURR: Series[int] = pa.Field(nullable=False)
    NAME_CONTRACT_TYPE: Series[str] = pa.Field(nullable=False)
    AMT_ANNUITY: Series[float] = pa.Field(nullable=True)
    AMT_APPLICATION: Series[float] = pa.Field(nullable=False)
    AMT_CREDIT: Series[float] = pa.Field(nullable=True)
    AMT_DOWN_PAYMENT: Series[float] = pa.Field(nullable=True)
    AMT_GOODS_PRICE: Series[float] = pa.Field(nullable=True)
    WEEKDAY_APPR_PROCESS_START: Series[str] = pa.Field(nullable=False)
    HOUR_APPR_PROCESS_START: Series[int] = pa.Field(nullable=False)
    FLAG_LAST_APPL_PER_CONTRACT: Series[str] = pa.Field(nullable=False)
    NFLAG_LAST_APPL_IN_DAY: Series[int] = pa.Field(nullable=False)
    RATE_DOWN_PAYMENT: Series[float] = pa.Field(nullable=True)
    RATE_INTEREST_PRIMARY: Series[float] = pa.Field(nullable=True)
    RATE_INTEREST_PRIVILEGED: Series[float] = pa.Field(nullable=True)
    NAME_CASH_LOAN_PURPOSE: Series[str] = pa.Field(nullable=False)
    NAME_CONTRACT_STATUS: Series[str] = pa.Field(nullable=False)
    DAYS_DECISION: Series[int] = pa.Field(nullable=False)
    NAME_PAYMENT_TYPE: Series[str] = pa.Field(nullable=False)
    CODE_REJECT_REASON: Series[str] = pa.Field(nullable=False)
    NAME_TYPE_SUITE: Series[str] = pa.Field(nullable=True)
    NAME_CLIENT_TYPE: Series[str] = pa.Field(nullable=False)
    NAME_GOODS_CATEGORY: Series[str] = pa.Field(nullable=False)
    NAME_PORTFOLIO: Series[str] = pa.Field(nullable=False)
    NAME_PRODUCT_TYPE: Series[str] = pa.Field(nullable=False)
    CHANNEL_TYPE: Series[str] = pa.Field(nullable=False)
    SELLERPLACE_AREA: Series[int] = pa.Field(nullable=False)
    NAME_SELLER_INDUSTRY: Series[str] = pa.Field(nullable=False)
    CNT_PAYMENT: Series[float] = pa.Field(nullable=True)
    NAME_YIELD_GROUP: Series[str] = pa.Field(nullable=False)
    PRODUCT_COMBINATION: Series[str] = pa.Field(nullable=True)
    # Sentinel 365243 observed here too (see module docstring) — not just on
    # application_train's DAYS_EMPLOYED as currently documented elsewhere.
    DAYS_FIRST_DRAWING: Series[float] = pa.Field(nullable=True)
    DAYS_FIRST_DUE: Series[float] = pa.Field(nullable=True)
    DAYS_LAST_DUE_1ST_VERSION: Series[float] = pa.Field(nullable=True)
    DAYS_LAST_DUE: Series[float] = pa.Field(nullable=True)
    DAYS_TERMINATION: Series[float] = pa.Field(nullable=True)
    NFLAG_INSURED_ON_APPROVAL: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True
