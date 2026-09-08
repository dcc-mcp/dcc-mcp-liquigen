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
    version: "0.2.0"  # x-release-please-version
    search-hint: "LiquiGen liquid VFX preset project inspect validate copy recipe nodes Unreal flipbook VAT Alembic OpenVDB export"
    tags: [pipeline, liquigen, unreal, vfx]
    tools: tools.yaml
---

# LiquiGen Project

Discover schemas with `list_node_schemas`, inspect a source with
`inspect_project_graph`, then write a new destination using
`apply_graph_transaction`. Use observed pin names. Transactions include graph,
parameter, keyframe, group, note and camera edits, and validate the readback.

For live operations, discover `list_host_commands` and use the fixed command
list through `invoke_host_command` or `run_host_sequence`. Keep the exact
PID/HWND binding. `run_export_workflow` opens a staged project and checks fresh,
stable output in a new empty directory.

`prepare_unreal_water_project` stages an installed official preset with
`export_profile: ue_vat` or `alembic`. Preserve the paired image exporter and
its output path; the supported host export interface can require it. The
source preset is a local input and is not included in an exported adapter.
`plan_liquid_chain_burst` supplies an optional graph-authoring example.

Use typed operations first and project-owned DCC-CUA for UI-only operations.
Never write projects in place or treat command acknowledgement as proof of a
completed export. Unsupported host interfaces return a compatibility error.
