"""Pandera contract for a serving-time Fraud request, once the API has turned it into rows
(ADR-0023): the transaction being scored plus the card's own recent transactions.

Deliberately narrower than `TransactionSchema`: the API takes the columns the feature pipeline
reads (`features/fraud/pipeline.py::assemble_features`), not the cardholder's name, address, job
or date of birth, which Sparkov carries and the model never uses. The constraints on the columns
both schemas share are kept identical to `TransactionSchema`.
"""

import pandera.pandas as pa
from pandera.typing import DateTime, Series


class TransactionRequestSchema(pa.DataFrameModel):
    trans_num: Series[str] = pa.Field(nullable=False, unique=True)
    trans_date_trans_time: Series[DateTime] = pa.Field(nullable=False)
    cc_num: Series[int] = pa.Field(nullable=False)
    category: Series[str] = pa.Field(nullable=False)
    amt: Series[float] = pa.Field(nullable=False, ge=0)
    lat: Series[float] = pa.Field(nullable=False, ge=-90, le=90)
    long: Series[float] = pa.Field(nullable=False, ge=-180, le=180)
    merch_lat: Series[float] = pa.Field(nullable=False, ge=-90, le=90)
    merch_long: Series[float] = pa.Field(nullable=False, ge=-180, le=180)

    class Config:
        strict = True
        coerce = True
