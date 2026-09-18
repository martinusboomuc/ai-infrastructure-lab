import numpy as np
import pandas as pd

from bankml.training.scorecard import fit_scorecard


def _synthetic_data(n=200, seed=0):
    rng = np.random.default_rng(seed)
    x1 = rng.normal(size=n)
    y = (x1 + rng.normal(scale=0.3, size=n) > 0).astype(int)
    return pd.DataFrame({"x1": x1}), pd.Series(y)


def test_fit_scorecard_returns_working_predict_proba():
    X_train, y_train = _synthetic_data()
    model = fit_scorecard(X_train, y_train)

    proba = model.predict_proba(X_train)

    assert proba.shape == (len(X_train), 2)
    assert np.allclose(proba.sum(axis=1), 1.0)


def test_bins_are_not_refit_when_scoring_a_distribution_shifted_dataset():
    """ADR-0005: bins are fit on training data only. Scoring new (even wildly
    distribution-shifted) data must never change the already-fitted bins."""
    X_train, y_train = _synthetic_data(seed=0)
    model = fit_scorecard(X_train, y_train)

    before = model.binning_process.transform(X_train)

    X_shifted = pd.DataFrame({"x1": np.full(50, 1000.0)})
    model.predict_proba(X_shifted)

    after = model.binning_process.transform(X_train)
    assert np.allclose(before, after)
