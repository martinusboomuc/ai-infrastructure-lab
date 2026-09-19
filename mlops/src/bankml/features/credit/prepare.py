"""Model-input column selection and dtype coercion for Credit Risk — shared by training
(`bankml.training.pipeline`) and serving (`bankml.serving.app`) so the exact same columns, in
the exact same dtypes, reach a model in both places (ADR-0006's training/serving parity).

Credit-specific, not core: `NON_FEATURE_COLUMNS` excludes `CODE_GENDER` as a fair-lending
decision (ADR-0005's discussion — a protected attribute may be used for slice/fairness
monitoring but never as a model input), which is a Credit Risk call, not a domain-agnostic one.
"""

from __future__ import annotations

import pandas as pd

# Bookkeeping / identifier columns, and slice-only columns (fair-lending exclusion) — never
# passed to a model as a training or serving-time feature.
NON_FEATURE_COLUMNS = {
    "SK_ID_CURR",
    "TARGET",
    "APPLICATION_DATE",
    "SPLIT",
    "IS_MATURE",
    "CODE_GENDER",
}


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS]


def capture_categories(df: pd.DataFrame, columns: list[str]) -> dict[str, list]:
    """Which columns are categorical, and their levels — decided once, from every mature row
    training sees (not just the train split), not re-inferred on every `prepare_features` call.

    Two failure modes this closes, both found by actually serving a request, not by inspection:

    1. Levels: an independent `.astype("category")` per call only sees whichever values are
       present in that call's own rows. Invisible at batch scale (a multi-thousand-row split
       almost always contains the full universe of values); a single-row serving request only
       ever has one value per column, and LightGBM's booster rejects predict-time levels that
       don't match what it was fit on ("train and valid dataset categorical_feature do not
       match").
    2. Column set: an aggregate `*_MEAN`/`*_SUM` column that is entirely NaN for one applicant
       (no history in that relational table — the common case for a new, request-time-only
       applicant) can come back `object`-dtyped from the left join, not `float64`, which a
       dtype-based `select_dtypes(include=["object"])` at serving time would then silently
       misdetect as categorical — changing *how many* columns look categorical, which trips the
       same LightGBM check for a different reason. Deciding the categorical column set once,
       from the real training data (where these columns are reliably numeric, since some rows
       always have real history), closes this regardless of what dtype a single degenerate
       request happens to infer.
    """
    object_columns = df[columns].select_dtypes(include=["object", "str"]).columns
    return {column: sorted(df[column].dropna().unique().tolist()) for column in object_columns}


def prepare_features(
    df: pd.DataFrame, columns: list[str], categories: dict[str, list] | None = None
) -> pd.DataFrame:
    """`categories` (from `capture_categories`) fixes both *which* columns are categorical and
    their levels to exactly what the model was fit on — training and serving always pass it.
    Omitted, categorical columns are inferred from `df` itself by dtype — correct only for a
    one-off, non-model-facing use (see this module's docstring and `capture_categories`).
    """
    X = df[columns].copy()
    if categories is not None:
        for column, levels in categories.items():
            X[column] = pd.Categorical(X[column], categories=levels)
    else:
        for column in X.select_dtypes(include=["object", "str"]).columns:
            X[column] = X[column].astype("category")
    return X
