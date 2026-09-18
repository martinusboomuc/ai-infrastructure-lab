"""Cost-sensitive evaluation metrics (ARCHITECTURE.md's "Evaluation" section).

ROC-AUC is recorded for comparability but never used as a gate on its own — this module reports
it alongside everything else, but nothing downstream should promote a model on it in isolation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve


def _recall_at_fpr(y_true: pd.Series, y_score: pd.Series, target_fpr: float) -> float:
    fpr, tpr, _ = roc_curve(y_true, y_score)
    eligible = fpr <= target_fpr
    idx = np.where(eligible)[0].max() if eligible.any() else 0
    return float(tpr[idx])


def compute_metrics(y_true: pd.Series, y_score: np.ndarray, eval_config: dict) -> dict:
    """PR-AUC, recall at a fixed FPR, alert volume against budget, and expected cost — the
    numbers ARCHITECTURE.md's evaluation section actually asks for, not accuracy or bare AUC.
    """
    y_true = pd.Series(y_true).reset_index(drop=True)
    y_score = pd.Series(y_score).reset_index(drop=True)

    pr_auc = average_precision_score(y_true, y_score)
    roc_auc = roc_auc_score(y_true, y_score)
    recall_at_fpr = _recall_at_fpr(y_true, y_score, eval_config["target_fpr"])

    alert_threshold = y_score.quantile(1 - eval_config["alert_budget_fraction"])
    flagged = y_score >= alert_threshold

    is_positive = y_true == 1
    true_positive = int((is_positive & flagged).sum())
    false_negative = int((is_positive & ~flagged).sum())
    false_positive = int((~is_positive & flagged).sum())
    true_negative = int((~is_positive & ~flagged).sum())

    cost_of_miss = eval_config["cost_of_miss"]
    cost_of_review = eval_config["cost_of_review"]
    expected_cost = false_negative * cost_of_miss + false_positive * cost_of_review

    return {
        "pr_auc": float(pr_auc),
        "roc_auc": float(roc_auc),
        "recall_at_target_fpr": recall_at_fpr,
        "alert_volume_fraction": float(flagged.mean()),
        "alert_threshold": float(alert_threshold),
        "expected_cost": float(expected_cost),
        "true_positive": true_positive,
        "false_negative": false_negative,
        "false_positive": false_positive,
        "true_negative": true_negative,
    }
