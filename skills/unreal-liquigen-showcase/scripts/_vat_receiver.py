"""UE 5.8 receiver for canonical LiquiGen dynamic-remeshing VAT bundles."""

from __future__ import annotations

import json
import math
from pathlib import Path

SIDEFX_FLUID_FUNCTION = (
    "/SideFX_Labs/Materials/MaterialFunctions/"
    "Houdini_VAT_DynamicRemeshing.Houdini_VAT_DynamicRemeshing"
)
SIDEFX_FLUID_CUSTOM_UVS = ((19, 1), (20, 2), (21, 3))


def _native_payload(payload: object, operation: str) -> dict:
    try:
        value = json.loads(payload) if isinstance(payload, str) else payload
    except (TypeError, ValueError) as error:
        raise RuntimeError(f"native VAT {operation} returned invalid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"native VAT {operation} returned an invalid result")
    if not value.get("success"):
        code = str(value.get("error_code") or "native_operation_failed")
        message = str(value.get("message") or code)
        raise RuntimeError(f"native VAT {operation} failed: {code}: {message}")
    return value


def _number(metadata: dict, key: str) -> float:
    value = metadata.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"VAT metadata field is not numeric: {key}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"VAT metadata field is not finite: {key}")
    return result


def _boolean_flag(metadata: dict, key: str) -> bool:
    """Normalize JSON booleans and LiquiGen's integer 0/1 flag encoding."""

    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError(f"VAT metadata field is invalid: {key}")


def canonical_vat_bundle(source_directory: Path) -> dict:
    """Validate and normalize one canonical LiquiGen fluid VAT directory."""

    try:
        source = source_directory.expanduser().resolve(strict=True)
    except OSError as error:
        raise ValueError("source_directory does not exist") from error
    if not source.is_dir():
        raise ValueError("source_directory must be an existing directory")
    info_files = list(source.glob("*_info.json"))
    if len(info_files) != 1:
        raise ValueError("VAT bundle must contain exactly one *_info.json file")
    info = info_files[0]
    try:
        payload = json.loads(info.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("VAT metadata is not valid UTF-8 JSON") from error
    metadata = payload[0] if isinstance(payload, list) and len(payload) == 1 else payload
    if not isinstance(metadata, dict):
        raise ValueError("VAT metadata must contain one object")
    stem = info.name[: -len("_info.json")]
    assets = {
        "geometry": source / f"{stem}.fbx",
        "lookup": source / f"{stem}_lookup.exr",
        "position": source / f"{stem}_pos.exr",
        "rotation": source / f"{stem}_rot.exr",
        "info": info,
    }
    missing = [
        path.name for path in assets.values() if not path.is_file() or path.stat().st_size <= 0
    ]
    if missing:
        raise ValueError("VAT bundle is missing canonical files: " + ", ".join(missing))
    axis_system = metadata.get("Axis System")
    frame_count = metadata.get("Frame Count")
    two_position_textures = _boolean_flag(metadata, "Two Position Textures")
    if not isinstance(axis_system, str) or not axis_system.strip():
        raise ValueError("VAT metadata field is invalid: Axis System")
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count <= 0:
        raise ValueError("VAT metadata field is invalid: Frame Count")
    if two_position_textures:
        raise ValueError(
            "two-position-texture LiquiGen VAT needs a separately verified file contract"
        )
    source_fps = _number(metadata, "Houdini FPS")
    if source_fps <= 0:
        raise ValueError("VAT metadata field is invalid: Houdini FPS")
    return {
        "source": source,
        "stem": stem,
        "axis_system": axis_system,
        "bounds_min": [
            _number(metadata, "Bound Min X"),
            _number(metadata, "Bound Min Y"),
            _number(metadata, "Bound Min Z"),
        ],
        "bounds_max": [
            _number(metadata, "Bound Max X"),
            _number(metadata, "Bound Max Y"),
            _number(metadata, "Bound Max Z"),
        ],
        "frame_count": frame_count,
        "source_fps": source_fps,
        "two_position_textures": two_position_textures,
        "assets": assets,
    }


def _import_task(unreal, filename: Path, destination: str, destination_name: str, options=None):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(filename))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", destination_name)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    if options is not None:
        task.set_editor_property("options", options)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = list(task.get_editor_property("imported_object_paths"))
    if len(imported) != 1:
        raise RuntimeError(f"expected one imported asset for {filename.name}, got {imported}")
    asset = unreal.EditorAssetLibrary.load_asset(imported[0])
    if asset is None:
        raise RuntimeError("imported asset failed readback: " + imported[0])
    return asset, imported[0]


def _configure_texture(unreal, texture) -> None:
    texture.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
    texture.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_16_BIT_DATA)
    texture.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_HDR)
    texture.set_editor_property("srgb", False)
    texture.modify()
    if not unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False):
        raise RuntimeError("failed to save configured VAT texture")


def _configure_fluid_mesh(unreal, mesh) -> None:
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if subsystem is None:
        raise RuntimeError("StaticMeshEditorSubsystem is unavailable")
    build_settings = subsystem.get_lod_build_settings(mesh, 0)
    build_settings.set_editor_property("use_full_precision_u_vs", False)
    build_settings.set_editor_property("use_backwards_compatible_f16_trunc_u_vs", True)
    build_settings.set_editor_property("generate_lightmap_u_vs", False)
    mesh.modify()
    subsystem.set_lod_build_settings(mesh, 0, build_settings)
    readback = subsystem.get_lod_build_settings(mesh, 0)
    if (
        readback.get_editor_property("use_full_precision_u_vs")
        or not readback.get_editor_property("use_backwards_compatible_f16_trunc_u_vs")
        or readback.get_editor_property("generate_lightmap_u_vs")
    ):
        raise RuntimeError("fluid VAT static mesh compatibility settings failed readback")
    if not unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False):
        raise RuntimeError("failed to save configured fluid VAT mesh")


def _customized_uv_bridge(unreal):
    bridge = getattr(unreal, "DccMcpAutomationLibrary", None)
    connect = getattr(bridge, "connect_material_expression_to_customized_uv", None)
    inspect = getattr(bridge, "get_material_customized_uv_connection", None)
    if not callable(connect) or not callable(inspect):
        raise RuntimeError(
            "DCC-MCP Unreal Customized UV native bridge is required for fluid VAT import"
        )
    return connect, inspect


def _material_instance_parameter_bridge(unreal):
    bridge = getattr(unreal, "DccMcpAutomationLibrary", None)
    configure = getattr(bridge, "configure_material_instance_parameters", None)
    if not callable(configure):
        raise RuntimeError(
            "DCC-MCP Unreal native Material Instance parameter bridge is required "
            "for fluid VAT import"
        )
    return configure


def _connect_fluid_customized_uvs(unreal, material, expression) -> None:
    connect, inspect = _customized_uv_bridge(unreal)
    expression_name = expression.get_name()
    for output_index, customized_uv_index in SIDEFX_FLUID_CUSTOM_UVS:
        result = _native_payload(
            connect(
                material,
                expression,
                output_index,
                "",
                customized_uv_index,
                False,
            ),
            f"Customized UV {customized_uv_index} connection",
        )
        if (
            not result.get("saved")
            or not result.get("verified")
            or result.get("source_output_index") != output_index
        ):
            raise RuntimeError(
                f"native VAT Customized UV {customized_uv_index} connection was not verified"
            )
        readback = _native_payload(
            inspect(material, customized_uv_index),
            f"Customized UV {customized_uv_index} readback",
        )
        expected = {
            "connected": True,
            "customized_uv_index": customized_uv_index,
            "source_expression_name": expression_name,
            "source_output_index": output_index,
            "package_dirty": False,
        }
        actual = {key: readback.get(key) for key in expected}
        if actual != expected:
            raise RuntimeError(
                f"native VAT Customized UV {customized_uv_index} post-save readback failed"
            )


def _create_material(unreal, destination: str, name: str):
    function = unreal.EditorAssetLibrary.load_asset(SIDEFX_FLUID_FUNCTION)
    if function is None:
        raise RuntimeError(
            "SideFX Labs UE 5.8 content plugin is required: " + SIDEFX_FLUID_FUNCTION
        )
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, destination, unreal.Material, unreal.MaterialFactoryNew()
    )
    if material is None:
        raise RuntimeError(f"failed to create VAT material: {destination}/{name}")
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property(
        "translucency_lighting_mode",
        unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING,
    )
    material.set_editor_property("two_sided", True)
    material.set_editor_property("tangent_space_normal", False)
    material.set_editor_property("used_with_instanced_static_meshes", True)
    material.set_editor_property("used_with_niagara_mesh_particles", True)
    expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionMaterialFunctionCall, -800, 0
    )
    expression.set_material_function(function)
    function_connections = (
        ("Normal (Tangent Space Normal Off)", unreal.MaterialProperty.MP_NORMAL),
        ("World Position Offset", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET),
    )
    for output_name, property_name in function_connections:
        if not unreal.MaterialEditingLibrary.connect_material_property(
            expression, output_name, property_name
        ):
            raise RuntimeError("failed to connect fluid VAT material output: " + output_name)

    water_tint = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -420, -300
    )
    water_tint.set_editor_property("parameter_name", "Water Tint")
    water_tint.set_editor_property("default_value", unreal.LinearColor(0.015, 0.12, 0.18, 1.0))
    scalar_specs = (
        ("Water Roughness", 0.08, unreal.MaterialProperty.MP_ROUGHNESS, -420, -180),
        ("Water Specular", 0.5, unreal.MaterialProperty.MP_SPECULAR, -420, -80),
        ("Water Opacity", 0.34, unreal.MaterialProperty.MP_OPACITY, -420, 20),
        ("Water IOR", 1.33, unreal.MaterialProperty.MP_REFRACTION, -420, 120),
    )
    if not unreal.MaterialEditingLibrary.connect_material_property(
        water_tint, "", unreal.MaterialProperty.MP_BASE_COLOR
    ):
        raise RuntimeError("failed to connect UE water tint")
    for parameter_name, default_value, property_name, node_x, node_y in scalar_specs:
        parameter = unreal.MaterialEditingLibrary.create_material_expression(
            material, unreal.MaterialExpressionScalarParameter, node_x, node_y
        )
        parameter.set_editor_property("parameter_name", parameter_name)
        parameter.set_editor_property("default_value", default_value)
        if not unreal.MaterialEditingLibrary.connect_material_property(
            parameter, "", property_name
        ):
            raise RuntimeError("failed to connect UE water parameter: " + parameter_name)
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError("failed to persist fluid VAT material before native graph wiring")
    _connect_fluid_customized_uvs(unreal, material, expression)
    errors = [str(item) for item in unreal.MaterialEditingLibrary.recompile_material(material)]
    if errors:
        raise RuntimeError("fluid VAT material compile failed: " + "; ".join(errors))
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError("failed to save fluid VAT material")
    return material


def _create_material_instance(unreal, material, destination: str, name: str):
    factory = unreal.MaterialInstanceConstantFactoryNew()
    instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, destination, unreal.MaterialInstanceConstant, factory
    )
    if instance is None:
        raise RuntimeError(f"failed to create VAT material instance: {destination}/{name}")
    library = unreal.MaterialEditingLibrary
    library.set_material_instance_parent(instance, material)
    if instance.get_editor_property("parent") != material:
        raise RuntimeError("failed to set VAT material instance parent")
    library.update_material_instance(instance)
    if not unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False):
        raise RuntimeError("failed to save staged VAT material instance")
    return instance


def _bind_material_instance(unreal, instance, textures: dict, bundle: dict) -> None:
    library = unreal.MaterialEditingLibrary
    texture_parameters = {
        "Lookup Table": textures["lookup"],
        "Position Texture": textures["position"],
        "Rotation Texture": textures["rotation"],
    }
    scalar_parameters = {
        "Houdini FPS": bundle["source_fps"],
        "Bound Min X": bundle["bounds_min"][0],
        "Bound Min Y": bundle["bounds_min"][1],
        "Bound Min Z": bundle["bounds_min"][2],
        "Bound Max X": bundle["bounds_max"][0],
        "Bound Max Y": bundle["bounds_max"][1],
        "Bound Max Z": bundle["bounds_max"][2],
        "Playback Speed": 1.0,
        "Game Time at First Frame": 0.0,
    }
    static_switch_parameters = {
        "Auto Playback": True,
        "Support Legacy Parameters and Instancing": False,
        "Positions Require Two Textures": bundle["two_position_textures"],
    }
    available_parameters = {
        "scalar": {str(name) for name in library.get_scalar_parameter_names(instance)},
        "texture": {str(name) for name in library.get_texture_parameter_names(instance)},
        "static switch": {
            str(name) for name in library.get_static_switch_parameter_names(instance)
        },
    }
    required_parameters = {
        "scalar": set(scalar_parameters),
        "texture": set(texture_parameters),
        "static switch": set(static_switch_parameters),
    }
    for parameter_type, required_names in required_parameters.items():
        missing = sorted(required_names - available_parameters[parameter_type])
        if missing:
            raise RuntimeError(
                f"VAT {parameter_type} parameters are unavailable: " + ", ".join(missing)
            )
    for parameter, value in static_switch_parameters.items():
        changed = library.set_material_instance_static_switch_parameter_value(
            instance, parameter, value
        )
        current = bool(
            library.get_material_instance_static_switch_parameter_value(instance, parameter)
        )
        if not changed and current is not value:
            raise RuntimeError("VAT static switch parameter is unavailable: " + parameter)
    library.update_material_instance(instance)
    if not unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False):
        raise RuntimeError("failed to save VAT playback and legacy-bounds parameters")
    configured = _native_payload(
        _material_instance_parameter_bridge(unreal)(
            instance,
            scalar_parameters,
            {},
            texture_parameters,
        ),
        "Material Instance parameter configuration",
    )
    expected_native = {
        "saved": True,
        "verified": True,
        "scalar_parameter_count": len(scalar_parameters),
        "texture_parameter_count": len(texture_parameters),
        "package_dirty": False,
    }
    if {key: configured.get(key) for key in expected_native} != expected_native:
        raise RuntimeError("native VAT Material Instance parameter verification failed")
    for parameter, texture in texture_parameters.items():
        if library.get_material_instance_texture_parameter_value(instance, parameter) != texture:
            raise RuntimeError("VAT texture parameter failed readback: " + parameter)
    for parameter, value in scalar_parameters.items():
        actual = float(library.get_material_instance_scalar_parameter_value(instance, parameter))
        if not math.isclose(actual, value, rel_tol=1e-6, abs_tol=1e-6):
            raise RuntimeError("VAT scalar parameter failed readback: " + parameter)
    for parameter, value in static_switch_parameters.items():
        actual = bool(
            library.get_material_instance_static_switch_parameter_value(instance, parameter)
        )
        if actual is not value:
            raise RuntimeError("VAT static switch parameter failed readback: " + parameter)


def _vat_names_and_paths(destination: str, prefix: str) -> tuple[dict, dict]:
    names = {
        "mesh": f"SM_{prefix}_VAT",
        "lookup": f"T_{prefix}_Lookup",
        "position": f"T_{prefix}_Position",
        "rotation": f"T_{prefix}_Rotation",
        "material": f"M_{prefix}_VAT",
        "material_instance": f"MI_{prefix}_VAT",
    }
    return names, {key: f"{destination}/{name}" for key, name in names.items()}


def _load_finalization_assets(unreal, paths: dict) -> dict:
    assets = {key: unreal.EditorAssetLibrary.load_asset(path) for key, path in paths.items()}
    missing = [paths[key] for key, asset in assets.items() if asset is None]
    if missing:
        raise RuntimeError("staged VAT assets are missing: " + ", ".join(missing))
    expected = {
        "mesh": unreal.StaticMesh,
        "lookup": unreal.Texture2D,
        "position": unreal.Texture2D,
        "rotation": unreal.Texture2D,
        "material": unreal.Material,
        "material_instance": unreal.MaterialInstanceConstant,
    }
    mismatched = [key for key, cls in expected.items() if not isinstance(assets[key], cls)]
    if mismatched:
        raise RuntimeError("staged VAT asset classes are invalid: " + ", ".join(mismatched))
    return assets


def import_vat_assets(unreal, bundle: dict, destination: str, prefix: str) -> dict:
    """Import the VAT FBX/EXRs and author a SideFX-backed fluid material."""

    function = unreal.EditorAssetLibrary.load_asset(SIDEFX_FLUID_FUNCTION)
    if function is None:
        raise RuntimeError(
            "SideFX Labs UE 5.8 content plugin is not mounted; install it before VAT import"
    )
    _customized_uv_bridge(unreal)
    _material_instance_parameter_bridge(unreal)
    del function
    unreal.EditorAssetLibrary.make_directory(destination)
    names, paths = _vat_names_and_paths(destination, prefix)
    existing = [path for path in paths.values() if unreal.EditorAssetLibrary.does_asset_exist(path)]
    if existing:
        raise RuntimeError("destination assets already exist: " + ", ".join(existing))

    fbx_options = unreal.FbxImportUI()
    fbx_options.set_editor_property("import_mesh", True)
    fbx_options.set_editor_property("import_as_skeletal", False)
    fbx_options.set_editor_property("import_materials", False)
    fbx_options.set_editor_property("import_textures", False)
    fbx_options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    static_mesh_import_data = fbx_options.get_editor_property("static_mesh_import_data")
    static_mesh_import_data.set_editor_property("combine_meshes", True)
    static_mesh_import_data.set_editor_property("generate_lightmap_u_vs", False)
    static_mesh_import_data.set_editor_property("remove_degenerates", False)
    static_mesh_import_data.set_editor_property("auto_generate_collision", False)
    fbx_options.set_editor_property("static_mesh_import_data", static_mesh_import_data)
    mesh, paths["mesh"] = _import_task(
        unreal, bundle["assets"]["geometry"], destination, names["mesh"], fbx_options
    )
    if not isinstance(mesh, unreal.StaticMesh):
        raise RuntimeError("VAT FBX did not import as StaticMesh")
    _configure_fluid_mesh(unreal, mesh)

    textures = {}
    for key in ("lookup", "position", "rotation"):
        texture, paths[key] = _import_task(unreal, bundle["assets"][key], destination, names[key])
        if not isinstance(texture, unreal.Texture2D):
            raise RuntimeError(f"VAT {key} did not import as Texture2D")
        _configure_texture(unreal, texture)
        textures[key] = texture

    material = _create_material(unreal, destination, names["material"])
    instance = _create_material_instance(unreal, material, destination, names["material_instance"])
    for asset in (mesh, *textures.values(), material, instance):
        unreal.EditorAssetLibrary.set_metadata_tag(asset, "LiquiGen.SourceKind", "liquigen_export")
        unreal.EditorAssetLibrary.set_metadata_tag(
            asset, "LiquiGen.SourcePath", str(bundle["source"])
        )
        unreal.EditorAssetLibrary.set_metadata_tag(
            asset, "LiquiGen.FrameCount", str(bundle["frame_count"])
        )
        unreal.EditorAssetLibrary.set_metadata_tag(
            asset, "LiquiGen.SourceFPS", str(bundle["source_fps"])
        )
        unreal.EditorAssetLibrary.set_metadata_tag(asset, "LiquiGen.PipelineStage", "staged")
        unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)
    return {
        "paths": paths,
        "pipeline_stage": "staged",
        "requires_finalize": True,
        "frame_count": bundle["frame_count"],
        "source_fps": bundle["source_fps"],
        "bounds_min": bundle["bounds_min"],
        "bounds_max": bundle["bounds_max"],
        "material_function": SIDEFX_FLUID_FUNCTION,
        "verified_classes": {
            "mesh": mesh.get_class().get_name(),
            "lookup": textures["lookup"].get_class().get_name(),
            "position": textures["position"].get_class().get_name(),
            "rotation": textures["rotation"].get_class().get_name(),
            "material": material.get_class().get_name(),
            "material_instance": instance.get_class().get_name(),
        },
    }


def finalize_vat_assets(unreal, bundle: dict, destination: str, prefix: str) -> dict:
    """Bind staged VAT parameters after Unreal has advanced at least one editor tick."""

    _customized_uv_bridge(unreal)
    _material_instance_parameter_bridge(unreal)
    _, paths = _vat_names_and_paths(destination, prefix)
    assets = _load_finalization_assets(unreal, paths)
    _configure_fluid_mesh(unreal, assets["mesh"])
    textures = {key: assets[key] for key in ("lookup", "position", "rotation")}
    _bind_material_instance(unreal, assets["material_instance"], textures, bundle)
    assets["mesh"].set_material(0, assets["material_instance"])
    for asset in assets.values():
        unreal.EditorAssetLibrary.set_metadata_tag(asset, "LiquiGen.SourceKind", "liquigen_export")
        unreal.EditorAssetLibrary.set_metadata_tag(
            asset, "LiquiGen.SourcePath", str(bundle["source"])
        )
        unreal.EditorAssetLibrary.set_metadata_tag(
            asset, "LiquiGen.FrameCount", str(bundle["frame_count"])
        )
        unreal.EditorAssetLibrary.set_metadata_tag(
            asset, "LiquiGen.SourceFPS", str(bundle["source_fps"])
        )
        unreal.EditorAssetLibrary.set_metadata_tag(asset, "LiquiGen.PipelineStage", "finalized")
        if not unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False):
            raise RuntimeError("failed to save finalized VAT asset: " + asset.get_name())
    return {
        "paths": paths,
        "pipeline_stage": "finalized",
        "requires_finalize": False,
        "frame_count": bundle["frame_count"],
        "source_fps": bundle["source_fps"],
        "bounds_min": bundle["bounds_min"],
        "bounds_max": bundle["bounds_max"],
        "material_function": SIDEFX_FLUID_FUNCTION,
        "verified_classes": {key: asset.get_class().get_name() for key, asset in assets.items()},
    }
