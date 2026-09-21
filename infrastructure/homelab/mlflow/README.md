# Self-hosted MLflow on docker-01

Docker Compose stack for BankML's MLflow tracking server, per
[ADR-0013](../../../mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md). Runs on
`docker-01` (see [ADR-0002](../../../docs/decisions/0002-proxmox-vm-layout.md)).

## Current state

The tracking server, Postgres backend, and the Cloudflare Tunnel + Access gate are all live and
verified working — `https://mlflow.homelab-boom.com` returns `403` with no credentials and `200`
with a valid Service Token. What's still open: artifact storage is a **local Docker volume**, not
Azure Blob (ADR-0013's decided design), and the deployed Azure Container App does not yet send
the Access credentials on its MLflow client requests — see "What's still open" below.

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
instead, and send the Access Service Token on every request as headers:

```
CF-Access-Client-Id: <client ID, from the bankml-container-app Service Token>
CF-Access-Client-Secret: <client secret>
```

`MLFLOW_TRACKING_URI=https://mlflow.homelab-boom.com` alone is not enough — MLflow's Python
client has no built-in way to attach arbitrary headers to its own requests, so this needs a
small `RequestHeaderProvider` plugin (an MLflow extension point) installed alongside `mlflow` in
the serving image, registered to inject those two headers on every call. That plugin does not
exist yet — writing and wiring it in is BankML application code, not homelab infrastructure, and
belongs with the rest of Phase 4's serving work.

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
- A `RequestHeaderProvider` plugin so MLflow's Python client sends the Access Service Token
  headers automatically — see "Using it from BankML" above.
- Adding `MLFLOW_TRACKING_URI` and the Service Token credentials to the deployed Azure Container
  App's configuration, and confirming it actually loads `credit-champion@production` on startup.
