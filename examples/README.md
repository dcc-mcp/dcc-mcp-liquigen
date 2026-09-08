# Examples

Supply your own installed LiquiGen presets and exported files. Examples write
to new output locations; no vendor assets are bundled.

| Example | Result | Entry point |
|---|---|---|
| Export preparation | A new project with a VAT or Alembic mesh exporter | `prepare_unreal_water_project` in the `liquigen-project` skill |
| Geometry Cache | An animated Alembic asset in Unreal | `probe_receiver`, then `import_cache` in [unreal-liquigen-geometry-cache](../skills/unreal-liquigen-geometry-cache/SKILL.md) |
| VAT material | An imported mesh and animation textures with a material | `probe_vat_receiver`, `import_vat_bundle`, then `finalize_vat_bundle` in [unreal-liquigen-showcase](../skills/unreal-liquigen-showcase/SKILL.md) |
| Flipbook | A ParticleSubUV material and Niagara burst | [Receiver example](ue58_receiver/README.md) |

Export preparation requires an official preset path, a new destination, an
output directory and a frame count. Choose `export_profile` as `ue_vat` or
`alembic`, then call `run_export_workflow` on a bound host. Keep the paired image
exporter enabled where required by the host export interface.

Geometry Cache import requires an absolute `.abc` path, a new `/Game` folder,
an asset name and explicit scale/rotation matching the source axes and units.
Enable source velocities only when present and compatible with the receiver.

VAT import requires the separate SideFX Labs Dynamic Remeshing material at
`/SideFX_Labs`. Finalization runs in a subsequent call so Unreal can refresh
material parameters. Check each skill's compatibility metadata and probe result
before import. A procedural demonstration is a separate effect, not the exported
simulation.
