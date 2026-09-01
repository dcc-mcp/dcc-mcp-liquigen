from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from dcc_mcp_core import validate_skill

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "unreal-liquigen-showcase"


def _common_module():
    path = SKILL / "scripts" / "_showcase_common.py"
    spec = importlib.util.spec_from_file_location("_showcase_common_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _vat_module():
    scripts = SKILL / "scripts"
    path = scripts / "_vat_receiver.py"
    spec = importlib.util.spec_from_file_location("_vat_receiver_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(scripts))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_showcase_skill_contract_is_valid() -> None:
    report = validate_skill(str(SKILL))
    assert not report.has_errors, [issue.message for issue in report.issues]


def test_chain_offsets_are_centered_and_alternate_depth() -> None:
    common = _common_module()
    assert common.chain_offsets(5, 260.0) == [
        (-520.0, -46.8, 0.0),
        (-260.0, 46.8, 0.0),
        (0.0, -46.8, 0.0),
        (260.0, 46.8, 0.0),
        (520.0, -46.8, 0.0),
    ]


def test_showcase_paths_fail_closed() -> None:
    common = _common_module()
    assert common.game_asset_path("/Game/LiquiGen/Showcase/") == "/Game/LiquiGen/Showcase"
    for bad_path in ("Game/LiquiGen", "/Engine/Test", "/Game/../Secrets"):
        try:
            common.game_asset_path(bad_path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe asset path accepted: {bad_path}")


def test_particle_material_declares_niagara_sprite_usage() -> None:
    receiver = (SKILL / "scripts" / "_receiver.py").read_text(encoding="utf-8")
    assert '"used_with_niagara_sprites", True' in receiver


def test_vat_receiver_parses_the_canonical_liquigen_fluid_bundle(tmp_path: Path) -> None:
    vat = _vat_module()
    (tmp_path / "chain.fbx").write_bytes(b"Kaydara FBX Binary")
    for suffix in ("lookup", "pos", "rot"):
        (tmp_path / f"chain_{suffix}.exr").write_bytes(b"v/1\x01synthetic-exr")
    (tmp_path / "chain_info.json").write_text(
        json.dumps(
            [
                {
                    "Axis System": "Right-Handed Z-Up",
                    "Bound Max X": 5.2,
                    "Bound Max Y": 1.8,
                    "Bound Max Z": 4.0,
                    "Bound Min X": -5.2,
                    "Bound Min Y": -1.8,
                    "Bound Min Z": 0.0,
                    "Frame Count": 64,
                    "Houdini FPS": 30.0,
                    "Two Position Textures": False,
                }
            ]
        ),
        encoding="utf-8",
    )

    bundle = vat.canonical_vat_bundle(tmp_path)

    assert bundle["stem"] == "chain"
    assert bundle["frame_count"] == 64
    assert bundle["source_fps"] == 30.0
    assert bundle["assets"] == {
        "geometry": tmp_path / "chain.fbx",
        "lookup": tmp_path / "chain_lookup.exr",
        "position": tmp_path / "chain_pos.exr",
        "rotation": tmp_path / "chain_rot.exr",
        "info": tmp_path / "chain_info.json",
    }


@pytest.mark.parametrize("encoded", [False, 0])
def test_vat_receiver_normalizes_false_two_position_texture_flags(encoded: object) -> None:
    vat = _vat_module()
    assert vat._boolean_flag({"Two Position Textures": encoded}, "Two Position Textures") is False


@pytest.mark.parametrize("encoded", [True, 1])
def test_vat_receiver_normalizes_true_two_position_texture_flags(encoded: object) -> None:
    vat = _vat_module()
    assert vat._boolean_flag({"Two Position Textures": encoded}, "Two Position Textures") is True


@pytest.mark.parametrize("encoded", [2, -1, 0.0, "0", None, [], {}])
def test_vat_receiver_rejects_invalid_two_position_texture_flags(encoded: object) -> None:
    vat = _vat_module()
    with pytest.raises(ValueError, match="Two Position Textures"):
        vat._boolean_flag({"Two Position Textures": encoded}, "Two Position Textures")


def test_vat_receiver_reports_a_stable_missing_directory_error(tmp_path: Path) -> None:
    vat = _vat_module()
    with pytest.raises(ValueError, match="source_directory does not exist"):
        vat.canonical_vat_bundle(tmp_path / "missing")


def test_vat_receiver_declares_sidefx_fluid_shader_and_lossless_texture_contract() -> None:
    vat = _vat_module()
    source = (SKILL / "scripts" / "_vat_receiver.py").read_text(encoding="utf-8")
    assert vat.SIDEFX_FLUID_FUNCTION == (
        "/SideFX_Labs/Materials/MaterialFunctions/"
        "Houdini_VAT_DynamicRemeshing.Houdini_VAT_DynamicRemeshing"
    )
    assert "TF_NEAREST" in source
    assert "TEXTUREGROUP_16_BIT_DATA" in source
    assert "TC_HDR" in source
    assert "TMGS_NO_MIPMAPS" in source
    assert '"srgb", False' in source
    assert '"use_full_precision_u_vs", False' in source
    assert '"use_backwards_compatible_f16_trunc_u_vs", True' in source
    assert '"generate_lightmap_u_vs", False' in source
    assert '"combine_meshes", True' in source
    assert '"remove_degenerates", False' in source
    assert '"generate_lightmap_u_vs", False' in source
    assert "StaticMeshEditorSubsystem" in source
    assert "get_lod_build_settings" in source
    assert "set_lod_build_settings" in source
    assert "set_material_instance_parent" in source
    assert "update_material_instance" in source
    assert vat.SIDEFX_FLUID_CUSTOM_UVS == ((19, 1), (20, 2), (21, 3))
    assert "connect_material_expression_to_customized_uv" in source
    assert "get_material_customized_uv_connection" in source
    assert "configure_material_instance_parameters" in source
    assert "get_material_instance_texture_parameter_value" in source
    assert "get_material_instance_scalar_parameter_value" in source
    assert '"Game Time at First Frame"' in source
    assert '"Auto Playback": True' in source
    assert '"Support Legacy Parameters and Instancing": False' in source
    assert '"Positions Require Two Textures": bundle["two_position_textures"]' in source
    assert "set_material_instance_static_switch_parameter_value" in source
    assert "get_material_instance_static_switch_parameter_value" in source
    assert "MP_CUSTOMIZED_UV" not in source
    assert "BLEND_TRANSLUCENT" in source
    assert "TLM_SURFACE_PER_PIXEL_LIGHTING" in source
    assert "MaterialExpressionVectorParameter" in source
    assert '"Water Tint"' in source
    assert '"Water Roughness"' in source
    assert '"Water Opacity"' in source
    assert '"Water IOR"' in source
    assert "MP_REFRACTION" in source


def test_vat_receiver_native_result_fails_closed() -> None:
    vat = _vat_module()

    with pytest.raises(RuntimeError, match="invalid JSON"):
        vat._native_payload("not-json", "connection")
    with pytest.raises(RuntimeError, match="failed"):
        vat._native_payload('{"success":false,"error_code":"occupied"}', "connection")
    assert vat._native_payload('{"success":true,"saved":true,"verified":true}', "connection") == {
        "success": True,
        "saved": True,
        "verified": True,
    }


def test_vat_receiver_uses_the_four_argument_native_parameter_contract() -> None:
    vat = _vat_module()
    calls = []

    class MaterialEditingLibrary:
        @staticmethod
        def get_scalar_parameter_names(_instance):
            return [
                "Houdini FPS",
                "Bound Min X",
                "Bound Min Y",
                "Bound Min Z",
                "Bound Max X",
                "Bound Max Y",
                "Bound Max Z",
                "Playback Speed",
                "Game Time at First Frame",
            ]

        @staticmethod
        def get_texture_parameter_names(_instance):
            return ["Lookup Table", "Position Texture", "Rotation Texture"]

        @staticmethod
        def get_static_switch_parameter_names(_instance):
            return [
                "Auto Playback",
                "Support Legacy Parameters and Instancing",
                "Positions Require Two Textures",
            ]

        @staticmethod
        def set_material_instance_static_switch_parameter_value(_instance, _parameter, _value):
            return True

        @staticmethod
        def get_material_instance_static_switch_parameter_value(_instance, parameter):
            return parameter != "Positions Require Two Textures"

        @staticmethod
        def update_material_instance(_instance):
            return None

        @staticmethod
        def get_material_instance_texture_parameter_value(_instance, _parameter):
            return object()

        @staticmethod
        def get_material_instance_scalar_parameter_value(_instance, _parameter):
            return 0.0

    class NativeBridge:
        @staticmethod
        def configure_material_instance_parameters(*args):
            calls.append(args)
            return json.dumps(
                {
                    "success": True,
                    "saved": True,
                    "verified": True,
                    "scalar_parameter_count": 9,
                    "texture_parameter_count": 3,
                    "package_dirty": False,
                }
            )

    class Unreal:
        pass

    class EditorAssetLibrary:
        @staticmethod
        def save_loaded_asset(_instance, only_if_is_dirty=False):
            return not only_if_is_dirty

    Unreal.DccMcpAutomationLibrary = NativeBridge
    Unreal.MaterialEditingLibrary = MaterialEditingLibrary
    Unreal.EditorAssetLibrary = EditorAssetLibrary

    with pytest.raises(RuntimeError, match="texture parameter failed readback"):
        vat._bind_material_instance(
            Unreal,
            object(),
            {"lookup": object(), "position": object(), "rotation": object()},
            {
                "source_fps": 60.0,
                "frame_count": 64,
                "two_position_textures": False,
                "bounds_min": [-1.0, -2.0, -3.0],
                "bounds_max": [1.0, 2.0, 3.0],
            },
        )

    assert len(calls) == 1
    assert len(calls[0]) == 4
    assert calls[0][2] == {}
    assert set(calls[0][3]) == {"Lookup Table", "Position Texture", "Rotation Texture"}


def test_vat_import_rejects_missing_native_bridge_before_asset_mutation() -> None:
    vat = _vat_module()

    class EditorAssetLibrary:
        @staticmethod
        def load_asset(_path):
            return object()

        @staticmethod
        def make_directory(_path):
            raise AssertionError("asset mutation occurred before native bridge preflight")

    class Unreal:
        pass

    Unreal.EditorAssetLibrary = EditorAssetLibrary

    with pytest.raises(RuntimeError, match="Customized UV native bridge"):
        vat.import_vat_assets(Unreal, {"assets": {}}, "/Game/Test", "Test")


def test_vat_import_rejects_missing_native_parameter_bridge_before_asset_mutation() -> None:
    vat = _vat_module()

    class EditorAssetLibrary:
        @staticmethod
        def load_asset(_path):
            return object()

        @staticmethod
        def make_directory(_path):
            raise AssertionError("asset mutation occurred before native bridge preflight")

    class NativeBridge:
        connect_material_expression_to_customized_uv = staticmethod(lambda *_args: "")
        get_material_customized_uv_connection = staticmethod(lambda *_args: "")

    class Unreal:
        pass

    Unreal.EditorAssetLibrary = EditorAssetLibrary
    Unreal.DccMcpAutomationLibrary = NativeBridge

    with pytest.raises(RuntimeError, match="Material Instance parameter bridge"):
        vat.import_vat_assets(Unreal, {"assets": {}}, "/Game/Test", "Test")


def test_vat_api_probe_is_a_read_only_skill_tool() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    probe = (SKILL / "scripts" / "probe_vat_receiver.py").read_text(encoding="utf-8")
    assert "name: probe_vat_receiver" in tools
    assert "read_only_hint: true" in tools
    assert "MaterialExpressionMaterialFunctionCall" in probe
    assert "TEXTUREGROUP_16_BIT_DATA" in probe
    assert "connect_material_expression_to_customized_uv" in probe
    assert "get_material_customized_uv_connection" in probe
    assert "configure_material_instance_parameters" in probe
    assert "MP_CUSTOMIZED_UV" not in probe


def test_vat_pipeline_declares_an_explicit_tick_boundary_and_finalizer() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    docs = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    finalizer = (SKILL / "scripts" / "finalize_vat_bundle.py").read_text(encoding="utf-8")

    assert "name: finalize_vat_bundle" in tools
    assert "on-success: [unreal_liquigen_showcase__finalize_vat_bundle]" in tools
    assert "editor tick" in docs
    assert "finalize_vat_assets" in finalizer
    assert '"pipeline_stage": "staged"' in (SKILL / "scripts" / "_vat_receiver.py").read_text(
        encoding="utf-8"
    )
    assert '"pipeline_stage": "finalized"' in (SKILL / "scripts" / "_vat_receiver.py").read_text(
        encoding="utf-8"
    )


def test_showcase_camera_auto_activates_for_standalone_game_capture() -> None:
    source = (SKILL / "scripts" / "stage_chain_burst.py").read_text(encoding="utf-8")
    assert (
        'camera.set_editor_property("auto_activate_for_player", unreal.AutoReceiveInput.PLAYER0)'
        in source
    )
    assert '"auto_activate_player_index": camera.get_auto_activate_player_index()' in source


def test_procedural_chain_burst_is_a_typed_honest_liquigen_receiver() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    script = (SKILL / "scripts" / "author_procedural_chain_burst.py").read_text(encoding="utf-8")
    receiver = (SKILL / "scripts" / "_receiver.py").read_text(encoding="utf-8")

    assert "name: author_procedural_chain_burst" in tools
    assert "required: [source_project, source_directory, destination, asset_prefix]" in tools
    assert 'source_kind = "liquigen_export"' in script
    assert '"LiquiGen.Appearance", "unreal_procedural"' in script
    assert "create_procedural_material" in receiver
    assert "MaterialExpressionTextureCoordinate" in receiver
    assert "MaterialExpressionDotProduct" in receiver
    assert "MaterialExpressionAdd" in receiver
    assert "MaterialExpressionMax" in receiver
    assert "SphereRenderMask" not in receiver
    assert "SpawnBurst_Instantaneous" in receiver
    assert "create_script_input_int(int(particle_count * count_scale))" in receiver
    assert "ShapeLocation.ShapeLocation" in receiver
    assert "SolveForcesAndVelocity" in receiver
    assert '"Loop Behavior"' in receiver
    assert '"Infinite"' in receiver


def test_showcase_stage_uses_movable_lights_to_avoid_unbuilt_lighting_overlay() -> None:
    source = (SKILL / "scripts" / "stage_chain_burst.py").read_text(encoding="utf-8")
    assert source.count('"mobility", unreal.ComponentMobility.MOVABLE') >= 3


def test_showcase_stage_exposes_and_verifies_effect_scale() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    source = (SKILL / "scripts" / "stage_chain_burst.py").read_text(encoding="utf-8")

    assert "effect_scale:" in tools
    assert "minimum: 0.1" in tools
    assert "maximum: 10.0" in tools
    assert "effect_scale: float = 1.0" in source
    assert "effect.set_actor_scale3d" in source
    assert "effect_scale=[" in source


def test_water_vat_stage_is_bounds_driven_and_uses_the_finalized_material() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    source = (SKILL / "scripts" / "stage_water_vat.py").read_text(encoding="utf-8")

    assert "name: stage_water_vat" in tools
    assert (
        "required: [source_directory, static_mesh_path, material_instance_path, source_kind]"
        in tools
    )
    assert "canonical_vat_bundle" in source
    assert "bounds_min" in source and "bounds_max" in source
    assert "set_static_mesh" in source
    assert "set_material(0, material)" in source
    assert 'camera.set_editor_property("auto_activate_for_player"' in source


def test_water_vat_preview_exposes_fixed_frame_and_auto_playback_controls() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    source = (SKILL / "scripts" / "configure_water_vat_preview.py").read_text(encoding="utf-8")

    assert "name: configure_water_vat_preview" in tools
    assert "auto_playback:" in tools
    assert "support_legacy_parameters:" in tools
    assert "display_frame:" in tools
    assert '"Auto Playback"' in source
    assert '"Support Legacy Parameters and Instancing"' in source
    assert '"Display Frame"' in source
    assert '"Water Opacity"' in source
    assert "set_material_instance_static_switch_parameter_value" in source
    assert "set_material_instance_scalar_parameter_value" in source
    assert "save_loaded_asset" in source


def test_effect_scale_validation_is_independent_from_chain_spacing() -> None:
    common = _common_module()

    assert common.effect_scale(2.6) == 2.6
    for value in (0.0, 0.09, 10.01, 100.0):
        with pytest.raises(ValueError, match="effect_scale"):
            common.effect_scale(value)


def test_procedural_water_cascade_is_a_first_class_liquigen_receiver() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    author = SKILL / "scripts" / "author_procedural_water_cascade.py"
    stage = SKILL / "scripts" / "stage_water_cascade.py"

    assert "name: author_procedural_water_cascade" in tools
    assert "name: stage_water_cascade" in tools
    assert author.is_file()
    assert stage.is_file()
    author_source = author.read_text(encoding="utf-8")
    stage_source = stage.read_text(encoding="utf-8")
    assert "create_procedural_water_system" in author_source
    assert 'source_kind = "liquigen_export"' in author_source
    assert '"LiquiGen.Appearance", "unreal_procedural_water"' in author_source
    assert '"LiquiGen_WaterCascade_Showcase"' in stage_source
    assert "NiagaraComponent" in stage_source


def test_water_cascade_layout_descends_and_exposes_three_layers() -> None:
    common = _common_module()
    offsets = common.water_cascade_offsets(5, 260.0, 180.0)
    layers = common.procedural_water_layer_specs(520.0)

    assert len(offsets) == 5
    assert all(offsets[index][2] > offsets[index + 1][2] for index in range(4))
    assert [layer[0] for layer in layers] == ["Sheet", "Foam", "Droplets"]


def test_replay_supports_pie_world_and_capture_pawn_suppression() -> None:
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    source = (SKILL / "scripts" / "replay_chain_burst.py").read_text(encoding="utf-8")

    assert "hide_default_pawn:" in tools
    assert "get_game_world" in source
    assert "GameplayStatics.get_all_actors_of_class" in source
    assert "set_actor_hidden_in_game(True)" in source


def test_procedural_blast_diameter_is_independent_and_drives_every_layer() -> None:
    common = _common_module()
    tools = (SKILL / "tools.yaml").read_text(encoding="utf-8")
    script = (SKILL / "scripts" / "author_procedural_chain_burst.py").read_text(encoding="utf-8")
    receiver = (SKILL / "scripts" / "_receiver.py").read_text(encoding="utf-8")

    assert "blast_diameter_cm:" in tools
    assert "blast_diameter_cm: float = 600.0" in script
    assert '"LiquiGen.BlastDiameterCm"' in script
    assert "procedural_layer_specs(blast_diameter_cm)" in receiver
    assert "(430.0, 430.0)" not in receiver

    layers = common.procedural_layer_specs(900.0)
    assert [layer[0] for layer in layers] == ["Core", "Plume", "Sparks"]
    assert layers[0][3] == (558.0, 558.0)
    assert layers[1][4] == (432.0, 432.0, 342.0)
    assert layers[2][3] == (54.0, 288.0)
    with pytest.raises(ValueError, match="blast_diameter_cm"):
        common.procedural_layer_specs(99.0)


def test_showcase_state_reads_back_procedural_size_and_appearance() -> None:
    source = (SKILL / "scripts" / "get_showcase_state.py").read_text(encoding="utf-8")

    assert '"LiquiGen.Appearance"' in source
    assert '"LiquiGen.BlastDiameterCm"' in source
    assert "blast_diameter_cm=" in source
