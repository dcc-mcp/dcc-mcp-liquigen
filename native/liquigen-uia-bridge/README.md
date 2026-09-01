# LiquiGen UIA bridge prototype

This Windows-only native library exposes a versioned semantic node snapshot as
a server-side Microsoft UI Automation provider. It is a contract prototype,
not a LiquiGen loader or injector.

Build and run the self-owned window integration test from the repository root:

```powershell
vx just native-test
```

The test proves COM discovery and UI-thread action dispatch for the
`export.directory` value field and `export.now` button. No test command loads
the bridge into LiquiGen or touches its licensing components.
