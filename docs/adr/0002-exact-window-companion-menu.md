# ADR 0002: Exact-window DCC-MCP companion menu

- Status: accepted for local prototype
- Date: 2026-08-31

## Context

LiquiGen 1.0.5 exposes a custom-rendered application surface, and its public
documentation does not describe a supported plug-in or menu-extension API. The
existing `liquigen-uia-bridge` prototype is deliberately same-process: it can
publish semantic UIA nodes only for a window owned by its own process and is not
a LiquiGen loader or injector.

We want a visible DCC-MCP control surface without modifying LiquiGen, relying on
private implementation details, or routing arbitrary code from a menu click.

## Decision

Ship an external `dcc-mcp-liquigen-menu` companion process. It owns a standard
Windows menu, follows one exact LiquiGen top-level window, and is identified as
`DCC-MCP · LiquiGen`. The companion is visually attached but is not an
in-process LiquiGen menu.

The companion must:

1. bind a full DCC-MCP instance UUID to one exact LiquiGen PID and HWND;
2. verify the executable name and HWND ownership at startup and before actions;
3. close when its target HWND disappears or changes owner;
4. expose standard accessible Windows menu controls from its own process;
5. invoke only a compiled action catalog through `dcc-mcp-cli`, with
   `shell=False` and bounded JSON arguments;
6. keep project/export paths explicit and subject to the adapter's configured
   allowed roots;
7. never inject, detour, subclass, patch, or synthesize input into LiquiGen.

The initial action catalog is:

| Menu action | DCC-MCP tool |
| --- | --- |
| Bridge Status | `get_status` |
| Discover Presets | `discover_presets` |
| Inspect Project | `inspect_project` |
| Validate Project for Unreal | `validate_project` |
| Stage Project Copy | `stage_project_copy` |
| List Node Schemas | `list_node_schemas` |
| Inspect Project Graph | `inspect_project_graph` |
| Build Chain Burst Project | `create_liquid_chain_burst_project` |
| Plan Chain Burst | `plan_liquid_chain_burst` |
| Validate Unreal Export | `validate_unreal_export_bundle` |

## Consequences

The menu remains compatible across LiquiGen versions as long as the process
name, native-window ownership, and named DCC-MCP interfaces still match. It can
be distributed with our Python adapter code because it contains no LiquiGen
binary, preset, injected DLL, or reverse-engineered writer.

It can create a new project containing node and connection changes through the
transactional document API. It cannot mutate the graph already resident in a
running LiquiGen process or press custom-rendered controls. Live commands remain
deferred until a stable command endpoint is exposed or JangaFX documents an
extension API.
