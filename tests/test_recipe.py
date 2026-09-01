import pytest

from dcc_mcp_liquigen.recipe import compile_liquid_chain_burst


def test_compile_unreal_vat_chain_burst_is_replayable_and_showcase_ready() -> None:
    plan = compile_liquid_chain_burst(
        output_directory="F:/exports/liquigen-chain",
        burst_count=5,
        delay_seconds=0.18,
        spacing_m=2.6,
        export_profile="ue_vat",
    )

    assert plan["effect_semantics"] == "liquid_chain_burst"
    assert plan["combustion_supported"] is False
    assert plan["export"]["node_type"] == "Node_Export_Mesh"
    assert plan["export"]["parameters"] == {
        "export_format": "Vertex Animated Texture",
        "vat_target_engine": "Unreal",
        "directory": "F:\\exports\\liquigen-chain",
    }
    assert [step["index"] for step in plan["steps"]] == list(range(1, len(plan["steps"]) + 1))
    assert sum(step["node_type"] == "Node_Emitter" for step in plan["steps"]) == 5
    assert [chapter["id"] for chapter in plan["showcase_chapters"]] == [
        "bridge_diagnostics",
        "preset_and_project",
        "node_graph_build",
        "simulation_and_export",
        "unreal_import",
        "ue_material_authoring",
        "runtime_verification",
    ]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"burst_count": 1}, "burst_count"),
        ({"delay_seconds": 0.01}, "delay_seconds"),
        ({"spacing_m": 0}, "spacing_m"),
        ({"export_profile": "unknown"}, "export_profile"),
        ({"output_directory": "relative/export"}, "output_directory"),
    ],
)
def test_chain_burst_recipe_rejects_ambiguous_or_unsafe_inputs(overrides, message):
    arguments = {"output_directory": "F:/exports/liquigen-chain"}
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        compile_liquid_chain_burst(**arguments)
