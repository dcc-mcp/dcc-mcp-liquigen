"""UE 5.8 ParticleSubUV and Niagara receiver authoring helpers."""

from __future__ import annotations

import struct
from pathlib import Path

from _showcase_common import chain_offsets, procedural_layer_specs


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or not header.startswith(b"\x89PNG\r\n\x1a\n") or header[12:16] != b"IHDR":
        raise ValueError("source_path is not a PNG with a valid IHDR header")
    return struct.unpack(">II", header[16:24])


def create_material(unreal, texture, destination: str, name: str):
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, destination, unreal.Material, unreal.MaterialFactoryNew()
    )
    if material is None:
        raise RuntimeError(f"failed to create material: {destination}/{name}")
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("used_with_niagara_sprites", True)
    expression = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionParticleSubUV, -300, 0
    )
    expression.set_editor_property("texture", texture)
    if not unreal.MaterialEditingLibrary.connect_material_property(
        expression, "RGB", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("failed to connect flipbook RGB to emissive color")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        expression, "A", unreal.MaterialProperty.MP_OPACITY
    ):
        raise RuntimeError("failed to connect flipbook alpha to opacity")
    errors = [str(item) for item in unreal.MaterialEditingLibrary.recompile_material(material)]
    if errors:
        raise RuntimeError("material compile failed: " + "; ".join(errors))
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError("failed to save flipbook material")
    return material


def create_procedural_material(
    unreal,
    destination: str,
    name: str,
    color: tuple[float, float, float],
    opacity: float,
):
    """Create an unlit additive Niagara sprite material from engine content only."""
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, destination, unreal.Material, unreal.MaterialFactoryNew()
    )
    if material is None:
        raise RuntimeError(f"failed to create material: {destination}/{name}")
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", True)
    material.set_editor_property("used_with_niagara_sprites", True)

    coordinates = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureCoordinate, -920, 120
    )
    center = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant2Vector, -920, 240
    )
    center.set_editor_property("r", 0.5)
    center.set_editor_property("g", 0.5)
    delta = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionSubtract, -720, 150
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(coordinates, "", delta, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(center, "", delta, "B")
    radius_squared = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionDotProduct, -540, 150
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(delta, "", radius_squared, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(delta, "", radius_squared, "B")
    normalize = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -360, 150
    )
    normalize.set_editor_property("const_b", -4.0)
    if not unreal.MaterialEditingLibrary.connect_material_expressions(
        radius_squared, "", normalize, "A"
    ):
        raise RuntimeError("failed to connect procedural radial distance scale")
    invert = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionAdd, -180, 150
    )
    invert.set_editor_property("const_b", 1.0)
    if not unreal.MaterialEditingLibrary.connect_material_expressions(normalize, "", invert, "A"):
        raise RuntimeError("failed to connect procedural radial inversion")
    mask = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionMax, 0, 150
    )
    mask.set_editor_property("const_b", 0.0)
    if not unreal.MaterialEditingLibrary.connect_material_expressions(invert, "", mask, "A"):
        raise RuntimeError("failed to connect procedural radial lower clamp")
    tint = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -320, -100
    )
    tint.set_editor_property("constant", unreal.LinearColor(*color, 1.0))
    emissive = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionMultiply, 420, -40
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(mask, "", emissive, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(tint, "", emissive, "B")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        raise RuntimeError("failed to connect procedural emissive material")
    opacity_value = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, 180, 340
    )
    opacity_value.set_editor_property("r", float(opacity))
    opacity_mask = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionMultiply, 420, 250
    )
    unreal.MaterialEditingLibrary.connect_material_expressions(mask, "", opacity_mask, "A")
    unreal.MaterialEditingLibrary.connect_material_expressions(opacity_value, "", opacity_mask, "B")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        opacity_mask, "", unreal.MaterialProperty.MP_OPACITY
    ):
        raise RuntimeError("failed to connect procedural opacity material")
    errors = [str(item) for item in unreal.MaterialEditingLibrary.recompile_material(material)]
    if errors:
        raise RuntimeError("procedural material compile failed: " + "; ".join(errors))
    if not unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False):
        raise RuntimeError("failed to save procedural material")
    return material


def _module(unreal, fx, emitter, name: str, asset_path: str, category):
    asset_data = fx.create_asset_data(asset_path)
    return emitter.find_or_add_module_script(
        name, unreal.CreateScriptContextArgs(asset_data), category
    )


def _configure_infinite_emitter(unreal, fx, emitter) -> None:
    state = _module(
        unreal,
        fx,
        emitter,
        "EmitterState",
        "/Niagara/Modules/Emitter/EmitterState.EmitterState",
        unreal.ScriptExecutionCategory.EMITTER_UPDATE,
    )
    state.set_parameter(
        "Life Cycle Mode",
        fx.create_script_input_enum(
            "/Niagara/Enums/ENiagaraEmitterLifeCycleMode.ENiagaraEmitterLifeCycleMode",
            "Self",
        ),
    )
    state.set_parameter(
        "Loop Behavior",
        fx.create_script_input_enum(
            "/Niagara/Enums/ENiagara_EmitterStateOptions.ENiagara_EmitterStateOptions",
            "Infinite",
        ),
    )


def create_procedural_chain_system(
    unreal,
    materials: dict[str, object],
    destination: str,
    name: str,
    chain: dict[str, float | int],
    blast_diameter_cm: float,
    particle_count: int,
):
    """Author a repeating multi-layer chain burst driven by LiquiGen graph timing."""
    system = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, destination, unreal.NiagaraSystem, unreal.NiagaraSystemFactoryNew()
    )
    if system is None:
        raise RuntimeError(f"failed to create Niagara system: {destination}/{name}")
    fx = unreal.FXConverterUtilitiesLibrary
    context = fx.create_system_conversion_context(system)
    offsets = chain_offsets(int(chain["count"]), float(chain["spacing_cm"]))
    layers = procedural_layer_specs(blast_diameter_cm)
    for stage, (x, y, z) in enumerate(offsets):
        direction = -1.0 if stage % 2 else 1.0
        for (
            layer_name,
            material_key,
            lifetime,
            sprite_size,
            box_size,
            velocity,
            count_scale,
        ) in layers:
            emitter = context.add_empty_emitter(f"LiquiGen{layer_name}{stage + 1:02d}")
            emitter.set_local_space(False)
            _configure_infinite_emitter(unreal, fx, emitter)
            spawn = _module(
                unreal,
                fx,
                emitter,
                "SpawnBurstInstantaneous",
                "/Niagara/Modules/Emitter/SpawnBurst_Instantaneous.SpawnBurst_Instantaneous",
                unreal.ScriptExecutionCategory.EMITTER_UPDATE,
            )
            spawn.set_parameter(
                "Spawn Count", fx.create_script_input_int(int(particle_count * count_scale))
            )
            spawn.set_parameter(
                "Spawn Time",
                fx.create_script_input_float(stage * float(chain["delay_seconds"])),
            )
            initialize = _module(
                unreal,
                fx,
                emitter,
                "InitializeParticle",
                "/Niagara/Modules/Spawn/Initialization/V2/InitializeParticle.InitializeParticle",
                unreal.ScriptExecutionCategory.PARTICLE_SPAWN,
            )
            initialize.set_parameter("Lifetime", fx.create_script_input_float(lifetime))
            initialize.set_parameter(
                "Sprite Size Mode",
                fx.create_script_input_enum(
                    "/Niagara/Enums/ENiagara_SizeScaleMode.ENiagara_SizeScaleMode",
                    "Non-Uniform",
                ),
            )
            initialize.set_parameter(
                "Sprite Size",
                fx.create_script_input_vec2(unreal.Vector2D(*sprite_size)),
                True,
                True,
            )
            shape = _module(
                unreal,
                fx,
                emitter,
                "ShapeLocation",
                "/Niagara/Modules/Spawn/Location/V2/ShapeLocation.ShapeLocation",
                unreal.ScriptExecutionCategory.PARTICLE_SPAWN,
            )
            shape.set_parameter(
                "Shape Primitive",
                fx.create_script_input_enum(
                    "/Niagara/Enums/Location/ENiagara_LocationShapes.ENiagara_LocationShapes",
                    "Box",
                ),
            )
            shape.set_parameter("Box Size", fx.create_script_input_vector(unreal.Vector(*box_size)))
            offset = _module(
                unreal,
                fx,
                emitter,
                "AddVectorToPosition",
                "/CascadeToNiagaraConverter/NiagaraScripts/ModuleScripts/AddVectorToPosition.AddVectorToPosition",
                unreal.ScriptExecutionCategory.PARTICLE_SPAWN,
            )
            offset.set_parameter("Vector", fx.create_script_input_vector(unreal.Vector(x, y, z)))
            add_velocity = _module(
                unreal,
                fx,
                emitter,
                "AddVelocity",
                "/Niagara/Modules/Spawn/Velocity/AddVelocity.AddVelocity",
                unreal.ScriptExecutionCategory.PARTICLE_SPAWN,
            )
            add_velocity.set_parameter(
                "Velocity",
                fx.create_script_input_vector(
                    unreal.Vector(direction * velocity[0], velocity[1], velocity[2])
                ),
            )
            if layer_name == "Sparks":
                gravity = _module(
                    unreal,
                    fx,
                    emitter,
                    "GravityForce",
                    "/Niagara/Modules/Update/Forces/GravityForce.GravityForce",
                    unreal.ScriptExecutionCategory.PARTICLE_UPDATE,
                )
                gravity.set_parameter(
                    "Gravity", fx.create_script_input_vector(unreal.Vector(0.0, 0.0, -980.0))
                )
            _module(
                unreal,
                fx,
                emitter,
                "ParticleState",
                "/Niagara/Modules/Update/Lifetime/ParticleState.ParticleState",
                unreal.ScriptExecutionCategory.PARTICLE_UPDATE,
            )
            _module(
                unreal,
                fx,
                emitter,
                "SolveForcesAndVelocity",
                "/Niagara/Modules/Solvers/SolveForcesAndVelocity.SolveForcesAndVelocity",
                unreal.ScriptExecutionCategory.PARTICLE_UPDATE,
            )
            renderer = unreal.NiagaraSpriteRendererProperties()
            renderer.set_editor_property("material", materials[material_key])
            renderer.set_editor_property("facing_mode", unreal.NiagaraSpriteFacingMode.FACE_CAMERA)
            renderer.set_editor_property("cast_shadows", False)
            emitter.add_renderer(f"LiquiGen{layer_name}Renderer{stage + 1:02d}", renderer)
    context.set_warmup_tick_delta(1.0 / 60.0)
    context.finalize()
    if not unreal.EditorAssetLibrary.save_loaded_asset(system, only_if_is_dirty=False):
        raise RuntimeError("failed to save procedural Niagara system")
    return system


def create_chain_system(
    unreal,
    material,
    destination: str,
    name: str,
    columns: int,
    rows: int,
    chain: dict[str, float | int],
):
    system = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, destination, unreal.NiagaraSystem, unreal.NiagaraSystemFactoryNew()
    )
    if system is None:
        raise RuntimeError(f"failed to create Niagara system: {destination}/{name}")
    fx = unreal.FXConverterUtilitiesLibrary
    context = fx.create_system_conversion_context(system)
    offsets = chain_offsets(int(chain["count"]), float(chain["spacing_cm"]))
    for stage, (x, y, z) in enumerate(offsets):
        emitter = context.add_empty_emitter(f"LiquiGenChainBurst{stage + 1:02d}")
        emitter.set_local_space(False)
        _module(
            unreal,
            fx,
            emitter,
            "EmitterState",
            "/Niagara/Modules/Emitter/EmitterState.EmitterState",
            unreal.ScriptExecutionCategory.EMITTER_UPDATE,
        )
        spawn = _module(
            unreal,
            fx,
            emitter,
            "SpawnBurstInstantaneous",
            "/Niagara/Modules/Emitter/SpawnBurst_Instantaneous.SpawnBurst_Instantaneous",
            unreal.ScriptExecutionCategory.EMITTER_UPDATE,
        )
        spawn.set_parameter("Spawn Count", fx.create_script_input_int(1))
        spawn.set_parameter(
            "Spawn Time", fx.create_script_input_float(stage * float(chain["delay_seconds"]))
        )
        initialize = _module(
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
                "/Niagara/Enums/ENiagara_SizeScaleMode.ENiagara_SizeScaleMode", "Non-Uniform"
            ),
        )
        initialize.set_parameter(
            "Sprite Size", fx.create_script_input_vec2(unreal.Vector2D(512.0, 512.0)), True, True
        )
        offset = _module(
            unreal,
            fx,
            emitter,
            "AddVectorToPosition",
            "/CascadeToNiagaraConverter/NiagaraScripts/ModuleScripts/AddVectorToPosition.AddVectorToPosition",
            unreal.ScriptExecutionCategory.PARTICLE_SPAWN,
        )
        offset.set_parameter("Vector", fx.create_script_input_vector(unreal.Vector(x, y, z)))
        _module(
            unreal,
            fx,
            emitter,
            "ParticleState",
            "/Niagara/Modules/Update/Lifetime/ParticleState.ParticleState",
            unreal.ScriptExecutionCategory.PARTICLE_UPDATE,
        )
        _module(
            unreal,
            fx,
            emitter,
            "SubUVAnimation",
            "/Niagara/Modules/Update/SubUV/V2/SubUVAnimation.SubUVAnimation",
            unreal.ScriptExecutionCategory.PARTICLE_UPDATE,
        )
        renderer = unreal.NiagaraSpriteRendererProperties()
        renderer.set_editor_property("material", material)
        renderer.set_editor_property("sub_image_size", unreal.Vector2D(float(columns), float(rows)))
        renderer.set_editor_property("sub_image_blend", True)
        renderer.set_editor_property("facing_mode", unreal.NiagaraSpriteFacingMode.FACE_CAMERA)
        renderer.set_editor_property("cast_shadows", False)
        emitter.add_renderer(f"LiquiGenChainRenderer{stage + 1:02d}", renderer)
    context.set_warmup_tick_delta(1.0 / 60.0)
    context.finalize()
    if not unreal.EditorAssetLibrary.save_loaded_asset(system, only_if_is_dirty=False):
        raise RuntimeError("failed to save Niagara system")
    return system
