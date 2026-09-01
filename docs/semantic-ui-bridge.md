# LiquiGen semantic UI bridge

## Purpose

The bridge turns a bounded, application-owned semantic model into a standard
Windows UI Automation provider. DCC-CUA and the DCC-MCP `ui-control` Skill can
then locate controls by `AutomationId`, inspect their current state, and invoke
supported patterns without coordinate clicks.

Windows `uiAccess=true` is not part of this design. That manifest flag changes
which integrity levels an automation client may drive; it does not expose
semantics for a custom-rendered target.

## Coverage contract

| LiquiGen surface | Preferred UIA pattern or command | Expected coverage |
| --- | --- | --- |
| Buttons and menu items | `Invoke` | Deterministic |
| Text, paths, numeric fields | `Value` / `RangeValue` | Deterministic after field mapping |
| Tabs, lists, dropdowns, node selection | `Selection` / `SelectionItem` | Deterministic after collection mapping |
| Checkboxes and switches | `Toggle` | Deterministic |
| Export progress | `RangeValue` plus property-change events | Observable |
| Node graph connections | Typed `graph.connect` command | Do not emulate as a blind drag |
| Curve and timeline editing | Typed keyframe commands | Do not reduce to raw pointer paths |
| Viewport camera and gizmos | Typed transform/camera commands | Pixel interaction is fallback only |
| Future unknown custom widgets | No implicit support | Fail closed until mapped and tested |

The intended result is complete automation of agreed production workflows, not
an unsupported claim that every current and future pixel is automatically a
semantic control.

## Native ABI v1

`native/liquigen-uia-bridge/include/liquigen_uia_bridge.h` exposes four C ABI
functions:

1. `LgUiaBridgeAbiVersion` reports the exact ABI.
2. `LgUiaBridgeAttach` attaches only to a window owned by the current process
   and only from that window's UI thread.
3. `LgUiaBridgePublish` atomically publishes one validated semantic generation.
4. `LgUiaBridgeDetach` removes the provider on the owning UI thread.

Every snapshot must have unique node IDs and automation IDs, exactly one root,
valid parent links, no cycles, bounded strings, finite rectangles, and a
strictly increasing generation. Stale provider objects return
`UIA_E_ELEMENTNOTAVAILABLE`.

`Invoke`, `SetValue`, and `SetFocus` requests arriving on COM worker threads are
posted to the owning window and dispatched through bounded callbacks on the UI
thread. The bridge exposes no arbitrary address invocation, raw memory access,
process injection, or licensing hook.

## Local contract test

Run the complete contract with project-managed runtimes:

```powershell
vx just native-test
```

The current test loads the bridge into a window created by the test executable,
publishes `export.directory` and `export.now`, discovers both through the real
Windows UI Automation client, calls `Value.SetValue` and `Invoke.Invoke`, and
verifies that both callbacks ran on the window thread.

This test deliberately does not load the DLL into LiquiGen. Any later local
attachment must first verify the executable name, owning PID/HWND, bridge ABI,
and named control interfaces. It must not depend on a LiquiGen executable hash.
Verify the published tree through provider `dcc-cua` before enabling callbacks.
