#!/usr/bin/env bash
# Provisions the Azure footprint for BankML Credit Risk serving (ROADMAP Phase 4).
#
# Run by hand, after `az login`, from a shell with the Azure CLI installed. Not run by Claude —
# these are real, billable resources (see ARCHITECTURE.md's "Cost control" section; Phase 0
# already put a budget alert on the subscription before any resource existed).
#
# Deliberately plain `az` CLI, not Terraform — ROADMAP.md lists "Terraform for the Azure
# footprint" under *Later*, reassessed after Phase 6, not required for Phase 4.
#
# Image comes from GitHub Container Registry, not Azure Container Registry — ADR-0010: ACR was
# disallowed outright on this project's Azure for Students subscription, independent of region.
# `GHCR_IMAGE` must already exist (and be public — see mlops-deploy.yml) before the Container App
# step below; run this after the first successful push, not before.
#
# Idempotent, but not via `az ... create`'s own behavior — unlike `az group create`,
# `az keyvault create`/`az containerapp create` error outright ("already exists") on a second
# run rather than treating it as a no-op. Every step below checks existence first and skips
# creation if found, which is what actually makes re-running this safe. Found by re-running it
# for real, not by reading the docs. Everything lands in one resource group so
# `bankml-teardown.sh` can remove it all with a single, verifiable delete.
#
# Usage: RESOURCE_GROUP=... GHCR_IMAGE=ghcr.io/<owner>/<repo>/bankml-serving \
#   MLFLOW_TRACKING_URI=https://mlflow.homelab-boom.com \
#   CF_ACCESS_CLIENT_ID=... CF_ACCESS_CLIENT_SECRET=... ./bankml-provision.sh
# (or just edit the defaults below for a one-off run)
#
# The last three wire the app to BankML's self-hosted MLflow tracking server, reached through a
# Cloudflare Tunnel gated by Access (mlops/docs/decisions/0013-self-hosted-mlflow-on-homelab.md)
# — CF_ACCESS_CLIENT_ID/SECRET are the "bankml-container-app" Service Token's credentials, read
# automatically by src/bankml/tracking_auth.py's MLflow request header provider. Required every
# run, same as GHCR_IMAGE — there's no safe default for a credential.

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-bankml-rg}"
# westeurope, eastus and francecentral are all disallowed for a Container Apps environment on
# this project's Azure for Students subscription (confirmed via both CLI and the Portal's own
# creation wizard — see ADR-0012) — spaincentral is confirmed to work end-to-end (Key Vault,
# Container Apps environment, Container App). Region availability on a restricted subscription
# is account-specific; override if yours differs.
LOCATION="${LOCATION:-spaincentral}"
CONTAINERAPPS_ENV="${CONTAINERAPPS_ENV:-bankml-env}"
CONTAINER_APP_NAME="${CONTAINER_APP_NAME:-bankml-credit-serving}"
KEY_VAULT_NAME="${KEY_VAULT_NAME:-bankml-kv}"          # must be globally unique
GHCR_IMAGE="${GHCR_IMAGE:?Set GHCR_IMAGE, e.g. ghcr.io/<owner>/<repo>/bankml-serving}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
CF_ACCESS_CLIENT_ID="${CF_ACCESS_CLIENT_ID:?Set CF_ACCESS_CLIENT_ID (the bankml-container-app Service Token's Client ID)}"
CF_ACCESS_CLIENT_SECRET="${CF_ACCESS_CLIENT_SECRET:?Set CF_ACCESS_CLIENT_SECRET (the bankml-container-app Service Token's Client Secret)}"

echo "== BankML Azure provisioning =="
echo "Resource group:     $RESOURCE_GROUP ($LOCATION)"
echo "Image:               $GHCR_IMAGE:$IMAGE_TAG"
echo "Container Apps env:  $CONTAINERAPPS_ENV"
echo "Container App:       $CONTAINER_APP_NAME"
echo "Key Vault:            $KEY_VAULT_NAME"
echo

az account show --output none || { echo "Not logged in. Run 'az login' first." >&2; exit 1; }

echo "-- Resource group --"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

echo "-- Key Vault --"
if az keyvault show --name "$KEY_VAULT_NAME" --output none 2>/dev/null; then
  echo "   already exists, skipping"
else
  az keyvault create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$KEY_VAULT_NAME" \
    --location "$LOCATION" \
    --output none
fi

# Requires the caller to already hold a data-plane role on the vault (e.g. "Key Vault Secrets
# Officer") — the RBAC permission model (this vault's, and the Portal's current default) does
# not grant secret access to the vault's creator/Owner automatically; that surprised us too.
# `secret set` itself is a genuine upsert, safe to re-run without a existence check.
#
# The self-hosted MLflow tracking server's URL and the Cloudflare Access Service Token that
# authenticates the app's requests to it through the Tunnel (ADR-0013). Defaults to the local
# SQLite path if MLFLOW_TRACKING_URI isn't set, which is what originally caused the deployed
# container to crash-loop — this default only makes sense for a from-scratch first run, not once
# the real value below is in use.
az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "mlflow-tracking-uri" \
  --value "${MLFLOW_TRACKING_URI:-sqlite:///mlflow.db}" \
  --output none

az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "cf-access-client-id" \
  --value "$CF_ACCESS_CLIENT_ID" \
  --output none

az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "cf-access-client-secret" \
  --value "$CF_ACCESS_CLIENT_SECRET" \
  --output none

echo "-- Container Apps environment (scale-to-zero by default per app, not the environment) --"
az extension add --name containerapp --upgrade --output none 2>/dev/null || true
az provider register --namespace Microsoft.App --wait
# Microsoft.App auto-creates a Log Analytics workspace for the environment unless one is
# provided, which needs this provider registered too — not obvious from Microsoft.App's own
# name, found by actually hitting "Subscription ... is not registered for the
# Microsoft.OperationalInsights resource provider" on a first-ever run.
az provider register --namespace Microsoft.OperationalInsights --wait
if az containerapp env show --resource-group "$RESOURCE_GROUP" --name "$CONTAINERAPPS_ENV" --output none 2>/dev/null; then
  echo "   already exists, skipping"
else
  az containerapp env create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CONTAINERAPPS_ENV" \
    --location "$LOCATION" \
    --output none
fi

echo "-- Container App (pulling a public GHCR image — no registry credentials needed) --"
if az containerapp show --resource-group "$RESOURCE_GROUP" --name "$CONTAINER_APP_NAME" --output none 2>/dev/null; then
  echo "   already exists, skipping (use 'az containerapp update --image ...' to roll out a new tag)"
else
  az containerapp create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$CONTAINER_APP_NAME" \
    --environment "$CONTAINERAPPS_ENV" \
    --image "$GHCR_IMAGE:$IMAGE_TAG" \
    --target-port 8000 \
    --ingress external \
    --min-replicas 0 \
    --max-replicas 3 \
    --output none
fi

echo "-- Granting the container app's managed identity Key Vault read --"
# Idempotent by nature: assigning a system identity that's already assigned just returns its
# existing principalId.
APP_PRINCIPAL_ID="$(az containerapp identity assign \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_APP_NAME" \
  --system-assigned \
  --query principalId --output tsv)"

# RBAC role assignment, not `az keyvault set-policy` — the vault uses the "Azure role-based
# access control" permission model, where the older access-policy API has no effect at all.
KEY_VAULT_ID="$(az keyvault show --name "$KEY_VAULT_NAME" --query id --output tsv)"
EXISTING_ASSIGNMENT="$(az role assignment list \
  --assignee "$APP_PRINCIPAL_ID" \
  --scope "$KEY_VAULT_ID" \
  --role "Key Vault Secrets User" \
  --query "[0].id" --output tsv)"
if [ -n "$EXISTING_ASSIGNMENT" ]; then
  echo "   role assignment already exists, skipping"
else
  az role assignment create \
    --assignee "$APP_PRINCIPAL_ID" \
    --role "Key Vault Secrets User" \
    --scope "$KEY_VAULT_ID" \
    --output none
fi

echo "-- Wiring the Key Vault secrets into the container app's environment --"
# keyvaultref + identityref:system: the app's own managed identity (granted read access just
# above) resolves these at revision-start time, not at CLI-call time — the RBAC role above
# doesn't need to have already propagated for this `secret set` call to succeed, only for the
# app to actually start cleanly afterward.
az containerapp secret set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_APP_NAME" \
  --secrets \
    "mlflow-tracking-uri=keyvaultref:https://$KEY_VAULT_NAME.vault.azure.net/secrets/mlflow-tracking-uri,identityref:system" \
    "cf-access-client-id=keyvaultref:https://$KEY_VAULT_NAME.vault.azure.net/secrets/cf-access-client-id,identityref:system" \
    "cf-access-client-secret=keyvaultref:https://$KEY_VAULT_NAME.vault.azure.net/secrets/cf-access-client-secret,identityref:system" \
  --output none

# --set-env-vars replaces the container's entire env var list, not just these three — harmless
# today since the app was created with none at all, but if anything else is ever added via the
# Portal directly instead of here, a future run of this script will silently drop it. Add it
# here, not in the Portal, if that ever happens.
az containerapp update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_APP_NAME" \
  --set-env-vars \
    MLFLOW_TRACKING_URI=secretref:mlflow-tracking-uri \
    CF_ACCESS_CLIENT_ID=secretref:cf-access-client-id \
    CF_ACCESS_CLIENT_SECRET=secretref:cf-access-client-secret \
  --output none

echo
echo "== Done =="
echo "This update itself rolled out a new revision (env vars changed) — check whether it's"
echo "actually serving now:"
echo "  az containerapp logs show --resource-group $RESOURCE_GROUP --name $CONTAINER_APP_NAME --tail 30"
echo "Next: push a new image tag (mlops-deploy.yml does this on merge to main), then"
echo "'az containerapp update --image $GHCR_IMAGE:<tag>' to roll out a new revision."
