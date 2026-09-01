# Install dcc-mcp-liquigen

The current repository is an alpha source distribution. For local evaluation,
clone the repository and install it with the vx-managed environment:

```powershell
vx setup
vx uv tool install .
```

After a public PyPI release is available, the package command will be:

```powershell
vx uv tool install dcc-mcp-liquigen
```

LiquiGen is a separate application and is never installed or redistributed by
this package. Use an existing licensed installation and pass the exact
`LiquiGen.exe` path, PID, and native window handle when launching the adapter.

The `dcc-mcp-cli install liquigen` path becomes available only after the
corresponding catalog change is released by `dcc-mcp-core`.
