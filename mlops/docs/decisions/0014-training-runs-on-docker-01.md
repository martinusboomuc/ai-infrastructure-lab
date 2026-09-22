# ADR-0014: BankML training runs on docker-01, not the MacBook

**Status:** Accepted
**Date:** 2026-09-21

## Context

BankML's data and training runs have lived on the MacBook since Phase 2. `mlops/CLAUDE.md`'s
hard rule on `BANKML_DATA_ROOT` has said since the beginning that it "currently points at a
local folder and will later point at a homelab machine" — this ADR is that migration actually
happening, and records what it turned out to involve.

`docs/architecture/homelab-architecture.md`'s role split table already states the constraint
this decision satisfies: "MacBook | Development client ... No infrastructure services, no
long-term data." A 2.5GB dataset sitting only on a laptop's disk is also the exact risk
[ADR-0001](0001-repo-placement.md)... more precisely the repo root's own hybrid-infrastructure
ADR calls out: nothing irreplaceable should be a sole copy.

The first proposal considered was an NFS share: `docker-01` exports the data directory, the
MacBook mounts it, and `BANKML_DATA_ROOT` points at the mount so training keeps running from the
laptop. Rejected before implementation — a developer's laptop live-mounting a share from a
machine under someone's desk is not how a real engineering org separates a dev workstation from
compute. The realistic pattern is the other way round: data and execution both live on shared
infrastructure, and the laptop edits code and triggers runs against it.

## Decision

Training runs on `docker-01` (ADR-0002), triggered from the MacBook over SSH. The full data
directory (`mlops/data/`) and DVC's cache are on `docker-01`, not the laptop. The MacBook clones
and edits the same repository but no longer needs `BANKML_DATA_ROOT` pointed at a real dataset
for anything beyond CI-fixture-scale work.

## Alternatives considered

- **NFS mount from the MacBook.** Rejected above — doesn't match how companies separate
  workstation from compute, and keeps the laptop in the runtime path for every local run.
- **A new dedicated VM for data only.** Rejected as unnecessary infrastructure for 2.5GB of
  data; `docker-01` already fits ADR-0002's stated role ("anything outside the cluster") and
  already runs the MLflow server training needs to reach anyway — a run on `docker-01` talks to
  it over `localhost`, not through the Cloudflare Tunnel `docker-01` itself sits behind.

## Consequences

**Found while doing this, not decided in advance:**

- The DVC remote (`bankmldvcstore`, an Azure Blob storage account from Phase 2) no longer
  existed — zero storage accounts remained anywhere in the subscription, and nothing in this
  repository ever created or deleted it, so it was set up by hand at some point and is not
  reproducible from a script. Recreated it (same name, still available) in a **separate**
  resource group, `bankml-data-rg` — deliberately not inside `bankml-rg`, so a future
  `bankml-teardown.sh` run (which deletes `bankml-rg` wholesale) can never delete this backup
  again by accident. `dvc push` from the MacBook repopulated it; `dvc pull` on `docker-01`
  restored the working copy there.
- `docker-01` has 4GB RAM and no swap. `bankml.features.credit.pipeline.load_raw_tables` loads
  all seven Home Credit tables (2.5GB of CSVs, up to 690MB each) into pandas simultaneously, so
  before running training for real a 6GB swapfile was added to `docker-01` as a safety net — an
  OOM kill on this machine risks taking down the live, already-running MLflow container the
  deployed Azure Container App depends on, not just the training process. In practice the full
  pipeline used well under 1GB of headroom end to end; the swapfile is a safety margin that
  turned out not to be load-bearing, kept anyway since it cost nothing to add.
- LightGBM needs `libgomp1` at runtime — the same gap already found and fixed in the serving
  Docker image, hit again here because `docker-01` is a bare Debian VM, not that image. Installed
  at the OS level.
- Found and fixed a real, previously-only-worked-around bug: `bankml.tracking.log_run` never
  called `mlflow.set_experiment(...)`, so every run fell into MLflow's "Default" experiment,
  whose `artifact_location` is fixed permanently at the moment that experiment was first created
  — before the self-hosted server's proxied-artifact fix
  ([ADR-0013](0013-self-hosted-mlflow-on-homelab.md)) existed, so it points at a bare filesystem
  path (`/mlflow/artifacts/0`) no remote client can write to. Someone had already hit this once
  and worked around it by hand-creating an experiment called `credit-risk-v2` — never captured in
  code, so the exact same failure reproduced immediately on `docker-01`. Fixed for real:
  `log_run` now takes `domain` and calls `mlflow.set_experiment(domain)`, so every domain gets
  its own experiment, created fresh, always inheriting the server's *current* default artifact
  root. The currently-deployed production model is unaffected — it's already registered, and the
  registry doesn't care which experiment its source run belongs to.
- `.env` is not auto-loaded by `uv run`; it needs `set -a && source .env && set +a` first, same
  as `local-setup.md` already documented for the Mac — this just hadn't been needed on a fresh
  machine before.

This makes future training runs reproducible from a shared, backed-up location instead of a
single laptop. It commits to `docker-01` being reachable over SSH for anyone doing BankML
training work going forward, and to the DVC remote actually being treated as durable
infrastructure (its own resource group, outside any teardown script's reach) rather than an
implicit assumption.
