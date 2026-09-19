import numpy as np
import pandas as pd

from bankml.registry.pyfunc_model import ProbabilityModel


class _FakeModel:
    """Stands in for ScorecardModel/LGBMClassifier — both expose predict_proba(X) returning
    an (n, 2) array of [P(class=0), P(class=1)]."""

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return np.column_stack([1 - X["risk"], X["risk"]])


def test_predict_returns_the_positive_class_probability():
    wrapped = ProbabilityModel(_FakeModel())
    X = pd.DataFrame({"risk": [0.1, 0.9]})

    result = wrapped.predict(context=None, model_input=X)

    np.testing.assert_allclose(result, [0.1, 0.9])
