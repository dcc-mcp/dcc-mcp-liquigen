# Contributing

Thank you for helping improve `dcc-mcp-liquigen`.

## Development setup

The repository uses [vx](https://github.com/loonghao/vx) to provide a
reproducible Python, uv, and just environment:

```powershell
vx setup
vx just check
```

`vx just check` runs Ruff, the Python tests, and both Windows native bridge
test suites. Pull requests that cannot run a licensed LiquiGen host should
still pass the complete mock and packaging gates and state the remaining live
host validation boundary.

## Changes

- Keep host operations behind typed DCC-MCP tools.
- Preserve source `.liquigen` files; write graph changes to a new destination.
- Do not commit LiquiGen executables, libraries, presets, projects, license
  files, exported media, Unreal assets, or locally built bridge binaries.
- Add or update tests for behavior changes.
- Use concise English Conventional Commit messages.

Run the public package build before submitting a release-related change:

```powershell
vx just build
```

## Pull requests

Describe the user-visible behavior, the exact validation commands run, and any
remaining LiquiGen or Unreal live-host acceptance gap. Report shared CLI,
gateway, or catalog changes separately in `dcc-mcp-core`.
