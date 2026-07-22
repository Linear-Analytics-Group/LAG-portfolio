#!/usr/bin/env bash
set -euo pipefail

# Provisions the Azure infrastructure this service's Key Vault-backed
# secrets management depends on: a dedicated resource group, an
# RBAC-authorized Key Vault (not the legacy access-policy model), and
# a role assignment granting the signed-in user "Key Vault Secrets
# Officer" (read + write) scoped to that one vault. Then writes the
# resulting vault URL into the repo-root .env file (git-ignored) as
# AZURE_KEY_VAULT_URL, so the vault name itself never has to appear in
# a tracked file — only as the command-line argument you type below
# and the .env line this script writes.
#
# No secret VALUES are read, written, or hardcoded here — this script
# only provisions infrastructure, grants access, and wires up the
# vault's URL. Once .env has real AZURE_TENANT_ID/AZURE_CLIENT_ID/
# AZURE_CLIENT_SECRET/DATAVERSE_URL values in it (see .env.example),
# push each into this vault (run from the repo root):
#
#   for VAR in AZURE_TENANT_ID AZURE_CLIENT_ID \
#              AZURE_CLIENT_SECRET DATAVERSE_URL; do
#     ./infra/azure/key-vault/key_vault_auto_pull.sh <vault-name> "$VAR"
#   done
#
# Usage (run from the repo root):
#   ./infra/azure/key-vault/key_vault_init.sh \
#       <resource-group> <vault-name> [location] [env-file]
#
# Example (replace with your own resource group/vault names):
#   ./infra/azure/key-vault/key_vault_init.sh \
#       rg-example-dev kv-example-dev eastus

usage() {
  echo "Usage: $0 <resource-group> <vault-name> [location] [env-file]" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This script lives at infra/azure/key-vault/ — three levels below the
# repo root, where .env actually lives.
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

if [[ $# -lt 2 ]]; then
  usage
fi

RESOURCE_GROUP="$1"
VAULT_NAME="$2"
LOCATION="${3:-eastus}"
ENV_FILE="${4:-${REPO_ROOT}/.env}"

echo "==> Creating resource group '${RESOURCE_GROUP}' in '${LOCATION}'..."
az group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none

echo "==> Creating RBAC-authorized Key Vault '${VAULT_NAME}'..."
az keyvault create \
  --name "${VAULT_NAME}" \
  --resource-group "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --enable-rbac-authorization true \
  --output none

echo "==> Granting the signed-in user 'Key Vault Secrets Officer'" \
  "on '${VAULT_NAME}'..."
az role assignment create \
  --role "Key Vault Secrets Officer" \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --scope "$(az keyvault show --name "${VAULT_NAME}" --query id -o tsv)" \
  --output none

# RBAC role assignments are recorded immediately but can take real time
# — Microsoft documents up to several minutes — to actually propagate
# to the data-plane authorization checks Key Vault itself enforces.
# Unlike resource-group-to-child-resource creation (ARM control-plane,
# strongly consistent, no wait needed), this is a genuinely different,
# slower system (Azure AD/Entra directory replication). A fixed sleep
# is a guess; polling a real, harmless operation actually confirms
# readiness instead. Bounded at 12 attempts x 15s = 180s.
#
# --maxresults 1 is a pagination cap, not a filter or a count
# assertion — it returns successfully whether the vault has 0, 1, or
# 100 secrets already (e.g. from a prior run of this script), and
# never errors just because the underlying collection is larger than
# the cap. It exists purely to keep each poll attempt cheap: this
# probe only cares whether the call is *authorized* at all, not what
# it returns, so there's no reason to fetch more than the minimum.
echo "==> Waiting for the RBAC role assignment to take effect..."
MAX_ATTEMPTS=12
SLEEP_SECONDS=15
attempt=1
until az keyvault secret list \
  --vault-name "${VAULT_NAME}" --maxresults 1 --output none 2>/dev/null; do
  if [[ "${attempt}" -ge "${MAX_ATTEMPTS}" ]]; then
    echo "Warning: role assignment still not effective after" \
      "$((MAX_ATTEMPTS * SLEEP_SECONDS))s. It may need more time to" \
      "propagate — if key_vault_auto_pull.sh fails with a 403, wait a" \
      "few minutes and try again." >&2
    break
  fi
  echo "    Not ready yet (attempt ${attempt}/${MAX_ATTEMPTS}) —" \
    "waiting ${SLEEP_SECONDS}s..."
  sleep "${SLEEP_SECONDS}"
  attempt=$((attempt + 1))
done

VAULT_URL="https://${VAULT_NAME}.vault.azure.net/"

echo "==> Writing AZURE_KEY_VAULT_URL to '${ENV_FILE}'..."
if [[ -f "${ENV_FILE}" ]] && grep -q "^AZURE_KEY_VAULT_URL=" "${ENV_FILE}"; then
  # Replace the existing line via a temp file + mv, not `sed -i` — BSD
  # sed (macOS) and GNU sed (Linux CI runners) require incompatible
  # -i syntax, but both write to stdout identically without it.
  TMP_ENV_FILE="$(mktemp)"
  trap 'rm -f "${TMP_ENV_FILE}"' EXIT
  sed "s|^AZURE_KEY_VAULT_URL=.*|AZURE_KEY_VAULT_URL=${VAULT_URL}|" \
    "${ENV_FILE}" > "${TMP_ENV_FILE}"
  mv "${TMP_ENV_FILE}" "${ENV_FILE}"
else
  echo "AZURE_KEY_VAULT_URL=${VAULT_URL}" >> "${ENV_FILE}"
fi

echo "==> Done."
echo "    Vault URL: ${VAULT_URL}"
echo "    AZURE_KEY_VAULT_URL is now set in '${ENV_FILE}' (git-ignored,"
echo "    never committed)."
echo "    Next: push real secret values into the vault with"
echo "    key_vault_auto_pull.sh (see this script's header comment)."
