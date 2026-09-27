"""Nexus backend: aggregates live homelab state (Tailscale presence, Prometheus health) into one
API the frontend polls. No state of its own — every response is computed fresh from the same
sources Grafana already reads, so this can be redeployed or restarted with nothing to lose.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.topology import get_topology

app = FastAPI(title="Nexus")

app.add_middleware(
    CORSMiddleware,
    # Wide open deliberately: this API carries no secrets and no mutating endpoints — it's a
    # read-only view over data that's already visible in Grafana on the same LAN/tailnet.
    allow_origins=["*"],
    allow_methods=["GET"],
)


@app.get("/api/topology")
async def topology():
    nodes = await get_topology()
    return {"nodes": [asdict(n) for n in nodes]}


@app.get("/health")
async def health():
    return {"status": "ok"}
