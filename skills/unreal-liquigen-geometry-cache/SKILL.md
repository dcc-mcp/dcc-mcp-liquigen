---
name: unreal-liquigen-geometry-cache
description: Import and inspect real LiquiGen Alembic mesh caches with explicit unit conversion and sample readback in Unreal.
metadata:
  dcc-mcp:
    dcc: unreal
    tools: tools.yaml
    version: "0.1.0"
---
# LiquiGen Geometry Cache

Use the official Alembic importer for a changing-topology liquid mesh. Run
`probe_receiver` first. Import only into a new asset folder with explicit scale
and rotation derived from the source export convention. Do not apply the
latest LiquiGen convention settings to an older export without checking units.

Readback proves imported cache structure and sampling, not visual equivalence.
Compare multiple frames in a separate, explicitly coordinated scene before
claiming acceptance. A procedural replacement is not a source-fluid comparison.
