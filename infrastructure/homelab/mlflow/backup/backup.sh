#!/bin/sh
# Dump the MLflow registry and upload it to Azure Blob (docs/decisions/0004). Run by the
# mlflow-backup systemd timer through `docker compose --profile backup run --rm backup`.
#
# The SAS token can create and write blobs in the `backups` container and nothing else: it cannot
# read, list or delete, so a leaked token cannot destroy existing backups. Retention is a lifecycle
# rule on the storage account, not this script.
set -eu

: "${BACKUP_CONTAINER_URL:?}" "${BACKUP_SAS_TOKEN:?}" "${PUSHGATEWAY_URL:?}"

stamp=$(date -u +%Y%m%dT%H%M%SZ)
dump="/tmp/mlflow-${stamp}.dump"

# Custom format: compressed, and pg_restore can restore it selectively.
pg_dump --format=custom --file="$dump"

# A dump pg_restore cannot read is not a backup. Fail here rather than upload it.
pg_restore --list "$dump" > /dev/null

size=$(wc -c < "$dump")
curl --fail --silent --show-error --retry 3 \
  -X PUT \
  -H "x-ms-blob-type: BlockBlob" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @"$dump" \
  "${BACKUP_CONTAINER_URL}/mlflow/mlflow-${stamp}.dump?${BACKUP_SAS_TOKEN}"

# Pushed only after the upload succeeded, so the staleness alert measures backups that exist.
cat <<METRICS | curl --fail --silent --show-error --data-binary @- \
  "${PUSHGATEWAY_URL}/metrics/job/backup/target/mlflow_postgres"
# TYPE backup_last_success_timestamp_seconds gauge
backup_last_success_timestamp_seconds $(date +%s)
# TYPE backup_size_bytes gauge
backup_size_bytes ${size}
METRICS

rm -f "$dump"
echo "Uploaded mlflow/mlflow-${stamp}.dump (${size} bytes)"
