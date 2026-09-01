"""Build a deterministic local stage for the LiquiGen chain burst."""

from __future__ import annotations

from _showcase_common import effect_scale as validate_effect_scale
from _showcase_common import game_asset_path
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

GENERATED_TAG = "DccMcpLiquiGenShowcase"


def _tag(actor, folder: str) -> None:
    actor.tags = [GENERATED_TAG]
    actor.set_folder_path(folder)


@skill_entry
def stage_chain_burst(
    niagara_system_path: str,
    source_kind: str,
    level_path: str = "/Game/LiquiGen/Showcase/L_LiquiGenChainBurstShowcase",
    actor_label: str = "LiquiGen_ChainBurst_Showcase",
    effect_scale: float = 1.0,
    **_kwargs,
) -> dict:
    try:
        import unreal

        niagara_system_path = game_asset_path(niagara_system_path)
        level_path = game_asset_path(level_path)
        effect_scale = validate_effect_scale(effect_scale)
        if source_kind not in {"liquigen_export", "synthetic_proxy"}:
            raise ValueError("source_kind must be liquigen_export or synthetic_proxy")
        system = unreal.load_asset(niagara_system_path)
        if system is None or system.get_class().get_name() != "NiagaraSystem":
            raise ValueError("niagara_system_path is not a NiagaraSystem")

        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        if unreal.EditorAssetLibrary.does_asset_exist(level_path):
            if not level_subsystem.load_level(level_path):
                raise RuntimeError("failed to load existing showcase level")
            for actor in list(actor_subsystem.get_all_level_actors()):
                if GENERATED_TAG in [str(tag) for tag in actor.tags]:
                    actor_subsystem.destroy_actor(actor)
        elif not level_subsystem.new_level(level_path):
            raise RuntimeError("failed to create showcase level")

        cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube.Cube")
        floor_material = unreal.EditorAssetLibrary.load_asset(
            "/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"
        )
        if cube is None:
            raise RuntimeError("engine Cube asset is unavailable")

        floor = actor_subsystem.spawn_actor_from_class(
            unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, -85.0), unreal.Rotator(), False
        )
        floor.set_actor_label("LiquiGen_Showcase_Floor")
        _tag(floor, "LiquiGenShowcase/Stage")
        floor.set_actor_scale3d(unreal.Vector(18.0, 18.0, 0.1))
        floor_component = floor.get_component_by_class(unreal.StaticMeshComponent)
        floor_component.set_static_mesh(cube)
        floor_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        if floor_material is not None:
            floor_component.set_material(0, floor_material)

        effect = unreal.EditorLevelLibrary.spawn_actor_from_object(
            system, unreal.Vector(0.0, 0.0, 160.0), unreal.Rotator()
        )
        if effect is None:
            raise RuntimeError("failed to spawn Niagara actor")
        effect.set_actor_label(actor_label)
        _tag(effect, "LiquiGenShowcase/VFX")
        effect.set_actor_scale3d(unreal.Vector(effect_scale, effect_scale, effect_scale))
        component = effect.get_component_by_class(unreal.NiagaraComponent)
        component.activate(reset=True)

        camera_position = unreal.Vector(-1500.0, -2400.0, 980.0)
        target = unreal.Vector(0.0, 0.0, 170.0)
        camera_rotation = unreal.MathLibrary.find_look_at_rotation(camera_position, target)
        camera = actor_subsystem.spawn_actor_from_class(
            unreal.CineCameraActor, camera_position, camera_rotation, False
        )
        camera.set_actor_label("LiquiGen_Showcase_Camera")
        _tag(camera, "LiquiGenShowcase/Camera")
        camera.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)
        cine = camera.get_cine_camera_component()
        cine.set_editor_property("current_focal_length", 42.0)
        cine.set_editor_property("current_aperture", 4.0)
        unreal.EditorLevelLibrary.set_level_viewport_camera_info(camera_position, camera_rotation)

        sun = actor_subsystem.spawn_actor_from_class(
            unreal.DirectionalLight,
            unreal.Vector(0.0, 0.0, 900.0),
            unreal.Rotator(roll=0.0, pitch=-42.0, yaw=-28.0),
            False,
        )
        sun.set_actor_label("LiquiGen_Showcase_Key")
        _tag(sun, "LiquiGenShowcase/Lights")
        sun_component = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sun_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sun_component.set_editor_property("intensity", 6.0)

        skylight = actor_subsystem.spawn_actor_from_class(
            unreal.SkyLight, unreal.Vector(0.0, 0.0, 500.0), unreal.Rotator(), False
        )
        skylight.set_actor_label("LiquiGen_Showcase_Fill")
        _tag(skylight, "LiquiGenShowcase/Lights")
        sky_component = skylight.get_component_by_class(unreal.SkyLightComponent)
        sky_component.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
        sky_component.set_editor_property("intensity", 0.8)

        if not unreal.EditorLevelLibrary.save_current_level():
            raise RuntimeError("failed to save showcase level")
        if not unreal.EditorAssetLibrary.does_asset_exist(level_path):
            raise RuntimeError("showcase level failed asset-registry readback")

        return skill_success(
            "Staged LiquiGen chain burst showcase",
            level_path=level_path,
            niagara_system_path=niagara_system_path,
            actor_label=actor_label,
            actor_path=effect.get_path_name(),
            effect_scale=[
                effect.get_actor_scale3d().x,
                effect.get_actor_scale3d().y,
                effect.get_actor_scale3d().z,
            ],
            source_kind=source_kind,
            camera={
                "actor_label": camera.get_actor_label(),
                "auto_activate_player_index": camera.get_auto_activate_player_index(),
                "location": [camera_position.x, camera_position.y, camera_position.z],
                "rotation": [camera_rotation.pitch, camera_rotation.yaw, camera_rotation.roll],
            },
            generated_actor_count=5,
            prompt="Start capture, then call replay_chain_burst for a clean take.",
        )
    except Exception as exc:
        return skill_error("Failed to stage LiquiGen chain burst", str(exc))


def main(**kwargs) -> dict:
    return stage_chain_burst(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
