"""LightGBM challenger (ADR-0005) for Credit Risk. Generic — see scorecard.py's module docstring:
which domain calls this the challenger (or champion, for Fraud) is a config decision, not
anything hardcoded here.
"""

from __future__ import annotations

import lightgbm as lgb
import pandas as pd


def fit_lightgbm(X_train: pd.DataFrame, y_train: pd.Series) -> lgb.LGBMClassifier:
    """Fit a LightGBM classifier. `X_train`'s categorical columns must already be pandas
    `category` dtype — LightGBM's sklearn API detects and handles those natively; it also
    handles NaN natively, so no imputation is needed here.
    """
    model = lgb.LGBMClassifier(random_state=42, verbose=-1)
    model.fit(X_train, y_train)
    return model
