# LiquiGen to Unreal Engine 5.8

## Recommended runtime asset: Unreal VAT

LiquiGen's Unreal-targeted Vertex Animated Texture (VAT) export is the default
handoff for a game-ready liquid surface. Keep its FBX geometry, animation
textures, and JSON metadata together as one source bundle. The UE receiver
imports that bundle, authors `M_LiquiGen_VAT_Master` and a material instance,
then exposes playback and water material parameters through Unreal's material
system. Niagara remains available for secondary timing or instancing behavior;
it is not required to decode the primary water mesh.

The verified local decoder is SideFX Labs 22.0.408's UE 5.8 content-only
`Houdini_VAT_DynamicRemeshing` material function. LiquiGen's canonical export
names and metadata match the Dynamic Remeshing (Fluid) contract: FBX geometry,
lookup/position/rotation EXRs, and `*_info.json`. The receiver configures EXRs as
nearest-filtered, no-mipmap, linear HDR data and enables full-precision mesh UVs
before authoring the material and instance.

SideFX Labs is a separate BSD-style dependency and is not copied into the
adapter bundle. For local testing, install and enable its UE 5.8 content plugin
so `/SideFX_Labs/Materials/MaterialFunctions/Houdini_VAT_DynamicRemeshing` is
mounted. A distribution may either document that prerequisite or redistribute
the permitted dependency with its copyright/license notice after an explicit
release decision.

## Higher-fidelity alternatives

## UE-native procedural fallback

Some LiquiGen 1.0.5 exports can pass the FBX/EXR/JSON contract while still
rendering no visible surface through the installed SideFX Dynamic Remeshing
function in UE 5.8. This is a host/material compatibility boundary, not proof
that the export files are corrupt. When the direct VAT preview is empty, use
`author_procedural_water_cascade` followed by `stage_water_cascade`. That path
keeps the real LiquiGen project, VAT metadata, timing, and source provenance,
but renders the water with UE-native Niagara and translucent materials. It is
the recommended acceptance path for the 0.1.0 showcase until the direct VAT
parameter contract is confirmed for the target LiquiGen build.

- Alembic: use an Unreal-centimeter export convention and import as a Geometry
  Cache when cinematic fidelity matters more than runtime cost.
- Image flipbook: use an EXR atlas for HDR or PNG for broad compatibility. It is
  the cheapest distant/billboard fallback and plays through Niagara SubUV.
- OpenVDB: LiquiGen documents velocity fields only. Import it into UE Sparse
  Volume Textures as auxiliary data, not as the primary liquid surface.

## Official water preset recipe

Call `prepare_unreal_water_project` with an official preset discovered in the
local LiquiGen installation, for example `ball_drop_splash.liquigen`. The tool
preserves the source, stages a new project, adds/configures an Unreal-targeted
VAT mesh export, and connects the existing simulation mesh through observed
typed pins. The result includes the applied operations and provenance so the
showcase can display exactly what the bridge changed without redistributing the
vendor preset.

The graph build does not require an interactive desktop or CUA. A live LiquiGen
process is required for simulation and export, but `run_export_workflow` now
loads the exact project path through the native loader, drives named playback
and export commands on the host UI thread, waits for a fresh stable bundle, and
validates it. CUA is reserved for optional visual acceptance and recording.
The workflow rejects a nonempty output directory before touching the host,
avoiding modal overwrite confirmation and preserving prior accepted bundles.

## Acceptance

1. Preserve the source `.liquigen` project and exact application version.
2. Export into a new directory; never overwrite a previous accepted bundle.
3. Run `run_export_workflow` and record fresh-file evidence, hashes, sizes, format,
   semantic role, and intended UE import target.
4. Import into UE 5.8, create the matching material/Niagara playback, and verify
   the effect in the viewport or PIE. File validation alone is not Unreal runtime
   acceptance.

The flipbook receiver under `examples/ue58_receiver` imports a validated PNG atlas,
creates an unlit translucent `ParticleSubUV` material, and authors a Niagara
sprite system with the requested SubUV grid. Its optional chain profile authors
2-12 spatially offset emitters with increasing spawn times. A separate cold-start verifier
reopens all three assets, checks Texture -> Material -> Niagara references, and
runs UE's registered validators. This non-interactive evidence still precedes
the final viewport or PIE acceptance. Its generated smoke atlas is a transport
fixture only and must never be reported as the LiquiGen effect.

The local `unreal-liquigen-showcase` skill additionally exposes
`import_vat_bundle`, which validates and imports the primary runtime fluid
surface with the SideFX material dependency. Final acceptance still requires a
real LiquiGen VAT export and viewport/PIE playback.

The format list and Unreal VAT target come from the official
[node/export reference](https://docs.jangafx.com/liquigen/pages/references/node_list.html).
For Geometry Cache handoff, follow LiquiGen's official
[Alembic coordinate and velocity convention](https://docs.jangafx.com/liquigen/pages/references/How-To%20Guides/alembic_convention.html).
