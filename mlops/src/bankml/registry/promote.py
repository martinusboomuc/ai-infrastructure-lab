"""Registry versions and promotion (ADR-0019, refining ADR-0005's gate).

A champion that passes the gate is always registered, so every model that could serve is a
version with its evidence attached: test metrics, data version, code version and gate result as
tags, and a description saying what it is. The `candidate` alias points at the newest of them.

Whether it also becomes `production` depends on the model already there. A candidate that is
not worse on test PR-AUC (within `evaluation.gate.max_pr_auc_regression`) is promoted. One that
is worse stays `candidate`, and promoting it is a deliberate human decision, run with
`python -m bankml.registry.promote --domain <domain> --version <n>`. Passing an absolute floor is
not enough to replace a model that is doing better.

Uses MLflow's alias API, not the deprecated stages API. When `production` moves, the version it
leaves is kept as `previous-production`, so a rollback is one alias change.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

PRODUCTION = "production"
CANDIDATE = "candidate"
PREVIOUS_PRODUCTION = "previous-production"

# The metrics a version carries as tags, so the registry page compares versions without opening
# each run.
VERSION_METRIC_TAGS = ("pr_auc", "roc_auc", "recall_at_target_fpr", "expected_cost")


@dataclass
class PromotionDecision:
    promote: bool
    reason: str


def decide_promotion(
    candidate_pr_auc: float, production_pr_auc: float | None, max_regression: float
) -> PromotionDecision:
    """Pure decision, so the rule is tested without a registry."""
    if production_pr_auc is None:
        return PromotionDecision(True, "no production version exists")
    floor = production_pr_auc - max_regression
    if candidate_pr_auc >= floor:
        return PromotionDecision(
            True,
            f"test PR-AUC {candidate_pr_auc:.4f} is within {max_regression} of production's "
            f"{production_pr_auc:.4f}",
        )
    return PromotionDecision(
        False,
        f"test PR-AUC {candidate_pr_auc:.4f} is more than {max_regression} below production's "
        f"{production_pr_auc:.4f}; promote by hand if the trade-off is wanted",
    )


def version_description(role: str, model_type: str, test_metrics: dict, run_id: str) -> str:
    return (
        f"{role.capitalize()} {model_type}. Test PR-AUC {test_metrics['pr_auc']:.4f}, "
        f"ROC-AUC {test_metrics['roc_auc']:.4f}, recall at target FPR "
        f"{test_metrics['recall_at_target_fpr']:.4f}. Figures and model card in run {run_id}."
    )


def _production_test_pr_auc(client: MlflowClient, name: str) -> tuple[str | None, float | None]:
    try:
        current = client.get_model_version_by_alias(name, PRODUCTION)
    except MlflowException:
        return None, None
    metrics = client.get_run(current.run_id).data.metrics
    return str(current.version), metrics.get("test_pr_auc")


def set_production(client: MlflowClient, name: str, version: str) -> None:
    """Point `production` at `version`, keeping the version it leaves as `previous-production`."""
    try:
        current = client.get_model_version_by_alias(name, PRODUCTION)
    except MlflowException:
        current = None
    if current is not None and str(current.version) != str(version):
        client.set_registered_model_alias(name, PREVIOUS_PRODUCTION, str(current.version))
    client.set_registered_model_alias(name, PRODUCTION, str(version))


def register_and_promote(
    run_id: str,
    registered_model_name: str,
    role: str,
    model_type: str,
    test_metrics: dict,
    tags: dict[str, str],
    max_pr_auc_regression: float,
) -> tuple[str, PromotionDecision]:
    """Register the gated model from `run_id`, alias it `candidate`, and promote it when it is
    not worse than production. Returns the version and the decision.
    """
    client = MlflowClient()
    production_version, production_pr_auc = _production_test_pr_auc(client, registered_model_name)

    # Versions are compared as str: a SQLite store returns them as int, the REST API as str.
    version = mlflow.register_model(
        f"runs:/{run_id}/model",
        registered_model_name,
        tags={
            **tags,
            "role": role,
            "model_type": model_type,
            "gate": "passed",
            **{f"test_{key}": f"{test_metrics[key]:.4f}" for key in VERSION_METRIC_TAGS},
        },
    ).version
    version = str(version)
    client.update_model_version(
        registered_model_name,
        version,
        description=version_description(role, model_type, test_metrics, run_id),
    )
    client.set_registered_model_alias(registered_model_name, CANDIDATE, version)

    decision = decide_promotion(test_metrics["pr_auc"], production_pr_auc, max_pr_auc_regression)
    client.set_model_version_tag(registered_model_name, version, "promotion", decision.reason)
    if production_version is not None:
        client.set_model_version_tag(
            registered_model_name, version, "compared_with_version", production_version
        )
    if decision.promote:
        set_production(client, registered_model_name, version)
    return version, decision


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote a registered version to production.")
    parser.add_argument("--domain", default="credit")
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    name = f"{args.domain}-champion"
    client = MlflowClient()
    client.get_model_version(name, args.version)  # Fails clearly if the version does not exist.
    set_production(client, name, args.version)
    client.set_model_version_tag(name, args.version, "promotion", "promoted by hand")
    print(f"{name} v{args.version} is now production")


if __name__ == "__main__":
    main()
