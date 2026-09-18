import numpy as np
import pytest

from bankml.evaluation.metrics import compute_metrics

EVAL_CONFIG = {
    "cost_of_miss": 10,
    "cost_of_review": 1,
    "target_fpr": 0.5,
    "alert_budget_fraction": 0.5,
}


def test_perfectly_separated_scores_give_maximal_pr_and_roc_auc():
    y_true = [0, 0, 0, 0, 1, 1, 1, 1]
    y_score = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]

    result = compute_metrics(y_true, np.array(y_score), EVAL_CONFIG)

    assert result["pr_auc"] == pytest.approx(1.0)
    assert result["roc_auc"] == pytest.approx(1.0)


def test_alert_volume_matches_the_configured_budget_fraction():
    y_true = [0] * 8 + [1] * 2
    y_score = np.linspace(0.0, 1.0, 10)

    result = compute_metrics(y_true, y_score, {**EVAL_CONFIG, "alert_budget_fraction": 0.2})

    # Top 20% of 10 scores = top 2 rows flagged.
    assert result["alert_volume_fraction"] == pytest.approx(0.2)


def test_expected_cost_matches_hand_computed_confusion_matrix():
    # 4 rows, alert budget flags the top 2 by score.
    y_true = [1, 0, 0, 1]  # indices 0 and 3
    y_score = np.array([0.9, 0.8, 0.2, 0.1])  # top 2 by score: indices 0, 1

    result = compute_metrics(y_true, y_score, {**EVAL_CONFIG, "alert_budget_fraction": 0.5})

    # Flagged: index 0 (TARGET=1, correctly caught -> TP) and index 1 (TARGET=0 -> FP).
    # Not flagged: index 2 (TARGET=0 -> TN) and index 3 (TARGET=1, missed -> FN).
    assert result["true_positive"] == 1
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1
    assert result["true_negative"] == 1
    assert result["expected_cost"] == pytest.approx(1 * 10 + 1 * 1)
