# LiquiGen 1.0.5 local interface evidence

Investigated on Windows using a locally installed LiquiGen 1.0.5 package. The
bound application executable was `LiquiGen.exe`; machine-specific package and
workspace paths are intentionally omitted.

| Surface | Local result | Adapter decision |
| --- | --- | --- |
| Documented CLI/headless exporter | Not found in package help, package layout, or official docs | Do not claim or emulate one |
| TCP/UDP automation listener | No listener owned by the live LiquiGen PID | Do not invent a socket bridge |
| SDK/plugin/script directory | Not present in the resolved 1.0.5 package | No vendor-provided in-process host bridge |
| Process/runtime family | Native x64 SDL/OpenGL; no UE, Unity, Mono, or IL2CPP runtime loaded | UE4SS and BepInEx cannot be reused directly |
| `LG.dll` exports | One `Auth` export; no authoring/export ABI | Treat licensing as out of scope; do not hook it |
| Windows UI Automation | Custom-rendered content lacks a useful semantic tree | Test a bounded server-side UIA provider before any local attachment |
| `.liquigen` project | Tagged binary; all installed official files parsed exactly and unchanged round-trips were byte-identical | Experimental bounded writer, new destinations only, mandatory reparse |
| Official presets | 49 project files in the resolved package | Discover and stage byte-identical non-overwriting copies |
| Node graph authoring | Internal names include node, pin, parameter, and project serialization operations | Transactional document API for create/clone/delete/parameters/keyframes/connections |
| Generated project host load | Independent LiquiGen process logged `load project` and remained responsive | Host accepted the authored graph; retain version evidence |
| Named host commands | Static consumer discovery plus live UI-thread delivery | Fixed whitelist exposes load, playback, export, graph framing, tabs, save, and command palette without CUA |
| Native project load | Exact path passed to the resolved project loader; loader returned success | `open_project_path` avoids the file dialog and proves host consumption |
| Live simulation/export trigger | Consumer-acknowledged `play`, `pause`, and `export-all` produced a fresh six-file, 64-frame VAT bundle | `run_export_workflow` requires a new empty directory, then waits for canonical assets, stability, and validation |
| Unreal interchange | Flipbook, VAT/FBX, Alembic, VDB and related export nodes | Validate a bounded bundle; UE viewport/PIE remains the final gate |

The first A/B acceptance asset used an official flipbook project. The current
chain-burst acceptance asset is a canonical LiquiGen VAT bundle containing FBX,
lookup/position/rotation EXRs, metadata, and a rasterizer preview. VAT remains
the primary UE runtime surface; flipbook and Alembic remain supported fallbacks.

The native contract harness under `native/liquigen-uia-bridge` attaches only to
its own test window. It validates a COM UIA tree containing stable
`AutomationId` values and proves that `Value.SetValue` and `Invoke.Invoke` are
marshalled back to the window's UI thread. It is not evidence that the same
tree has been populated from, or loaded into, LiquiGen.
