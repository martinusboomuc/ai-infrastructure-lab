"""Model-input column selection and dtype coercion for Fraud Detection — shared by training
(`bankml.training.pipeline`) so the exact same columns, in the exact same dtypes, reach a model.
Same interface contract as `bankml.features.credit.prepare` (ADR-0006's training/serving parity;
serving isn't in scope for Phase 6, but the contract training resolves dynamically against is
identical either way — see `bankml.training.pipeline._load_prepare_module`).

Unlike Credit Risk, there is no fair-lending exclusion here: no protected attribute was ever
added to Fraud's feature set (CLAUDE.md: fraud carries no adverse-action requirement), so
`NON_FEATURE_COLUMNS` is just bookkeeping columns.
"""

from __future__ import annotations

import pandas as pd

NON_FEATURE_COLUMNS = {
    "trans_num",
    "trans_date_trans_time",
    "TARGET",
    "SPLIT",
    "IS_MATURE",
}


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURE_COLUMNS]


def capture_categories(df: pd.DataFrame, columns: list[str]) -> dict[str, list]:
    """Same rationale as bankml.features.credit.prepare.capture_categories: captured once from
    every mature row, not re-inferred per call, so a single category's levels never depend on
    which split (or how few rows) a given `prepare_features` call happens to see.
    """
    object_columns = df[columns].select_dtypes(include=["object", "str"]).columns
    return {column: sorted(df[column].dropna().unique().tolist()) for column in object_columns}


def prepare_features(
    df: pd.DataFrame, columns: list[str], categories: dict[str, list] | None = None
) -> pd.DataFrame:
    X = df[columns].copy()
    if categories is not None:
        for column, levels in categories.items():
            X[column] = pd.Categorical(X[column], categories=levels)
    else:
        for column in X.select_dtypes(include=["object", "str"]).columns:
            X[column] = X[column].astype("category")
    return X
