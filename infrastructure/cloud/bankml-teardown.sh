#!/usr/bin/env bash
# Tears down every Azure resource `bankml-provision.sh` created (ROADMAP Phase 4 exit
# criterion: "infrastructure/teardown.sh verified to leave zero billable resources").
#
# Run by hand, after `az login`. Deletes the whole resource group in one call — everything
# provisioning created (Container Apps environment + app, Key Vault) lives in it, so this is the
# actual guarantee of "zero billable resources left," not a per-resource checklist that can
# drift out of sync with what provisioning creates. The image itself lives in GitHub Container
# Registry (ADR-0010), outside Azure entirely — nothing to tear down there.
#
# Usage: RESOURCE_GROUP=... ./bankml-teardown.sh

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-bankml-rg}"

az account show --output none || { echo "Not logged in. Run 'az login' first." >&2; exit 1; }

if ! az group exists --name "$RESOURCE_GROUP" | grep -q true; then
  echo "Resource group '$RESOURCE_GROUP' does not exist — nothing to tear down."
  exit 0
fi

echo "Deleting resource group '$RESOURCE_GROUP' and everything in it..."
az group delete --name "$RESOURCE_GROUP" --yes

echo "Verifying..."
if az group exists --name "$RESOURCE_GROUP" | grep -q true; then
  echo "'$RESOURCE_GROUP' still exists — deletion did not complete cleanly." >&2
  exit 1
fi

echo "Confirmed: '$RESOURCE_GROUP' no longer exists. Zero billable BankML resources remain."
