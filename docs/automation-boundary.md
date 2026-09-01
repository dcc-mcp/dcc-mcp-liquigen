# LiquiGen automation boundary

## Confirmed local surface

The tested LiquiGen 1.0.5 package contains the application, official presets,
templates, render resources, and licensing libraries. It does not contain a
documented SDK, script folder, plug-in bridge, or headless exporter. A running
instance does not expose a local TCP or UDP listener.

The `.liquigen` format is a tagged binary document with embedded thumbnail data.
The local decoder consumed every byte of the installed official project corpus,
resolved its reference records, and reproduced unchanged documents byte for
byte. The writer is still an experimental compatibility layer, not a published
JangaFX API.

## Supported routes

1. Use `list_node_schemas` to discover node types, parameter names, and observed
   input/output pins from the installed official projects.
2. Use `inspect_project_graph` for structured graph readback.
3. Use one `apply_graph_transaction` to create, clone, delete, configure,
   animate, connect, or disconnect nodes. Writes are new-path-only, validate
   observed pins, and reparse before success.
4. Use `open_project_path` and the fixed host-command whitelist for project
   loading, playback, export, graph framing, tabs, save, and command-palette
   activation. These commands execute on the exact LiquiGen UI thread without
   mouse, keyboard, or CUA.
5. Use `run_export_workflow` for the complete open, simulate, export, freshness,
   stability, and Unreal-bundle validation sequence. Its output directory must
   be new and empty so LiquiGen never enters an overwrite-confirmation path.
6. Use project-owned DCC-CUA only for optional visual viewport acceptance and
   recording, or a genuinely unexposed future widget.

Do not add a raw script executor, an adapter-local screenshot/input layer,
arbitrary memory access, or an arbitrary native-call surface. Never patch or
hook LiquiGen licensing or activation code. If JangaFX publishes a supported
SDK or CLI, prefer it after a versioned live acceptance test.

Official LiquiGen documentation describes project open/save and File > Export
All as editor operations; it does not document a script or headless export
surface. See the [UI reference](https://docs.jangafx.com/liquigen/pages/references/ui_reference.html)
and [getting-started guide](https://docs.jangafx.com/liquigen/pages/getting_started.html).
