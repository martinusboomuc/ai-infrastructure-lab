# ADR-0004: Back up the MLflow registry daily to Azure Blob with a write-only token

**Status:** Accepted
**Date:** 2026-11-15

## Context

BankML's MLflow server runs on `docker-01` (mlops ADR-0013). Its state is split in two:

- **Artifacts** (model files, the drift reference) are on Azure Blob, in `mlflow-artifacts`. That
  is LRS storage outside the homelab.
- **The backend store** is a Postgres container on `docker-01`'s only disk, in the
  `mlflow_postgres-data` volume. It holds the experiments, runs, metrics, registered models,
  versions and aliases.

Nothing copied the backend store anywhere. A failed disk, a deleted volume or a bad migration
would lose the record of which model is in production and why, including the
`credit-champion@production` alias the deployed API loads at startup. The artifacts would survive
but would no longer be attached to anything.

The database is small: 11 MB on disk, and 145 KB as a compressed dump. It changes only when
something trains, promotes or runs the drift job, which happens a few times a day at most.

## Decision

1. **A daily logical dump.**
   - `pg_dump --format=custom` runs at 03:30 Lisbon time.
   - The dump is checked with `pg_restore --list` before it is uploaded, so an unreadable dump
     fails the run instead of being stored as a backup.
2. **Run it on `docker-01`, next to the database.**
   - It is a `backup` service in the MLflow Compose stack, under a profile so `docker compose up`
     never starts it.
   - A systemd timer runs it (`infrastructure/homelab/mlflow/systemd/`). It reaches Postgres over
     the stack's own network, so the database is never published on the host.
3. **Store it in Azure Blob, in a separate `backups` container on the existing storage account.**
4. **Write with a token that cannot destroy anything.**
   - The SAS token is signed against a stored access policy, `backup-writer`, that grants create
     and write only.
   - It cannot read, list or delete. A leaked token can add files, but cannot remove or overwrite
     the backups already there, because every name carries a timestamp.
   - Deleting the policy revokes the token without rotating the account key.
5. **Retention is a storage lifecycle rule:** blobs under `backups/mlflow/` are deleted 30 days
   after creation (`infrastructure/homelab/mlflow/backup/lifecycle-policy.json`).
6. **A missing backup alerts.**
   - After a successful upload, the job pushes `backup_last_success_timestamp_seconds` to the
     Pushgateway.
   - Grafana's "Backup has not succeeded recently" rule fires to the homelab Discord channel when
     the last success is more than 36 hours old, or when the metric does not exist.
   - The Pushgateway now keeps a persistence file, so a restart no longer looks like a missed
     backup.
7. **Restores are tested, not assumed.** On 2026-11-15 a dump was restored into a throwaway
   Postgres 16 container. Experiments, runs, metrics, registered models, versions and the
   production alias all matched the live database. The procedure is in
   `docs/runbooks/mlflow-backup-restore.md`.

## Alternatives considered

**A k3s CronJob, like the BankML jobs (mlops ADR-0015).**
- It would keep every scheduled job in one place, with Kubernetes' record of each run.
- It lost because the pod would need to reach Postgres. That means publishing port 5432 on the
  LAN for a database whose only user is the MLflow server, just so it can be backed up.
- The systemd journal and the staleness alert cover what the cluster's job history would have
  shown.

**Continuous archiving with WAL-G or pgBackRest, for point-in-time recovery.**
- It would lose minutes of data at most, instead of up to a day.
- It lost on proportion. The registry changes a few times a day, and every change can be
  reproduced by rerunning the job that made it. A daily dump of 145 KB is enough.
- WAL archiving would also add a continuously running agent and a base-backup schedule to
  maintain.

**Proxmox `vzdump` snapshots of the whole `docker-01` VM.**
- One mechanism would cover everything on the VM.
- It lost because the snapshots would land on the same Proxmox host, so they do not survive that
  host's disk.
- A crash-consistent image of a running Postgres is also a weaker guarantee than a dump that
  Postgres itself produced and that has been restored once.

**Upload with the storage account connection string, as the MLflow server already does.**
- No new credential would be needed.
- It lost because that key can delete every blob in the account, including every backup. A
  backup that the backed-up host can erase does not protect against that host being compromised.

## Consequences

- **Bounded loss.** Losing `docker-01`'s disk now costs at most a day of registry history, and
  usually nothing, because most days nothing changes.
- **One more credential to rotate.** The SAS token expires on the date set when it was generated
  (one year). The staleness alert is what will say it has expired, because uploads start failing
  with 403.
- **Retention cannot be shortened by mistake from the homelab.** It lives in Azure, out of reach
  of the token.
- **The same LRS account holds the artifacts and the backups.** An outage of that storage account
  affects both at once. Geo-redundant storage would cost more than the problem is worth here.
- **Only the registry is covered.** Terraform state, Grafana's database and the cluster's
  hand-made Secrets are still not backed up. The alert and push format take a `target` label so
  that each can be added without a new rule.
