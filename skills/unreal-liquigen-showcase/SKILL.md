---
name: unreal-liquigen-showcase
description: >-
  Import a LiquiGen Unreal VAT bundle or PNG flipbook into Unreal Engine 5.8 as
  a verified fluid surface or ParticleSubUV/Niagara chain burst. Use for local
  LiquiGen-to-Unreal demonstrations and repeatable capture.
license: MIT-0
metadata:
  dcc-mcp:
    dcc: unreal
    version: "0.1.0"
    layer: domain
    compatibility: "Unreal Engine 5.8; Python 3.11+"
    tags: [pipeline, unreal, niagara, vfx]
    search-hint: "LiquiGen VAT fluid dynamic remeshing flipbook import chain explosion Niagara UE 5.8 showcase"
    tools: tools.yaml
---

# Unreal LiquiGen Showcase

Use this local workflow skill after a VAT bundle or PNG atlas has been exported
from LiquiGen. The runtime-liquid path is deliberately two-phase because Unreal
refreshes a newly authored material's instance-parameter cache on the next
editor tick. `import_vat_bundle` validates and stages the canonical FBX/lookup
EXR/position EXR/rotation EXR/JSON set with lossless data-texture settings and
the SideFX Labs UE 5.8 Dynamic Remeshing graph. After that call returns, invoke
`finalize_vat_bundle` with the same arguments to bind and read back every
material parameter, assign the mesh slot, and mark provenance finalized. The
flipbook path remains a billboard fallback and records real-export versus
synthetic-proxy provenance.

The VAT tool requires the separately installed SideFX Labs UE 5.8 content
plugin mounted at `/SideFX_Labs`; this skill does not copy or silently install
third-party binaries. Staging and replay then build a deterministic editor level
for capture.

Do not label a synthetic validation atlas as a LiquiGen export. Replace it with
the real export before final viewport acceptance.
