#!/usr/bin/env bash
set -euo pipefail

# Pushes a single value already present in a local .env file up into
# Azure Key Vault as a secret, translating ENV_VAR_NAME -> env-var-name
# (Key Vault secret names cannot contain underscores at all).
#
# The secret's actual value is never hardcoded here, and never passed
# to `az` as a literal --value argument — that would put it in this
# process's argument list, briefly visible to other local users via
# `ps aux` while the command runs. Instead it's read out of the .env
# file into a private, 0600-permissioned temp file that `az` reads
# directly via --file, deleted immediately afterward via a trap that
# fires even if the script exits early on error.
#
# Usage (run from the repo root):
#   ./infra/azure/key-vault/key_vault_auto_pull.sh \
#       <vault-name> <env-var-name> [env-file]
#
# Example (replace with your own vault name):
#   ./infra/azure/key-vault/key_vault_auto_pull.sh \
#       kv-example-dev AZURE_CLIENT_SECRET
#
# Once this succeeds, YOU may choose to also set AZURE_KEY_VAULT_URL
# and remove AZURE_CLIENT_SECRET from your own .env — but that's an
# optional, per-developer choice, not a requirement this creates for
# anyone else. The .env/plain-environment-variable path stays fully
# supported on its own for local dev without Azure access at all; this
# script only gives Key Vault a real value to serve to whoever *does*
# set AZURE_KEY_VAULT_URL (see README.md's Secrets Management section).

usage() {
  echo "Usage: $0 <vault-name> <env-var-name> [env-file]" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This script lives at infra/azure/key-vault/ — three levels below the
# repo root, where .env actually lives.
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

if [[ $# -lt 2 ]]; then
  usage
fi

VAULT_NAME="$1"
ENV_VAR_NAME="$2"
ENV_FILE="${3:-${REPO_ROOT}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Error: environment file '${ENV_FILE}' not found." >&2
  exit 1
fi

KV_SECRET_NAME="$(echo "${ENV_VAR_NAME}" | tr '_' '-')"

SECRET_VALUE="$(
  grep "^${ENV_VAR_NAME}=" "${ENV_FILE}" \
    | cut -d '=' -f2- \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
          -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
)"

if [[ -z "${SECRET_VALUE}" ]]; then
  echo "Error: '${ENV_VAR_NAME}' not found or empty in '${ENV_FILE}'." >&2
  exit 1
fi

TMP_SECRET_FILE="$(mktemp)"
trap 'rm -f "${TMP_SECRET_FILE}"' EXIT
chmod 600 "${TMP_SECRET_FILE}"
printf '%s' "${SECRET_VALUE}" > "${TMP_SECRET_FILE}"

echo "==> Pushing '${ENV_VAR_NAME}' from '${ENV_FILE}' to Key Vault" \
  "'${VAULT_NAME}' as '${KV_SECRET_NAME}'..."

az keyvault secret set \
  --vault-name "${VAULT_NAME}" \
  --name "${KV_SECRET_NAME}" \
  --file "${TMP_SECRET_FILE}" \
  --output none

echo "==> Done. '${KV_SECRET_NAME}' is now stored in '${VAULT_NAME}'."
echo "    You can now remove '${ENV_VAR_NAME}' from '${ENV_FILE}' and set"
echo "    AZURE_KEY_VAULT_URL instead."
