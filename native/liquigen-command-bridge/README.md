# LiquiGen semantic command bridge

This local Windows bridge injects one enumerated LiquiGen command name into the
bound host's own transient command set. Windows invokes the hook inside the
exact UI thread identified by the requested PID/HWND pair. It does not send
mouse or keyboard input and it does not expose arbitrary memory writes or
native function calls.

The current V2 profile recognizes the LiquiGen 1.0.5 UI-command and project-load
interfaces by bounded instruction signatures, resolves the application/UI
context at runtime, requires an official command-name literal for named events,
and validates the command-set structure before inserting an event. Executable
hashes are not used. A mismatched build fails closed with `profile_mismatch`.

The whitelist contains project open/save, timeline play/pause/reset, export all,
export selected, graph framing, viewport/export tabs, fullscreen graph, the
project palette, and the command palette. `show_project_palette` and
`return_to_project` set and read back the host-owned Home/project state without
mouse or keyboard input. `open_project_path` carries one validated UTF-8 absolute path
through the shared V2 payload and calls the resolved native loader on the host
UI thread; success is reported only when that loader returns true. Licensing,
activation, quit, raw input, and arbitrary command names are intentionally
outside this bridge.

Project open, play, pause, export, and graph-scoped commands require consumer
acknowledgement. Event insertion alone is not success for those operations.

## Managed bridge location

Internal `liquigen_setup` packages may set
`DCC_MCP_LIQUIGEN_COMMAND_HOOK_DLL` to the fully qualified path of the approved
hook DLL. The command client validates that the value points to a regular file
and loads that path for the current invocation. When the variable is absent, it
falls back to a hook DLL next to the command client (the local development
layout). The variable is inherited by the adapter child process; no registry
write or global DLL search-path change is required.
