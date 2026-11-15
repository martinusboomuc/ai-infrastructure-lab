# ADR-0015: Schedule the drift check as a k3s CronJob, with its reference stored on the model run

**Status:** Accepted
**Date:** 2026-11-14

## Context

The drift job (`bankml.monitoring.drift`, Phase 5) was only ever run by hand. Its last run was
on 2026-09-22. Two Grafana alerts had been firing since 2026-09-23 without anyone acting on them:
"BankML drift job has not run recently", and the drift rule itself in a no-data state. Nothing
ran on a schedule anywhere. `docker-01`'s `.env` did not set `BANKML_PUSHGATEWAY_URL`, so even a
manual run there would not have reached Prometheus.

The job needs three inputs:

- **The logged predictions.** These are read from Azure Blob, so any machine with the storage
  connection string can read them.
- **The production model.** This comes from MLflow.
- **The reference population.** These are the `SPLIT="train"` rows of the processed feature set,
  and that file existed only on `docker-01`'s disk under `BANKML_DATA_ROOT` (ADR-0014).

The lab already runs one application workload on k3s (Nexus, `docs/decisions/0003` at the
repository root). The cluster's stated next step was to run BankML's batch jobs there.

Running the job for real also exposed two faults:

- **No minimum sample.** The prediction log holds 2 records. PSI computed on 2 records marked
  95% of features as drifted, which is noise.
- **No heartbeat without traffic.** A run with no traffic to compare pushed nothing to the
  Pushgateway. The staleness alert therefore could not tell a working job on a quiet API apart
  from a job that had stopped.

## Decision

1. **Run the drift check as a Kubernetes CronJob on k3s** (`mlops/deploy/k8s/`), daily at 06:00
   Lisbon time, from the existing `bankml-serving` image. That image already contains the
   package and every dependency.
2. **Store the reference population on the model's own MLflow run**, as
   `reference/features_train.parquet`:
   - The training pipeline logs it on every run (`bankml.tracking.log_reference`).
   - The drift job reads it from the run behind `<domain>-champion@production`.
   - The reference therefore always belongs to the model being monitored, and the job needs no
     local data.
   - `BANKML_DATA_ROOT` remains a fallback, only for runs that predate the artifact.
   - The current production model (`credit-champion` v1, run `c15624f3...`) was backfilled. Its
     training-time `features.parquet` (DVC md5 `8abba1fe...`) was read from the DVC remote and
     compared with the file on `docker-01`. The values are identical; only the column order
     differs.
3. **Require at least 500 logged predictions before computing PSI** (`DEFAULT_MIN_CURRENT`).
   PSI uses ten buckets, so 500 records give about 50 observations per bucket. Below that, a
   run reports `no_data`.
4. **Push a heartbeat on every run.** A `no_data` run pushes only
   `bankml_drift_last_run_timestamp_seconds`, merged into the job's metric group with
   `pushadd_to_gateway`. The last real drift values stay in place.
5. **The drift rule treats missing data as OK.** The staleness rule already catches a stopped
   job, which is the same split the homelab alert rules use.

Retraining is not scheduled by this ADR. A drift alert goes to Discord. Retraining stays a
deliberate run on `docker-01`, where the full feature set lives (ADR-0014), through the same gate
as before.

## Alternatives considered

**A systemd timer on `docker-01` running `make retrain-on-drift`.**
- Least change, and it closes the whole loop, from drift to a gated retrain, because the data is
  already there.
- It lost because it schedules work on a pet VM with no record of what ran, and leaves the
  cluster with no batch workload.
- It also chains an automatic retrain onto a check that, with this traffic volume, has nothing
  to measure.

**Run the full drift-and-retrain flow as a CronJob, with the data fetched from the DVC remote.**
- This would automate retraining as well.
- It lost on memory: `k8s-01` has 3.8 GB shared with the control plane, and a retrain needs the
  full feature set and model fitting.
- It would also need a Git checkout and DVC inside the job to resolve `dvc.lock`.

**Read the reference straight from the DVC remote by its md5 in `dvc.lock`.**
- This needs no change to training.
- It lost because the job would need `dvc.lock` and the DVC remote layout baked into the image.
- It would also compare against whatever `dvc.lock` says today, which is not necessarily the
  population the production model was fit on. Here the two had already diverged in hash.

**Keep the reference only under `BANKML_DATA_ROOT` and mount it into the pod with `hostPath`.**
- It lost because the data is on `docker-01` and the pod runs on `k8s-01`. A network share
  between VMs is the coupling ADR-0014 rejected for the MacBook.

## Consequences

- **Daily heartbeat.** Drift is checked every day without anyone remembering to. The staleness
  alert now means the job stopped, not that the API was quiet.
- **Larger runs.** Every training run stores about 12 MB more in Azure Blob, the size of the
  credit training population as Parquet.
- **Drift is not measured yet.** With 2 logged predictions, every run reports `no_data`. That is
  the correct answer, and it stays that way until the API serves at least 500 requests.
  Generating realistic traffic, for example by replaying the held-out test split through the
  API, is a separate decision.
- **One more secret.** The cluster holds `AZURE_STORAGE_CONNECTION_STRING` in the `bankml`
  namespace, created by hand and never committed.
- **Two-commit releases.** A code change ships as an image, then a commit that bumps the tag in
  `mlops/deploy/k8s/kustomization.yaml`, until GitOps replaces the manual apply.
