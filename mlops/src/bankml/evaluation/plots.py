"""Evaluation figures logged with every training run (ADR-0019).

The metrics in `metrics.py` say how good a model is in a handful of numbers. These figures show
where those numbers come from: how the score separates the classes, how well a predicted
probability matches the observed default rate, and what the alert threshold actually catches.
Each function returns a matplotlib Figure and never shows or saves it; the caller logs it.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # Training runs headless, on docker-01 or in CI.

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)


def roc_figure(y_true: pd.Series, y_score: np.ndarray, target_fpr: float) -> Figure:
    fpr, tpr, _ = roc_curve(y_true, y_score)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(fpr, tpr, label=f"ROC-AUC {roc_auc_score(y_true, y_score):.3f}")
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey", label="Random")
    ax.axvline(target_fpr, linestyle=":", color="black", label=f"Target FPR {target_fpr:g}")
    ax.set(xlabel="False positive rate", ylabel="True positive rate", title="ROC curve")
    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig


def precision_recall_figure(y_true: pd.Series, y_score: np.ndarray) -> Figure:
    precision, recall, _ = precision_recall_curve(y_true, y_score)
    base_rate = float(np.mean(y_true))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(recall, precision, label=f"PR-AUC {average_precision_score(y_true, y_score):.3f}")
    ax.axhline(base_rate, linestyle="--", color="grey", label=f"Base rate {base_rate:.3f}")
    ax.set(xlabel="Recall", ylabel="Precision", title="Precision-recall curve")
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def calibration_figure(y_true: pd.Series, y_score: np.ndarray, n_bins: int = 10) -> Figure:
    """Observed default rate per score decile against the mean predicted probability.

    Quantile bins, because scores for a rare event pile up near zero and uniform bins would
    leave most of them empty.
    """
    observed, predicted = calibration_curve(y_true, y_score, n_bins=n_bins, strategy="quantile")
    upper = max(float(observed.max()), float(predicted.max()))
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot(predicted, observed, marker="o", label="Model")
    ax.plot([0, upper], [0, upper], linestyle="--", color="grey", label="Perfectly calibrated")
    ax.set(
        xlabel="Mean predicted probability",
        ylabel="Observed default rate",
        title="Calibration (score deciles)",
    )
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig


def confusion_figure(metrics: dict) -> Figure:
    """The counts at the alert threshold that `compute_metrics` already chose, so the figure
    and the logged metrics describe exactly the same decision.
    """
    counts = np.array(
        [
            [metrics["true_negative"], metrics["false_positive"]],
            [metrics["false_negative"], metrics["true_positive"]],
        ]
    )
    fig, ax = plt.subplots(figsize=(5, 4.5))
    ax.imshow(counts, cmap="Blues")
    for (row, col), value in np.ndenumerate(counts):
        share = value / counts.sum()
        colour = "white" if value > counts.max() / 2 else "black"
        ax.text(col, row, f"{value:,}\n{share:.1%}", ha="center", va="center", color=colour)
    ax.set_xticks([0, 1], labels=["Not flagged", "Flagged"])
    ax.set_yticks([0, 1], labels=["Repaid", "Defaulted"])
    ax.set_title(f"At the alert threshold ({metrics['alert_threshold']:.3f})")
    fig.tight_layout()
    return fig


def score_distribution_figure(y_true: pd.Series, y_score: np.ndarray, threshold: float) -> Figure:
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    bins = np.linspace(0, float(y_score.max()), 50)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(y_score[y_true == 0], bins=bins, alpha=0.6, density=True, label="Repaid")
    ax.hist(y_score[y_true == 1], bins=bins, alpha=0.6, density=True, label="Defaulted")
    ax.axvline(threshold, linestyle=":", color="black", label="Alert threshold")
    ax.set(xlabel="Score", ylabel="Density", title="Score distribution by outcome")
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig


def evaluation_figures(
    y_true: pd.Series, y_score: np.ndarray, metrics: dict, eval_config: dict
) -> dict[str, Figure]:
    """Every figure for one split, keyed by the file name it is logged under."""
    return {
        "roc_curve.png": roc_figure(y_true, y_score, eval_config["target_fpr"]),
        "precision_recall_curve.png": precision_recall_figure(y_true, y_score),
        "calibration.png": calibration_figure(y_true, y_score),
        "confusion_matrix.png": confusion_figure(metrics),
        "score_distribution.png": score_distribution_figure(
            y_true, y_score, metrics["alert_threshold"]
        ),
    }
