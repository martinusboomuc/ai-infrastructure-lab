"""Per-node quick-launch links to the real tool each homelab node represents — Grafana,
Prometheus, MLflow, the Proxmox web UI. A second piece of deliberately hardcoded homelab-specific
knowledge alongside topology.py's `_KNOWN_HOSTS` table: which tool lives where isn't something
any live source reports, so it's named here explicitly rather than guessed from the node id at
render time in the frontend.

The Discord alert channels are not node links: they belong to the alerts view (app/alerts.py),
which links the channels themselves and never the webhook URLs Grafana posts to.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Opened by the viewer's browser, so these use the VMs' short hostnames: the home router resolves
# them on the LAN and Tailscale's MagicDNS resolves them over the tailnet, so the same link works
# in both places. A LAN IP only works at home.
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://monitoring-01:3000")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_UI_URL", "http://monitoring-01:9090")
# MLflow's own port, not its public domain: Cloudflare Access on that domain admits only the
# Azure Container App's service token, and refuses a browser with 403.
MLFLOW_URL = os.environ.get("MLFLOW_URL", "http://docker-01:5000")

# The "Homelab Overview" dashboard has no per-role template variable — every panel plots all
# roles at once (infrastructure/homelab/monitoring/grafana/provisioning/dashboards/json/
# homelab-overview.json) — so there's no real per-node deep link into it, only the dashboard
# itself, and it is offered once, on monitoring-01, rather than as a fabricated per-node link.
_GRAFANA_DASHBOARD_URL = f"{GRAFANA_URL}/d/homelab-overview/homelab-overview"


@dataclass
class QuickLink:
    label: str
    url: str


def quick_links(node_id: str, tailscale_ip: str | None) -> list[QuickLink]:
    """Direct links out to the tools that run on a node. A node lists only what it hosts, so
    the links also say where each tool lives; a node that hosts nothing linkable has none.
    """
    links: list[QuickLink] = []

    if node_id == "monitoring-01":
        # Grafana and Prometheus are linked from the one machine they run on. Both cover every
        # host, and an earlier version put them on every monitored node (Prometheus as a query
        # scoped to that node), which read as both tools running everywhere. A node's own
        # figures are on its display in the room; the per-node query link was the cost of this.
        links.append(QuickLink("Grafana", _GRAFANA_DASHBOARD_URL))
        links.append(QuickLink("Prometheus", PROMETHEUS_URL))

    if node_id == "pve01" and tailscale_ip:
        # The Proxmox web UI only listens on the host's own address. Always its live Tailscale
        # IP, never a hardcoded one — a LAN lease can change under it (network-topology.md).
        links.append(QuickLink("Proxmox Web UI", f"https://{tailscale_ip}:8006"))

    if node_id == "docker-01":
        links.append(QuickLink("MLflow", MLFLOW_URL))

    return links
