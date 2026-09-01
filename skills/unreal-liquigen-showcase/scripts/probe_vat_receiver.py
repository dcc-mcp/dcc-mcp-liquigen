"""Read-only live UE 5.8 probe for the LiquiGen VAT receiver dependencies."""

from __future__ import annotations

from _vat_receiver import SIDEFX_FLUID_FUNCTION
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success


@skill_entry
def probe_vat_receiver(**_kwargs) -> dict:
    try:
        import unreal

        function = unreal.EditorAssetLibrary.load_asset(SIDEFX_FLUID_FUNCTION)
        native_bridge = getattr(unreal, "DccMcpAutomationLibrary", None)
        checks = {
            "material_function_loaded": function is not None,
            "texture_filter_nearest": hasattr(unreal.TextureFilter, "TF_NEAREST"),
            "texture_group_16bit_data": hasattr(unreal.TextureGroup, "TEXTUREGROUP_16_BIT_DATA"),
            "texture_no_mipmaps": hasattr(unreal.TextureMipGenSettings, "TMGS_NO_MIPMAPS"),
            "texture_hdr_compression": hasattr(unreal.TextureCompressionSettings, "TC_HDR"),
            "material_function_call": hasattr(
                unreal.MaterialExpressionMaterialFunctionCall, "set_material_function"
            ),
            "material_base_color": hasattr(unreal.MaterialProperty, "MP_BASE_COLOR"),
            "material_normal": hasattr(unreal.MaterialProperty, "MP_NORMAL"),
            "material_wpo": hasattr(unreal.MaterialProperty, "MP_WORLD_POSITION_OFFSET"),
            "native_customized_uv_connect": callable(
                getattr(native_bridge, "connect_material_expression_to_customized_uv", None)
            ),
            "native_customized_uv_readback": callable(
                getattr(native_bridge, "get_material_customized_uv_connection", None)
            ),
            "native_material_instance_parameters": callable(
                getattr(native_bridge, "configure_material_instance_parameters", None)
            ),
            "set_texture_parameter": hasattr(
                unreal.MaterialEditingLibrary,
                "set_material_instance_texture_parameter_value",
            ),
            "set_scalar_parameter": hasattr(
                unreal.MaterialEditingLibrary,
                "set_material_instance_scalar_parameter_value",
            ),
            "set_static_switch_parameter": hasattr(
                unreal.MaterialEditingLibrary,
                "set_material_instance_static_switch_parameter_value",
            ),
        }
        missing = sorted(key for key, available in checks.items() if not available)
        if missing:
            return skill_error(
                "LiquiGen VAT receiver dependency probe failed",
                "missing UE 5.8 interfaces: " + ", ".join(missing),
                possible_solutions=[
                    "Install and enable the SideFX Labs UE 5.8 content plugin.",
                    "Install and restart with a DCC-MCP Unreal plugin that exposes "
                    "the native Customized UV and Material Instance parameter bridges.",
                ],
            )
        return skill_success(
            "LiquiGen VAT receiver dependencies are available",
            checks=checks,
            material_function=SIDEFX_FLUID_FUNCTION,
            material_function_class=function.get_class().get_name(),
        )
    except Exception as exc:
        return skill_error(
            "LiquiGen VAT receiver dependency probe failed",
            str(exc),
            possible_solutions=[
                "Install and enable the SideFX Labs UE 5.8 content plugin.",
            ],
        )


def main(**kwargs) -> dict:
    return probe_vat_receiver(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
