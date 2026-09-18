import numpy as np
import pandas as pd

from bankml.training.gbm import fit_lightgbm


def test_fit_lightgbm_returns_working_predict_proba():
    rng = np.random.default_rng(0)
    n = 200
    x1 = rng.normal(size=n)
    y = (x1 > 0).astype(int)
    X = pd.DataFrame({"x1": x1})

    model = fit_lightgbm(X, pd.Series(y))
    proba = model.predict_proba(X)

    assert proba.shape == (n, 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_handles_categorical_columns_and_missing_values_natively():
    rng = np.random.default_rng(1)
    n = 100
    x1 = rng.normal(size=n)
    x1[::10] = np.nan  # every 10th value missing
    y = (x1 > 0).astype(int)
    cat = pd.Series(rng.choice(["a", "b", "c"], size=n)).astype("category")
    X = pd.DataFrame({"x1": x1, "cat": cat})

    model = fit_lightgbm(X, pd.Series(y))
    proba = model.predict_proba(X)

    assert proba.shape == (n, 2)
