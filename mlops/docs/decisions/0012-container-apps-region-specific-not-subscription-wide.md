# ADR-0012: The Container Apps restriction was region-specific, not subscription-wide

**Status:** Accepted
**Date:** 2026-09-19

## Context

[ADR-0011](0011-defer-live-azure-deployment.md) concluded, from five independent confirmations
(three via CLI, two via the Azure Portal, across `westeurope`, `eastus` and `francecentral`)
that this project's Azure for Students subscription had a Container Apps environment quota of
**zero**, subscription-wide — a hard block with no self-service fix, distinct from the
region-specific `RequestDisallowedByAzure` denials that hit ACR and Key Vault (resolved by
ADR-0010 and by finding `francecentral`, respectively).

That conclusion was wrong in one specific way: it was never tested in a region other than the
three above. Trying a fourth region, `spaincentral`, through the Azure Portal's "Create
Container app" wizard succeeded — the environment, and the Container App itself, both
provisioned without error. The restriction was region-specific all along, exactly like the ACR
and Key Vault denials; it just took a wider region search to find the boundary, because the
error message (`MaxNumberOfEnvironmentsInSubExceeded`, "cannot create Container App Environments
in region 'France Central'. Please try another region.") reads as a subscription-wide count in a
way that `RequestDisallowedByAzure` does not, and the Portal's Quotas page showing generic
non-region-specific-looking numbers reinforced that misreading.

## Decision

Live deployment is no longer deferred. `spaincentral` is the region for every resource this
project provisions to Azure — `infrastructure/cloud/bankml-provision.sh`'s default `LOCATION` is
updated accordingly. The Container App (`bankml-credit-serving`) and its environment
(`managedEnvironment-bankmlrg-b8f1`) are running in `spaincentral` as of this ADR.

A genuinely separate, still-open problem surfaced once the app was actually running: it crashes
on startup with `mlflow.exceptions.MlflowException: Registered Model with name=credit-champion
not found`. This is not a region or quota issue — `MLFLOW_TRACKING_URI=sqlite:///mlflow.db`
resolves to a path *inside the container's own filesystem*, not the repository owner's laptop.
SQLite is a local file format, not a network service; the container correctly creates a fresh,
empty MLflow database and correctly reports that nothing is registered in it. Making the
deployed container and local training runs see the *same* registry needs a real, shared,
network-reachable MLflow tracking backend — a distinct piece of infrastructure work, deliberately
not addressed in this ADR. See ROADMAP.md's Phase 4 entry for that as the next concrete step.

## Alternatives considered

**Leave ADR-0011's conclusion in place and stop.** This is what nearly happened — the evidence
at the time (five confirmations) looked complete. Superseding it once contradicting evidence
appeared, rather than treating five confirmations as unfalsifiable, is the more honest move; an
ADR records the best available conclusion at the time, not a permanent verdict immune to new
information.

## Consequences

- ADR-0011 stays in the record, marked superseded, rather than edited or deleted — the
  investigation that led to it (the ACR and Key Vault fixes, the RBAC and provider-registration
  fixes, the idempotency rewrite of the provisioning script) was all real and still stands; only
  its final conclusion about Container Apps specifically was wrong.
- ROADMAP.md's Phase 4 checklist updates: "Deployed to Azure Container Apps" is met (a real
  revision is running); the remaining gap is a working `MLFLOW_TRACKING_URI` the deployed
  container can actually reach, not the deployment mechanism itself.
- `mlops-deploy.yml`'s `deploy` job can now genuinely target something once `AZURE_CREDENTIALS`,
  `RESOURCE_GROUP` and `CONTAINER_APP_NAME` secrets are added — no longer blocked on "nowhere to
  deploy to," only on those three secrets and, separately, the shared-backend problem above.
