"""Pandera contract for fraudTrain.csv/fraudTest.csv (the Sparkov synthetic transaction table).

Columns, dtypes and nullability were determined by inspecting the real downloaded files (both
1,296,676 and 555,720 rows) — not from memory of the public dataset. Every column came back with
zero nulls on a full-file scan, unlike Credit Risk's application_train.csv.
"""

import pandera.pandas as pa
from pandera.typing import Series


class TransactionSchema(pa.DataFrameModel):
    trans_date_trans_time: Series[str] = pa.Field(nullable=False)
    cc_num: Series[int] = pa.Field(nullable=False)
    merchant: Series[str] = pa.Field(nullable=False)
    category: Series[str] = pa.Field(nullable=False)
    amt: Series[float] = pa.Field(nullable=False, ge=0)
    first: Series[str] = pa.Field(nullable=False)
    last: Series[str] = pa.Field(nullable=False)
    gender: Series[str] = pa.Field(nullable=False, isin=["F", "M"])
    street: Series[str] = pa.Field(nullable=False)
    city: Series[str] = pa.Field(nullable=False)
    state: Series[str] = pa.Field(nullable=False)
    zip: Series[int] = pa.Field(nullable=False)
    lat: Series[float] = pa.Field(nullable=False, ge=-90, le=90)
    long: Series[float] = pa.Field(nullable=False, ge=-180, le=180)
    city_pop: Series[int] = pa.Field(nullable=False, ge=0)
    job: Series[str] = pa.Field(nullable=False)
    dob: Series[str] = pa.Field(nullable=False)
    trans_num: Series[str] = pa.Field(nullable=False, unique=True)
    unix_time: Series[int] = pa.Field(nullable=False)
    merch_lat: Series[float] = pa.Field(nullable=False, ge=-90, le=90)
    merch_long: Series[float] = pa.Field(nullable=False, ge=-180, le=180)
    is_fraud: Series[int] = pa.Field(nullable=False, isin=[0, 1])

    class Config:
        strict = True
        coerce = True
