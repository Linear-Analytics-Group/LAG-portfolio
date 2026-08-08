← [Back to README](../../README.md) · [All docs](../README.md)

# Design Decisions: Configuration & Secrets

How settings are composed, why configuration values are constructor-
injected rather than read ad hoc from the environment, how secrets
escalate from a plaintext `.env` to Azure Key Vault, and why config
validation checks format, not just presence.

## Table of Contents

- [Settings Composition via Mixins](#settings-composition-via-mixins)
- [Constructor Injection vs. Environment Bloat](#constructor-injection-vs-environment-bloat)
- [Secrets Management: Azure Key Vault vs. Plain `.env`](#secrets-management-azure-key-vault-vs-plain-env)
- [Config Validation: Format Checks, Not Just Presence Checks](#config-validation-format-checks-not-just-presence-checks)

## Settings Composition via Mixins

`InventorySyncSettings` (in `services/inventory-sync-engine/config.py`)
adds no fields of its own — it composes two `lag-service-kit` mixins:

```python
class InventorySyncSettings(DataverseConnectionSettings, BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=find_repo_env_file(Path(__file__)),
        ...
    )
```

- `DataverseConnectionSettings` — `azure_tenant_id`, `azure_client_id`,
  `azure_client_secret`, `dataverse_url`, with whitespace- and
  trailing-slash-stripping validators. Any future service that talks to
  Dataverse mixes this in rather than redeclaring the same four fields.
- `BaseServiceSettings` — `log_level`, shared by every service regardless
  of destination system.
- `find_repo_env_file(Path(__file__))` walks upward from the calling
  module looking for a `.env` file, mirroring `python-dotenv`'s discovery
  behavior — a service finds its repo-root `.env` without hardcoding how
  many directories separate it from that root.

Missing or empty required fields raise `pydantic.ValidationError` with a
field-by-field report, caught once in `BaseSyncRunner.run()` (not by the
service's own `main()`, which has no error handling of its own) and
logged.

## Constructor Injection vs. Environment Bloat

During the design of the deduplication pipeline, we weighed two
approaches for handling variable business keys (e.g., `sku_id`):
driving the key dynamically via `.env` (e.g., `DEDUPE_KEY=item_sku`)
vs. injecting the dependency/key via Python constructors.

We chose **Constructor Injection** at the service layer for three
critical enterprise reasons — a decision that has since generalized
beyond `dedupe_key` to every tunable in `defaults.py`
(`DEFAULT_MAX_WORKERS`, `DEFAULT_CHUNK_SIZE`,
`DEFAULT_WRITE_WINDOW_SIZE`, `DEFAULT_FAILURE_THRESHOLD`), each
overridable the same way and never read from the environment:

1. **Separation of Concerns (Domain vs. Environment):** Environmental
   variables (`.env`) should govern deployment-specific secrets,
   endpoints, and log levels. A deduplication key is a fundamental
   business domain rule bound to the database schema — and a
   concurrency limit, chunk size, or failure threshold is an
   operational tuning decision a code reviewer should see change in a
   diff, not one silently flipped in a deployment's environment.
   Exposing either kind to `.env` would allow operational environments
   to change core sync behavior without a formal code review or
   deployment pipeline.
2. **Preventing Framework Pollution:** Forcing the generic
   `BaseSyncRunner` in the scaffolding kit to store and expose
   stateful configurations violates the Dependency Inversion
   Principle. By keeping our scaffolding stateless and injecting
   dependencies through the service constructors, we keep our core
   orchestration engine incredibly lightweight and testable.
3. **Fully Isolated Unit Testing:** Constructor injection guarantees that we
   can instantiate the sync runners in a local test suite and inject
   mock schemas, mock configurations, and lightweight in-memory
   DataFrames instantly, without mocking global environment variables
   or loading `.env` files.

## Secrets Management: Azure Key Vault vs. Plain `.env`

A plaintext, git-ignored `.env` file is adequate for a solo
developer's local machine, but not on its own for a service meant to
demonstrate enterprise-grade secrets handling: a plaintext file is one
accidental `git add -f`, shared support ticket, or backup away from
leaking a live credential — a real risk for `AZURE_CLIENT_SECRET`, the
Entra ID app registration's credential. Azure Key Vault closes that
gap as an optional, non-breaking upgrade layered on top of the same
`.env` path.

**Two separate identities are in play here, easy to conflate:** the
Entra ID app registration (service principal) that authenticates *to
Dataverse* via MSAL, versus whatever identity is allowed to *read the
secret out of Key Vault* in the first place — your own Azure AD user
locally (`az login`), or a Managed Identity if this ever ran inside
Azure. `azure.identity.DefaultAzureCredential` resolves the second
one transparently, trying a chain of credential sources in order, so
the exact same code path handles both without branching on where it's
running.

**The mechanism:**
`lag_service_kit.azure_key_vault.AzureKeyVaultSettingsSource` is a
`pydantic_settings.PydanticBaseSettingsSource` — the same extension
point `BaseSettings` already uses internally for environment variables
and `.env` — added via
`BaseServiceSettings.settings_customise_sources()` only when
`AZURE_KEY_VAULT_URL` is actually set as a real environment variable
(checked via `env_settings()`, not a raw `os.environ` read, so it
reuses this class's own case-sensitivity/encoding configuration
instead of duplicating it). Priority, highest wins: a real environment
variable, then Key Vault, then `.env`. Unconfigured, Key Vault is
absent from the resolution chain entirely — not merely empty — so it
costs nothing and changes nothing for a deployment that never sets
`AZURE_KEY_VAULT_URL`. This is an optional upgrade, not a requirement;
the `.env`-only path stays fully supported for local dev without Azure
access at all.

**All four Dataverse connection values are vault-backed, not just the
client secret** — declared via `vault_secret_fields` on
`DataverseConnectionSettings`. The tenant ID, client ID, and Dataverse
URL aren't credentials on their own, but in a *public* repository they
are real reconnaissance value: together they identify exactly which
Entra ID tenant and live Dataverse environment this points to, a
specific target for phishing or consent-phishing against this exact
app registration, even though none of the three would authenticate
anything by itself.

**Provisioning is infrastructure-as-code**, not a manual portal
click-through — see `infra/azure/key-vault/` for the scripts that
create the vault (RBAC-authorized, not the legacy access-policy
model), grant the minimum role needed, and push values in. Every
example in that directory uses placeholder names; no real resource
names or subscription identifiers appear in this repository.

## Config Validation: Format Checks, Not Just Presence Checks

A value's presence is not enough for validation. A value could be
non-empty and still nonsensical: a `LOG_LEVEL` typo, a
`DATAVERSE_URL` missing its `https://` scheme, or an
`AZURE_TENANT_ID` that isn't a real GUID.

```
settings accepted log_level: 'NOT_A_REAL_LEVEL'
downstream issue at runtime: ValueError Unable to configure root logger
```

That `ValueError` is raised deep inside
`lag_service_kit.logging.configure_logging()`, not by pydantic — and
critically, `pydantic.ValidationError` does **not** catch a plain
`ValueError` (it's a subclass of `ValueError`, not the reverse).
Without specific `except` clauses in `BaseSyncRunner.run()` these
errors would simply be logged as "Unexpected error during sync" —
the same miscategorization problem "Ingest Validation" (see
[Data Pipeline](data-pipeline.md)) solves for bad source data, but here
for a typo'd `.env` value.

**Three targeted `field_validator`s, not one generic check:**

* `BaseServiceSettings._validate_log_level` checks `log_level`
  against a fixed set of real `logging` level names
  (`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`), normalizing to
  uppercase. The valid set is written out explicitly rather than
  introspected from `logging`'s internals (`logging._nameToLevel` is
  a private, underscore-prefixed implementation detail, not public
  API) — this way the validator's behavior can't shift under a future
  Python version that renames or restructures that private mapping.
* `DataverseConnectionSettings._validate_guid` checks
  `azure_tenant_id`/`azure_client_id` are syntactically valid GUIDs
  via the standard-library `uuid.UUID(value)`, no new dependency.
* `DataverseConnectionSettings._validate_https_url` checks
  `dataverse_url` parses to an absolute `https://` URL with a real
  host, via the standard-library `urllib.parse.urlparse`.

**Why three small validators instead of one that branches on field
name:** each check is conceptually distinct — a closed set of level
names has nothing to do with GUID syntax, which has nothing to do
with URL structure — so each gets its own single-purpose function,
matching this codebase's existing `_strip_whitespace` /
`_strip_trailing_slash` split in the same two classes. A validator
shared across fields is reserved for logic that's genuinely identical
regardless of which field it runs against (like whitespace-stripping
already is); branching internally on `info.field_name` to run
different logic per field would combine unrelated checks into one
function body, harder to read and to test in isolation.

**A consequence worth naming:** strict GUID validation means any
`DataverseConnectionSettings`/`InventorySyncSettings` test fixture
must use a syntactically valid GUID
(`"12345678-1234-1234-1234-123456789abc"`-style) for
`azure_tenant_id`/`azure_client_id`, never an arbitrary placeholder
string like `"tenant-id"` — a fixture-authoring constraint, not a
design compromise.

---

← [Back to README](../../README.md) · [All docs](../README.md)
