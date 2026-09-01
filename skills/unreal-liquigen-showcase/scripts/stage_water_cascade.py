"""Build a deterministic UE 5.8 stage for a procedural LiquiGen water cascade."""

from __future__ import annotations

from _showcase_common import effect_scale as validate_effect_scale
from _showcase_common import game_asset_path
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

GENERATED_TAG = "DccMcpLiquiGenWaterShowcase"


def _tag(actor, folder: str) -> None:
    actor.tags = [GENERATED_TAG]
    actor.set_folder_path(folder)


@skill_entry
def stage_water_cascade(
    niagara_system_path: str,
    source_kind: str,
    pool_material_path: str | None = None,
    level_path: str = "/Game/LiquiGen/Showcase/L_LiquiGenWaterCascadeProceduralShowcase",
    actor_label: str = "LiquiGen_WaterCascade_Showcase",
    effect_scale: float = 1.0,
    **_kwargs,
) -> dict:
    try:
        import unreal

        niagara_system_path = game_asset_path(niagara_system_path)
        level_path = game_asset_path(level_path)
        effect_scale = validate_effect_scale(effect_scale)
        if source_kind != "liquigen_export":
            raise ValueError("source_kind must be liquigen_export")
        system = unreal.load_asset(niagara_system_path)
        if system is None or system.get_class().get_name() != "NiagaraSystem":
            raise ValueError("niagara_system_path is not a NiagaraSystem")
        pool_material = None
        if pool_material_path:
            pool_material_path = game_asset_path(pool_material_path)
            pool_material = unreal.load_asset(pool_material_path)
            if pool_material is None or pool_material.get_class().get_name() not in {
                "Material",
                "MaterialInstanceConstant",
            }:
                raise ValueError("pool_material_path is not a Material or MaterialInstanceConstant")

        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if unreal.EditorAssetLibrary.does_asset_exist(level_path):
            if not level_subsystem.load_level(level_path):
                raise RuntimeError("failed to load existing water showcase level")
            for actor in list(actor_subsystem.get_all_level_actors()):
                if GENERATED_TAG in [str(tag) for tag in actor.tags]:
                    actor_subsystem.destroy_actor(actor)
        elif not level_subsystem.new_level(level_path):
            raise RuntimeError("failed to create water showcase level")

        cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube.Cube")
        floor_material = unreal.EditorAssetLibrary.load_asset(
            "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
        )
        if cube is None:
            raise RuntimeError("engine Cube asset is unavailable")
        floor = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, -90.0), unreal.Rotator(), False
        )
        floor.set_actor_label("LiquiGen_Water_Stage")
        _tag(floor, "LiquiGenWaterShowcase/Stage")
        floor.set_actor_scale3d(unreal.Vector(20.0, 16.0, 0.12))
        floor_component = floor.get_component_by_class(unreal.StaticMeshComponent)
        floor_component.set_static_mesh(cube)
        floor_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        if floor_material is not None:
            floor_component.set_material(0, floor_material)

        pool = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(50.0, 0.0, -70.0), unreal.Rotator(), False
        )
        pool.set_actor_label("LiquiGen_Water_Pool")
        _tag(pool, "LiquiGenWaterShowcase/Stage")
        pool.set_actor_scale3d(unreal.Vector(8.0, 6.0, 0.025))
        pool_component = pool.get_component_by_class(unreal.StaticMeshComponent)
        pool_component.set_static_mesh(cube)
        pool_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        if pool_material is not None:
            pool_component.set_material(0, pool_material)

        effect = unreal.EditorLevelLibrary.spawn_actor_from_object(
            system, unreal.Vector(0.0, 0.0, 120.0), unreal.Rotator()
        )
        if effect is None:
            raise RuntimeError("failed to spawn water Niagara actor")
        effect.set_actor_label(actor_label)
        _tag(effect, "LiquiGenWaterShowcase/VFX")
        effect.set_actor_scale3d(unreal.Vector(effect_scale, effect_scale, effect_scale))
        component = effect.get_component_by_class(unreal.NiagaraComponent)
        component.activate(reset=True)

        camera_position = unreal.Vector(-1450.0, -2350.0, 900.0)
        target = unreal.Vector(-220.0, -20.0, 470.0)
        camera_rotation = unreal.MathLibrary.find_look_at_rotation(camera_position, target)
        camera = actor_subsystem.spawn_actor_from_class(
            unreal.CineCameraActor, camera_position, camera_rotation, False
        )
        camera.set_actor_label("LiquiGen_Water_Showcase_Camera")
        _tag(camera, "LiquiGenWaterShowcase/Camera")
        camera.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
        cine = camera.get_cine_camera_component()
        cine.set_editor_property("current_focal_length", 38.0)
        cine.set_editor_property("current_aperture", 3.2)
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(camera_position, camera_rotation)

        sun = actor_subsystem.spawn_actor_from_class(
            unreal.DirectionalLight,
            unreal.Vector(0.0, 0.0, 1100.0),
            unreal.Rotator(roll=0.0, pitch=-46.0, yaw=-32.0),
            False,
        )
        sun.set_actor_label("LiquiGen_Water_Key")
        _tag(sun, "LiquiGenWaterShowcase/Lights")
        sun_component = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sun_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sun_component.set_editor_property("intensity", 4.0)

        skylight = actor_subsystem.spawn_actor_from_class(
            unreal.SkyLight, unreal.Vector(0.0, 0.0, 600.0), unreal.Rotator(), False
        )
        skylight.set_actor_label("LiquiGen_Water_Fill")
        _tag(skylight, "LiquiGenWaterShowcase/Lights")
        sky_component = skylight.get_component_by_class(unreal.SkyLightComponent)
        sky_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sky_component.set_editor_property("intensity", 1.1)

        accent = actor_subsystem.spawn_actor_from_class(
            unreal.PointLight, unreal.Vector(0.0, -250.0, 540.0), unreal.Rotator(), False
        )
        accent.set_actor_label("LiquiGen_Water_Accent")
        _tag(accent, "LiquiGenWaterShowcase/Lights")
        accent_component = accent.get_component_by_class(unreal.PointLightComponent)
        accent_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        accent_component.set_editor_property("intensity", 900.0)
        accent_component.set_editor_property("attenuation_radius", 1800.0)
        accent_component.set_editor_property("light_color", unreal.Color(40, 150, 255, 255))

        if not unreal.EditorLevelLibrary.save_current_level():
            raise RuntimeError("failed to save water showcase level")
        if not unreal.EditorAssetLibrary.does_asset_exist(level_path):
            raise RuntimeError("water showcase level failed asset-registry readback")
        return skill_success(
            "Staged LiquiGen procedural water cascade showcase",
            level_path=level_path,
            niagara_system_path=niagara_system_path,
            pool_material_path=pool_material_path,
            actor_label=actor_label,
            actor_path=effect.get_path_name(),
            effect_scale=[effect_scale, effect_scale, effect_scale],
            source_kind=source_kind,
            appearance="unreal_procedural_water",
            camera={
                "actor_label": camera.get_actor_label(),
                "auto_activate_player_index": camera.get_auto_activate_player_index(),
                "location": [camera_position.x, camera_position.y, camera_position.z],
                "rotation": [camera_rotation.pitch, camera_rotation.yaw, camera_rotation.roll],
            },
            generated_actor_count=7,
            prompt="Start capture, then call replay_chain_burst with this actor label.",
        )
    except Exception as exc:
        return skill_error("Failed to stage LiquiGen procedural water cascade", str(exc))


def main(**kwargs) -> dict:
    return stage_water_cascade(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
