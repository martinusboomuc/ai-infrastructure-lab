"""BankML's models as the bank sees them: what is registered, what serves, how each version was
promoted, and what production monitoring says about it.

Read live from the same sources the rest of the lab uses, never copied: the MLflow registry on
docker-01 for versions, aliases and their evidence tags (mlops ADR-0019, ADR-0024), and Prometheus
for the gauges the monitoring jobs push (ADR-0021, ADR-0022). Nothing here writes to either.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import httpx

from app.links import MLFLOW_URL
from app.prometheus import PROMETHEUS_URL

# The registry's API over the LAN, reachable from the cluster. MLFLOW_URL is the browser's link.
MLFLOW_API_URL = os.environ.get("MLFLOW_API_URL", "http://192.168.1.115:5000")

# What each model decides, in the bank's terms. The registry names are `<domain>-champion`.
DOMAINS = {
    "credit": (
        "Credit Risk",
        (
            "Scores a loan application for the chance the applicant defaults. A flag sends the "
            "application to manual review."
        ),
    ),
    "fraud": (
        "Fraud Detection",
        (
            "Scores a card transaction for the chance it is fraud, from the card's last 30 days. "
            "A flag sends it to the fraud review queue."
        ),
    ),
}
_METRICS = ("pr_auc", "roc_auc", "recall_at_target_fpr", "expected_cost")
_PERFORMANCE = ("measured", "n_labeled", "n_positive", "roc_auc", "test_roc_auc", "roc_auc_drop")


@dataclass
class ModelVersion:
    version: str
    aliases: list[str]
    created_ms: int
    model_type: str
    gate: str
    gate_reasons: list[str]
    promotion: str
    metrics: dict[str, float]
    description: str
    mlflow_url: str


@dataclass
class Monitoring:
    performance: dict[str, float] = field(default_factory=dict)
    drift_detected: bool | None = None
    drift_last_run_s: float | None = None


@dataclass
class Model:
    domain: str
    title: str
    purpose: str
    registered_name: str
    production_version: str | None
    versions: list[ModelVersion]
    monitoring: Monitoring
    error: str | None = None


def _gate_reasons(raw: str) -> list[str]:
    try:
        reasons = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return [raw]
    return [str(r) for r in reasons] if isinstance(reasons, list) else [str(reasons)]


def _version(name: str, raw: dict) -> ModelVersion:
    tags = {t["key"]: t["value"] for t in raw.get("tags", [])}
    metrics = {}
    for key in _METRICS:
        try:
            metrics[key] = float(tags[f"test_{key}"])
        except (KeyError, ValueError):
            continue
    return ModelVersion(
        version=str(raw["version"]),
        aliases=sorted(raw.get("aliases", [])),
        created_ms=int(raw.get("creation_timestamp", 0)),
        model_type=tags.get("model_type", ""),
        gate=tags.get("gate", ""),
        gate_reasons=_gate_reasons(tags.get("gate_reasons", "")),
        promotion=tags.get("promotion", ""),
        metrics=metrics,
        description=raw.get("description", ""),
        mlflow_url=f"{MLFLOW_URL}/#/models/{name}/versions/{raw['version']}",
    )


async def _versions(client: httpx.AsyncClient, name: str) -> list[ModelVersion]:
    found, model = await asyncio.gather(
        client.get(
            f"{MLFLOW_API_URL}/api/2.0/mlflow/model-versions/search",
            params={"filter": f"name='{name}'", "max_results": 100},
        ),
        client.get(f"{MLFLOW_API_URL}/api/2.0/mlflow/registered-models/get", params={"name": name}),
    )
    found.raise_for_status()
    model.raise_for_status()
    # The version search leaves aliases out; the registered model lists them.
    aliases: dict[str, list[str]] = {}
    for alias in model.json()["registered_model"].get("aliases", []):
        aliases.setdefault(str(alias["version"]), []).append(alias["alias"])
    versions = [
        _version(name, {**raw, "aliases": aliases.get(str(raw["version"]), [])})
        for raw in found.json().get("model_versions", [])
    ]
    return sorted(versions, key=lambda v: int(v.version), reverse=True)


async def _gauges(client: httpx.AsyncClient, expr: str) -> list[dict]:
    response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr})
    response.raise_for_status()
    return response.json()["data"]["result"]


async def _monitoring(client: httpx.AsyncClient, domain: str, version: str | None) -> Monitoring:
    """The production version's own gauges only: after a promotion, the old version's values
    describe a model that no longer serves."""
    monitoring = Monitoring()
    if version is None:
        return monitoring
    names = "|".join(f"bankml_performance_{name}" for name in _PERFORMANCE)
    selector = f'{{__name__=~"{names}",domain="{domain}",model_version="{version}"}}'
    drift = f'bankml_drift_dataset_drift{{domain="{domain}"}}'
    drift_run = f'bankml_drift_last_run_timestamp_seconds{{domain="{domain}"}}'
    try:
        performance, drift_rows, drift_run_rows = await asyncio.gather(
            _gauges(client, selector), _gauges(client, drift), _gauges(client, drift_run)
        )
    except (httpx.HTTPError, KeyError):
        return monitoring
    for row in performance:
        name = row["metric"]["__name__"].removeprefix("bankml_performance_")
        monitoring.performance[name] = float(row["value"][1])
    if drift_rows:
        monitoring.drift_detected = float(drift_rows[0]["value"][1]) > 0
    if drift_run_rows:
        monitoring.drift_last_run_s = float(drift_run_rows[0]["value"][1])
    return monitoring


async def _model(client: httpx.AsyncClient, domain: str) -> Model:
    title, purpose = DOMAINS[domain]
    name = f"{domain}-champion"
    try:
        versions = await _versions(client, name)
    except httpx.HTTPError as exc:
        return Model(domain, title, purpose, name, None, [], Monitoring(), error=str(exc))
    production = next((v.version for v in versions if "production" in v.aliases), None)
    monitoring = await _monitoring(client, domain, production)
    return Model(domain, title, purpose, name, production, versions, monitoring)


async def get_models() -> list[Model]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        return list(await asyncio.gather(*(_model(client, domain) for domain in DOMAINS)))
