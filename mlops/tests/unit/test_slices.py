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

    assert group_a["pr_auc"] > group_b["pr_auc"]
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
    assert only_negative["pr_auc"] is None
    assert only_negative["within_tolerance"] is None
    assert only_negative["n"] == 2


def test_raises_no_error_when_no_slices_configured():
    result = compute_slice_metrics(pd.DataFrame({"x": [1, 2]}), [0, 1], [0.1, 0.9], {"slices": []})
    assert result["slices"] == {}
    assert result["overall_pr_auc"] == pytest.approx(1.0)
