---
name: unreal-liquigen-showcase
description: >-
  Import a LiquiGen Unreal VAT bundle or PNG flipbook into Unreal as
  an animated mesh or ParticleSubUV/Niagara chain burst. Use for local
  LiquiGen-to-Unreal demonstrations and repeatable capture.
license: MIT-0
metadata:
  dcc-mcp:
    dcc: unreal
    version: "0.1.0"
    layer: domain
    compatibility: "Unreal Engine 5.8; Python 3.11+"
    tags: [pipeline, unreal, niagara, vfx]
    search-hint: "LiquiGen VAT fluid dynamic remeshing flipbook import chain explosion Niagara showcase"
    tools: tools.yaml
---

# Unreal receiver examples

For VAT, call `probe_vat_receiver`, `import_vat_bundle`, then
`finalize_vat_bundle` with the same arguments in a subsequent call. The
separate call allows Unreal to refresh material parameters on the next editor tick. Supply the FBX,
lookup/position/rotation textures and JSON metadata together.

The VAT example requires the separately installed SideFX Labs content plugin
compatible with the declared engine version, mounted at `/SideFX_Labs`.
Nothing is downloaded or installed by this skill.

For a flipbook, supply a PNG atlas and its grid to `import_chain_burst`.
Staging and replay tools create an example level. Procedural demonstrations
are separate effects; a synthetic atlas is a receiver test fixture.
