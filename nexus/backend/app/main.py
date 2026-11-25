"""Nexus backend: aggregates live homelab state (Tailscale presence, Prometheus health, Grafana
alerts, the service catalog) into one API the frontend polls. No state of its own — every response
is computed fresh from the same sources Grafana already reads, so this can be redeployed or
restarted with nothing to lose.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException

from app.alerts import discord_channels, get_alerts
from app.bankml import TestBenchError, get_examples, get_models, predict
from app.services import get_services
from app.topology import get_topology

app = FastAPI(title="Nexus")


@app.get("/api/topology")
async def topology():
    nodes = await get_topology()
    return {"nodes": [asdict(n) for n in nodes]}


@app.get("/api/services")
async def services():
    return {"services": [asdict(s) for s in await get_services(discord_channels())]}


@app.get("/api/alerts")
async def alerts():
    return asdict(await get_alerts())


@app.get("/api/bankml/models")
async def bankml_models():
    return {"models": [asdict(m) for m in await get_models()]}


@app.get("/api/bankml/examples/{domain}")
async def bankml_examples(domain: str):
    try:
        return await get_examples(domain)
    except TestBenchError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.post("/api/bankml/predict/{domain}")
async def bankml_predict(domain: str, request: dict[str, Any]):
    try:
        return await predict(domain, request)
    except TestBenchError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@app.get("/health")
async def health():
    return {"status": "ok"}
