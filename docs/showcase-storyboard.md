# LiquiGen bridge capability showcase

This storyboard follows `prepare_unreal_water_project` from an installed
official water preset. The final capture must use a real LiquiGen export;
synthetic assets may appear only when permanently labelled `SYNTHETIC PROXY`.

## 1. Bridge diagnostics

- Show provider/runtime version, LiquiGen version, exact-window binding state,
  and named interface probes.
- Mask machine-specific PID, HWND, and local paths in the public render while
  preserving an unredacted local evidence record.
- Demonstrate that host executable hashes are advisory and package checksums
  remain mandatory.

## 2. Preset and project staging

- Search the local official presets for `splash` and select
  `ball_drop_splash.liquigen` without copying it into the repository.
- Display the source hash, application/project versions, and baseline node
  inventory.
- Stage a byte-identical writable copy into a new path and show the no-overwrite
  guard.

## 3. Visible node-graph preparation

- Keep the LiquiGen graph and recipe step card visible together.
- Preserve the official preset's simulation, collider, camera, and water
  appearance parameters.
- Add/configure the Unreal VAT Export Mesh node and highlight the typed
  Simulation Mesh -> Export Mesh connection.
- Show requested values and post-action readback before advancing, then display
  the complete prepared graph and provenance record.

## 4. Simulation and export validation

- Show simulation playback, then select Unreal VAT on Export Mesh.
- Briefly compare the four supported handoffs: VAT runtime surface, Alembic
  cinematic surface, flipbook billboard fallback, and auxiliary VDB velocity.
- Display output file count, sequence continuity, headers, metadata validity,
  bundle hashes, and semantic role.

## 5. Unreal Engine 5.8 import

- Import the VAT FBX, textures, and JSON as one provenance-linked bundle.
- Show deterministic asset names and the source bundle hash.
- Cold-reopen the generated assets to prove that the import was saved.

## 6. Programmatic UE material authoring

- Build `M_LiquiGen_Water_VAT_Master` and `MI_LiquiGen_BallDropSplash` from the export
  metadata.
- Display the position/normal animation textures, frame range, mesh bounds,
  tint, opacity, and refraction parameter bindings.
- Show the material instance assigned to the imported mesh after readback.

## 7. Runtime verification

- Replay the VAT water mesh from time zero and expose play rate, water tint,
  opacity, roughness, and refraction through UE material/runtime parameters.
- Change at least two water parameters live, restore the accepted values, and
  replay the ball-drop splash.
- End with viewport or PIE playback, asset validation results, material binding
  verification, and a clear `REAL LIQUIGEN EXPORT` provenance card.

## Acceptance gates

The final video is accepted only when the real LiquiGen project, real export
bundle, generated UE assets, runtime evidence, and final render all share the
same provenance record. A successful MCP response or synthetic proxy is not a
substitute for visible LiquiGen and UE runtime acceptance.
