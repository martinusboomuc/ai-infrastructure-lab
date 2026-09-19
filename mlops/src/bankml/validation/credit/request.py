"""Pandera contract for a single serving-time request's applicant fields (Phase 4).

Deliberately narrower than `ApplicationTrainSchema`: a real lending-decision API call submits the
fields the model actually consumes (`features/credit/pipeline.py::BASE_APPLICANT_COLUMNS`), not
the full ~120-column raw ingestion contract — nobody submits apartment-condition indices at
request time, and ARCHITECTURE.md's serving section never implies they would. Field-level
constraints (nullability, dtype) for the columns both schemas share are kept identical to
`ApplicationTrainSchema` on purpose, so "the training Pandera contract" is honoured at the level
that actually matters: the columns that flow into the model.

The relational history tables a request may attach (bureau, previous_application, ...) are
validated against their own existing schemas in this package — see
`bankml.serving.app` — not duplicated here.
"""

import pandera.pandas as pa
from pandera.typing import Series


class ApplicationRequestSchema(pa.DataFrameModel):
    SK_ID_CURR: Series[int] = pa.Field(nullable=False, unique=True)
    CODE_GENDER: Series[str] = pa.Field(nullable=False)
    DAYS_BIRTH: Series[int] = pa.Field(nullable=False)
    # Sentinel 365243 means "not employed" (configs/credit.yaml) — not rejected here, same as
    # ApplicationTrainSchema; sentinel handling stays feature-pipeline work.
    DAYS_EMPLOYED: Series[int] = pa.Field(nullable=False)
    AMT_INCOME_TOTAL: Series[float] = pa.Field(nullable=False)
    AMT_CREDIT: Series[float] = pa.Field(nullable=False)
    AMT_ANNUITY: Series[float] = pa.Field(nullable=True)
    NAME_EDUCATION_TYPE: Series[str] = pa.Field(nullable=False)
    NAME_FAMILY_STATUS: Series[str] = pa.Field(nullable=False)
    NAME_HOUSING_TYPE: Series[str] = pa.Field(nullable=False)
    CNT_CHILDREN: Series[int] = pa.Field(nullable=False)
    EXT_SOURCE_1: Series[float] = pa.Field(nullable=True)
    EXT_SOURCE_2: Series[float] = pa.Field(nullable=True)
    EXT_SOURCE_3: Series[float] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True
