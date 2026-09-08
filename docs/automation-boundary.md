# Automation contract

The adapter reads and writes the tagged `.liquigen` document format as an
experimental compatibility layer. It is not a published JangaFX scripting API.

1. Discover schemas with `list_node_schemas` and read projects with
   `inspect_project_graph`.
2. Use `apply_graph_transaction` for graph edits. Connections must use observed
   pins, destinations must be new, and completed writes are reparsed.
3. Use `open_project_path` and the fixed host-command list for live operations.
   Commands execute against the bound PID/HWND and require host acknowledgement.
4. Use `run_export_workflow` with a new empty output directory. It checks file
   freshness, stability and bundle structure before reporting success.

The named command bridge exposes no arbitrary native calls or input events.
Use project-owned DCC-CUA for UI operations that have no typed route, retaining
its exact-window binding and observation requirements. Licensing and activation
are outside the adapter's command surface.

See the [examples](../examples/README.md) for export and receiver entry points.
