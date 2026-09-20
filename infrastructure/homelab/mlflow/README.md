# Self-hosted MLflow on docker-01

Docker Compose stack for BankML's MLflow tracking server, per
[ADR-0013](../../../mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md). Runs on
`docker-01` (see [ADR-0002](../../../docs/decisions/0002-proxmox-vm-layout.md)).

## Current state: interim, not the full ADR-0013 design

This stack currently uses a **local Docker volume for artifact storage**, not Azure Blob, and
has **no Cloudflare Tunnel** — both are still-open follow-up work. It is not yet reachable by
the deployed Azure Container App. What's here now is enough to point local BankML training runs
at a real, shared, network-reachable tracking server instead of a local SQLite file — that alone
is real progress over the previous state, just not the complete decided design.

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

Point training runs at it instead of the local `sqlite:///mlflow.db`:

```bash
export MLFLOW_TRACKING_URI=http://<docker-01's IP>:5000
```

This only works from machines on the same LAN today — there is no external exposure yet. The
deployed Azure Container App still cannot reach this until the Cloudflare Tunnel from ADR-0013
exists.

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

## What's still open (ADR-0013's actual design, not built yet)

- Artifact storage on Azure Blob instead of the local `mlflow-artifacts` volume.
- A Cloudflare Tunnel exposing this server's port to the deployed Azure Container App, gated by
  Cloudflare Access.
- Adding `MLFLOW_TRACKING_URI` and Blob credentials to the Container App's own configuration.
