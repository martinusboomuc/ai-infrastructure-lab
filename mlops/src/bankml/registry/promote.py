"""Registry promotion — only reached if the gate (gate.py) passed.

Uses MLflow's current alias-based registry API (`set_registered_model_alias`), not the
`transition_model_version_stage` stages API, which MLflow has deprecated in favor of aliases.
The "production" alias is this project's equivalent of the roadmap's "Production" stage.
"""

from __future__ import annotations

import mlflow
from mlflow import MlflowClient


def promote_to_production(run_id: str, registered_model_name: str) -> str:
    """Register the model from `run_id` and alias it "production". Returns the version string.

    Only ever called after `gate.evaluate_gate` has passed — a run that fails the gate stays
    logged in MLflow (inspectable, comparable) but is never registered or promoted.
    """
    model_uri = f"runs:/{run_id}/model"
    version = mlflow.register_model(model_uri, registered_model_name)

    client = MlflowClient()
    client.set_registered_model_alias(registered_model_name, "production", version.version)

    return version.version
