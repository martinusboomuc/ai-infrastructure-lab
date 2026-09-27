# Nexus

> A live, visual command center for the homelab — infrastructure topology today, MLflow model and
> feature browsing next, a local-LLM copilot last.

Grafana already answers "is anything broken." Nexus answers a different question: "what does my
system actually look like, and what's running where" — a designed, explorable view over the same
underlying data (Tailscale presence, Prometheus health, eventually MLflow's model registry and
BankML's feature metadata), not another set of generic metric panels.

**Status:** Phase 1 (topology + presence) — deployed and live on `docker-01`. See
`infrastructure/homelab/monitoring/` for the Grafana/Prometheus stack this reads from.

## Why a separate app, not another Grafana dashboard

Grafana is built around metrics and panels. This is built around homelab *objects* — a VM, a
model, a feature — as first-class, clickable things, with room to grow into an AI-assisted
exploration tool (ask a locally-hosted LLM about a specific feature or model, grounded in that
model's real MLflow metadata) that a generic dashboarding tool has no natural place for.

## Architecture

```text
nexus/
├── backend/    FastAPI — aggregates live Tailscale presence + Prometheus health into one API
└── frontend/   React + Vite + React Flow — renders it as a live, polling topology graph
```

The backend holds no state of its own — every response is computed fresh from the same sources
Grafana already reads (the exact same PromQL, so a number here never disagrees with what Grafana
shows), so it can be restarted or redeployed with nothing to lose.

## Running locally (dev servers, hot reload)

```bash
cd backend && uv sync && uv run uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
```

The frontend's own code only ever calls a relative `/api/...` path — Vite's dev server proxies
that to the backend on `:8000` (`vite.config.ts`), the same way nginx does in production
(`frontend/nginx.conf`). No IP address or hostname is ever baked into the frontend at all, in
either environment — found the hard way once already: an earlier version baked in a specific
address at build time, which worked from the LAN and silently failed once the page was loaded
from anywhere else.

## Deploying

```bash
cd nexus
docker compose up -d --build
```

Builds and runs both services on `docker-01`: the backend has no published port at all (nginx
reverse-proxies `/api/` to it internally, by Compose service name — nothing external needs to
reach it directly), the frontend (a static build served by nginx) is published on `:8081`.
Requires `/var/run/tailscale/tailscaled.sock` to exist on the host running this (i.e., a host
that's already joined the tailnet) — see `backend/app/tailscale.py`'s docstring.

## Roadmap

1. **Topology + presence** (done) — live node graph: the Proxmox host, its three VMs, and
   personal devices (MacBook, iPhone) shown only while actually connected to the tailnet.
2. **Deployment** (done) — containerized and running on `docker-01` alongside MLflow and
   monitoring. Not yet reachable at its own subdomain through the existing Cloudflare Tunnel.
3. **Quick-launch per node** — click a node, get its live detail plus direct links out to the
   real tool it represents (Grafana's dashboard, Prometheus, MLflow, the Discord alert channels).
4. **MLflow and feature browsing** — select a registered model, see its real metrics, model card,
   and the features it was trained on, grounded in the same data the training pipeline itself
   produces (`features.parquet`, Evidently drift reports, SHAP reason codes).
5. **Local LLM copilot** — deliberately last. A real NVIDIA GTX 1650 Super (4GB VRAM) sits unused
   on the Proxmox host, enough for a real local model (a 7-8B model at 4-bit quantization, or
   smaller comfortably) once GPU passthrough is set up — a separate hardware decision, not a
   software one, which is why it's sequenced after everything the chat feature would need to be
   useful already exists.
