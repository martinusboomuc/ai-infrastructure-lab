# ADR-0013: Self-host the MLflow tracking server on the homelab, artifacts on Azure Blob

**Status:** Accepted
**Date:** 2026-09-20

## Context

ADR-0012 shipped a live Container App in `spaincentral`, but it crash-loops:
`MLFLOW_TRACKING_URI=sqlite:///mlflow.db` resolves to a path inside the container's own
filesystem, not the repository owner's laptop, so it opens a fresh, empty registry and correctly
reports `credit-champion` missing. ROADMAP.md names the fix as "a real, shared,
network-reachable MLflow tracking backend the deployed container and local training runs both
point at — not yet designed." This ADR designs it.

Two facts bound the answer:

- **Cost.** `ARCHITECTURE.md`'s Stack rationale already states Azure spend is a real constraint
  on Azure for Students, and Container Apps were chosen specifically for scale-to-zero. A managed
  MLflow backend in Azure (a Postgres Flexible Server plus a place to run `mlflow server`) has no
  scale-to-zero equivalent — a database that must always be reachable is an always-on cost for as
  long as the project runs, unlike the serving app it would support.
- **Reachability.** [ADR-0001](../../../docs/decisions/0001-hybrid-infrastructure.md)'s
  Consequences already anticipated this exact situation: placing a service on the homelab that
  the cloud side needs to reach requires resolving CI/CD-style reachability explicitly, naming
  three paths — a self-hosted Actions runner inside the VPN (doesn't apply; this is runtime
  traffic from the deployed app, not CI), keeping the specific service cloud-hosted instead, or a
  narrowly scoped tunnel for just that one endpoint.

[ADR-0002](../../../docs/decisions/0002-proxmox-vm-layout.md) already put a plain Docker host,
`docker-01`, on the homelab for exactly this kind of service.

## Decision

MLflow's tracking server runs as a Docker Compose stack on `docker-01`:

- **Tracking server + backend store:** `mlflow server` backed by a Postgres container, both on
  `docker-01`. Postgres, not SQLite — the whole point is a store two independent things (local
  training runs and the deployed Container App) read and write concurrently, which is the
  situation MLflow's own docs say SQLite is not meant for.
- **Artifact store:** the Azure Blob Storage account BankML's DVC remote already uses (ADR-0001),
  in a new `mlflow-artifacts` container. Model binaries do not become the sole copy on the
  homelab's single, non-redundant disk — the same reasoning ADR-0001 gave for keeping the DVC
  remote on Azure applies here.
- **Reachability:** a Cloudflare Tunnel container on `docker-01` exposes only the tracking
  server's HTTP port, under a subdomain, gated by Cloudflare Access rather than left as a bare
  public endpoint. This is the "narrowly scoped tunnel for just that one endpoint" path ADR-0001
  named.
- Local training runs and the deployed Container App both set `MLFLOW_TRACKING_URI` to this same
  tunnel URL, and both get credentials for the Blob artifact store.

## Alternatives considered

**Fully managed in Azure** (Postgres Flexible Server + Blob, or a second Container App running
`mlflow server`). Rejected on cost: no scale-to-zero for a database that must stay reachable,
against a finite student credit, for a service that does not need to be cloud-hosted — and it
skips the self-hosted-infra practice this lab exists for, for no reason beyond convenience.

**Self-host everything, including artifacts, on `docker-01`'s local disk.** Rejected: recreates
the exact "sole copy on non-redundant temporary hardware" problem ADR-0001 avoided for the DVC
remote. A model binary lost with the disk is a bigger loss than a dataset that can be re-pulled
from a public source.

**Site-to-site VPN between Azure and the homelab** instead of a narrow tunnel. Rejected as more
than the problem needs: only one endpoint has to be reached, and Container Apps has no
straightforward way to attach a persistent VPN sidecar, whereas a tunnel client is one container.

**Keep SQLite, just move the file somewhere both sides can reach** (e.g., a mounted network
share). Rejected: SQLite over a network filesystem is a known way to corrupt the database under
concurrent writers, which is precisely the failure mode being fixed.

## Consequences

- `docker-01`'s Docker Compose stack grows by three containers (`mlflow`, `postgres`,
  `cloudflared`). Its 4 GB RAM budget from ADR-0002 needs rechecking once this and anything else
  on that VM are both running — worth watching, not yet a known problem.
- A publicly reachable (though access-gated) tunnel endpoint is new attack surface that did not
  exist before. Cloudflare Access must be configured before this ships — an open tunnel with no
  access policy is not an acceptable interim state.
- Needs the `mlflow-artifacts` Blob container provisioned and credentials issued (extends
  `infrastructure/cloud/bankml-provision.sh` or a sibling script), `mlflow[azure]` added as a
  dependency, and `MLFLOW_TRACKING_URI` plus Blob credentials added to both `.env.example` and
  the Container App's secrets.
- This resolves the placement question ROADMAP.md and `ARCHITECTURE.md`'s Known Simplifications
  both flag as open. It does not implement the stack — `docker-01` does not exist yet
  (ADR-0002 is decided, not yet provisioned). Implementation is Phase 4's next concrete step,
  now with a design to build instead of an open question.
