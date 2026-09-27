"""Host health, queried from the same Prometheus instance and using the exact same PromQL as
`infrastructure/homelab/monitoring/`'s Grafana dashboard and alert rules — not re-derived here,
so a number shown in this frontend always agrees with what Grafana and the Discord alerts say
about the same host at the same moment.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://192.168.1.136:9090")

_CPU_QUERY = '100 - (avg by (role) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
_MEMORY_QUERY = "(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100"
_DISK_QUERY = (
    '(1 - (node_filesystem_avail_bytes{mountpoint="/"} / '
    'node_filesystem_size_bytes{mountpoint="/"})) * 100'
)
_UP_QUERY = 'up{job=~"node-.*"}'


@dataclass
class HostHealth:
    cpu_pct: float | None = None
    memory_pct: float | None = None
    disk_pct: float | None = None
    up: bool | None = None


async def _query_by_role(client: httpx.AsyncClient, expr: str) -> dict[str, float]:
    response = await client.get(
        f"{PROMETHEUS_URL}/api/v1/query", params={"query": expr}, timeout=5.0
    )
    response.raise_for_status()
    result = response.json()["data"]["result"]
    return {
        row["metric"]["role"]: float(row["value"][1]) for row in result if "role" in row["metric"]
    }


async def get_health_by_role() -> dict[str, HostHealth]:
    """One HostHealth per `role` label Prometheus currently has data for — a role with no
    node_exporter data at all (host down, or never scraped) simply doesn't appear in the result;
    the caller treats a missing role as unknown, not as a zero.
    """
    async with httpx.AsyncClient() as client:
        cpu, memory, disk, up = await asyncio.gather(
            _query_by_role(client, _CPU_QUERY),
            _query_by_role(client, _MEMORY_QUERY),
            _query_by_role(client, _DISK_QUERY),
            _query_by_role(client, _UP_QUERY),
        )

    roles = set(cpu) | set(memory) | set(disk) | set(up)
    return {
        role: HostHealth(
            cpu_pct=cpu.get(role),
            memory_pct=memory.get(role),
            disk_pct=disk.get(role),
            up=bool(up[role]) if role in up else None,
        )
        for role in roles
    }
