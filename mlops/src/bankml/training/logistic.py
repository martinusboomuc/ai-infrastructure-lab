"""Plain logistic regression (Phase 6): the model-type dispatch in training/pipeline.py used to
support only "scorecard" (WoE-binned logistic regression) and "lightgbm" — both happened to cover
Credit Risk's two roles, but neither is what CLAUDE.md's modelling table means by Fraud's
challenger, "Logistic regression". This is a third, generic model type, not a domain-specific one
— which domain and role uses it stays entirely a config decision, same as scorecard.py/gbm.py.

Unlike ScorecardModel (whose WoE binning already emits purely-numeric input) and LightGBM (which
consumes pandas `category` columns and NaN natively), plain sklearn LogisticRegression needs
categoricals one-hot encoded and missing values imputed first — done here, wrapped in a Pipeline
so the fitted encoder always travels with the model instead of needing to be re-derived at
predict time.
"""

from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


def fit_logistic_regression(X_train: pd.DataFrame, y_train: pd.Series) -> Pipeline:
    """Fit a one-hot-encoded, median-imputed logistic regression, using only the rows passed in.

    The caller is responsible for passing training-split rows only (same discipline as
    fit_scorecard/fit_lightgbm) — this function has no split awareness of its own.
    """
    categorical_columns = X_train.select_dtypes(include=["category"]).columns.tolist()
    numeric_columns = [c for c in X_train.columns if c not in categorical_columns]

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical_columns,
            ),
            ("numeric", SimpleImputer(strategy="median"), numeric_columns),
        ]
    )
    model = Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("logistic_regression", LogisticRegression(max_iter=1000)),
        ]
    )
    model.fit(X_train, y_train)
    return model
