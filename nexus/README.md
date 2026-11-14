# Nexus

> A live, visual command center for the homelab — infrastructure topology today, MLflow model and
> feature browsing next, a local-LLM copilot last.

Grafana already answers "is anything broken." Nexus answers a different question: "what does my
system actually look like, and what's running where" — a designed, explorable view over the same
underlying data (Tailscale presence, Prometheus health, eventually MLflow's model registry and
BankML's feature metadata), not another set of generic metric panels.

**Status:** Phase 1 (topology + presence), running on the k3s cluster on `k8s-01` and reachable
at `http://k8s-01/` over the tailnet. See `infrastructure/homelab/monitoring/` for the
Grafana/Prometheus stack this reads from.

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

The backend reads tailnet presence from the Tailscale API, so it needs a read-only OAuth client
in the environment (`TS_OAUTH_CLIENT_ID`, `TS_OAUTH_CLIENT_SECRET`). For the full stack on one
host, put both in `nexus/.env` (git-ignored) and run `docker compose up -d --build`; the
frontend is then on `:8081`.

## Deploying

Nexus runs on k3s, from the Kustomize manifests in `deploy/k8s/`. The reasoning is in
[ADR-0003](../docs/decisions/0003-nexus-on-k3s.md).

1. A push to `main` that touches `backend/` or `frontend/` builds both images and pushes them to
   GHCR, tagged with the commit's first 12 SHA characters (`.github/workflows/nexus-images.yml`).
2. A release is a commit that sets those tags in `deploy/k8s/kustomization.yaml`.
3. On `k8s-01`, from the repository checkout:

   ```bash
   sudo k3s kubectl apply -k nexus/deploy/k8s
   sudo k3s kubectl -n nexus rollout status deploy/backend deploy/frontend
   ```

Before the first apply, the Tailscale OAuth client is created once in the Tailscale admin console
(Settings, Trust credentials) with only the `devices:core:read` scope. Its secret goes into the
cluster by hand and is never committed. `read -s` keeps it out of the shell history:

```bash
sudo k3s kubectl create namespace nexus
read -s TS_ID; read -s TS_SECRET
sudo k3s kubectl -n nexus create secret generic tailscale-oauth \
  --from-literal=TS_OAUTH_CLIENT_ID="$TS_ID" --from-literal=TS_OAUTH_CLIENT_SECRET="$TS_SECRET"
unset TS_ID TS_SECRET
```

Inside the cluster the backend is a ClusterIP Service with no external exposure. nginx
reverse-proxies `/api/` to it, and Traefik routes the node's port 80 to nginx.

## Roadmap

1. **Topology + presence** (done) — live node graph: the Proxmox host, its three VMs, and
   personal devices (MacBook, iPhone) shown only while actually connected to the tailnet.
2. **Deployment** (done) — containerized, first on `docker-01` under Compose, now on k3s with
   images built by CI (ADR-0003). Not yet reachable at its own subdomain through the existing
   Cloudflare Tunnel.
3. **Quick-launch per node** (done) — click a node, get a detail panel with its live status,
   health, and direct links out to the real tool it represents: Grafana's dashboard and a
   Prometheus query scoped to that node's `role` for every monitored host, plus the Proxmox web
   UI on `pve01` and MLflow on `docker-01`. The Discord alert channels are deliberately not
   linked — the webhook URL is a credential and isn't in this repository (see
   `infrastructure/homelab/monitoring/README.md`), and no separate, safely-linkable channel URL
   is documented anywhere else.
4. **MLflow and feature browsing** — select a registered model, see its real metrics, model card,
   and the features it was trained on, grounded in the same data the training pipeline itself
   produces (`features.parquet`, Evidently drift reports, SHAP reason codes).
5. **Local LLM copilot** — deliberately last. A real NVIDIA GTX 1650 Super (4GB VRAM) sits unused
   on the Proxmox host, enough for a real local model (a 7-8B model at 4-bit quantization, or
   smaller comfortably) once GPU passthrough is set up — a separate hardware decision, not a
   software one, which is why it's sequenced after everything the chat feature would need to be
   useful already exists.
