"""Combines live Tailscale presence with Prometheus health into the node graph the frontend
renders. The known-host table below is this project's one hardcoded piece of homelab-specific
knowledge — everything else (presence, health) is queried live, never assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.prometheus import HostHealth, get_health_by_role
from app.tailscale import get_tailnet_status

# Tailscale hostname -> (node id, display label, node type, Prometheus `role` label if monitored,
# parent node id). Personal devices (macbook/iphone) have no `role` — they were never added to
# prometheus.yml's node_exporter scrape config, and never will be; their only signal is Tailscale
# presence.
_KNOWN_HOSTS: dict[str, tuple[str, str, str, str | None, str | None]] = {
    "pve01": ("pve01", "Proxmox Host", "host", "proxmox", None),
    "k8s-01": ("k8s-01", "k8s-01", "vm", "k8s-01", "pve01"),
    "docker-01": ("docker-01", "docker-01", "vm", "docker-01", "pve01"),
    "monitoring-01": ("monitoring-01", "monitoring-01", "vm", "monitoring-01", "pve01"),
}
# Keyed by Tailscale `OS`, not `HostName` — a phone's HostName is an unhelpful generic value
# ("localhost" observed in practice), but its OS is a reliable, meaningful signal.
_PERSONAL_DEVICE_OS: dict[str, tuple[str, str]] = {
    "macOS": ("macbook", "MacBook"),
    "iOS": ("iphone", "iPhone"),
}


@dataclass
class TopologyNode:
    id: str
    label: str
    type: str  # host | vm | laptop | phone
    parent: str | None
    online: bool
    tailscale_ip: str | None
    health: HostHealth | None = field(default=None)


async def get_topology() -> list[TopologyNode]:
    peers = await get_tailnet_status()
    try:
        health_by_role = await get_health_by_role()
    except (httpx.HTTPError, KeyError, ValueError):
        # Prometheus being unreachable, slow, or returning an unexpected shape shouldn't take
        # down presence — a node with no health data still renders, just without CPU/memory/disk
        # figures.
        health_by_role = {}

    nodes = []
    for peer in peers:
        if peer.hostname in _KNOWN_HOSTS:
            node_id, label, node_type, role, parent = _KNOWN_HOSTS[peer.hostname]
            nodes.append(
                TopologyNode(
                    id=node_id,
                    label=label,
                    type=node_type,
                    parent=parent,
                    online=peer.online,
                    tailscale_ip=peer.tailscale_ip,
                    health=health_by_role.get(role) if role else None,
                )
            )
        elif peer.os in _PERSONAL_DEVICE_OS:
            node_id, label = _PERSONAL_DEVICE_OS[peer.os]
            node_type = "laptop" if peer.os == "macOS" else "phone"
            nodes.append(
                TopologyNode(
                    id=node_id,
                    label=label,
                    type=node_type,
                    parent=None,
                    online=peer.online,
                    tailscale_ip=peer.tailscale_ip,
                )
            )
    return nodes
