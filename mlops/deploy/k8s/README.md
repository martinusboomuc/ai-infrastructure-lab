# BankML on k3s

The daily drift check for Credit Risk, as a CronJob on `k8s-01`. The reasoning is in
[ADR-0015](../../docs/decisions/0015-scheduled-drift-check-on-k3s.md).

## What runs

`drift-credit`, daily at 06:00 Lisbon time, runs `python -m bankml.monitoring.drift --domain
credit` from the `bankml-serving` image. It reads:

- the logged predictions, from Azure Blob;
- the production model and its reference population, from MLflow on `docker-01`.

It pushes the result to the Pushgateway on `monitoring-01`, where the Grafana rules in
`infrastructure/homelab/monitoring/grafana/provisioning/alerting/drift.yaml` read it. With fewer
than 500 logged predictions it reports `no_data` and pushes only a heartbeat.

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

A release is a commit that sets the image tag in `kustomization.yaml`; the tag is the first 12
characters of the commit `.github/workflows/mlops-deploy.yml` built. Then, on `k8s-01`:

```bash
sudo k3s kubectl apply -k mlops/deploy/k8s
```

To run it now rather than waiting for 06:00:

```bash
sudo k3s kubectl -n bankml create job --from=cronjob/drift-credit drift-credit-manual
sudo k3s kubectl -n bankml logs -f job/drift-credit-manual
```
