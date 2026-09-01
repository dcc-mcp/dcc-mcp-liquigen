"""Build a bounds-driven UE 5.8 stage for one finalized LiquiGen water VAT."""

from __future__ import annotations

from pathlib import Path

from _showcase_common import effect_scale as validate_effect_scale
from _showcase_common import game_asset_path
from _vat_receiver import canonical_vat_bundle
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

GENERATED_TAG = "DccMcpLiquiGenWaterShowcase"


def _tag(actor, folder: str) -> None:
    actor.tags = [GENERATED_TAG]
    actor.set_folder_path(folder)


@skill_entry
def stage_water_vat(
    source_directory: str,
    static_mesh_path: str,
    material_instance_path: str,
    source_kind: str,
    level_path: str = "/Game/LiquiGen/Showcase/L_LiquiGenWaterCascadeShowcase",
    actor_label: str = "LiquiGen_WaterCascade_Showcase",
    effect_scale: float = 0.65,
    **_kwargs,
) -> dict:
    try:
        import unreal

        if source_kind != "liquigen_export":
            raise ValueError("source_kind must be liquigen_export")
        bundle = canonical_vat_bundle(Path(source_directory))
        static_mesh_path = game_asset_path(static_mesh_path)
        material_instance_path = game_asset_path(material_instance_path)
        level_path = game_asset_path(level_path)
        scale = validate_effect_scale(effect_scale)

        mesh = unreal.load_asset(static_mesh_path)
        material = unreal.load_asset(material_instance_path)
        if mesh is None or mesh.get_class().get_name() != "StaticMesh":
            raise ValueError("static_mesh_path is not a StaticMesh")
        if material is None or material.get_class().get_name() != "MaterialInstanceConstant":
            raise ValueError("material_instance_path is not a MaterialInstanceConstant")

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

        bounds_min = bundle["bounds_min"]
        bounds_max = bundle["bounds_max"]
        center_x = (bounds_min[0] + bounds_max[0]) * 0.5
        center_y = (bounds_min[1] + bounds_max[1]) * 0.5
        width = (bounds_max[0] - bounds_min[0]) * scale
        depth = (bounds_max[1] - bounds_min[1]) * scale
        height = (bounds_max[2] - bounds_min[2]) * scale
        radius = max(width, depth, height, 300.0)
        effect_location = unreal.Vector(
            -center_x * scale,
            -center_y * scale,
            -bounds_min[2] * scale + 12.0,
        )

        effect = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, effect_location, unreal.Rotator(), False
        )
        effect.set_actor_label(actor_label)
        _tag(effect, "LiquiGenWaterShowcase/VFX")
        effect.set_actor_scale3d(unreal.Vector(scale, scale, scale))
        effect_component = effect.get_component_by_class(unreal.StaticMeshComponent)
        effect_component.set_static_mesh(mesh)
        effect_component.set_material(0, material)
        effect_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)

        cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube.Cube")
        floor_material = unreal.EditorAssetLibrary.load_asset(
            "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
        )
        if cube is None:
            raise RuntimeError("engine Cube asset is unavailable")
        floor = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, -20.0), unreal.Rotator(), False
        )
        floor.set_actor_label("LiquiGen_Water_Showcase_Floor")
        _tag(floor, "LiquiGenWaterShowcase/Stage")
        floor_extent = max(14.0, radius / 45.0)
        floor.set_actor_scale3d(unreal.Vector(floor_extent, floor_extent, 0.2))
        floor_component = floor.get_component_by_class(unreal.StaticMeshComponent)
        floor_component.set_static_mesh(cube)
        floor_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        if floor_material is not None:
            floor_component.set_material(0, floor_material)

        target = unreal.Vector(0.0, 0.0, max(height * 0.42, 180.0))
        camera_position = unreal.Vector(-radius * 1.15, -radius * 1.85, max(height * 0.72, 520.0))
        camera_rotation = unreal.MathLibrary.find_look_at_rotation(camera_position, target)
        camera = actor_subsystem.spawn_actor_from_class(
            unreal.CineCameraActor, camera_position, camera_rotation, False
        )
        camera.set_actor_label("LiquiGen_Water_Showcase_Camera")
        _tag(camera, "LiquiGenWaterShowcase/Camera")
        camera.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
        cine = camera.get_cine_camera_component()
        cine.set_editor_property("current_focal_length", 48.0)
        cine.set_editor_property("current_aperture", 3.2)
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(camera_position, camera_rotation)

        sun = actor_subsystem.spawn_actor_from_class(
            unreal.DirectionalLight,
            unreal.Vector(0.0, 0.0, height + 600.0),
            unreal.Rotator(roll=0.0, pitch=-38.0, yaw=-32.0),
            False,
        )
        sun.set_actor_label("LiquiGen_Water_Key")
        _tag(sun, "LiquiGenWaterShowcase/Lights")
        sun_component = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sun_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sun_component.set_editor_property("intensity", 5.5)

        skylight = actor_subsystem.spawn_actor_from_class(
            unreal.SkyLight, unreal.Vector(0.0, 0.0, height), unreal.Rotator(), False
        )
        skylight.set_actor_label("LiquiGen_Water_Fill")
        _tag(skylight, "LiquiGenWaterShowcase/Lights")
        sky_component = skylight.get_component_by_class(unreal.SkyLightComponent)
        sky_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sky_component.set_editor_property("intensity", 1.2)

        rim = actor_subsystem.spawn_actor_from_class(
            unreal.PointLight,
            unreal.Vector(radius * 0.45, -radius * 0.2, max(height * 0.72, 480.0)),
            unreal.Rotator(),
            False,
        )
        rim.set_actor_label("LiquiGen_Water_Rim")
        _tag(rim, "LiquiGenWaterShowcase/Lights")
        rim_component = rim.get_component_by_class(unreal.PointLightComponent)
        rim_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        rim_component.set_editor_property("intensity", 4200.0)
        rim_component.set_editor_property("light_color", unreal.Color(110, 190, 255, 255))

        if not unreal.EditorLevelLibrary.save_current_level():
            raise RuntimeError("failed to save water showcase level")
        if not unreal.EditorAssetLibrary.does_asset_exist(level_path):
            raise RuntimeError("water showcase level failed asset-registry readback")

        return skill_success(
            "Staged LiquiGen water VAT showcase",
            level_path=level_path,
            static_mesh_path=static_mesh_path,
            material_instance_path=material_instance_path,
            actor_path=effect.get_path_name(),
            actor_label=effect.get_actor_label(),
            source_kind=source_kind,
            bounds_min=bounds_min,
            bounds_max=bounds_max,
            effect_scale=[scale, scale, scale],
            effect_location=[effect_location.x, effect_location.y, effect_location.z],
            camera={
                "actor_label": camera.get_actor_label(),
                "auto_activate_player_index": camera.get_auto_activate_player_index(),
                "location": [camera_position.x, camera_position.y, camera_position.z],
                "rotation": [camera_rotation.pitch, camera_rotation.yaw, camera_rotation.roll],
            },
            generated_actor_count=6,
            prompt="Start capture, then play the level for the looping water VAT take.",
        )
    except Exception as exc:
        return skill_error("Failed to stage LiquiGen water VAT", str(exc))


def main(**kwargs) -> dict:
    return stage_water_vat(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
