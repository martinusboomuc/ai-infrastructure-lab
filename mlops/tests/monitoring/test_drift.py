"""Drift detection tests (Phase 5). Synthetic fixtures only (ADR-0007's pattern) — these exercise
`compute_drift` directly, not `run_drift_job`, so they need no real data, MLflow server, or
registered model. ROADMAP's Phase 5 exit criterion in one sentence: injecting synthetic drift
into the input stream raises an alert.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bankml.monitoring.drift import compute_drift


@pytest.fixture
def stable_population():
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 1_000),
            "education": rng.choice(["Higher", "Secondary"], 1_000, p=[0.4, 0.6]),
            "children": rng.integers(0, 4, 1_000),
        }
    )


def test_a_shifted_numeric_feature_is_flagged_drifted(stable_population):
    rng = np.random.default_rng(1)
    drifted = pd.DataFrame(
        {
            "income": rng.normal(400_000, 20_000, 200),  # far outside the reference distribution
            "education": rng.choice(["Higher", "Secondary"], 200, p=[0.4, 0.6]),  # unchanged
            "children": rng.integers(0, 4, 200),  # unchanged
        }
    )

    result = compute_drift(stable_population, drifted)

    assert result["features"]["income"]["drifted"] is True
    assert result["features"]["education"]["drifted"] is False
    assert result["features"]["children"]["drifted"] is False
    # only 1 of 3 columns drifted, below Evidently's own 0.5 drift_share default for a
    # dataset-wide alert — a single unstable feature shouldn't read as "everything moved"
    assert result["dataset_drift"] is False


def test_a_shifted_categorical_feature_is_flagged_drifted(stable_population):
    rng = np.random.default_rng(2)
    drifted = pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 200),  # unchanged
            "education": rng.choice(["Higher", "Secondary"], 200, p=[0.95, 0.05]),  # flipped
        }
    )

    result = compute_drift(stable_population, drifted)

    assert result["features"]["education"]["drifted"] is True
    assert result["features"]["income"]["drifted"] is False


def test_no_drift_when_current_matches_the_reference_distribution(stable_population):
    rng = np.random.default_rng(3)
    same_distribution = pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 200),
            "education": rng.choice(["Higher", "Secondary"], 200, p=[0.4, 0.6]),
        }
    )

    result = compute_drift(stable_population, same_distribution)

    assert result["dataset_drift"] is False
    assert all(not f["drifted"] for f in result["features"].values())


def test_a_column_entirely_null_in_current_is_skipped_not_a_crash(stable_population):
    rng = np.random.default_rng(4)
    current = pd.DataFrame(
        {
            "income": rng.normal(150_000, 20_000, 50),
            "education": [None] * 50,
        }
    )

    result = compute_drift(stable_population, current)

    assert "education" in result["skipped_columns"]
    assert "education" not in result["features"]
    assert "income" in result["features"]


def test_boolean_columns_do_not_crash_the_numeric_stats_path():
    reference = pd.DataFrame({"flag": [True, False, True, False, True] * 20})
    current = pd.DataFrame({"flag": [True] * 20})

    result = compute_drift(reference, current)

    assert "flag" in result["features"]


def test_raises_when_reference_and_current_share_no_comparable_columns():
    reference = pd.DataFrame({"a": [1, 2, 3]})
    current = pd.DataFrame({"b": [1, 2, 3]})

    with pytest.raises(ValueError, match="no columns"):
        compute_drift(reference, current)
