"""Generic MLflow pyfunc wrapper so every role/model type is logged and loaded uniformly.

Fixes a real gap: logging a `ScorecardModel` via
`mlflow.sklearn.log_model(model.logistic_regression, ...)` (the previous approach) drops the WoE
`binning_process` — `ScorecardModel.predict_proba` needs both steps together (see
`training/scorecard.py`). Wrapping the whole model object in a
`PythonModel` keeps them together, and makes serving load every role's production model the same
way (`mlflow.pyfunc.load_model(...).predict(X)`) regardless of whether it is a scorecard or a
LightGBM model — necessary since which model type is champion is a per-domain config choice
(ADR-0005: scorecard for Credit, LightGBM for Fraud), not something serving should branch on.
"""

from __future__ import annotations

import mlflow.pyfunc
import pandas as pd


class ProbabilityModel(mlflow.pyfunc.PythonModel):
    """Wraps any model exposing `predict_proba(X)` (ScorecardModel, LGBMClassifier, ...) and
    exposes the positive-class probability through pyfunc's uniform `predict(X)` interface.
    """

    def __init__(self, model):
        self.model = model

    def predict(self, context, model_input: pd.DataFrame, params=None):
        return self.model.predict_proba(model_input)[:, 1]
