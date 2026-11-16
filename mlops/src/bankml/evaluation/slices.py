"""Slice metrics with configured tolerances (ARCHITECTURE.md's "Slices" section / roadmap item).

Catches a model that performs well in aggregate while degrading on a segment, before promotion
— per a domain's `evaluation.slices` config, not hardcoded to any particular column.
"""

from __future__ import annotations

import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def compute_slice_metrics(
    slice_source_df: pd.DataFrame, y_true: pd.Series, y_score, eval_config: dict
) -> dict:
    """ROC-AUC, PR-AUC and base rate per value of each configured slice column.

    The tolerance applies to the drop in ROC-AUC against overall (ADR-0020). PR-AUC moves with a
    slice's positive rate even when ranking quality is the same, so comparing it across groups
    with different base rates flags the base rate, not the model. PR-AUC and the base rate are
    still reported per slice, so the reader sees both.

    `slice_source_df` supplies the slice columns (e.g. CODE_GENDER) — it is not necessarily the
    same DataFrame the model was trained on, since slice columns like CODE_GENDER are
    deliberately excluded from model inputs (fair-lending — see
    src/bankml/features/credit/pipeline.py) but still needed here for fairness monitoring.
    """
    y_true = pd.Series(y_true).reset_index(drop=True)
    y_score = pd.Series(y_score).reset_index(drop=True)
    overall_roc_auc = float(roc_auc_score(y_true, y_score))
    overall_pr_auc = float(average_precision_score(y_true, y_score))

    results = {
        "overall_roc_auc": overall_roc_auc,
        "overall_pr_auc": overall_pr_auc,
        "overall_positive_rate": float(y_true.mean()),
        "slices": {},
    }

    for slice_config in eval_config.get("slices", []):
        column = slice_config["column"]
        tolerance = slice_config["tolerance"]
        values = slice_source_df[column].reset_index(drop=True)

        slice_results = {}
        for value in values.dropna().unique():
            mask = values == value
            slice_y_true = y_true[mask]
            slice_y_score = y_score[mask]

            if slice_y_true.nunique() < 2:
                # Neither AUC exists with only one class present in the slice — recorded as such
                # rather than silently skipped or given a misleading fallback number.
                slice_results[str(value)] = {
                    "n": int(mask.sum()),
                    "positive_rate": float(slice_y_true.mean()),
                    "roc_auc": None,
                    "pr_auc": None,
                    "within_tolerance": None,
                }
                continue

            slice_roc_auc = float(roc_auc_score(slice_y_true, slice_y_score))
            slice_results[str(value)] = {
                "n": int(mask.sum()),
                "positive_rate": float(slice_y_true.mean()),
                "roc_auc": slice_roc_auc,
                "pr_auc": float(average_precision_score(slice_y_true, slice_y_score)),
                "within_tolerance": (overall_roc_auc - slice_roc_auc) <= tolerance,
            }

        results["slices"][column] = slice_results

    return results
