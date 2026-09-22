# BankML Platform

> Production-inspired MLOps platform for banking machine learning — built one vertical slice at a time.

**Status:** Phase 5 done · Monitoring and retraining (Credit Risk) · A Container App runs live on
Azure, serves real scored Credit Risk decisions with reason codes, and is watched by drift
detection, alerting and drift-triggered retraining through the Phase 3 gate. Phase 4's one
remaining item (verifying the teardown script) is deliberately deferred, not blocking. See
[ROADMAP.md](ROADMAP.md).

BankML Platform reproduces how a bank builds, ships, monitors and governs machine learning
models in production.

Most ML portfolio projects stop when the model is trained. This one starts there. The hard
problems in banking ML are not accuracy — they are **temporal correctness, label delay,
cost-sensitive decisioning, explainability under regulation, drift, and the operational
machinery that keeps a model honest months after deployment.**

---

## What exists today

This README is the product spec, and the repository gets filled in against it, publicly, in
order. The table below is the honest state of the build and is updated with every merged change.

| Component | Status |
|---|---|
| Documentation, architecture, ADRs | In progress |
| Repository scaffolding, tooling, CI | Done |
| Data ingestion + schema validation | Done |
| Feature pipeline (point-in-time correct) | Done |
| Training pipeline + experiment tracking | Done |
| Model registry + model cards | Done |
| Serving API | In progress |
| Monitoring + drift detection | Not started |
| Cloud deployment | Not started |
| Second domain (portability proof) | Not started |

---

## Approach: one vertical slice, then prove portability

The platform is built end-to-end on **a single domain first** — Credit Risk. Every layer
(ingestion → validation → features → training → registry → serving → monitoring → retraining)
has to actually work for that one domain before a second one is added.

The second domain, **Fraud Detection**, is the real test. If the architecture is genuinely
domain-agnostic, adding it should be mostly configuration and a domain-specific feature module —
not a rewrite. **That diff is the deliverable**: it is the evidence that this is a platform and
not five notebooks sharing a folder.

Remaining domains stay on the roadmap until the first two are done. Shipping a working narrow
thing beats describing a broad one.

---

## Domains

Domains are tiered by what they are *for*, not by how impressive they sound.

### Tier 1 — the platform is built on these

| Domain | Dataset | Scale | Why this one |
|---|---|---|---|
| **Credit Risk** | [Home Credit Default Risk](https://www.kaggle.com/competitions/home-credit-default-risk) | ~307k applicants across 7 relational tables | Real joins and aggregations, semantically meaningful features, genuine point-in-time hazards. The only dataset here that truly justifies a feature pipeline. |
| **Fraud Detection** | [Sparkov synthetic credit-card transactions](https://www.kaggle.com/datasets/kartik2112/fraud-detection) | ~1.85M transactions | Real timestamps, merchant, category and geo — so velocity, distance and recency features can be engineered and defended. Preferred over IEEE-CIS, whose features are anonymized. |

### Tier 2 — CI fixtures, not showcase models

| Domain | Dataset | Scale | Role |
|---|---|---|---|
| Customer Churn | [Bank Customer Churn](https://www.kaggle.com/datasets/shubhammeshram579/bank-customer-churn-prediction) | ~10k rows | Smoke-tests the full pipeline in CI in seconds. |
| Marketing | [Bank Marketing (UCI)](https://archive.ics.uci.edu/dataset/222/bank+marketing) | ~45k rows | Second fixture; exercises a different schema shape. |

These are teaching datasets. Using them as end-to-end pipeline fixtures is honest and useful —
presenting them as production banking models would not be.

### Tier 3 — planned

| Domain | Dataset | Note |
|---|---|---|
| Anti-Money Laundering | [IBM Transactions for AML](https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml) | `HI-Small` variant only. Real AML is rules + anomaly detection + network analysis with almost no labels (SARs are rare and biased); a supervised classifier is an acknowledged simplification. |

Full details, sizes and licensing caveats: [docs/datasets/](docs/datasets/README.md).

---

## What makes this banking ML and not Kaggle ML

These constraints are enforced by the platform, not left to the modeller's discipline. They are
the reason the pipeline is shaped the way it is.

**Temporal splits, never random.** Random cross-validation on fraud and credit data leaks future
information backwards and produces AUCs that evaporate in production. All splits are
chronological, with an explicit gap between train and validation windows.

**Point-in-time correctness.** A feature value used for a training row must be computable from
data available at that row's decision timestamp. This is the actual justification for a feature
store — not the tooling fashion.

**Label maturity.** A credit default label takes 12–24 months to mature. Training on recent
applications means training on mislabelled non-defaults. Every dataset has a declared maturity
window, and recent rows are excluded from training accordingly.

**Cost-sensitive metrics.** At 0.1% positive rate, accuracy is meaningless and ROC-AUC is
misleading. The platform reports PR-AUC, recall at a fixed false-positive rate, alert volume
against a stated review budget, and expected monetary cost.

**Explainability as a requirement.** A declined applicant is legally entitled to a reason.
Reason codes and a model card ship with every registered model, and a model that cannot produce
them cannot be promoted.

---

## Lifecycle

Every domain runs the identical lifecycle. Domain-specific logic is confined to a feature module
and a config file.

```text
Raw data
   │
   ▼
Ingestion  ──────────►  versioned with DVC, immutable snapshots
   │
   ▼
Schema validation  ──►  Pandera contracts; pipeline fails loudly, never silently
   │
   ▼
Feature pipeline  ───►  point-in-time correct, leakage tests in CI
   │
   ▼
Training  ───────────►  temporal split, cost-sensitive metrics, champion + challenger
   │
   ▼
Experiment tracking ─►  MLflow: params, metrics, artifacts, data version
   │
   ▼
Evaluation gate  ────►  thresholds, fairness slices, reason-code sanity
   │
   ▼
Model registry  ─────►  MLflow Model Registry + model card
   │
   ▼
Serving  ────────────►  FastAPI, containerised, feature parity with training
   │
   ▼
Monitoring  ─────────►  latency, data drift, prediction drift, delayed-label performance
   │
   ▼
Retraining  ─────────►  triggered by drift or schedule, back through the same gate
```

---

## Stack

Chosen for what it teaches per unit of setup cost. Rationale for the contested choices is in
[ARCHITECTURE.md](ARCHITECTURE.md) and the [ADRs](docs/decisions/).

| Layer | Tool |
|---|---|
| Language & tooling | Python 3.12, `uv`, `ruff`, `pre-commit`, `pytest`, `make` |
| Modelling | scikit-learn, LightGBM, `optbinning` (WoE scorecards), SHAP |
| Data versioning | DVC (private remote — see dataset licensing) |
| Data validation | Pandera |
| Experiment tracking & registry | MLflow (tracking + Model Registry) |
| Orchestration | Prefect |
| Serving | FastAPI + Uvicorn, structured logging with request IDs |
| Containers | Docker, GitHub Container Registry (ADR-0010) |
| CI/CD | GitHub Actions |
| Monitoring | Evidently, Prometheus, Grafana |
| Cloud | Azure Container Apps, Azure Blob Storage, Azure Key Vault |
| Later | Feast, Kubernetes, Terraform |

**Explicitly out of scope:** user management, authentication UI, and anything else that is a web
application feature rather than an MLOps concern.

---

## Repository structure

```text
mlops/
├── README.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── CONTRIBUTING.md
│
├── configs/                 # per-domain config: schema, split windows, metrics, thresholds
├── data/                    # DVC-tracked; no raw data in git
├── src/
│   └── bankml/
│       ├── ingestion/
│       ├── validation/      # Pandera schemas and contracts
│       ├── features/        # shared transforms + per-domain feature modules
│       ├── training/
│       ├── evaluation/      # cost-sensitive metrics, gates, fairness slices
│       ├── registry/
│       └── serving/         # FastAPI application
├── pipelines/               # orchestrated end-to-end runs
├── monitoring/              # drift jobs, Evidently reports, Grafana dashboards
├── infrastructure/          # IaC and deployment manifests
├── docker/
├── notebooks/               # exploration only; nothing here is a dependency
├── tests/
└── docs/
    ├── datasets/
    ├── architecture/
    ├── mlops/
    ├── api/
    ├── monitoring/
    └── decisions/           # ADRs
```

---

## Long-term goal

A production-inspired ML platform that supports multiple independent domains through one shared
lifecycle. Although the framing is banking, the architecture is deliberately domain-agnostic:
the constraints it enforces — temporal correctness, label delay, cost-sensitive thresholds,
explainability — apply equally to insurance, healthcare and manufacturing.

---

## Disclaimer

Built for educational and portfolio purposes. No confidential or proprietary banking data is
used. All datasets are publicly available and attributed in [docs/datasets/](docs/datasets/README.md);
some carry competition terms that restrict redistribution, which is why data is versioned by
reference and never committed to this repository.
