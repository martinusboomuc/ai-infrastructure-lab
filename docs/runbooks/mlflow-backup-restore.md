# MLflow registry: backups and restore

How the MLflow backend store is backed up, how to check it, and how to restore it. The reasoning
is in [ADR-0004](../decisions/0004-mlflow-registry-backups.md).

## What is backed up

The Postgres database behind the MLflow server on `docker-01`: experiments, runs, metrics,
registered models, versions and aliases. Model artifacts are not in it. They live in the
`mlflow-artifacts` blob container and are not affected by losing `docker-01`.

Backups land in `bankmldvcstore/backups/mlflow/mlflow-<UTC timestamp>.dump`, daily at 03:30
Lisbon time, and are deleted after 30 days.

## Checking that backups run

On `docker-01`:

```bash
systemctl list-timers mlflow-backup.timer
systemctl status mlflow-backup.service
journalctl -u mlflow-backup.service -n 20
```

From the Mac, with `az login` done:

```bash
az storage blob list --account-name bankmldvcstore --container-name backups \
  --prefix mlflow/ --auth-mode login --query "[].{name:name, size:properties.contentLength}" -o table
```

Grafana's "Backup has not succeeded recently" alert, in the Homelab folder, fires to the
homelab Discord channel when the last success is more than 36 hours old.

## Running a backup now

```bash
sudo systemctl start mlflow-backup.service
journalctl -u mlflow-backup.service -n 5
```

## Restoring

The token on `docker-01` cannot read backups, so a restore downloads with your own Azure login.

1. Download the dump you want, from the Mac:

   ```bash
   az storage blob download --account-name bankmldvcstore --container-name backups \
     --name mlflow/mlflow-<timestamp>.dump --file mlflow.dump --auth-mode login
   scp -i ~/.ssh/id_ed25519_ai_lab mlflow.dump ops@192.168.1.115:/tmp/mlflow.dump
   ```

2. Test it first, against a throwaway database, on `docker-01`:

   ```bash
   cd ~/ai-infrastructure-lab/infrastructure/homelab/mlflow
   set -a && . ./.env && set +a
   docker run -d --name restore-test -e POSTGRES_PASSWORD=restoretest \
     -e POSTGRES_USER="$POSTGRES_USER" -e POSTGRES_DB="$POSTGRES_DB" postgres:16-alpine
   docker exec restore-test pg_isready -U "$POSTGRES_USER"   # repeat until it accepts
   docker exec -i restore-test pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     --exit-on-error < /tmp/mlflow.dump
   docker exec restore-test psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "select name, alias, version from registered_model_aliases"
   docker rm -f restore-test
   ```

3. Restore into the real database. This replaces everything in it, so stop the MLflow server
   first:

   ```bash
   docker compose stop mlflow cloudflared
   docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     --clean --if-exists --exit-on-error < /tmp/mlflow.dump
   docker compose start mlflow cloudflared
   curl -s http://localhost:5000/health
   ```

   If the volume itself is gone, `docker compose up -d postgres` creates an empty database first,
   and the same `pg_restore` (without `--clean`) fills it.

4. Restart the Azure Container App's revision so the API reloads `credit-champion@production`
   from the restored registry.

## Rotating the SAS token

The token is signed against the `backup-writer` stored access policy on the `backups`
container. To revoke it immediately, delete that policy. To issue a new one, recreate the policy
with a new expiry and generate a token against it, as in the MLflow README's "Backups" section.
