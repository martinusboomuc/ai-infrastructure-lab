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

import mlflow
import mlflow.pyfunc

from bankml.registry.pyfunc_model import ProbabilityModel


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _dvc_data_version(mlops_root: Path) -> str:
    dvc_lock_path = mlops_root / "dvc.lock"
    if not dvc_lock_path.exists():
        return "unknown"
    return hashlib.sha256(dvc_lock_path.read_bytes()).hexdigest()[:12]


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
    categories: dict[str, list] | None = None,
) -> str:
    """Log one champion/challenger run to MLflow. Returns the MLflow run ID.

    Explicitly sets the experiment by domain name rather than leaving every run to fall into
    MLflow's "Default" experiment (id 0). An experiment's `artifact_location` is fixed at
    creation time and never changes retroactively — the homelab MLflow server's Default
    experiment was created before ADR-0013's proxied-artifact fix landed, so it's permanently
    stuck pointing at a bare filesystem path no remote client can write to
    (`PermissionError: [Errno 13] Permission denied: '/mlflow'`, found running training from
    docker-01). A per-domain experiment, created fresh, always inherits the server's *current*
    default-artifact-root — this is what actually fixes it, not a one-off manually-created
    experiment that the next person (or the next machine) won't know to point at.
    """
    mlflow.set_experiment(domain)
    with mlflow.start_run(run_name=f"{domain}-{role}") as run:
        mlflow.log_param("role", role)
        mlflow.log_param("model_type", model_type)

        for split_name, split_metrics in metrics.items():
            for metric_name, value in split_metrics.items():
                if isinstance(value, (int, float)):
                    mlflow.log_metric(f"{split_name}_{metric_name}", value)

        mlflow.set_tag("git_sha", _git_sha())
        mlflow.set_tag("dvc_data_version", _dvc_data_version(mlops_root))

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

        # Logged uniformly for every model type (see pyfunc_model.py's docstring) — this is what
        # keeps `model.logistic_regression`-only logging from silently dropping the scorecard's
        # WoE binning step, and lets serving load any role's production model the same way.
        mlflow.pyfunc.log_model(python_model=ProbabilityModel(model), name="model")

        return run.info.run_id
