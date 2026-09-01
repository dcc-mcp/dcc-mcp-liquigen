# Distribution

This repository ships an **unofficial external adapter**. It is not affiliated
with or endorsed by JangaFX.

## Local evaluation bundle

Build the complete local evaluation bundle with:

```powershell
vx just local-release
```

The resulting
`dcc-mcp-liquigen-<version>-local-native-windows-x64.zip` contains:

- the Python wheel;
- a `vx uv tool install` installer;
- a machine-readable compatibility manifest;
- the original semantic command client and hook DLL needed for native project
  loading, playback, export, and fresh-bundle orchestration;
- the accessible exact-window companion-menu command;
- the UE 5.8 VAT/flipbook receiver source project and its DCC-MCP skill/tool catalog;
- package SHA-256 checksums;
- this notice and the adapter's MIT license.

Every included payload has its own entry in `SHA256SUMS`. These checks protect
the adapter package itself; LiquiGen host compatibility still never uses an
executable hash. The installer places each local command bridge generation
under `%LOCALAPPDATA%\dcc-mcp-liquigen\native\<bridge-content-id>` and atomically
updates `current.txt`. A running host may retain its loaded generation while a
new host discovers the update, without a persistent environment variable.

Build the public-candidate, external-only profile with `vx just release`. Its
archive omits both native bridge binaries and advertises
`host_command_bridge_included: false`; graph authoring, inspection, companion
menu, and export validation remain available, but live host workflows do not.

The wheel includes the experimental tagged-document graph API. Repository
publication does not authorize redistributing LiquiGen software, presets,
projects, exports, licenses, or locally built bridge binaries.

The manifest also publishes the typed bridge capability list and the Unreal
handoff roles (`ue_vat`, `alembic`, `flipbook`, and auxiliary VDB velocity), so
installers and agents can discover the pipeline without parsing prose.

The host match is deliberately version-advisory. The adapter checks the exact
process name (`LiquiGen.exe`), native-window ownership, and named interface
contracts. It does **not** require or record a LiquiGen executable hash. An
untested LiquiGen version may run when those interfaces match. The manifest
keeps locally tested versions separate from the current recommended release
(1.7.1). If an interface probe fails, diagnostics recommend that release.

Package checksums remain mandatory because they verify that the adapter archive
was not corrupted or replaced; they are unrelated to LiquiGen compatibility.

## Public-release boundary

The public Python release is source/external-only. It must not contain:

- LiquiGen executables, libraries, presets, project files, or license data;
- licensing, protection-bypass, or vendor-modification payloads;
- the experimental in-process UIA provider DLL.

The graph writer is documented as an unofficial compatibility layer and is
tested with synthetic fixtures. Installed official presets are accepted only
as local inputs and are never copied into the repository or package.

The native UIA source in this development workspace is an original provider
contract that attaches only to a window owned by its own process. Publishing a
LiquiGen-specific injected build requires a documented vendor integration path
or written permission first.

The Python companion menu is part of the adapter wheel. It owns its window,
binds an exact LiquiGen PID/HWND and MCP instance UUID, and invokes only a fixed
typed-tool catalog. It is not an injected payload.

JangaFX's current EULA restricts redistribution of its software, reverse
engineering, modification, and tampering. Review the authoritative
[JangaFX EULA](https://jangafx.com/legal/end-user-license-agreement) before any
public release. The normal UI and export workflow is documented in the
[official LiquiGen documentation](https://docs.jangafx.com/liquigen/pages/getting_started.html).

This note is an engineering release boundary, not legal advice.
