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
from urllib.parse import urlencode

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
# itself. Every monitored node links to the same URL rather than a fabricated, unscoped one.
_GRAFANA_DASHBOARD_URL = f"{GRAFANA_URL}/d/homelab-overview/homelab-overview"


@dataclass
class QuickLink:
    label: str
    url: str


def quick_links(node_id: str, role: str | None, tailscale_ip: str | None) -> list[QuickLink]:
    """Direct links out to the real tool a node represents. `role` is the Prometheus `role`
    label (see topology.py's `_KNOWN_HOSTS`) — present only for monitored hosts, so personal
    devices correctly get no monitoring links at all; there's nothing to show for them.
    """
    links: list[QuickLink] = []

    if role:
        links.append(QuickLink("Grafana", _GRAFANA_DASHBOARD_URL))
        # Scoped to this node's own `role` label — the one axis Prometheus's own UI can filter
        # on directly, without needing a Grafana dashboard variable that doesn't exist.
        query = urlencode({"g0.expr": f'up{{role="{role}"}}', "g0.tab": "1"})
        links.append(QuickLink("Prometheus", f"{PROMETHEUS_URL}/graph?{query}"))

    if node_id == "pve01" and tailscale_ip:
        # The Proxmox web UI only listens on the host's own address. Always its live Tailscale
        # IP, never a hardcoded one — a LAN lease can change under it (network-topology.md).
        links.append(QuickLink("Proxmox Web UI", f"https://{tailscale_ip}:8006"))

    if node_id == "docker-01":
        links.append(QuickLink("MLflow", MLFLOW_URL))

    return links
