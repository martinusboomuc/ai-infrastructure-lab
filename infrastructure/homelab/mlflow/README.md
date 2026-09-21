# Self-hosted MLflow on docker-01

Docker Compose stack for BankML's MLflow tracking server, per
[ADR-0013](../../../mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md). Runs on
`docker-01` (see [ADR-0002](../../../docs/decisions/0002-proxmox-vm-layout.md)).

## Current state

The full reachability chain is live and verified working end-to-end, including real production
traffic: the deployed Azure Container App reaches this server through the Cloudflare Tunnel,
authenticates via Access using the `bankml-container-app` Service Token (sent automatically by
`src/bankml/tracking_auth.py`'s MLflow request header provider), and loads a real
`credit-champion@production` model registered and promoted against it. `GET /health` and
`POST /predict/credit` on the live Azure endpoint both return genuine responses — a real score,
decision, threshold and SHAP-derived reason codes — see mlops' own ROADMAP.md, Phase 4.

Also still open: artifact storage is a **local Docker volume**, not Azure Blob as ADR-0013
decided.

## Deploying

On `docker-01`, over SSH:

```bash
git clone https://github.com/martinusboomuc/ai-infrastructure-lab.git
cd ai-infrastructure-lab/infrastructure/homelab/mlflow
cp .env.example .env
# edit .env with a real POSTGRES_PASSWORD

docker compose up -d
```

Check it came up:

```bash
docker compose ps
curl http://localhost:5000/health
```

## Using it from BankML

From the LAN (e.g. local training runs), point directly at the container:

```bash
export MLFLOW_TRACKING_URI=http://<docker-01's IP>:5000
```

From outside the LAN — the path the deployed Azure Container App needs — go through the tunnel
instead:

```bash
export MLFLOW_TRACKING_URI=https://mlflow.homelab-boom.com
export CF_ACCESS_CLIENT_ID=<client ID, from the bankml-container-app Service Token>
export CF_ACCESS_CLIENT_SECRET=<client secret>
```

No manual header code needed — `bankml`'s `tracking_auth.py` registers an MLflow
`RequestHeaderProvider` (an MLflow extension point) that reads those two env vars and attaches
them to every request automatically, and is a complete no-op when they aren't set. Verified
working both ways: LAN-direct with no env vars, and through the tunnel with them set.

## Cloudflare Tunnel setup notes (why the config looks the way it does)

Two non-obvious things were needed to get a `200` instead of a `403` once the Access policy was
correctly matching:

- **The public hostname route's `HTTP Host Header` must be set to `localhost:5000`, not
  `mlflow:5000`.** `cloudflared` otherwise forwards the original public hostname
  (`mlflow.homelab-boom.com`) straight through as the `Host` header, which MLflow's own server
  rejects (`Rejected request with invalid Host header`) — but it also rejects the Docker Compose
  service name `mlflow:5000`, since MLflow's security layer only trusts `localhost`/`127.0.0.1`
  values. Rewriting to `localhost:5000` satisfies that check; it doesn't change which container
  `cloudflared` actually connects to (that's the separate "Service" field, still `mlflow:5000`).
- **A route or policy change to an already-running `cloudflared` container isn't picked up
  automatically** — restart it (`docker compose restart cloudflared`) after any change made in
  the Cloudflare dashboard.

## Updating

```bash
cd ai-infrastructure-lab/infrastructure/homelab/mlflow
git pull
docker compose up -d --build
```

## Tearing down

```bash
docker compose down
```

Add `-v` to also delete the Postgres and artifact volumes — that permanently discards every
logged run and model, not just stops the containers.

## What's still open

- Artifact storage on Azure Blob instead of the local `mlflow-artifacts` volume.
