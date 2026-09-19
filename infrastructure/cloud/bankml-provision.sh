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
# Idempotent: every `az ... create` below is safe to re-run against the same names — Azure
# either returns the existing resource unchanged or updates it in place. Everything lands in one
# resource group so `bankml-teardown.sh` can remove it all with a single, verifiable delete.
#
# Usage: RESOURCE_GROUP=... GHCR_IMAGE=ghcr.io/<owner>/<repo>/bankml-serving ./bankml-provision.sh
# (or just edit the defaults below for a one-off run)

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-bankml-rg}"
LOCATION="${LOCATION:-eastus}"
CONTAINERAPPS_ENV="${CONTAINERAPPS_ENV:-bankml-env}"
CONTAINER_APP_NAME="${CONTAINER_APP_NAME:-bankml-credit-serving}"
KEY_VAULT_NAME="${KEY_VAULT_NAME:-bankml-kv}"          # must be globally unique
GHCR_IMAGE="${GHCR_IMAGE:?Set GHCR_IMAGE, e.g. ghcr.io/<owner>/<repo>/bankml-serving}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

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
az keyvault create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$KEY_VAULT_NAME" \
  --location "$LOCATION" \
  --output none

# Real runtime secrets go here as this project grows past a local SQLite MLflow store — e.g. a
# hosted MLFLOW_TRACKING_URI, an Azure Storage connection string for prediction-log persistence.
# Placeholder so the container app below has at least one secret reference to wire up; replace
# with real values before first deploy.
az keyvault secret set \
  --vault-name "$KEY_VAULT_NAME" \
  --name "mlflow-tracking-uri" \
  --value "${MLFLOW_TRACKING_URI:-sqlite:///mlflow.db}" \
  --output none

echo "-- Container Apps environment (scale-to-zero by default per app, not the environment) --"
az extension add --name containerapp --upgrade --output none 2>/dev/null || true
az provider register --namespace Microsoft.App --wait
az containerapp env create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINERAPPS_ENV" \
  --location "$LOCATION" \
  --output none

echo "-- Container App (pulling a public GHCR image — no registry credentials needed) --"
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

echo "-- Granting the container app's managed identity Key Vault read --"
APP_PRINCIPAL_ID="$(az containerapp identity assign \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CONTAINER_APP_NAME" \
  --system-assigned \
  --query principalId --output tsv)"

az keyvault set-policy \
  --name "$KEY_VAULT_NAME" \
  --object-id "$APP_PRINCIPAL_ID" \
  --secret-permissions get list \
  --output none

echo
echo "== Done =="
echo "Next: push a new image tag (mlops-deploy.yml does this on merge to main), then"
echo "'az containerapp update --image $GHCR_IMAGE:<tag>' to roll out a new revision."
