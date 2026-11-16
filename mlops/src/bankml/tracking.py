"""MLflow run tracking (roadmap item). Domain-agnostic (ADR-0002).

git_sha and dvc_data_version are the application reading its own provenance at runtime — a
normal, expected engineering practice for experiment tracking, not something done on Claude's
behalf. They tag every run with exactly which code and which data revision produced it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import mlflow.data
import mlflow.pyfunc
import pandas as pd
from mlflow import MlflowClient

from bankml.evaluation.plots import evaluation_figures
from bankml.registry.pyfunc_model import ProbabilityModel

# Splits that get evaluation figures. Train is left out: its curves only show how well the model
# fits data it has seen, which the train metrics already say.
FIGURE_SPLITS = ("validation", "test")

# Where a run keeps the population its model was fit on. The drift job compares live traffic
# against exactly this file, read from the production model's own run (ADR-0015), so the
# reference always matches the model being monitored and the job needs no local data copy.
REFERENCE_ARTIFACT_DIR = "reference"
REFERENCE_ARTIFACT_PATH = f"{REFERENCE_ARTIFACT_DIR}/features_train.parquet"


def log_reference(reference: pd.DataFrame, run_id: str | None = None) -> None:
    """Log the training population as a Parquet artifact: to the active run, or to `run_id`
    when given, which is how a model trained before this artifact existed gets one afterwards.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / Path(REFERENCE_ARTIFACT_PATH).name
        reference.to_parquet(path, index=False)
        if run_id is None:
            mlflow.log_artifact(str(path), artifact_path=REFERENCE_ARTIFACT_DIR)
        else:
            MlflowClient().log_artifact(run_id, str(path), artifact_path=REFERENCE_ARTIFACT_DIR)


def experiment_name(domain: str, purpose: str) -> str:
    """`bankml-<domain>-<purpose>`, the one naming scheme for every experiment (ADR-0019).
    `purpose` is `training` or `monitoring`.
    """
    return f"bankml-{domain}-{purpose}"


def git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def git_dirty() -> str:
    """ "true" when the working tree has uncommitted changes, so a run's git_sha is known not to
    describe exactly the code that produced it.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        )
        return "true" if result.stdout.strip() else "false"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def dvc_data_version(mlops_root: Path) -> str:
    dvc_lock_path = mlops_root / "dvc.lock"
    if not dvc_lock_path.exists():
        return "unknown"
    return hashlib.sha256(dvc_lock_path.read_bytes()).hexdigest()[:12]


def run_description(domain: str, role: str, model_type: str, metrics: dict) -> str:
    """The text shown at the top of the run page: what was trained and how it did on test."""
    test = metrics.get("test", {})
    lines = [f"{domain} {role}, {model_type}."]
    if test:
        lines.append(
            f"Test: PR-AUC {test['pr_auc']:.4f}, ROC-AUC {test['roc_auc']:.4f}, "
            f"recall at target FPR {test['recall_at_target_fpr']:.4f}, "
            f"expected cost {test['expected_cost']:.0f}."
        )
    lines.append("Figures for validation and test are under figures/; the card is model_card.md.")
    return " ".join(lines)


def log_run(
    domain: str,
    role: str,
    model_type: str,
    model,
    metrics: dict,
    slice_metrics: dict,
    reason_codes: list[dict],
    model_card: str,
    mlops_root: Path,
    eval_config: dict,
    categories: dict[str, list] | None = None,
    reference: pd.DataFrame | None = None,
    scores: dict[str, tuple[pd.Series, object]] | None = None,
    datasets: dict[str, pd.DataFrame] | None = None,
    features_path: Path | None = None,
) -> str:
    """Log one champion/challenger run to MLflow. Returns the MLflow run ID.

    Runs go to `bankml-<domain>-training` (ADR-0019), never to MLflow's "Default" experiment
    (id 0): that one was created before ADR-0013's proxied-artifact fix and points at a bare
    filesystem path no remote client can write to (`PermissionError: [Errno 13] Permission
    denied: '/mlflow'`). An experiment created by name inherits the server's current artifact
    root.

    `scores` maps a split name to `(y_true, y_score)` and drives the evaluation figures.
    `datasets` maps a split name to the rows it was evaluated on, logged as run inputs with the
    DVC data version as their digest, so the run records exactly which data it saw.
    """
    dvc_version = dvc_data_version(mlops_root)
    mlflow.set_experiment(experiment_name(domain, "training"))
    with mlflow.start_run(run_name=f"{domain}-{role}-{model_type}") as run:
        mlflow.set_tags(
            {
                "domain": domain,
                "role": role,
                "model_type": model_type,
                "git_sha": git_sha(),
                "git_dirty": git_dirty(),
                "dvc_data_version": dvc_version,
                "mlflow.note.content": run_description(domain, role, model_type, metrics),
            }
        )
        mlflow.log_params(
            {
                "role": role,
                "model_type": model_type,
                **{
                    f"eval_{key}": value
                    for key, value in eval_config.items()
                    if isinstance(value, (int, float, str))
                },
            }
        )

        for split_name, split_metrics in metrics.items():
            for metric_name, value in split_metrics.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(f"{split_name}_{metric_name}", value)

        for split_name, split_df in (datasets or {}).items():
            dataset = mlflow.data.from_pandas(
                split_df,
                source=str(features_path) if features_path else None,
                name=f"{domain}-features-{split_name}",
                digest=dvc_version,
            )
            mlflow.log_input(dataset, context=split_name)
            mlflow.log_metric(f"{split_name}_rows", len(split_df))
            if "TARGET" in split_df:
                mlflow.log_metric(f"{split_name}_positive_rate", float(split_df["TARGET"].mean()))

        for split_name in FIGURE_SPLITS:
            if not scores or split_name not in scores:
                continue
            y_true, y_score = scores[split_name]
            figures = evaluation_figures(y_true, y_score, metrics[split_name], eval_config)
            for file_name, figure in figures.items():
                mlflow.log_figure(figure, f"figures/{split_name}/{file_name}")
                plt.close(figure)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            slice_path = tmp_path / "slice_metrics.json"
            slice_path.write_text(json.dumps(slice_metrics, indent=2, default=str))
            mlflow.log_artifact(str(slice_path))

            reason_codes_path = tmp_path / "reason_codes_sample.json"
            reason_codes_path.write_text(json.dumps(reason_codes, indent=2))
            mlflow.log_artifact(str(reason_codes_path))

            model_card_path = tmp_path / "model_card.md"
            model_card_path.write_text(model_card)
            mlflow.log_artifact(str(model_card_path))

            if categories is not None:
                # Serving loads this back (bankml.serving.app) so prepare_features encodes
                # categoricals with exactly the levels this run was fit on — see
                # capture_categories's docstring for why an inferred-at-call-time category
                # dtype breaks for a single-row serving request.
                categories_path = tmp_path / "categorical_levels.json"
                categories_path.write_text(json.dumps(categories, indent=2))
                mlflow.log_artifact(str(categories_path))

        if reference is not None:
            log_reference(reference)

        # Logged uniformly for every model type (see pyfunc_model.py's docstring) — this is what
        # keeps `model.logistic_regression`-only logging from silently dropping the scorecard's
        # WoE binning step, and lets serving load any role's production model the same way.
        # No signature: pyfunc would then enforce it on every predict call, and the categorical
        # dtypes serving builds per request do not round-trip through MLflow's schema types.
        mlflow.pyfunc.log_model(python_model=ProbabilityModel(model), name="model")

        return run.info.run_id
