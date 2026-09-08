# Flipbook receiver example

Import a PNG atlas as a Texture2D, ParticleSubUV material and Niagara burst
sequence. Use the engine association and plugins declared in
`LiquiGenUE58.uproject`; the example requires Unreal's editor Python APIs.

```powershell
$env:LIQUIGEN_FLIPBOOK_PATH = '<absolute-atlas.png>'
$env:LIQUIGEN_FLIPBOOK_COLUMNS = '8'
$env:LIQUIGEN_FLIPBOOK_ROWS = '8'
$env:LIQUIGEN_CHAIN_COUNT = '5'
$env:LIQUIGEN_CHAIN_DELAY_SECONDS = '0.18'
$env:LIQUIGEN_CHAIN_SPACING_CM = '260'
$env:LIQUIGEN_UE_RESULT_PATH = '<new-result.json>'
& '<ENGINE>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' `
  '<project.uproject>' `
  '-ExecutePythonScript=<absolute-import_flipbook.py>' `
  -unattended -nop4 -nullrhi -nosplash -NoSound
```

The import runs in editor mode because Niagara conversion requires editor
state. Run `verify_flipbook.py` afterward via `-run=pythonscript` to read back
asset types, texture bindings and dimensions. `generate_smoke_atlas.py` creates
a synthetic grid for testing this receiver; it is not a LiquiGen export.
