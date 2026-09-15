# Architecture

How BankML Platform is put together, and why. Decisions that had a real alternative are recorded
as [ADRs](docs/decisions/); this document describes the resulting system.

---

## 1. Design principles

**One lifecycle, many domains.** Ingestion, validation, training, registry, serving and
monitoring are domain-agnostic. A domain contributes exactly two things: a config file and a
feature module. If adding a domain requires touching the core, the core is wrong.

**Config over code.** Split windows, label maturity, metric thresholds, alert budgets and schema
contracts live in `configs/<domain>.yaml`. They are reviewable, diffable and versioned alongside
the model that used them.

**Fail loudly at boundaries.** Every stage validates its input against a contract before doing
work. A pipeline that silently processes a renamed column is worse than one that crashes.

**Reproducibility is a property of the artifact, not the author.** Every registered model
records the data version (DVC hash), the code version (git SHA), the config, the environment
lock and the metrics it was gated on.

**Training and serving share one code path.** Feature logic is imported by both. Training–serving
skew is designed out rather than monitored for.

---

## 2. System overview

```text
                      ┌───────────────────────────────────────────┐
                      │            Source datasets                │
                      │      (public, license-constrained)        │
                      └──────────────────┬────────────────────────┘
                                         │  ingestion
                                         ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  Data layer — Azure Blob Storage, versioned by DVC                       │
  │  raw/  →  validated/  →  features/                                       │
  │  Pandera contracts enforced at each boundary                             │
  └──────────────────┬───────────────────────────────────┬───────────────────┘
                     │ offline (training)                │ online (serving)
                     ▼                                   │
  ┌──────────────────────────────────────┐               │
  │  Training                            │               │
  │  temporal split · label maturity     │               │
  │  champion + challenger · SHAP        │               │
  └──────────────────┬───────────────────┘               │
                     ▼                                   │
  ┌──────────────────────────────────────┐               │
  │  MLflow — tracking + Model Registry   │              │
  │  evaluation gate · model card         │              │
  └──────────────────┬───────────────────┘               │
                     │ promoted model                    │
                     ▼                                   ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  Serving — FastAPI on Azure Container Apps (image from ACR)              │
  │  shared feature code · request IDs · prediction log                      │
  └──────────────────┬───────────────────────────────────────────────────────┘
                     │ predictions + inputs
                     ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │  Monitoring — Evidently (drift) · Prometheus (ops) · Grafana (dashboards)│
  │  delayed-label performance once labels mature                            │
  └──────────────────┬───────────────────────────────────────────────────────┘
                     │ drift or schedule
                     └────────────────► retraining, back through the same gate
```

---

## 3. Temporal correctness

The single most important property of the system, and the thing that most distinguishes it from
a Kaggle pipeline.

### Splitting

Splits are chronological and configured per domain:

```yaml
split:
  train:      { from: 2016-01-01, to: 2017-06-30 }
  gap_days:   30          # nothing is drawn from this window
  validation: { from: 2017-08-01, to: 2017-12-31 }
  test:       { from: 2018-01-01, to: 2018-06-30 }
```

The gap prevents features with lookback windows from straddling the boundary. `sklearn`'s
random splitters are banned in `src/` by a lint rule, not by convention.

### Point-in-time correctness

A feature attached to a row with decision timestamp `t` may only use data with an effective
timestamp `< t`. Aggregations over relational tables (Home Credit's bureau, previous
applications, instalment history) are the main hazard: a naive `GROUP BY customer_id` pulls in
records that postdate the application.

Every aggregation therefore takes an explicit as-of timestamp, and CI runs a **leakage test**:
build features for a held-out row twice, once with the full table and once with the table
truncated at that row's timestamp, and assert the two feature vectors are identical. A feature
that fails this test cannot be merged.

### Label maturity

```yaml
label:
  maturity_days: 540      # credit default observation window
```

Rows whose decision timestamp is more recent than `now - maturity_days` are excluded from
training: their "no default" label is not yet trustworthy. This is also why the monitoring layer
cannot compute live performance immediately — it computes drift now and performance later, when
labels arrive.

---

## 4. Evaluation

### Metrics

Reported for every run, per domain config:

- **PR-AUC** — primary ranking metric under severe class imbalance.
- **Recall @ fixed FPR** — the operational question: how much fraud is caught if the review team
  can tolerate 0.5% false positives?
- **Alert volume vs. budget** — how many cases per day does the threshold generate, against the
  team's declared capacity?
- **Expected cost** — `FN × cost_of_miss + FP × cost_of_review`, the number a business actually
  optimises.
- ROC-AUC is recorded for comparability but never used as a gate on its own.

### Slices

Metrics are computed on configured slices as well as overall, so a model that performs well in
aggregate while degrading on a segment is caught before promotion.

### Gate

Promotion to the registry requires: challenger beats champion on the primary metric by a
configured margin; no slice degrades beyond tolerance; reason codes are producible; the model
card is complete. A run failing any of these can still be logged to MLflow — it simply cannot be
promoted.

---

## 5. Modelling strategy per domain

### Credit Risk — scorecard as champion

The industry standard for credit decisioning is **WoE binning + logistic regression** (a
scorecard), because lending decisions must be explainable to the applicant and defensible to a
regulator under model risk management practice. Here the logistic scorecard is the **champion**,
not a throwaway baseline, and **LightGBM is the challenger**.

The interesting engineering is therefore the comparison itself: how much AUC does the GBM buy,
what does that gain cost in explainability, and does the scorecard's monotonic, binned structure
hold up? Both models ship SHAP-derived reason codes; the scorecard's are trivially auditable,
the GBM's are not, and that asymmetry is part of the finding. See
[ADR-0005](docs/decisions/0005-scorecard-champion-gbm-challenger.md).

### Fraud Detection — GBM as champion

No adverse-action requirement, extreme imbalance, and features with real semantics (velocity,
distance from usual merchant location, time since last transaction). LightGBM is the champion,
logistic regression the baseline. Threshold selection is driven entirely by the alert budget.

### Churn and Marketing — fixtures

Logistic regression, small and fast. Their purpose is to exercise the pipeline in CI, not to
demonstrate modelling.

---

## 6. Serving

FastAPI behind Uvicorn, containerised, deployed to Azure Container Apps from an image in Azure
Container Registry. Per request:

1. Validate the payload against the same Pandera contract used in training.
2. Build features using the **imported domain feature module** — the same code the training
   pipeline ran.
3. Score, apply the domain threshold, produce reason codes.
4. Log the request ID, input hash, feature vector, prediction and model version to the prediction
   store, for later drift analysis and delayed-label evaluation.

Every response carries the model version and the request ID. Secrets come from Azure Key Vault;
nothing is baked into the image.

---

## 7. Monitoring

| Signal | Tool | Answers |
|---|---|---|
| Latency, throughput, error rate | Prometheus → Grafana | Is the service healthy? |
| Input data drift | Evidently | Has the population moved away from the training window? |
| Prediction drift | Evidently | Is the score distribution shifting, even before labels arrive? |
| Feature-level PSI | Evidently | Which specific features moved? |
| Delayed performance | Custom job | Once labels mature, was the model actually right? |

Drift alone never triggers an automatic promotion — it triggers a retraining run, which must
still pass the evaluation gate.

---

## 8. Stack rationale

| Choice | Why, and over what |
|---|---|
| **Pandera** over Great Expectations | Code-first, pytest-native, an order of magnitude less setup. GX is powerful but heavy and its API has churned across major versions. The CV value is identical. [ADR-0003](docs/decisions/0003-pandera-over-great-expectations.md) |
| **DVC** with a private remote | Home Credit and IEEE-CIS carry competition terms restricting redistribution, so data is versioned by reference, never committed. |
| **MLflow** for tracking *and* registry | One service, two responsibilities. The registry is not separate technology. |
| **Prefect deferred to Phase 4** | `make` plus GitHub Actions is sufficient for linear pipelines. Orchestration earns its keep when there are branching, retrying, scheduled flows. |
| **Feature store deferred** | Feast without an online store is mostly ceremony. The real skill is point-in-time-correct feature construction, which is built in Phase 2 regardless. [ADR-0006](docs/decisions/0006-defer-feature-store.md) |
| **Azure Container Apps** over AKS | Serverless containers, scale-to-zero, no cluster to babysit or pay for. Kubernetes is a later exercise, not a starting requirement. |
| **`uv`** over pip/Poetry | Fast, lockfile-based, single tool for envs and dependencies. |
| **`optbinning`** | Mature WoE/scorecard implementation; writing binning from scratch is not the point. |

### Cost control

Azure spend is a real constraint on a portfolio project. A **budget alert is configured before
the first resource is created**, Container Apps are configured to scale to zero, and storage
uses the cool tier for raw snapshots. The teardown script in `infrastructure/` is maintained as a
first-class artifact.

---

## 9. Known simplifications

Stated openly, because pretending otherwise is the failure mode this project exists to avoid.

- Datasets are public, historical and static; there is no live transaction stream.
- AML is modelled as supervised classification. Real AML is rules plus anomaly detection plus
  network analysis, with extremely sparse and biased labels from SAR filings.
- No real regulatory review, model validation function, or independent challenge exists here.
  The governance artifacts (model cards, reason codes, evaluation gates) simulate their outputs.
- Fairness slicing uses proxy segments available in the data, not protected attributes, which
  these datasets largely do not contain.
