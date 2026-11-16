"""Training run logging (ADR-0019), against a real MLflow tracking store in SQLite."""

from __future__ import annotations

import mlflow
import numpy as np
import pandas as pd
import pytest
from mlflow import MlflowClient
from sklearn.linear_model import LogisticRegression

from bankml.evaluation.metrics import compute_metrics
from bankml.evaluation.plots import evaluation_figures
from bankml.tracking import experiment_name, log_run

EVAL_CONFIG = {
    "target_fpr": 0.05,
    "alert_budget_fraction": 0.10,
    "cost_of_miss": 10,
    "cost_of_review": 1,
}


@pytest.fixture
def scored_split():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 2))
    y = pd.Series((x[:, 0] + rng.normal(size=400) > 1.2).astype(int))
    model = LogisticRegression().fit(x, y)
    score = model.predict_proba(x)[:, 1]
    return model, x, y, score


def test_experiment_names_follow_one_scheme():
    assert experiment_name("credit", "training") == "bankml-credit-training"
    assert experiment_name("fraud", "monitoring") == "bankml-fraud-monitoring"


def test_every_figure_is_produced_for_a_split(scored_split):
    _, _, y, score = scored_split
    metrics = compute_metrics(y, score, EVAL_CONFIG)

    figures = evaluation_figures(y, score, metrics, EVAL_CONFIG)

    assert set(figures) == {
        "roc_curve.png",
        "precision_recall_curve.png",
        "calibration.png",
        "confusion_matrix.png",
        "score_distribution.png",
    }


def test_a_run_carries_its_provenance_figures_and_inputs(tmp_path, monkeypatch, scored_split):
    uri = f"sqlite:///{tmp_path / 'mlflow.db'}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("MLFLOW_DEFAULT_ARTIFACT_ROOT", (tmp_path / "a").as_uri())
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("bankml-credit-training", artifact_location=(tmp_path / "a").as_uri())
    model, x, y, score = scored_split
    metrics = {split: compute_metrics(y, score, EVAL_CONFIG) for split in ("validation", "test")}
    frame = pd.DataFrame(x, columns=["a", "b"]).assign(TARGET=y)

    try:
        run_id = log_run(
            "credit",
            "champion",
            "logistic_regression",
            model,
            metrics,
            {},
            [{"reason": "a"}],
            "# card",
            tmp_path,
            EVAL_CONFIG,
            scores={"validation": (y, score), "test": (y, score)},
            datasets={"test": frame},
        )

        client = MlflowClient()
        run = client.get_run(run_id)
        experiment = client.get_experiment(run.info.experiment_id)
        artifacts = {f.path for f in client.list_artifacts(run_id, "figures/test")}
    finally:
        mlflow.set_tracking_uri(None)

    assert experiment.name == "bankml-credit-training"
    assert run.info.run_name == "credit-champion-logistic_regression"
    assert run.data.tags["model_type"] == "logistic_regression"
    assert run.data.tags["git_dirty"] in {"true", "false", "unknown"}
    assert "Test: PR-AUC" in run.data.tags["mlflow.note.content"]
    assert run.data.params["eval_target_fpr"] == "0.05"
    assert run.data.metrics["test_rows"] == 400
    assert "figures/test/roc_curve.png" in artifacts
    assert [i.dataset.name for i in run.inputs.dataset_inputs] == ["credit-features-test"]
