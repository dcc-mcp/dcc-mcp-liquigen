"""Import a LiquiGen atlas and author its UE ParticleSubUV/Niagara receiver."""

from __future__ import annotations

import gc
import json
import os
import struct
from collections.abc import Mapping
from pathlib import Path


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or not header.startswith(b"\x89PNG\r\n\x1a\n") or header[12:16] != b"IHDR":
        raise ValueError("flipbook is not a PNG with a valid IHDR header")
    return struct.unpack(">II", header[16:24])


def _required_path(name: str) -> Path:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    path = Path(value).expanduser().resolve(strict=True)
    return path


def _output_path(name: str) -> Path:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    raw = Path(value).expanduser()
    parent = raw.parent.resolve(strict=True)
    path = parent / raw.name
    if path.exists():
        raise ValueError(f"{name} already exists")
    return path


def _required_grid(name: str) -> int:
    value = int(os.environ.get(name, "0"))
    if value < 1 or value > 64:
        raise ValueError(f"{name} must be between 1 and 64")
    return value


def chain_configuration(environment: Mapping[str, str] = os.environ) -> dict[str, object]:
    count = int(environment.get("LIQUIGEN_CHAIN_COUNT", "5"))
    delay = float(environment.get("LIQUIGEN_CHAIN_DELAY_SECONDS", "0.18"))
    spacing = float(environment.get("LIQUIGEN_CHAIN_SPACING_CM", "260"))
    if count < 2 or count > 12:
        raise ValueError("LIQUIGEN_CHAIN_COUNT must be between 2 and 12")
    if delay < 0.05 or delay > 2.0:
        raise ValueError("LIQUIGEN_CHAIN_DELAY_SECONDS must be between 0.05 and 2.0")
    if spacing < 1.0 or spacing > 5000.0:
        raise ValueError("LIQUIGEN_CHAIN_SPACING_CM must be between 1 and 5000")
    return {"count": count, "delay_seconds": delay, "spacing_cm": spacing}


def _create_material(unreal, texture, destination: str, name: str):
    object_path = f"{destination}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(object_path):
        raise RuntimeError(f"material already exists: {object_path}")
    unreal.EditorAssetLibrary.make_directory(destination)
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name,
        destination,
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    if material is None:
        raise RuntimeError(f"failed to create material: {object_path}")
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    expression = unreal.MaterialEditingLibrary.create_material_expression(
        material,
        unreal.MaterialExpressionParticleSubUV,
        -300,
        0,
    )
    if expression is None:
        raise RuntimeError("failed to create MaterialExpressionParticleSubUV")
    expression.set_editor_property("texture", texture)
    if not unreal.MaterialEditingLibrary.connect_material_property(
        expression,
        "RGB",
        unreal.MaterialProperty.MP_EMISSIVE_COLOR,
    ):
        raise RuntimeError("failed to connect flipbook RGB to emissive color")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        expression,
        "A",
        unreal.MaterialProperty.MP_OPACITY,
    ):
        raise RuntimeError("failed to connect flipbook alpha to opacity")
    compile_errors = [
        str(item) for item in unreal.MaterialEditingLibrary.recompile_material(material)
    ]
    if compile_errors:
        raise RuntimeError("material compile failed: " + "; ".join(compile_errors))
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError(f"failed to save material: {object_path}")
    return material, object_path


def _niagara_module(unreal, fx, emitter, name: str, asset_path: str, category):
    asset_data = fx.create_asset_data(asset_path)
    args = unreal.CreateScriptContextArgs(asset_data)
    return emitter.find_or_add_module_script(name, args, category)


def _create_niagara_system(
    unreal,
    material,
    destination: str,
    name: str,
    columns: int,
    rows: int,
    chain: dict[str, object],
):
    object_path = f"{destination}/{name}"
    if unreal.EditorAssetLibrary.does_asset_exist(object_path):
        raise RuntimeError(f"Niagara system already exists: {object_path}")
    system = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name,
        destination,
        unreal.NiagaraSystem,
        unreal.NiagaraSystemFactoryNew(),
    )
    if system is None:
        raise RuntimeError(f"failed to create Niagara system: {object_path}")

    fx = unreal.FXConverterUtilitiesLibrary
    system_context = fx.create_system_conversion_context(system)
    count = int(chain["count"])
    delay = float(chain["delay_seconds"])
    spacing = float(chain["spacing_cm"])
    for stage in range(count):
        emitter = system_context.add_empty_emitter(f"LiquiGenChainBurst{stage + 1:02d}")
        emitter.set_local_space(False)

        _niagara_module(
            unreal,
            fx,
            emitter,
            "EmitterState",
            "/Niagara/Modules/Emitter/EmitterState.EmitterState",
            unreal.ScriptExecutionCategory.EMITTER_UPDATE,
        )
        spawn = _niagara_module(
            unreal,
            fx,
            emitter,
            "SpawnBurstInstantaneous",
            "/Niagara/Modules/Emitter/SpawnBurst_Instantaneous.SpawnBurst_Instantaneous",
            unreal.ScriptExecutionCategory.EMITTER_UPDATE,
        )
        spawn.set_parameter("Spawn Count", fx.create_script_input_int(1))
        spawn.set_parameter("Spawn Time", fx.create_script_input_float(stage * delay))
        initialize = _niagara_module(
            unreal,
            fx,
            emitter,
            "InitializeParticle",
            "/Niagara/Modules/Spawn/Initialization/V2/InitializeParticle.InitializeParticle",
            unreal.ScriptExecutionCategory.PARTICLE_SPAWN,
        )
        initialize.set_parameter("Lifetime", fx.create_script_input_float(2.0))
        initialize.set_parameter(
            "Sprite Size Mode",
            fx.create_script_input_enum(
                "/Niagara/Enums/ENiagara_SizeScaleMode.ENiagara_SizeScaleMode",
                "Non-Uniform",
            ),
        )
        initialize.set_parameter(
            "Sprite Size",
            fx.create_script_input_vec2(unreal.Vector2D(512.0, 512.0)),
            True,
            True,
        )
        offset = _niagara_module(
            unreal,
            fx,
            emitter,
            "AddVectorToPosition",
            "/CascadeToNiagaraConverter/NiagaraScripts/ModuleScripts/"
            "AddVectorToPosition.AddVectorToPosition",
            unreal.ScriptExecutionCategory.PARTICLE_SPAWN,
        )
        x = (stage - (count - 1) / 2.0) * spacing
        y = (1.0 if stage % 2 else -1.0) * spacing * 0.18
        offset.set_parameter(
            "Vector",
            fx.create_script_input_vector(unreal.Vector(x, y, 0.0)),
        )
        _niagara_module(
            unreal,
            fx,
            emitter,
            "ParticleState",
            "/Niagara/Modules/Update/Lifetime/ParticleState.ParticleState",
            unreal.ScriptExecutionCategory.PARTICLE_UPDATE,
        )
        _niagara_module(
            unreal,
            fx,
            emitter,
            "SubUVAnimation",
            "/Niagara/Modules/Update/SubUV/V2/SubUVAnimation.SubUVAnimation",
            unreal.ScriptExecutionCategory.PARTICLE_UPDATE,
        )

        renderer = unreal.NiagaraSpriteRendererProperties()
        renderer.set_editor_property("material", material)
        renderer.set_editor_property(
            "sub_image_size", unreal.Vector2D(float(columns), float(rows))
        )
        renderer.set_editor_property("sub_image_blend", True)
        renderer.set_editor_property("facing_mode", unreal.NiagaraSpriteFacingMode.FACE_CAMERA)
        renderer.set_editor_property("cast_shadows", False)
        emitter.add_renderer(f"LiquiGenChainRenderer{stage + 1:02d}", renderer)

    system_context.set_warmup_tick_delta(1.0 / 60.0)
    system_context.finalize()
    if not unreal.EditorAssetLibrary.save_loaded_asset(system, only_if_is_dirty=False):
        raise RuntimeError(f"failed to save Niagara system: {object_path}")
    return system, object_path


def main() -> None:
    import unreal

    source = _required_path("LIQUIGEN_FLIPBOOK_PATH")
    result_path = _output_path("LIQUIGEN_UE_RESULT_PATH")
    columns = _required_grid("LIQUIGEN_FLIPBOOK_COLUMNS")
    rows = _required_grid("LIQUIGEN_FLIPBOOK_ROWS")
    chain = chain_configuration()
    if source.suffix.casefold() != ".png":
        raise ValueError("LIQUIGEN_FLIPBOOK_PATH must point to a PNG atlas")
    width, height = png_dimensions(source)
    if width % columns or height % rows:
        raise ValueError("PNG dimensions are not divisible by the requested grid")

    destination = os.environ.get("LIQUIGEN_UE_DESTINATION", "/Game/LiquiGen/Splash").rstrip("/")
    if not destination.startswith("/Game/"):
        raise ValueError("LIQUIGEN_UE_DESTINATION must start with /Game/")
    texture_name = os.environ.get("LIQUIGEN_UE_TEXTURE_NAME", "T_LiquiGen_Splash_Flipbook")
    material_name = os.environ.get("LIQUIGEN_UE_MATERIAL_NAME", "M_LiquiGen_Splash_Flipbook")
    niagara_name = os.environ.get("LIQUIGEN_UE_NIAGARA_NAME", "NS_LiquiGen_Splash_Flipbook")
    texture_path = f"{destination}/{texture_name}"
    if unreal.EditorAssetLibrary.does_asset_exist(texture_path):
        raise RuntimeError(f"texture already exists: {texture_path}")

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", texture_name)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported_paths = [str(item) for item in task.get_editor_property("imported_object_paths")]
    if not imported_paths:
        raise RuntimeError("AssetImportTask returned no imported object paths")
    texture = unreal.EditorAssetLibrary.load_asset(texture_path)
    if texture is None or not isinstance(texture, unreal.Texture2D):
        raise RuntimeError(f"imported texture is unavailable or has wrong type: {texture_path}")
    texture.set_editor_property("srgb", True)
    texture.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    if not unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False):
        raise RuntimeError(f"failed to save texture settings: {texture_path}")

    material, material_path = _create_material(unreal, texture, destination, material_name)
    niagara, niagara_path = _create_niagara_system(
        unreal,
        material,
        destination,
        niagara_name,
        columns,
        rows,
        chain,
    )
    verified_texture = unreal.EditorAssetLibrary.load_asset(texture_path)
    verified_material = unreal.EditorAssetLibrary.load_asset(material_path)
    verified_niagara = unreal.EditorAssetLibrary.load_asset(niagara_path)
    if verified_texture is None or verified_material is None or verified_niagara is None:
        raise RuntimeError("saved UE assets failed readback")

    result = {
        "success": True,
        "engine_version": str(unreal.SystemLibrary.get_engine_version()),
        "source": str(source),
        "source_dimensions": [width, height],
        "grid": {"columns": columns, "rows": rows},
        "chain": chain,
        "emitter_count": chain["count"],
        "frame_dimensions": [width // columns, height // rows],
        "texture_path": texture_path,
        "material_path": material_path,
        "niagara_path": niagara_path,
        "texture_class": verified_texture.get_class().get_name(),
        "material_class": verified_material.get_class().get_name(),
        "niagara_class": verified_niagara.get_class().get_name(),
        "imported_object_paths": imported_paths,
        "niagara_configuration_required": False,
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    unreal.log("LIQUIGEN_UE_RECEIVER_RESULT=" + json.dumps(result, sort_keys=True))

    # ExecutePythonScript queues QUIT_EDITOR immediately after this file returns.
    # Release converter/editor wrappers and queue UE GC before shutdown so their
    # destructors cannot attempt to reload AssetTools after module teardown.
    packages = [
        verified_niagara.get_outermost(),
        verified_material.get_outermost(),
        verified_texture.get_outermost(),
    ]
    del verified_niagara, verified_material, verified_texture
    del niagara, material, texture, task
    gc.collect()
    unload_result = unreal.EditorLoadingAndSavingUtils.unload_packages(packages)
    unreal.log("LIQUIGEN_UE_RECEIVER_UNLOAD=" + str(unload_result))
    del unload_result, packages
    gc.collect()
    unreal.SystemLibrary.collect_garbage()


if __name__ == "__main__":
    main()
