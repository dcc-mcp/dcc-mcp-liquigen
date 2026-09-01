# dcc-mcp-liquigen

Unofficial, local-first DCC-MCP adapter for LiquiGen. It exposes typed,
transactional operations for `.liquigen` node graphs, drives a fixed set of
host commands against one exact LiquiGen process/window, and validates
LiquiGen-to-Unreal export bundles.

This repository contains no LiquiGen software, presets, projects, license data,
or generated assets. LiquiGen and its official examples remain user-installed
inputs and are subject to JangaFX's terms.

## Water workflow for Unreal Engine 5.8

The primary first-release workflow starts from an official water preset in the
user's installed LiquiGen preset directory, such as `ball_drop_splash.liquigen`.
The adapter writes a new project rather than changing the read-only preset,
preserves the preset's water simulation and appearance settings, and adds an
Unreal-targeted Vertex Animated Texture (VAT) export path.

`prepare_unreal_water_project` records source provenance, configures the mesh
export for Unreal VAT, connects the simulation mesh through typed graph pins,
and keeps the output directory explicit. `run_export_workflow` then loads the
exact staged project, drives named playback/export commands, waits for fresh
stable files, and validates the canonical VAT bundle before UE handoff.

For UE 5.8 hosts where the SideFX Dynamic Remeshing material produces an empty
surface, `author_procedural_water_cascade` and `stage_water_cascade` provide a
UE-native Niagara/translucent-material fallback. It preserves the real
LiquiGen graph timing and export provenance while avoiding a version-specific
VAT shader parameter mismatch.

The repository includes a UE 5.8 receiver for the VAT FBX, animation textures,
and metadata, plus a flipbook fallback. Automated tests cover graph mutation,
bundle validation, host binding, and receiver contracts. A passing CI run does
not replace visual acceptance in licensed LiquiGen and Unreal hosts; the
official water preset end-to-end viewport result is tracked as a live release
gate.

The earlier procedural chain-burst recipe remains available as a secondary
graph-authoring example. It is no longer the primary showcase or the visual
acceptance target.

## Typed automation surface

- `list_node_schemas` discovers installed node types, parameters, and observed
  pins from local projects.
- `inspect_project_graph` returns nodes, parameters, keyframes, and
  connections.
- `apply_graph_transaction` creates, clones, deletes, configures, animates,
  connects, and disconnects nodes, and manages groups, notes, project settings,
  and the active camera in one all-or-nothing write.
- `prepare_unreal_water_project` stages an installed official water preset to a
  new path and adds a validated Unreal VAT export route.
- `open_project_path` uses LiquiGen's project loader for one exact project.
- Fixed host commands expose playback, export, graph framing, tabs, save, the
  project palette, and the command palette without raw pointer/keyboard input.
- The MCP instance is bound to the exact LiquiGen PID/HWND and becomes
  unroutable when that identity is no longer live.

Graph writes never overwrite an existing file. Connections are checked against
observed node/pin signatures and every completed write is reparsed before it is
reported as successful. LiquiGen version matching is advisory: compatibility
uses the `LiquiGen.exe` name, exact window ownership, and named interface probes
rather than a host executable hash.

CUA is not required for graph authoring, project loading, playback, export, or
bundle validation. Project-owned DCC-CUA is reserved for optional visual
viewport acceptance and recording when a typed host operation cannot provide
that evidence.

## Local development

```powershell
vx setup
vx just check
vx just build
```

`vx.toml` owns the Python, uv, and just versions. `justfile` is the single entry
point for Python and native bridge checks. The native lane uses the installed
Windows CMake/MSVC environment through `vx --use-system-path`.

Install the current source checkout for local evaluation:

```powershell
vx uv tool install .
```

Start LiquiGen, resolve its exact PID and HWND, then launch the adapter:

```powershell
vx uv run dcc-mcp-liquigen `
  --pid <PID> `
  --window-handle <HWND> `
  --executable <ABSOLUTE-LIQUIGEN-EXE> `
  --version <DETECTED-VERSION> `
  --allowed-root <ABSOLUTE-WORKSPACE>
```

Use `dcc-mcp-cli list`, followed by `search -> describe -> call`. Until the
LiquiGen catalog registration lands in `dcc-mcp-core`, the package entry point
can be used directly from this checkout.

## Companion menu

The adapter includes an accessible external companion menu. It follows one
exact LiquiGen window and invokes only the adapter's typed bridge tools. It does
not claim to be a native LiquiGen menu:

```powershell
vx uv run dcc-mcp-liquigen-menu `
  --pid <PID> `
  --window-handle <HWND> `
  --instance-id <FULL-INSTANCE-UUID> `
  --version <DETECTED-VERSION> `
  --project-path <ABSOLUTE-LIQUIGEN-PROJECT> `
  --export-path <NEW-ABSOLUTE-EXPORT-DIRECTORY>
```

See [the distribution boundary](docs/distribution.md),
[the automation boundary](docs/automation-boundary.md),
[the semantic UI bridge contract](docs/semantic-ui-bridge.md), and
[the UE 5.8 workflow](docs/ue-5.8-workflow.md). Architecture decisions are
recorded under [docs/adr](docs/adr).

## Project status

`0.1.0` is an alpha integration. The tagged-document graph writer and named
command bridge are compatibility layers, not a vendor-supported LiquiGen SDK.
Keep source projects immutable, retain exact application-version evidence, and
verify output in the target DCC before production use.

## License

Adapter source is available under the [MIT License](LICENSE). LiquiGen is a
separate commercial product. This project is not affiliated with or endorsed
by JangaFX.
