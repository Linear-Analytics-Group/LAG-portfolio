# Azure Key Vault — provisioning scripts

Infrastructure-as-code for this service's optional Azure Key
Vault-backed secrets management (see the root `README.md`'s "Secrets
Management" section for the application-level design). Nothing here
reads, writes, or hardcodes an actual secret value — these scripts
only provision infrastructure and move already-configured local values
into the vault.

## Prerequisites

- Azure CLI (`az`), logged in (`az login`) with permission to create
  resource groups and Key Vaults in the target subscription.
- A local `.env` at the repo root (copy `.env.example` if you don't
  have one yet) with real `AZURE_TENANT_ID`/`AZURE_CLIENT_ID`/
  `AZURE_CLIENT_SECRET`/`DATAVERSE_URL` values, before pushing them
  into the vault.

## Usage

Run both from the repo root.

1. **Provision the vault** — creates a dedicated resource group, an
   RBAC-authorized Key Vault, grants your signed-in user
   `Key Vault Secrets Officer` on it, waits for that role assignment to
   actually take effect, and writes the resulting vault URL into your
   local `.env` as `AZURE_KEY_VAULT_URL`:

   ```bash
   ./infra/azure/key-vault/key_vault_init.sh \
       <resource-group> <vault-name> [location] [env-file]
   ```

2. **Push each connection value into the vault** — reads a value
   already in `.env` and stores it as a Key Vault secret (translating
   `ENV_VAR_NAME` to `env-var-name`, since Key Vault secret names
   can't contain underscores):

   ```bash
   for VAR in AZURE_TENANT_ID AZURE_CLIENT_ID \
              AZURE_CLIENT_SECRET DATAVERSE_URL; do
     ./infra/azure/key-vault/key_vault_auto_pull.sh <vault-name> "$VAR"
   done
   ```

All four are vault-backed, not just the client secret — see the root
`README.md`'s "Secrets Management" section for why the tenant ID,
client ID, and Dataverse URL are treated as sensitive too, even though
none of them are credentials on their own.

## What's deliberately not here

- No secret values, real resource names, or subscription identifiers —
  every example above uses generic placeholders.
- No automatic secret rotation or deletion tooling; these two scripts
  cover provisioning and one-time migration of a value into the vault,
  not ongoing secret lifecycle management.
