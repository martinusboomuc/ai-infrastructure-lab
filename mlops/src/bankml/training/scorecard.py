"""WoE binning + logistic regression scorecard (ADR-0005's champion for Credit Risk).

Generic, domain-agnostic mechanism — per ADR-0002, which domain calls this the champion is a
config decision (a domain's `modelling.champion`), never hardcoded here.
"""

from __future__ import annotations

import pandas as pd
from optbinning import BinningProcess
from sklearn.linear_model import LogisticRegression


class ScorecardModel:
    """A fitted WoE-binning + logistic-regression scorecard, with a LightGBM-compatible
    `predict_proba` so both model types are interchangeable to the evaluation step."""

    def __init__(self, binning_process: BinningProcess, logistic_regression: LogisticRegression):
        self.binning_process = binning_process
        self.logistic_regression = logistic_regression

    def predict_proba(self, X: pd.DataFrame):
        X_woe = self.binning_process.transform(X)
        return self.logistic_regression.predict_proba(X_woe)


def fit_scorecard(
    X_train: pd.DataFrame, y_train: pd.Series, categorical_variables: list[str] | None = None
) -> ScorecardModel:
    """Fit WoE bins and a logistic regression, using only the rows passed in.

    The caller is responsible for passing training-split rows only (ADR-0005: bins are fit on
    training data only, never on validation/test) — this function has no split awareness of its
    own, by design, so that discipline lives in exactly one place: bankml.training.pipeline.
    """
    binning_process = BinningProcess(
        variable_names=list(X_train.columns),
        categorical_variables=categorical_variables,
    )
    binning_process.fit(X_train, y_train)
    X_woe = binning_process.transform(X_train)

    logistic_regression = LogisticRegression(max_iter=1000)
    logistic_regression.fit(X_woe, y_train)

    return ScorecardModel(binning_process, logistic_regression)
