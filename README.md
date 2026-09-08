# dcc-mcp-liquigen

Unofficial DCC-MCP adapter for LiquiGen. Inspect and edit project graphs,
execute supported host commands, and validate exported assets.

## Capabilities

- Discover installed presets and node schemas.
- Inspect nodes, parameters, animation and connections.
- Apply validated graph transactions to a new project file.
- Open projects and run bounded playback, save and export commands.
- Validate VAT, Alembic and image export bundles.

Host operations bind to one exact LiquiGen process and window. Graph writes
preserve the source file and validate the resulting document. Unsupported
interfaces return a compatibility error; this is not a vendor-supported SDK.

## Install and run

Install LiquiGen separately, then install the adapter:

```powershell
uv tool install dcc-mcp-liquigen
```

Attach to a running LiquiGen instance:

```powershell
dcc-mcp-liquigen --pid <PID> --window-handle <HWND> `
  --executable <ABSOLUTE-LIQUIGEN-EXE> --version <VERSION> `
  --allowed-root <ABSOLUTE-WORKSPACE>
```

With a locally built native command bridge, the standalone launcher can start
LiquiGen and bind its window:

```powershell
dcc-mcp-liquigen-launch --executable <ABSOLUTE-LIQUIGEN-EXE> `
  --hook-dll <ABSOLUTE-HOOK-DLL> --allowed-root <ABSOLUTE-WORKSPACE>
```

`DCC_MCP_LIQUIGEN_COMMAND_HOOK_DLL` can also select the hook for an attached
instance. Pass the detected application version with `--version`, or set
`DCC_MCP_LIQUIGEN_VERSION`. Public packages do not include native bridge binaries;
see [distribution](docs/distribution.md) for build profiles.

Use `dcc-mcp-cli list`, then `search`, `describe` and `call` to discover tools.
The optional `dcc-mcp-liquigen-menu` command provides an external companion menu
for a bound instance; it is not a native LiquiGen menu.

## Examples and development

- [Examples](examples/README.md): export preparation and Unreal receivers.
- [Automation contract](docs/automation-boundary.md).
- [Contributing](CONTRIBUTING.md): build and test instructions.
- [UI bridge contract](docs/semantic-ui-bridge.md).

```powershell
vx setup
vx just check
vx just build
```

## License

Adapter source is available under the [MIT License](LICENSE). LiquiGen is a
separate commercial product. Vendor software, presets, projects and licenses
are not included. This project is not affiliated with or endorsed by JangaFX.
