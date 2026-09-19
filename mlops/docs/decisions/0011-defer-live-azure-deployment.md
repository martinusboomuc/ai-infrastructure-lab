# ADR-0011: Defer live Azure deployment — Container Apps blocked on Azure for Students

**Status:** Superseded by [ADR-0012](0012-container-apps-region-specific-not-subscription-wide.md)
**Date:** 2026-09-19

## Context

Running `infrastructure/cloud/bankml-provision.sh` against this project's real Azure
subscription (Azure for Students) for the first time surfaced a sequence of real, independent
restrictions, each confirmed by actually hitting it rather than by reading documentation:

1. Azure Container Registry creation disallowed outright (`RequestDisallowedByAzure`), in two
   different regions (`westeurope`, `eastus`) — resolved by [ADR-0010](0010-github-container-registry-instead-of-acr.md):
   serve the image from GitHub Container Registry instead.
2. Key Vault creation also disallowed in both of those regions, via both the CLI and the Azure
   Portal directly (ruling out a CLI-specific automation flag) — resolved by finding a region
   (`francecentral`) the subscription does allow.
3. The vault's "Azure role-based access control" permission model (the Portal's current default)
   does not grant the vault's own creator secret-level data access automatically, unlike the
   legacy access-policy model — resolved with an explicit `Key Vault Secrets Officer` role
   assignment for the operator, and a `Key Vault Secrets User` assignment for the container app's
   managed identity instead of the now-ineffective `az keyvault set-policy`.
4. Azure Container Apps environment creation failed with `MaxNumberOfEnvironmentsInSubExceeded`
   — and `az containerapp env list` across the whole subscription came back empty, confirming
   the allowed count is **zero**, not a stale leftover consuming an existing quota slot.
5. Re-confirmed twice more after a full teardown and re-provision, including in a second region
   (`eastus`, then `francecentral` again) — identical error both times. The Azure Portal's own
   Quotas page (Quotas → My quotas → Azure Container Apps) showed "Managed Environment Count:
   0 of 1" for every region checked, suggesting headroom — but creation failed identically
   regardless. The Quotas page is showing a generic, documented default limit, not the actual
   per-subscription restriction; whatever enforces this sits in the same policy layer as items
   1–2's `RequestDisallowedByAzure` denials, invisible to the standard quota UI entirely.
6. Re-confirmed a fifth time through the Azure Portal's own "Create Container app" wizard
   (Basics → Container → Ingress → Review + create), not the CLI at all — identical
   `MaxNumberOfEnvironmentsInSubExceeded` at the validation step, same error code and wording.
   This rules out "CLI automation flagged differently than interactive use" definitively: the
   restriction is enforced identically by both clients, at the Azure Resource Manager level, not
   in the CLI's own request shape.

Items 4–6 are a different kind of blocker than 1–3. Those were all workable around (a different
registry, a different region, a different RBAC call). A restriction enforced below the level the
Quotas UI can even see, reproduced identically across two regions and three independent
provisioning attempts — two via CLI, one via the Portal's own creation wizard — is not something
a third region, another retry, or a different client fixes. The only paths left are an actual
Microsoft support ticket (of uncertain outcome and turnaround on a free/education subscription)
or a different subscription entirely.

## Decision

Defer live deployment to Azure Container Apps. Everything else Phase 4 set out to build stays
as the verified deliverable: the FastAPI serving app, request validation, structured logging and
prediction log, the Dockerfile (built and verified locally), the Prefect flow, and the
provisioning/teardown scripts and CI/CD workflow — all written, reviewed, and correct code, kept
exactly as they are for whenever a subscription without this restriction is available. Nothing
in the codebase is rolled back or simplified to route around this; the blocker is recorded as
what it is, an external account-tier constraint, not a defect in the platform design.

`infrastructure/cloud/bankml-teardown.sh` is run now regardless, to leave the resource group's
Key Vault (the one piece that did get created) torn down rather than sitting there unused.

## Alternatives considered

**Request a quota increase via the Azure Portal's self-service Quotas page.** Tried: the page
showed existing headroom ("0 of 1") rather than a request form, and re-provisioning against
that same apparently-available quota failed identically — so there was nothing to actually
request an increase to. A genuine Microsoft support ticket remains available if the repository
owner wants to pursue it later, but isn't pursued now: turnaround and approval odds on a
free/education subscription are both uncertain, and blocking further project progress on a
ticket of unknown outcome isn't a good trade for a portfolio project's own pace.

**Switch cloud providers entirely** (a platform with no such quota, e.g. Fly.io, Render,
Railway). Rejected: this project's stack rationale (ARCHITECTURE.md §8) reasons specifically
about Azure the whole way through — Blob Storage, Key Vault, Container Apps' scale-to-zero
economics. Abandoning Azure over one account-tier limit on one resource type is a much larger
architectural change than the actual problem warrants, and would strand every other
Azure-specific decision already made and justified.

**Simplify away Key Vault or Container Apps to fit under some other quota** (e.g. an Azure VM
instead). Rejected: that isn't "the same architecture, deployed" — it's a different, worse
architecture adopted to dodge a limit, contradicting ARCHITECTURE.md's own design principles
(scale-to-zero via Container Apps was itself a reasoned choice, not incidental).

## Consequences

- ROADMAP.md's Phase 4 checklist keeps three items unchecked (deployed to Container Apps,
  CI/CD firing for real, verified teardown) until a workable subscription exists. The phase's
  exit criterion is otherwise met: `tests/parity/test_training_serving_parity.py` is green and a
  real locally-run FastAPI service returned real scored decisions against the actual
  `credit-champion@production` model.
- `mlops-deploy.yml`'s `deploy` job is conditioned on `AZURE_CREDENTIALS` existing
  (`if: secrets.AZURE_CREDENTIALS != ''`) and skips cleanly rather than failing — deliberately,
  since there is nowhere for it to deploy to yet. The `build-test-push` job (lint, test, build,
  push to GHCR) still runs and gates every merge regardless.
- If a different Azure subscription (a work account, a Pay-As-You-Go conversion, an approved
  quota increase) becomes available, `infrastructure/cloud/bankml-provision.sh` needs no changes
  to attempt deployment again — it was never the script that was wrong.
