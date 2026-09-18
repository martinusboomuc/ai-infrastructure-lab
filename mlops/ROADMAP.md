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

## Phase 2 — Data platform (Credit Risk)

Home Credit only. This is where the hardest thinking happens.

- [ ] Ingestion of all 7 Home Credit tables into `raw/`
- [ ] DVC configured against a private Azure Blob remote
- [ ] Pandera contracts for every table, enforced at the `raw → validated` boundary
- [ ] Temporal split configuration with an explicit gap window
- [ ] Label maturity window applied and documented
- [ ] Feature pipeline with as-of-timestamp aggregations
- [ ] **Leakage test in CI**: features built against the full table and against the
      timestamp-truncated table are identical

**Exit criteria:** `make features DOMAIN=credit` reproduces a byte-identical feature set from a
clean clone at a given DVC revision, and the leakage test is green in CI.

---

## Phase 3 — Modelling and registry (Credit Risk)

- [ ] WoE binning + logistic scorecard (champion) via `optbinning`
- [ ] LightGBM challenger
- [ ] Cost-sensitive evaluation: PR-AUC, recall @ fixed FPR, alert volume, expected cost
- [ ] Slice metrics with configured tolerances
- [ ] SHAP reason codes for both models
- [ ] MLflow tracking: params, metrics, artifacts, DVC data version, git SHA
- [ ] MLflow Model Registry with a promotion gate that can actually block
- [ ] Model card generated automatically at promotion

**Exit criteria:** a model can only reach `Production` in the registry by passing the gate, and a
deliberately degraded model is demonstrably rejected by it.

---

## Phase 4 — Serving and deployment (Credit Risk)

- [ ] FastAPI service importing the *same* feature module used in training
- [ ] Request validation against the training Pandera contract
- [ ] Structured logging with request IDs; prediction log persisted
- [ ] Dockerfile; image published to Azure Container Registry
- [ ] Deployed to Azure Container Apps, scale-to-zero, secrets from Key Vault
- [ ] CI/CD: merge to `main` builds, tests, pushes and deploys
- [ ] Prefect introduced for the end-to-end flow
- [ ] `infrastructure/teardown.sh` verified to leave zero billable resources

**Exit criteria:** a live endpoint returns a scored decision with reason codes and a model
version, and a training-vs-serving parity test confirms identical features for the same input.

---

## Phase 5 — Monitoring and retraining (Credit Risk)

- [ ] Prometheus metrics exposed; Grafana dashboard for latency, throughput, errors
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
