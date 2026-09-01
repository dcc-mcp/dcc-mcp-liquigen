# UE 5.8 receiver smoke

This project tests the Unreal half of the LiquiGen flipbook handoff without
opening the editor UI. `import_flipbook.py` imports a PNG atlas, checks its
grid, creates a `Texture2D`, and authors an unlit translucent
`ParticleSubUV` material plus a Niagara sprite system whose SubUV grid is
bound to the recorded columns and rows. The system contains a configurable
chain of 2-12 emitters. Each emitter has an increasing burst time and a bounded
world-space offset, producing a left-to-right staggered burst sequence from one
LiquiGen atlas.

`verify_flipbook.py` reopens those assets in a separate UE process, checks
their classes, ParticleSubUV texture binding, Texture -> Material -> Niagara
dependency chain, dimensions, and registered UE validators.

`generate_smoke_atlas.py` creates a synthetic colored grid only to test the
receiver. It is not a LiquiGen render and is never final asset evidence.

The authoring entry point must run in editor mode because Niagara conversion
finalization requires editor Slate state:

```powershell
$env:LIQUIGEN_FLIPBOOK_PATH = '<absolute-atlas.png>'
$env:LIQUIGEN_FLIPBOOK_COLUMNS = '8'
$env:LIQUIGEN_FLIPBOOK_ROWS = '8'
$env:LIQUIGEN_CHAIN_COUNT = '5'
$env:LIQUIGEN_CHAIN_DELAY_SECONDS = '0.18'
$env:LIQUIGEN_CHAIN_SPACING_CM = '260'
$env:LIQUIGEN_UE_RESULT_PATH = '<new-result.json>'
& '<UE_5.8>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' `
  '<project.uproject>' `
  '-ExecutePythonScript=<absolute-import_flipbook.py>' `
  -unattended -nop4 -nullrhi -nosplash -NoSound
```

Run `verify_flipbook.py` afterward through `-run=pythonscript`; it is read-only
and supports the pure commandlet entry point.

The final acceptance sequence is:

1. Export the real atlas from the staged `.liquigen` project through the exact
   DCC-CUA-authorized LiquiGen window.
2. Validate it with `validate_unreal_export_bundle`.
3. Run this receiver against the real PNG.
4. Verify the generated Niagara effect in a UE 5.8 viewport or PIE.
