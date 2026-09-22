# Roadmap

Each phase has **exit criteria** — a concrete, checkable condition. A phase is not done because
work happened on it; it is done when the criteria pass. No dates, because estimating a side
project is fiction; the order is what matters.

---

## Phase 0 — Foundations *(done)*

Repository scaffolding and the tooling that every later phase depends on.

- [x] `uv` project, Python 3.12, locked dependencies
- [x] `ruff` + `pre-commit`, `pytest`, `Makefile` with `make setup | lint | test | train | serve`
- [x] GitHub Actions: lint and test on every PR
- [x] `src/bankml` package skeleton, `configs/` layout
- [x] Azure subscription with a **budget alert configured before any resource exists**

**Exit criteria:** `make setup && make lint && make test` passes from a clean clone, and the same
checks pass in CI.

---

## Phase 1 — Documentation and decisions *(done, ahead of Phase 0)*

- [x] README as product spec, with an honest status table
- [x] ARCHITECTURE.md
- [x] ROADMAP.md, CONTRIBUTING.md
- [x] Initial ADRs
- [x] Dataset catalogue with licensing caveats
- [x] Working conventions (`CLAUDE.md`), environment config, local setup guide
- [x] Domain config schema drafted for Credit Risk

**Exit criteria:** a reader can tell, from the repository alone, what is built, what is planned,
and why each contested technical choice was made.

---

## Phase 2 — Data platform (Credit Risk) *(done)*

Home Credit only. This is where the hardest thinking happens.

- [x] Ingestion of all 7 Home Credit tables into `raw/`
- [x] DVC configured against a private Azure Blob remote
- [x] Pandera contracts for every table, enforced at the `raw → validated` boundary
- [x] Temporal split configuration with an explicit gap window
- [x] Label maturity window applied and documented
- [x] Feature pipeline with as-of-timestamp aggregations
- [x] **Leakage test in CI**: features built against the full table and against the
      timestamp-truncated table are identical

**Exit criteria:** `make features DOMAIN=credit` reproduces a byte-identical feature set from a
clean clone at a given DVC revision, and the leakage test is green in CI.

---

## Phase 3 — Modelling and registry (Credit Risk) *(done)*

- [x] WoE binning + logistic scorecard (champion) via `optbinning`
- [x] LightGBM challenger
- [x] Cost-sensitive evaluation: PR-AUC, recall @ fixed FPR, alert volume, expected cost
- [x] Slice metrics with configured tolerances
- [x] SHAP reason codes for both models
- [x] MLflow tracking: params, metrics, artifacts, DVC data version, git SHA
- [x] MLflow Model Registry with a promotion gate that can actually block
- [x] Model card generated automatically at promotion

**Exit criteria:** a model can only reach `Production` in the registry by passing the gate, and a
deliberately degraded model is demonstrably rejected by it.

---

## Phase 4 — Serving and deployment (Credit Risk)

- [x] FastAPI service importing the *same* feature module used in training
- [x] Request validation against the training Pandera contract
- [x] Structured logging with request IDs; prediction log persisted
- [x] Dockerfile; image published to GitHub Container Registry (ADR-0010)
- [x] Deployed to Azure Container Apps, scale-to-zero — **running**, in `spaincentral` (ADR-0012); Key Vault secrets wired up, self-hosted MLflow reachable through the Cloudflare Tunnel (ADR-0013)
- [x] CI/CD fully working: build+push, then deploy — `AZURE_CREDENTIALS`/`RESOURCE_GROUP`/`CONTAINER_APP_NAME` are set as GitHub secrets (a service principal scoped only to `bankml-rg`, not the whole subscription), so a merge to `main` touching `mlops/` now rolls out a real Container Apps revision on its own
- [x] Prefect introduced for the end-to-end flow
- [x] Live endpoint serves real scored decisions with reason codes and a model version
- [ ] `infrastructure/cloud/bankml-teardown.sh` verified to leave zero billable resources

**Exit criteria:** a live endpoint returns a scored decision with reason codes and a model
version, and a training-vs-serving parity test confirms identical features for the same input.
**Both halves are now met.** The parity half: `tests/parity/test_training_serving_parity.py` is
green (see [ADR-0009](docs/decisions/0009-serving-time-feature-construction.md)), and a
locally-run `uv run uvicorn bankml.serving.app:app` against a real, gate-tested
`credit-champion@production` model returned a real scored decision with reason codes for both a
real applicant with history and one with none. The live half: provisioning against this
project's real Azure subscription (Azure for Students) hit Azure Container Registry blocked
outright ([ADR-0010](docs/decisions/0010-github-container-registry-instead-of-acr.md)), then
what looked like a subscription-wide Container Apps quota of zero across three regions — turned
out to be region-specific after all, like ACR; `spaincentral` works
([ADR-0012](docs/decisions/0012-container-apps-region-specific-not-subscription-wide.md),
superseding [ADR-0011](docs/decisions/0011-defer-live-azure-deployment.md)). The Container App
running there originally crash-looped because `MLFLOW_TRACKING_URI=sqlite:///mlflow.db` resolved
to a path inside the container's own filesystem, not the repository owner's laptop, so it opened
a fresh, empty registry and correctly reported `credit-champion` not found. That's resolved: a
self-hosted MLflow tracking server now runs on the homelab's `docker-01`
([ADR-0002](../../docs/decisions/0002-proxmox-vm-layout.md)), reachable through a Cloudflare
Tunnel gated by Access ([ADR-0013](docs/decisions/0013-self-hosted-mlflow-on-homelab.md)), and
the deployed Container App's requests authenticate through it correctly
(`src/bankml/tracking_auth.py`'s MLflow request header provider, wired via Key Vault secrets in
`infrastructure/cloud/bankml-provision.sh`). A `credit-champion` model is registered and promoted
against that server, and the last blocker — `OSError: libgomp.so.1: cannot open shared object
file`, LightGBM's compiled extension needing a system library absent from the `python:3.12-slim`
base image, invisible until a real model was actually loaded rather than just imported — is
fixed by installing `libgomp1` in the Dockerfile. The deployed endpoint now returns genuine
scored decisions:

```json
{"request_id":"2aa70773-3dd7-4297-8c0b-a68969a586b3","model_version":"1",
 "score":0.03648135154305376,"decision":"pass","threshold":0.178139549605622,
 "reason_codes":[{"feature":"EXT_SOURCE_3","shap_value":-0.34710569936954694}, ...]}
```

`mlops-deploy.yml`'s deploy job is now real: `AZURE_CREDENTIALS`/`RESOURCE_GROUP`/`CONTAINER_APP_NAME`
are set as GitHub secrets, so a merge to `main` touching `mlops/` builds, pushes and rolls out a
new Container Apps revision with no manual step. `infrastructure/cloud/bankml-provision.sh` and a
direct `az containerapp update --image ...` still work for one-off rollouts outside the normal
merge flow.

---

## Phase 5 — Monitoring and retraining (Credit Risk)

- [x] Prometheus metrics exposed (`GET /metrics`, `src/bankml/serving/metrics.py`); Grafana
      dashboard for latency, throughput and errors, scraping the live Azure endpoint from
      Prometheus on the homelab's `monitoring-01`
      ([infrastructure/homelab/monitoring/README.md](../infrastructure/homelab/monitoring/README.md)).
      Request count (by path, method and status code), request latency and predictions (by
      domain and decision) all confirmed working against a real local run with a real registered
      model. The Azure scrape target itself will read `down` until the deployed image is rebuilt
      and redeployed with this code — Prometheus can't scrape an endpoint that doesn't exist yet
      on the currently-running revision.
- [ ] Evidently jobs: input drift, prediction drift, per-feature PSI
- [ ] Drift alerting with configured thresholds
- [ ] Delayed-label performance job that runs once labels mature
- [ ] Retraining triggered by drift or schedule, routed through the Phase 3 gate

**Exit criteria:** injecting synthetic drift into the input stream raises an alert and triggers a
retraining run, which is then blocked or promoted by the gate on its own merits.

---

## Phase 6 — Portability proof (Fraud Detection)

The point of the whole exercise.

- [ ] Fraud domain added as a config file plus a feature module
- [ ] Velocity, geo-distance and recency features
- [ ] Threshold set from an explicit alert budget
- [ ] Full lifecycle runs for fraud with **no changes to core platform code**

**Exit criteria:** the pull request adding Fraud Detection touches `configs/` and
`src/bankml/features/fraud/` and nothing else. If it touches the core, the core gets fixed and
the claim is re-tested.

---

## Phase 7 — Platform surface

- [ ] Churn and Marketing wired in as CI smoke-test fixtures
- [ ] Operations dashboard: registered models, versions, drift status, deployment history
- [ ] Data catalogue generated from the Pandera contracts

---

## Later

Reassessed once Phase 6 is done, not before.

- Anti-Money Laundering domain (`HI-Small` variant)
- Feature store (Feast) with an online store, if a genuine online/offline skew problem exists
- Terraform for the Azure footprint
- Kubernetes as a deployment alternative
- Graph features for AML

---

## Deliberately excluded

- User management and authentication UI — a web application concern, not an MLOps one
- Deep learning on tabular data — gradient boosting is the correct tool here
- A general-purpose dashboard framework — the operations view exists to display platform state,
  nothing more
