"""Nexus backend: aggregates live homelab state (Tailscale presence, Prometheus health) into one
API the frontend polls. No state of its own — every response is computed fresh from the same
sources Grafana already reads, so this can be redeployed or restarted with nothing to lose.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI

from app.topology import get_topology

app = FastAPI(title="Nexus")


@app.get("/api/topology")
async def topology():
    nodes = await get_topology()
    return {"nodes": [asdict(n) for n in nodes]}


@app.get("/health")
async def health():
    return {"status": "ok"}
