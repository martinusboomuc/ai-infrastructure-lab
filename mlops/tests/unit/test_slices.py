import numpy as np
import pandas as pd
import pytest

from bankml.evaluation.slices import compute_slice_metrics

EVAL_CONFIG = {"slices": [{"column": "GROUP", "tolerance": 0.05}]}


def test_a_degraded_slice_is_flagged_outside_tolerance():
    # Group A: well separated (high PR-AUC). Group B: inversely correlated (low PR-AUC).
    y_true = [0, 0, 1, 1, 0, 0, 1, 1]
    y_score = [0.1, 0.2, 0.8, 0.9, 0.9, 0.8, 0.2, 0.1]
    df = pd.DataFrame({"GROUP": ["A", "A", "A", "A", "B", "B", "B", "B"]})

    result = compute_slice_metrics(df, y_true, y_score, EVAL_CONFIG)

    group_a = result["slices"]["GROUP"]["A"]
    group_b = result["slices"]["GROUP"]["B"]

    assert group_a["roc_auc"] > group_b["roc_auc"]
    assert group_a["within_tolerance"] is True
    assert group_b["within_tolerance"] is False


def test_a_slice_with_only_one_class_reports_none_rather_than_crashing():
    y_true = [0, 0, 1, 1]
    y_score = [0.1, 0.9, 0.2, 0.8]
    df = pd.DataFrame({"GROUP": ["A", "A", "ONLY_NEGATIVE", "ONLY_NEGATIVE"]})
    # "ONLY_NEGATIVE" rows both have y_true=0 in this fixture's pairing below.
    y_true = [0, 1, 0, 0]

    result = compute_slice_metrics(df, y_true, y_score, EVAL_CONFIG)

    only_negative = result["slices"]["GROUP"]["ONLY_NEGATIVE"]
    assert only_negative["roc_auc"] is None
    assert only_negative["pr_auc"] is None
    assert only_negative["within_tolerance"] is None
    assert only_negative["n"] == 2


def test_raises_no_error_when_no_slices_configured():
    result = compute_slice_metrics(pd.DataFrame({"x": [1, 2]}), [0, 1], [0.1, 0.9], {"slices": []})
    assert result["slices"] == {}
    assert result["overall_pr_auc"] == pytest.approx(1.0)


def test_a_lower_base_rate_alone_does_not_fail_the_slice():
    # ADR-0020. Both groups get scores from the same distributions, so ranking quality is the
    # same; group B has a third of A's positive rate. PR-AUC falls with the base rate, ROC-AUC
    # does not, and only ROC-AUC decides the tolerance.
    rng = np.random.default_rng(0)
    n_a_pos, n_b_pos, n_neg = 1200, 400, 8000
    y_true = [1] * n_a_pos + [0] * n_neg + [1] * n_b_pos + [0] * n_neg
    y_score = np.concatenate(
        [
            rng.normal(1.0, 1.0, n_a_pos),
            rng.normal(0.0, 1.0, n_neg),
            rng.normal(1.0, 1.0, n_b_pos),
            rng.normal(0.0, 1.0, n_neg),
        ]
    )
    df = pd.DataFrame({"GROUP": ["A"] * (n_a_pos + n_neg) + ["B"] * (n_b_pos + n_neg)})

    result = compute_slice_metrics(df, y_true, y_score, EVAL_CONFIG)
    group_b = result["slices"]["GROUP"]["B"]

    assert result["overall_pr_auc"] - group_b["pr_auc"] > 0.05
    assert group_b["within_tolerance"] is True
    assert group_b["positive_rate"] < result["overall_positive_rate"]
