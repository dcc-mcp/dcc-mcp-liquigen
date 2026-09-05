---
name: liquigen-project
description: >-
  Inspect and transactionally edit bounded LiquiGen projects, discover official
  node schemas and presets, compile replayable liquid recipes, and validate
  LiquiGen exports for Unreal handoff.
license: MIT
compatibility: "Python 3.9+, LiquiGen version-advisory interface probing, dcc-mcp-core 0.20.22+"
allowed-tools: "python"
metadata:
  dcc-mcp:
    dcc: liquigen
    layer: domain
    version: "0.3.0"  # x-release-please-version
    search-hint: "LiquiGen liquid VFX preset project inspect validate copy recipe nodes Unreal UE 5.8 flipbook VAT Alembic OpenVDB export"
    tags: [pipeline, liquigen, unreal, vfx]
    tools: tools.yaml
---

# LiquiGen Project

Use these typed tools as the primary graph-control route. `list_node_schemas`
discovers version-local node types, parameters, and pin names from installed
official projects. `inspect_project_graph` returns structured nodes, keyframes,
and connections. `apply_graph_transaction` creates, clones, deletes,
configures, animates, clears animation, connects, and disconnects nodes in one
all-or-nothing write to a new project path. New connections must use observed
source and target pins. The tool validates a complete readback and never
overwrites an existing file.

The same graph transaction surface creates, updates, and deletes groups and
notes, updates existing project settings, and selects an existing camera. Use
these semantic operations for node layout and wiring; do not drag ports through
pixel input.

Use `list_host_commands` and `invoke_host_command` for the live host operations
that LiquiGen exposes through its own named command set. The local bridge runs
inside the exact PID/HWND UI thread and currently maps project open/save,
timeline play/pause, export all/selected, and command palette activation. It
does not synthesize mouse or keyboard input, require CUA, accept arbitrary
command names, or touch licensing state. A command result proves delivery to
the host command set; inspect the saved project or export bundle separately to
prove the operation completed. Prefer `run_export_workflow` for production
handoff: it opens the exact project, simulates, exports, waits for changed files
to stabilize, requires the canonical output assets to be fresh, and validates
the Unreal bundle in one bounded call. Always configure and pass a new empty
output directory; the workflow rejects previous outputs instead of accepting an
overwrite dialog.

Use `plan_liquid_chain_burst` to produce a deterministic, numbered node recipe,
showcase chapter list, export choice, and Unreal material/Niagara contract. The
planner is read-only; compile its steps into one `apply_graph_transaction`
request, then inspect the destination graph before opening it in LiquiGen.

For an official water showcase, use `prepare_unreal_water_project` with a preset
path returned by `discover_presets`. It preserves the official simulation,
collider, camera, and appearance parameters, disables the preset's image export,
and adds one canonical Unreal VAT exporter. The generated group and note expose
the bridge steps in LiquiGen's node graph. The source must remain inside the
installed official preset directory; never bundle or redistribute that source.

For a game-ready liquid surface, prefer LiquiGen's Unreal VAT export. Use
Alembic for cinematic geometry, EXR/PNG flipbooks for inexpensive billboard
fallbacks, and OpenVDB only as auxiliary velocity data. LiquiGen does not
simulate combustion, so describe this recipe as a liquid chain burst rather
than fire or smoke.

The locally investigated LiquiGen package has no confirmed public scripting
SDK, plug-in API, or headless exporter. Compatibility is therefore discovered
from node type, parameter, pin, command-name, and bounded host-interface
signatures; no executable hash is used. If a requested interface is absent,
fail with an installed-version compatibility error. The transactional graph
route does not require an interactive desktop. Use project-owned DCC-CUA only
for optional viewport acceptance and recording, or an editor action that has
not yet gained a semantic interface.

Do not use raw scripting or adapter-local screenshot/input layers. Never write
in place, touch licensing state, or accept an unvalidated project readback.
