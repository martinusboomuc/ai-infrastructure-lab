import numpy as np
import pandas as pd

from bankml.training.logistic import fit_logistic_regression


def test_fit_logistic_regression_returns_working_predict_proba():
    rng = np.random.default_rng(0)
    n = 200
    x1 = rng.normal(size=n)
    y = (x1 > 0).astype(int)
    X = pd.DataFrame({"x1": x1})

    model = fit_logistic_regression(X, pd.Series(y))
    proba = model.predict_proba(X)

    assert proba.shape == (n, 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_handles_categorical_columns_and_missing_values():
    rng = np.random.default_rng(1)
    n = 100
    x1 = rng.normal(size=n)
    x1[::10] = np.nan  # every 10th value missing — LogisticRegression can't handle NaN natively
    y = (np.nan_to_num(x1) > 0).astype(int)
    cat = pd.Series(rng.choice(["a", "b", "c"], size=n)).astype("category")
    X = pd.DataFrame({"x1": x1, "cat": cat})

    model = fit_logistic_regression(X, pd.Series(y))
    proba = model.predict_proba(X)

    assert proba.shape == (n, 2)


def test_handles_a_category_unseen_during_fit():
    """OneHotEncoder(handle_unknown="ignore") — a serving-time request with a category level
    training never saw must not raise, unlike the default OneHotEncoder behaviour."""
    X_train = pd.DataFrame(
        {"x1": [0.1, 0.2, 0.3, 0.4], "cat": pd.Categorical(["a", "b", "a", "b"])}
    )
    y_train = pd.Series([0, 1, 0, 1])
    model = fit_logistic_regression(X_train, y_train)

    X_new = pd.DataFrame({"x1": [0.5], "cat": pd.Categorical(["unseen"])})
    proba = model.predict_proba(X_new)

    assert proba.shape == (1, 2)
