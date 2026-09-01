"""Read back the staged LiquiGen water VAT actor and its render bindings."""

from __future__ import annotations

import json

from _showcase_common import game_asset_path
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def get_water_vat_state(
    actor_label: str = "LiquiGen_WaterCascade_V1",
    expected_level_path: str = "/Game/LiquiGen/Showcase/L_LiquiGenWaterCascadeV1Showcase",
    **_kwargs,
) -> dict:
    try:
        import unreal

        expected_level_path = game_asset_path(expected_level_path)
        world = unreal.EditorLevelLibrary.get_editor_world()
        current_level_path = world.get_outer().get_path_name() if world is not None else ""
        actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        matches = [
            actor
            for actor in actor_subsystem.get_all_level_actors()
            if actor.get_actor_label() == actor_label
        ]
        if len(matches) != 1:
            raise RuntimeError(f"expected one water VAT actor, found {len(matches)}")
        actor = matches[0]
        component = actor.get_component_by_class(unreal.StaticMeshComponent)
        if component is None:
            raise RuntimeError("water VAT actor has no StaticMeshComponent")
        mesh = component.get_editor_property("static_mesh")
        material = component.get_material(0)
        if mesh is None or material is None:
            raise RuntimeError("water VAT mesh or material slot is unbound")
        origin, extent = actor.get_actor_bounds(False)
        mesh_box = mesh.get_bounding_box()
        mesh_build_settings = unreal.get_editor_subsystem(
            unreal.StaticMeshEditorSubsystem
        ).get_lod_build_settings(mesh, 0)
        material_library = unreal.MaterialEditingLibrary
        parameter_names = {
            "scalar": [str(name) for name in material_library.get_scalar_parameter_names(material)],
            "texture": [str(name) for name in material_library.get_texture_parameter_names(material)],
            "static_switch": [
                str(name) for name in material_library.get_static_switch_parameter_names(material)
            ],
        }
        scalar_values = {
            name: float(material_library.get_material_instance_scalar_parameter_value(material, name))
            for name in parameter_names["scalar"]
        }
        static_switch_values = {
            name: bool(
                material_library.get_material_instance_static_switch_parameter_value(
                    material, name
                )
            )
            for name in parameter_names["static_switch"]
        }
        texture_values = {}
        for name in parameter_names["texture"]:
            texture = material_library.get_material_instance_texture_parameter_value(
                material, name
            )
            texture_values[name] = texture.get_path_name() if texture is not None else None
        parent_material = material.get_editor_property("parent")
        expressions = material_library.get_material_expressions(parent_material)
        function_calls = [
            expression
            for expression in expressions
            if expression.get_class().get_name() == "MaterialExpressionMaterialFunctionCall"
        ]
        function_outputs = (
            material_library.get_material_expression_output_names(function_calls[0])
            if len(function_calls) == 1
            else []
        )
        property_output_names = {
            "world_position_offset": material_library.get_material_property_input_node_output_name(
                parent_material, unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET
            ),
            "normal": material_library.get_material_property_input_node_output_name(
                parent_material, unreal.MaterialProperty.MP_NORMAL
            ),
            "base_color": material_library.get_material_property_input_node_output_name(
                parent_material, unreal.MaterialProperty.MP_BASE_COLOR
            ),
            "opacity": material_library.get_material_property_input_node_output_name(
                parent_material, unreal.MaterialProperty.MP_OPACITY
            ),
        }
        bridge = unreal.DccMcpAutomationLibrary
        customized_uvs = {
            str(index): json.loads(bridge.get_material_customized_uv_connection(parent_material, index))
            for index in (1, 2, 3)
        }
        location = actor.get_actor_location()
        scale = actor.get_actor_scale3d()
        return skill_success(
            "Read back LiquiGen water VAT showcase state",
            level_path=current_level_path,
            expected_level_path=expected_level_path,
            level_matches=current_level_path.startswith(expected_level_path),
            actor_label=actor.get_actor_label(),
            actor_path=actor.get_path_name(),
            location=[location.x, location.y, location.z],
            scale=[scale.x, scale.y, scale.z],
            bounds_origin=[origin.x, origin.y, origin.z],
            bounds_extent=[extent.x, extent.y, extent.z],
            mesh_bounds_min=[mesh_box.min.x, mesh_box.min.y, mesh_box.min.z],
            mesh_bounds_max=[mesh_box.max.x, mesh_box.max.y, mesh_box.max.z],
            mesh_build_settings={
                "generate_lightmap_u_vs": bool(
                    mesh_build_settings.get_editor_property("generate_lightmap_u_vs")
                ),
                "use_full_precision_u_vs": bool(
                    mesh_build_settings.get_editor_property("use_full_precision_u_vs")
                ),
                "use_backwards_compatible_f16_trunc_u_vs": bool(
                    mesh_build_settings.get_editor_property(
                        "use_backwards_compatible_f16_trunc_u_vs"
                    )
                ),
            },
            mesh_path=mesh.get_path_name(),
            material_path=material.get_path_name(),
            parent_material_path=parent_material.get_path_name(),
            vat_function_output_names=[str(name) for name in function_outputs],
            material_property_output_names=property_output_names,
            material_customized_uvs=customized_uvs,
            material_parameter_names=parameter_names,
            material_scalar_values=scalar_values,
            material_static_switch_values=static_switch_values,
            material_texture_values=texture_values,
            component_visible=component.is_visible(),
            component_hidden_in_game=component.get_editor_property("hidden_in_game"),
            mobility=str(component.get_editor_property("mobility")),
        )
    except Exception as exc:
        return skill_error("Failed to read LiquiGen water VAT showcase state", str(exc))


def main(**kwargs) -> dict:
    return get_water_vat_state(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
