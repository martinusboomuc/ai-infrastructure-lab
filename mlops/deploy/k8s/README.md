# BankML on k3s

Two daily CronJobs for Credit Risk on `k8s-01`: replayed traffic at 05:00 and the drift check at
06:00. The reasoning is in [ADR-0015](../../docs/decisions/0015-scheduled-drift-check-on-k3s.md)
and [ADR-0016](../../docs/decisions/0016-replay-held-out-applicants-as-traffic.md).

## What runs

`drift-credit`, daily at 06:00 Lisbon time, runs `python -m bankml.monitoring.drift --domain
credit` from the `bankml-serving` image. It reads:

- the logged predictions, from Azure Blob;
- the production model and its reference population, from MLflow on `docker-01`.

It pushes the result to the Pushgateway on `monitoring-01`, where the Grafana rules in
`infrastructure/homelab/monitoring/grafana/provisioning/alerting/drift.yaml` read it. With fewer
than 500 logged predictions it reports `no_data` and pushes only a heartbeat.

`replay-credit`, daily at 05:00, runs `python -m bankml.monitoring.replay --domain credit
--batch-size 200`. It posts the next 200 prepared requests to the API on Azure Container Apps
with `X-Traffic-Source: replay`, and moves the cursor in the `replay` blob container.

## Building the replay requests

The requests are built from the raw Home Credit files, so this runs on `docker-01`, once, and
again only when the production model is retrained on a different split. Uploading resets the
cursor.

```bash
cd ~/ai-infrastructure-lab/mlops
set -a && . ./.env && set +a
uv run python -m bankml.features.credit.replay --output /tmp/replay/credit.jsonl.gz --upload
```

## Deploying

The Azure Storage connection string is created once by hand and never committed. `read -s` keeps
it out of the shell history:

```bash
sudo k3s kubectl create namespace bankml
read -s AZ
sudo k3s kubectl -n bankml create secret generic azure-storage \
  --from-literal=AZURE_STORAGE_CONNECTION_STRING="$AZ"
unset AZ
```

The replay job authenticates to the API with the `replay` client key
([ADR-0017](../../docs/decisions/0017-per-client-api-keys.md)). The same key must be one of the
pairs in the Container App's `BANKML_API_KEYS` secret:

```bash
read -s KEY
sudo k3s kubectl -n bankml create secret generic bankml-api-key \
  --from-literal=BANKML_API_KEY="$KEY"
unset KEY
```

A release is a commit that sets the image tag in `kustomization.yaml`; the tag is the first 12
characters of the commit `.github/workflows/mlops-deploy.yml` built. Then, on `k8s-01`:

```bash
sudo k3s kubectl apply -k mlops/deploy/k8s
```

To run either job now rather than waiting for its schedule:

```bash
sudo k3s kubectl -n bankml create job --from=cronjob/replay-credit replay-credit-manual
sudo k3s kubectl -n bankml logs -f job/replay-credit-manual
sudo k3s kubectl -n bankml create job --from=cronjob/drift-credit drift-credit-manual
sudo k3s kubectl -n bankml logs -f job/drift-credit-manual
```

A manual replay run moves the cursor like a scheduled one, so it never resends applicants.
