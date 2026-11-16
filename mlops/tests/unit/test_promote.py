"""Registry versions and promotion (ADR-0019), against a real MLflow registry in SQLite."""

from __future__ import annotations

import mlflow
import pytest
from mlflow import MlflowClient

from bankml.registry.promote import (
    CANDIDATE,
    PREVIOUS_PRODUCTION,
    PRODUCTION,
    decide_promotion,
    register_and_promote,
    set_production,
)

NAME = "credit-champion"


def test_the_first_version_is_promoted():
    assert decide_promotion(0.20, None, 0.005).promote


def test_a_candidate_within_the_tolerance_is_promoted():
    assert decide_promotion(0.238, 0.242, 0.005).promote


def test_a_worse_candidate_is_not_promoted():
    decision = decide_promotion(0.224, 0.242, 0.005)

    assert not decision.promote
    assert "promote by hand" in decision.reason


@pytest.fixture
def registry(tmp_path, monkeypatch):
    # SQLite rather than a ./mlruns directory: MLflow 3 refuses the file store by default.
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("promote-test", artifact_location=(tmp_path / "a").as_uri())
    mlflow.set_experiment("promote-test")
    yield MlflowClient()
    mlflow.set_tracking_uri(None)


class _Constant(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        return [0.5] * len(model_input)


def _logged_run(test_pr_auc: float) -> str:
    with mlflow.start_run() as run:
        mlflow.log_metric("test_pr_auc", test_pr_auc)
        mlflow.pyfunc.log_model(python_model=_Constant(), name="model")
    return run.info.run_id


def _metrics(pr_auc: float) -> dict:
    return {"pr_auc": pr_auc, "roc_auc": 0.76, "recall_at_target_fpr": 0.26, "expected_cost": 1.0}


def _register(run_id: str, pr_auc: float):
    return register_and_promote(
        run_id, NAME, "champion", "scorecard", _metrics(pr_auc), {"run_id": run_id}, 0.005
    )


def test_registering_tags_and_describes_the_version(registry):
    run_id = _logged_run(0.24)

    version, decision = _register(run_id, 0.24)

    mv = registry.get_model_version(NAME, version)
    assert decision.promote
    assert mv.tags["gate"] == "passed"
    assert mv.tags["test_pr_auc"] == "0.2400"
    assert mv.tags["model_type"] == "scorecard"
    assert run_id in mv.description
    assert str(registry.get_model_version_by_alias(NAME, PRODUCTION).version) == version
    assert str(registry.get_model_version_by_alias(NAME, CANDIDATE).version) == version


def test_a_worse_candidate_leaves_production_where_it_is(registry):
    first, _ = _register(_logged_run(0.242), 0.242)

    second, decision = _register(_logged_run(0.224), 0.224)

    assert not decision.promote
    assert str(registry.get_model_version_by_alias(NAME, PRODUCTION).version) == first
    assert str(registry.get_model_version_by_alias(NAME, CANDIDATE).version) == second
    assert registry.get_model_version(NAME, second).tags["compared_with_version"] == first


def test_promotion_keeps_the_previous_production_version(registry):
    first, _ = _register(_logged_run(0.24), 0.24)
    second, _ = _register(_logged_run(0.25), 0.25)

    assert str(registry.get_model_version_by_alias(NAME, PRODUCTION).version) == second
    assert str(registry.get_model_version_by_alias(NAME, PREVIOUS_PRODUCTION).version) == first


def test_a_candidate_can_be_promoted_by_hand(registry):
    first, _ = _register(_logged_run(0.242), 0.242)
    second, _ = _register(_logged_run(0.224), 0.224)

    set_production(registry, NAME, second)

    assert str(registry.get_model_version_by_alias(NAME, PRODUCTION).version) == second
    assert str(registry.get_model_version_by_alias(NAME, PREVIOUS_PRODUCTION).version) == first
