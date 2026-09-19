# ADR-0010: GitHub Container Registry instead of Azure Container Registry

**Status:** Accepted
**Date:** 2026-09-19

## Context

ARCHITECTURE.md's original serving design pushed the Dockerfile's image to Azure Container
Registry, alongside Azure Container Apps and Key Vault. Running `infrastructure/cloud/bankml-provision.sh`
against this project's real Azure subscription (Azure for Students) failed at the ACR creation
step:

```
(RequestDisallowedByAzure) Resource 'bankmlacr' was disallowed by Azure: This policy maintains a
set of best available regions where your subscription can deploy resources... The selected
region is currently not accepting new customers.
```

Retrying in a second region (`eastus` after `westeurope`) failed with the same
`RequestDisallowedByAzure` error, minus the "not accepting new customers" clause — the resource
group and Key Vault creation in the same script succeeded in both regions without issue. That
combination (same generic denial, two different regions, only ACR affected) points at a
subscription-level policy restricting which resource *types* Azure for Students accounts can
create at all, not a per-region capacity limit that trying a third or fourth region would route
around.

## Decision

Serve the image from GitHub Container Registry (`ghcr.io`) instead. The package is made public
once, by hand, in its GitHub settings after the first push, so Azure Container Apps pulls it
with zero registry credentials — no service principal role assignment, no `--registry-server`/
`--registry-identity` wiring, one fewer secret than the ACR path needed.
`.github/workflows/mlops-deploy.yml` authenticates to GHCR with the workflow's own built-in
`GITHUB_TOKEN` (`packages: write` permission), not a new secret.
`infrastructure/cloud/bankml-provision.sh` no longer creates or references ACR at all.

## Alternatives considered

**Keep troubleshooting Azure regions, or contact Azure support.** Rejected for now: the evidence
(two regions, one denial, no region-specific detail in the second) suggests this is a
subscription-tier restriction on the resource type itself, not a region search problem, and
support-ticket turnaround isn't worth blocking a portfolio project's Phase 4 on. Revisit if a
later, less-restricted Azure subscription is ever used for this project.

**Docker Hub.** Rejected: free-tier pull-rate limits are a real operational hazard for a service
that scales from zero on every cold start, and it adds a second platform/credential set for no
benefit over GHCR, which is already the platform this project's CI already runs on.

## Consequences

- One fewer billable, policy-restricted Azure resource type in the footprint; the image itself
  lives entirely outside Azure, so `bankml-teardown.sh` deleting the resource group is still the
  complete, sufficient teardown.
- The GHCR package must be public for the zero-credential pull to work. Acceptable here: the
  image contains only application code already public in this repository, no secrets are baked
  into it (real secrets come from Key Vault at runtime), and a public portfolio project has no
  meaningful confidentiality reason to keep a build artifact of public source private.
- If Azure Container Apps ever needs a *private* image (a real bank would not publish serving
  images publicly), the fix is a registry credential on the Container App
  (`--registry-username`/`--registry-password` with a GHCR PAT, or a private ACR once accessible
  on a non-restricted subscription) — not a reason to revisit this decision now.
