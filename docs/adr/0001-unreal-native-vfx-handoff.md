# ADR 0001: Unreal-native LiquiGen VFX handoff

- Status: Superseded by ADR 0003
- Date: 2026-08-31

## Context

The bridge must preserve an editable LiquiGen source, show how the node graph
was generated, transfer the result into Unreal Engine 5.8, author the receiving
material programmatically, and remain useful across application versions.
LiquiGen is a liquid simulator; its documented VDB fields are velocity data,
while its Mesh Export node supports an Unreal-targeted Vertex Animated Texture
(VAT) bundle.

At the time of this decision, writing `.liquigen` files had not been validated.
Later local evidence established a bounded tagged-document transaction route;
ADR 0003 replaces the graph-mutation portion of this decision.

## Decision

1. Name the effect `liquid_chain_burst`. Do not claim combustion, fire, or
   smoke generation from LiquiGen.
2. Use LiquiGen's Unreal VAT export (FBX, animation textures, and metadata) as
   the default game-runtime liquid surface.
3. Support Alembic as the cinematic/high-fidelity geometry path and EXR/PNG
   flipbooks as the inexpensive billboard fallback.
4. Classify LiquiGen OpenVDB sequences as auxiliary velocity fields. UE Sparse
   Volume Texture import may consume them, but they are not the primary liquid
   surface and UE 5.8 marks Sparse Volume Textures Experimental.
5. Keep the `.liquigen` project, export bundle, hashes, bridge recipe, and UE
   authoring recipe as canonical source artifacts. Treat `.uasset` files as
   derived outputs.
6. Author a UE master material, per-export material instance, and Niagara
   wrapper deterministically from the VAT metadata. Expose burst count, delay,
   spacing, play rate, tint, and refraction as Niagara user parameters.
7. Compile each LiquiGen build into numbered steps containing operation, node
   type, parameters, and a verification statement. The same structure powers
   execution logs and the showcase chapter overlay.
8. Superseded: use ADR 0003 for graph mutation. Keep this ADR's Unreal handoff
   and runtime-asset decisions.

## Non-functional requirements

- Fail closed when host binding, typed ports, output headers, frame continuity,
  or UE runtime verification cannot be proven.
- Record source application version and interface capability results, but do
  not require an executable hash match.
- Never overwrite a staged project or previously accepted export directory.
- Keep planning deterministic and runnable without an interactive desktop.
- Require a live LiquiGen host for simulation/export, but route those operations
  through the semantic command bridge rather than CUA. Require UE viewport or
  PIE evidence for final runtime acceptance.

## Consequences

The public bridge can demonstrate diagnostics, preset discovery, safe staging,
binary inspection, deterministic recipes, typed graph operations, bundle
validation, UE import, material authoring, Niagara orchestration, and runtime
verification as one traceable pipeline.

VAT adds a metadata-to-material mapping step and Alembic has greater runtime
cost. Sparse Volume Textures cannot substitute for a liquid surface unless a
separate density-producing workflow is introduced. A fiery chain explosion
requires a combustion-capable source DCC, but can reuse the UE orchestration
and verification portions of this architecture.

## References

- [LiquiGen node and export reference](https://docs.jangafx.com/liquigen/pages/references/node_list.html)
- [UE 5.8 Sparse Volume Textures](https://dev.epicgames.com/documentation/unreal-engine/sparse-volume-textures-in-unreal-engine)
- [UE Niagara overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/overview-of-niagara-effects-for-unreal-engine)
