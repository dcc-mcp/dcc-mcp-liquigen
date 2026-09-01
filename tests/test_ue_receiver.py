import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load(name: str):
    path = Path(__file__).parents[1] / "examples" / "ue58_receiver" / name
    spec = spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_atlas_is_valid_8x8_png(tmp_path: Path):
    generator = _load("generate_smoke_atlas.py")
    receiver = _load("import_flipbook.py")
    atlas = generator.write_smoke_atlas(tmp_path / "smoke.png")
    assert receiver.png_dimensions(atlas) == (128, 128)
    assert atlas.read_bytes().endswith(b"IEND\xaeB`\x82")


def test_receiver_authors_niagara_subuv_contract():
    source = (
        Path(__file__).parents[1] / "examples" / "ue58_receiver" / "import_flipbook.py"
    ).read_text(encoding="utf-8")
    assert "NiagaraSpriteRendererProperties" in source
    assert '"sub_image_size"' in source
    assert "/Niagara/Modules/Update/SubUV/V2/SubUVAnimation.SubUVAnimation" in source
    assert '"niagara_configuration_required": False' in source


def test_receiver_parses_a_bounded_chain_burst_configuration():
    receiver = _load("import_flipbook.py")

    config = receiver.chain_configuration(
        {
            "LIQUIGEN_CHAIN_COUNT": "6",
            "LIQUIGEN_CHAIN_DELAY_SECONDS": "0.2",
            "LIQUIGEN_CHAIN_SPACING_CM": "240",
        }
    )

    assert config == {"count": 6, "delay_seconds": 0.2, "spacing_cm": 240.0}


def test_receiver_authors_sequenced_positioned_niagara_emitters():
    source = (
        Path(__file__).parents[1] / "examples" / "ue58_receiver" / "import_flipbook.py"
    ).read_text(encoding="utf-8")

    assert 'spawn.set_parameter("Spawn Time"' in source
    assert 'spawn.set_parameter("Spawn Count"' in source
    assert "AddVectorToPosition" in source
    assert '"chain": chain' in source


def test_cold_start_verifier_checks_dependency_chain():
    source = (
        Path(__file__).parents[1] / "examples" / "ue58_receiver" / "verify_flipbook.py"
    ).read_text(encoding="utf-8")
    assert "MaterialExpressionParticleSubUV" in source
    assert "find_package_referencers_for_asset(texture_path, True)" in source
    assert "find_package_referencers_for_asset(material_path, True)" in source
    assert "validator.is_object_valid" in source


def test_receiver_project_enables_niagara_authoring_plugins():
    project_path = (
        Path(__file__).parents[1] / "examples" / "ue58_receiver" / "LiquiGenUE58.uproject"
    )
    project = json.loads(project_path.read_text(encoding="utf-8"))
    enabled = {plugin["Name"] for plugin in project["Plugins"] if plugin["Enabled"]}
    assert {"Niagara", "CascadeToNiagaraConverter"} <= enabled
