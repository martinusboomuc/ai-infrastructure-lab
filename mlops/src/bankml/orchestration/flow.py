"""Prefect flow for the Credit Risk end-to-end pipeline (ROADMAP Phase 4: "Prefect introduced
for the end-to-end flow"). Thin orchestration only — wraps the existing feature and training
pipeline entrypoints as tasks; neither entrypoint's own behavior changes. `make` plus GitHub
Actions was sufficient while the pipeline was linear (ARCHITECTURE.md's stack rationale); this
is the first point retries and a visible run history earn their keep.
"""

from __future__ import annotations

from prefect import flow, task

from bankml.features.credit import pipeline as feature_pipeline
from bankml.training import pipeline as training_pipeline


@task(name="build-credit-features", retries=1)
def build_features_task() -> None:
    feature_pipeline.main()


@task(name="train-and-evaluate-credit", retries=0)
def train_and_evaluate_task() -> None:
    # No retry: a training run that fails partway shouldn't silently re-run and double-log to
    # MLflow — a failure here should surface, not be papered over.
    training_pipeline.main(domain="credit")


@flow(name="bankml-credit-pipeline")
def credit_pipeline() -> None:
    """Build features, then train + evaluate + gate + (maybe) promote, as one tracked run."""
    build_features_task()
    train_and_evaluate_task()


if __name__ == "__main__":
    credit_pipeline()
