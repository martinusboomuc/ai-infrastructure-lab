"""The service catalog: every tool the lab runs or depends on, with a live status, links out to
it, and the alternative that lost to it where an ADR records one. This is what makes Nexus the
single entry point to the lab rather than one more dashboard.

Descriptions are written here, in plain terms, rather than copied from each vendor's tagline.
Alternatives are only filled in where an ADR in this repository records the comparison; a
service with no recorded decision has none, rather than an invented one.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field

import httpx

from app.alerts import GRAFANA_API_URL
from app.links import GRAFANA_URL, MLFLOW_URL, QuickLink
from app.links import PROMETHEUS_URL as PROMETHEUS_UI_URL
from app.prometheus import PROMETHEUS_URL
from app.tailscale import get_tailnet_status

REPO_URL = "https://github.com/martinusboomuc/ai-infrastructure-lab"
BANKML_API_URL = os.environ.get(
    "BANKML_API_URL",
    "https://bankml-credit-serving.delightfulgrass-66b6c9e3.spaincentral.azurecontainerapps.io",
)
# LAN addresses, reachable from inside the cluster. The public MLflow domain sits behind
# Cloudflare Access and answers 403 without a login, so it is probed separately as the tunnel.
_MLFLOW_HEALTH_URL = os.environ.get("MLFLOW_HEALTH_URL", "http://192.168.1.115:5000/health")
_GRAFANA_HEALTH_URL = f"{GRAFANA_API_URL}/api/health"
_MLFLOW_PUBLIC_URL = "https://mlflow.homelab-boom.com"


def _repo(path: str) -> str:
    return f"{REPO_URL}/blob/main/{path}"


@dataclass
class Decision:
    alternative: str
    reason: str
    adr: QuickLink


@dataclass
class Service:
    id: str
    name: str
    layer: str
    description: str
    links: list[QuickLink]
    decision: Decision | None = None
    status: str = "unknown"  # up | down | unknown


@dataclass
class _Check:
    """How a service's status is found. `job`: the Prometheus scrape job whose `up` series
    says whether it is reachable. `http`: a URL and the status codes that count as healthy.
    `tailscale`: the Tailscale API answering. None of them: no live check, status unknown.
    """

    job: str | None = None
    http: str | None = None
    http_ok: frozenset[int] = field(default_factory=lambda: frozenset({200}))
    tailscale: bool = False


_CATALOG: list[tuple[Service, _Check]] = [
    (
        Service(
            "proxmox",
            "Proxmox VE",
            "Infrastructure",
            "Hypervisor on the homelab host. Runs the three VMs that Terraform and cloud-init "
            "provision.",
            [QuickLink("Architecture", _repo("docs/architecture/homelab-architecture.md"))],
            Decision(
                "One VM for everything",
                "Monitoring would share a failure domain with what it monitors, and could not "
                "report that its own VM is down.",
                QuickLink("ADR-0002", _repo("docs/decisions/0002-proxmox-vm-layout.md")),
            ),
        ),
        _Check(job="node-proxmox"),
    ),
    (
        Service(
            "k3s",
            "k3s",
            "Infrastructure",
            "Single-node Kubernetes on k8s-01. Runs Nexus, deployed from Kustomize manifests, "
            "and kube-state-metrics.",
            [QuickLink("Manifests", f"{REPO_URL}/tree/main/nexus/deploy/k8s")],
            Decision(
                "Multi-node kubeadm cluster",
                "Needs three or four VMs at 2 GB or more each before running a single workload, "
                "which 16 GB of RAM cannot spare.",
                QuickLink("ADR-0002", _repo("docs/decisions/0002-proxmox-vm-layout.md")),
            ),
        ),
        _Check(job="kube-state-metrics"),
    ),
    (
        Service(
            "tailscale",
            "Tailscale",
            "Networking",
            "WireGuard mesh VPN. Every machine in the lab is reachable off the LAN, with nothing "
            "exposed to the internet.",
            [
                QuickLink("Admin console", "https://login.tailscale.com/admin/machines"),
                QuickLink("Network", _repo("docs/network/network-topology.md")),
            ],
        ),
        _Check(tailscale=True),
    ),
    (
        Service(
            "cloudflare",
            "Cloudflare Tunnel and Access",
            "Networking",
            "Publishes MLflow on its own domain through an outbound tunnel, with no inbound port "
            "opened. Access admits only the BankML API's service token.",
            [QuickLink("Dashboard", "https://dash.cloudflare.com")],
            Decision(
                "Site-to-site VPN between Azure and the homelab",
                "More than the problem needs: only one endpoint has to be reached, and a tunnel "
                "client is one container.",
                QuickLink(
                    "ADR-0013", _repo("mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md")
                ),
            ),
        ),
        # Cloudflare Access answers an anonymous request with 403. Getting that answer means the
        # tunnel is up; a tunnel that is down returns a 5xx from Cloudflare's edge instead.
        _Check(http=_MLFLOW_PUBLIC_URL, http_ok=frozenset({200, 302, 403})),
    ),
    (
        Service(
            "prometheus",
            "Prometheus",
            "Observability",
            "Scrapes every host, container and pod in the lab, plus the BankML API, every 15 "
            "seconds.",
            [
                QuickLink("Open", PROMETHEUS_UI_URL),
                QuickLink("Targets", f"{PROMETHEUS_UI_URL}/targets"),
            ],
        ),
        _Check(job="prometheus"),
    ),
    (
        Service(
            "grafana",
            "Grafana",
            "Observability",
            "Dashboards and alert rules over Prometheus. Sends homelab and BankML alerts to "
            "Discord.",
            [
                QuickLink("Homelab Overview", f"{GRAFANA_URL}/d/homelab-overview/homelab-overview"),
                QuickLink("Alert rules", f"{GRAFANA_URL}/alerting/list"),
            ],
        ),
        _Check(http=_GRAFANA_HEALTH_URL),
    ),
    (
        Service(
            "pushgateway",
            "Pushgateway",
            "Observability",
            "Holds the metrics of BankML's drift job, which exits before Prometheus could scrape "
            "it.",
            [],
        ),
        _Check(job="pushgateway"),
    ),
    (
        Service(
            "cadvisor",
            "cAdvisor",
            "Observability",
            "Per-container CPU and memory on docker-01.",
            [],
        ),
        _Check(job="cadvisor"),
    ),
    (
        Service(
            "mlflow",
            "MLflow",
            "ML platform",
            "Experiment tracking and model registry for BankML. Metadata in Postgres on "
            "docker-01, artifacts in Azure Blob Storage.",
            [QuickLink("Open", MLFLOW_URL)],
            Decision(
                "Fully managed in Azure",
                "A database that must stay reachable cannot scale to zero, which costs student "
                "credit for a service that does not need the cloud.",
                QuickLink(
                    "ADR-0013", _repo("mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md")
                ),
            ),
        ),
        _Check(http=_MLFLOW_HEALTH_URL),
    ),
    (
        Service(
            "bankml-api",
            "BankML API",
            "ML platform",
            "Credit-risk scoring API on Azure Container Apps. Scales to zero when idle, so the "
            "first request after a pause is slow.",
            [
                QuickLink("API docs", f"{BANKML_API_URL}/docs"),
                QuickLink("Project", f"{REPO_URL}/tree/main/mlops"),
            ],
            Decision(
                "Fly.io, Render or Railway",
                "The design depends on Azure Blob Storage, Key Vault and Container Apps' "
                "scale-to-zero; moving over one quota limit would strand all of it.",
                QuickLink(
                    "ADR-0011",
                    _repo("mlops/docs/decisions/0011-defer-live-azure-deployment.md"),
                ),
            ),
        ),
        _Check(job="bankml-credit-serving"),
    ),
    (
        Service(
            "azure-blob",
            "Azure Blob Storage",
            "ML platform",
            "DVC data remote, MLflow artifacts and the BankML prediction log.",
            [QuickLink("Portal", "https://portal.azure.com")],
            Decision(
                "Artifacts on docker-01's local disk",
                "The only copy of every model would sit on non-redundant, temporary hardware.",
                QuickLink(
                    "ADR-0013", _repo("mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md")
                ),
            ),
        ),
        _Check(),
    ),
    (
        Service(
            "github-actions",
            "GitHub Actions",
            "Delivery",
            "CI for BankML and Nexus: lint, test, build and push images, and deploy BankML to "
            "Azure.",
            [
                QuickLink("Runs", f"{REPO_URL}/actions"),
                QuickLink("Repository", REPO_URL),
            ],
        ),
        _Check(),
    ),
    (
        Service(
            "ghcr",
            "GitHub Container Registry",
            "Delivery",
            "Registry for the BankML and Nexus images, each tagged with the commit it was built "
            "from.",
            [QuickLink("Packages", "https://github.com/martinusboomuc?tab=packages")],
            Decision(
                "Docker Hub",
                "Free-tier pull limits are a hazard for a service that cold-starts on every "
                "scale-up, and it adds a second set of credentials.",
                QuickLink(
                    "ADR-0010",
                    _repo("mlops/docs/decisions/0010-github-container-registry-instead-of-acr.md"),
                ),
            ),
        ),
        _Check(),
    ),
    (
        Service(
            "discord",
            "Discord",
            "Communication",
            "Where alerts land: one channel for infrastructure, one for BankML model drift.",
            [],
        ),
        _Check(),
    ),
]


async def _up_by_job(client: httpx.AsyncClient) -> dict[str, bool]:
    response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": "up"})
    response.raise_for_status()
    up: dict[str, bool] = {}
    for row in response.json()["data"]["result"]:
        job = row["metric"].get("job")
        if job:
            # A job with several targets counts as up only if every target is.
            up[job] = up.get(job, True) and row["value"][1] == "1"
    return up


async def _http_ok(client: httpx.AsyncClient, url: str, ok: frozenset[int]) -> bool:
    try:
        response = await client.get(url, follow_redirects=False)
    except httpx.HTTPError:
        return False
    return response.status_code in ok


async def _tailscale_ok() -> bool:
    try:
        await get_tailnet_status()
    except (httpx.HTTPError, RuntimeError, KeyError):
        return False
    return True


async def get_services(discord_links: list[QuickLink]) -> list[Service]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            up_by_job = await _up_by_job(client)
        except (httpx.HTTPError, KeyError, ValueError):
            # Prometheus itself down: every job-based status becomes unknown, not down.
            up_by_job = None

        async def status(check: _Check) -> str:
            if check.job:
                if up_by_job is None or check.job not in up_by_job:
                    return "unknown"
                return "up" if up_by_job[check.job] else "down"
            if check.http:
                return "up" if await _http_ok(client, check.http, check.http_ok) else "down"
            if check.tailscale:
                return "up" if await _tailscale_ok() else "down"
            return "unknown"

        statuses = await asyncio.gather(*(status(check) for _, check in _CATALOG))

    services = []
    for (service, _), service_status in zip(_CATALOG, statuses, strict=True):
        links = discord_links if service.id == "discord" else service.links
        services.append(
            Service(
                service.id,
                service.name,
                service.layer,
                service.description,
                links,
                service.decision,
                service_status,
            )
        )
    return services
