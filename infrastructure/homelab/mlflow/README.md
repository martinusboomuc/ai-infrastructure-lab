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

Artifacts live on Azure Blob (`bankml-data-rg/bankmldvcstore/mlflow-artifacts`), not a local
Docker volume, matching ADR-0013's decided design in full. Migrated the existing
production model's artifacts across before switching (not a fresh start) — verified the
deployed Azure Container App still loads `credit-champion@production` and returns an identical
prediction after the cutover, and confirmed a fresh training run's artifacts land in the new
container, not any leftover local path.

## Deploying

On `docker-01`, over SSH:

```bash
git clone https://github.com/martinusboomuc/ai-infrastructure-lab.git
cd ai-infrastructure-lab/infrastructure/homelab/mlflow
cp .env.example .env
# edit .env with a real POSTGRES_PASSWORD and AZURE_STORAGE_CONNECTION_STRING

docker compose up -d
```

Check it came up:

```bash
docker compose ps
curl http://localhost:5000/health
```

## Backups

The Postgres backend store is dumped daily at 03:30 to the `backups` blob container, kept 30
days, and alerted on when a day is missed
([ADR-0004](../../../docs/decisions/0004-mlflow-registry-backups.md)). Checking, running and
restoring are in [the runbook](../../../docs/runbooks/mlflow-backup-restore.md).

One-time setup, from the Mac with `az login` done. The account key is read inline and never
printed, and the SAS token goes straight into `docker-01`'s `.env`:

```bash
KEY="$(az storage account keys list -g bankml-data-rg -n bankmldvcstore --query '[0].value' -o tsv)"
az storage container create --account-name bankmldvcstore --name backups --account-key "$KEY"
# Create and write only: the token cannot read, list or delete. Deleting the policy revokes it.
az storage container policy create --account-name bankmldvcstore --container-name backups \
  --name backup-writer --permissions cw --expiry 2027-11-15T00:00Z --account-key "$KEY"
az storage account management-policy create -g bankml-data-rg --account-name bankmldvcstore \
  --policy @infrastructure/homelab/mlflow/backup/lifecycle-policy.json
az storage container generate-sas --account-name bankmldvcstore --name backups \
  --policy-name backup-writer --https-only --account-key "$KEY" -o tsv \
| ssh -i ~/.ssh/id_ed25519_ai_lab ops@192.168.1.115 \
  'cd ~/ai-infrastructure-lab/infrastructure/homelab/mlflow && read -r t && grep -v "^BACKUP_SAS_TOKEN=" .env > .env.new && printf "BACKUP_SAS_TOKEN=%s\n" "$t" >> .env.new && chmod 600 .env.new && mv .env.new .env'
unset KEY
```

Then, on `docker-01`, install the timer:

```bash
cd ~/ai-infrastructure-lab/infrastructure/homelab/mlflow
sudo cp systemd/mlflow-backup.service systemd/mlflow-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mlflow-backup.timer
sudo systemctl start mlflow-backup.service   # first backup now, rather than at 03:30
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

Nothing from ADR-0013's original design remains open. Newer, separate items live in
`mlops/ROADMAP.md`'s Phase 5 (drift monitoring, alerting) and this repo's own `monitoring/`
stack.
