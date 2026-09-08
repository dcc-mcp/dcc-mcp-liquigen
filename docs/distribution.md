# Distribution

The adapter is an unofficial, independent project. LiquiGen software, presets,
projects and license data are not included.

## Build profiles

- `vx just release` builds the public external-only archive: Python wheel,
  installer, compatibility manifest, receiver examples, license and checksums.
- `vx just local-release` also builds and includes the Windows command client
  and hook DLL for local host commands. These binaries are not in the public
  Python package.

Graph authoring, inspection and export validation work without a native command
bridge. Live project loading, playback and export require that bridge. The
companion menu invokes available typed tools for one bound instance.

The installer verifies every payload against `SHA256SUMS`. Native bridge
versions are stored under
`%LOCALAPPDATA%\dcc-mcp-liquigen\native\<bridge-content-id>`; `current.txt`
selects the installed generation. A running host can retain its loaded version.
Use `--hook-dll` or `DCC_MCP_LIQUIGEN_COMMAND_HOOK_DLL` for an explicit local path.

The manifest lists capabilities, supported formats, tested host versions and
recommended versions. Host compatibility uses process/window ownership and
interface probes, not a LiquiGen executable hash. Checksums verify adapter
payload integrity, not host compatibility.

## Contents and dependencies

Receiver entry points are documented in [examples](https://github.com/dcc-mcp/dcc-mcp-liquigen/tree/main/examples).
The VAT example requires a separately installed SideFX Labs material plugin.
The adapter does not download it or include vendor application data.

Keep locally generated projects, renders, exports, investigation notes and
machine configuration outside published source and packages. The public
profile excludes injected binaries and the experimental UIA provider DLL.

Adapter source is MIT licensed. LiquiGen is subject to
[JangaFX's terms](https://jangafx.com/legal/end-user-license-agreement).
