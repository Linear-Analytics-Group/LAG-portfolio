# PluginAssemblies Directory

This directory serves as the source-controlled container for unpacked Dataverse C# plugin assembly metadata and compiled binaries (`.dll`).

## Architectural Context & ALM Workflow

In a Dataverse Configuration-as-Code pipeline, plugin code is not treated as unmanaged loose files. Instead, plugin assemblies follow a structured lifecycle to maintain transactional integrity between the entity schema and server-side execution logic:

### 1. Registration & Metadata Generation

- C# plugin assemblies are compiled from source (`.csproj`) into a strong-named `.dll`.
- The assembly is registered in a development Dataverse environment via the Power Platform Plugin Registration Tool or VS Code Power Platform Tools extension.
- Event handlers (SDK Message Processing Steps) and class definitions (Plugin Types) are linked to target entities (e.g., `lagsol_inventory`).

### 2. Unpacking & Source Control (`pac solution unpack`)

When exporting and unpacking the unmanaged solution via `pac` CLI:

```bash
pac solution unpack --zipfile LAGInventorySync_Dev.zip --folder platform/src --packagetype Unmanaged
```

SolutionPackager extracts both the binary and its system registration declarations into this folder:

- **Assembly Binary (`.dll`):** The compiled C# assembly.
- **Assembly Metadata (`.xml`):** Defines the assembly name, version, culture, public key token, and custom plugin type mappings.
- **Step Definitions:** SDK message processing step registrations are output in parallel under `Other/Customizations.xml`.

### 3. Compilation & Solution Packing (`pac solution pack`)

During CI/CD build pipelines, `pac solution pack` compiles the XML schema and binary dependencies into a deployable solution artifact:

```bash
pac solution pack --folder platform/src --zipfile dist/LAGInventorySync.zip --packagetype Managed
```

The packer validates that every assembly in `PluginAssemblies/` matches a corresponding PluginType and SdkMessageProcessingStep declaration, ensuring atomic deployments across environments.

## Current Repository Architecture Note

This repository currently implements business rules, payload validations, and stream processing at the Python/OData data engine layer. This directory structure is maintained to ensure the platform schema remains forward-compatible with synchronous, in-process Dataverse server-side event execution if future low-latency requirements dictate C# plugin extensions.
