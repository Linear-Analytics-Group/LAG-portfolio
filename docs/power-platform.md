← [Back to README](../README.md)

# Power Platform Solution: Configuration-as-Code Schema

`platform/power-platform/LAGInventorySync/` is the Dataverse schema
this sync engine writes to, held as version-controlled source rather
than only existing inside a Dataverse environment. It defines one
entity, `lagsol_InventoryItem`, with the entity set
`lagsol_inventoryitems` and three fields the sync engine addresses
directly: `lagsol_skuid` (the alternate key every upsert targets),
`lagsol_name`, and `lagsol_unitprice`. This schema and the sync
engine's own field-mapping constants
(`runners.dataverse.DEFAULT_ENTITY_SET`/`DEFAULT_ALTERNATE_KEY_FIELD`/`DEFAULT_FIELD_MAPPING`)
are checked against each other directly by
`tests/acceptance/test_power_platform_schema.py`, which parses the
real `Entity.xml` — a schema change on either side that isn't
mirrored on the other fails locally, without needing a live Dataverse
environment to surface it.

This repository prioritizes a pure `pac` CLI solution packing strategy
over `.cdsproj` MSBuild wrappers to maintain a clean, language-agnostic
schema layer tailored for Python/OData data engine integration. The
solution structure is forward-compatible with Dataverse extensibility
standards: server-side C# plugin assemblies could be integrated into
the deployment pipeline by outputting compiled binaries directly into
the solution's assembly path — see `src/PluginAssemblies/` for where
that would land, reserved and documented, not wired up today.

`src/` holds the unmanaged, dev-authored schema source —
`pac solution pack --folder src --zipfile dist/LAGInventorySync.zip
--packagetype Unmanaged` reproduces the deployable unmanaged solution
locally, for re-importing into a dev/sandbox environment. `pac solution
unpack` is its inverse, for pulling a schema change made in the Maker
Portal back into version control. Neither command needs a `.cdsproj`,
MSBuild, or a NuGet restore step — `pac` operates on the `src/` folder
directly.

A managed solution — the sealed, non-editable form required for every
environment downstream of dev (test, UAT, production) — is exported
directly from the live Dataverse environment
(`pac solution export --managed true`) as a release-pipeline step, not
repacked locally from the unmanaged source: Dataverse itself seals the
managed layer server-side at export time. That zip is a build
artifact, not committed here (see this directory's `.gitignore`) — the
same treatment this repo already gives every other built artifact
(wheels, lock files): generated on demand from the one source of truth
that *is* committed.

---

← [Back to README](../README.md)
