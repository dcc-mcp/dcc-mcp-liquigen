import json
from pathlib import Path

from conftest import write_png_header

from dcc_mcp_liquigen.export_bundle import validate_unreal_export_bundle


def test_validate_8x8_image_flipbook(tmp_path: Path):
    atlas = write_png_header(tmp_path / "splash.png", 2048, 2048)
    result = validate_unreal_export_bundle(str(atlas), columns=8, rows=8, roots=[tmp_path])
    assert result["valid"] is True
    assert result["bundle_type"] == "image_flipbook"
    assert result["grid"] == {"columns": 8, "rows": 8}


def test_flipbook_rejects_non_divisible_grid(tmp_path: Path):
    atlas = write_png_header(tmp_path / "splash.png", 2001, 2048)
    result = validate_unreal_export_bundle(str(atlas), columns=8, rows=8, roots=[tmp_path])
    assert result["valid"] is False
    assert "not divisible" in result["errors"][0]


def test_validate_vat_bundle(tmp_path: Path):
    (tmp_path / "splash.fbx").write_bytes(b"Kaydara FBX Binary")
    write_png_header(tmp_path / "splash_position.png", 64, 64)
    (tmp_path / "splash.json").write_text('{"frames": 32}', encoding="utf-8")
    result = validate_unreal_export_bundle(str(tmp_path), roots=[tmp_path])
    assert result["valid"] is True
    assert result["bundle_type"] == "liquigen_vat"


def test_validate_canonical_liquigen_vat_bundle_maps_export_roles(tmp_path: Path):
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
                    "Name": "VAT",
                    "Two Position Textures": 0,
                }
            ]
        ),
        encoding="utf-8",
    )

    result = validate_unreal_export_bundle(str(tmp_path), roots=[tmp_path])

    assert result["valid"] is True
    assert result["vat"] == {
        "axis_system": "Right-Handed Z-Up",
        "bounds_min": [-5.2, -1.8, 0.0],
        "bounds_max": [5.2, 1.8, 4.0],
        "frame_count": 64,
        "source_fps": 30.0,
        "two_position_textures": False,
        "assets": {
            "geometry": "chain.fbx",
            "info": "chain_info.json",
            "lookup": "chain_lookup.exr",
            "position": "chain_pos.exr",
            "rotation": "chain_rot.exr",
        },
    }


def test_canonical_vat_bundle_fails_closed_when_rotation_texture_is_missing(tmp_path: Path):
    (tmp_path / "chain.fbx").write_bytes(b"Kaydara FBX Binary")
    for suffix in ("lookup", "pos"):
        (tmp_path / f"chain_{suffix}.exr").write_bytes(b"v/1\x01synthetic-exr")
    (tmp_path / "chain_info.json").write_text(
        json.dumps(
            [
                {
                    "Axis System": "Right-Handed Z-Up",
                    "Bound Max X": 1,
                    "Bound Max Y": 1,
                    "Bound Max Z": 1,
                    "Bound Min X": -1,
                    "Bound Min Y": -1,
                    "Bound Min Z": 0,
                    "Frame Count": 32,
                    "Houdini FPS": 30,
                    "Name": "VAT",
                    "Two Position Textures": False,
                }
            ]
        ),
        encoding="utf-8",
    )

    result = validate_unreal_export_bundle(str(tmp_path), roots=[tmp_path])

    assert result["valid"] is False
    assert "chain_rot.exr" in result["errors"][0]


def test_validate_openvdb_sequence_for_unreal_sparse_volume_texture(tmp_path: Path):
    for frame in range(3):
        (tmp_path / f"chain_density_{frame:04d}.vdb").write_bytes(
            (0x56444220).to_bytes(4, "little") + b"synthetic-vdb-metadata"
        )

    result = validate_unreal_export_bundle(str(tmp_path), roots=[tmp_path])

    assert result["valid"] is True
    assert result["bundle_type"] == "openvdb_sequence"
    assert result["ue_import_target"] == "animated_sparse_volume_texture"
    assert result["material_template"] == "sparse_volume_material"
    assert result["semantic_role"] == "velocity_field_auxiliary"
    assert result["recommended_surface_renderer"] is False
    assert "velocity" in result["warnings"][0]


def test_openvdb_sequence_rejects_invalid_magic(tmp_path: Path):
    (tmp_path / "chain_density_0000.vdb").write_bytes(b"not-openvdb")

    result = validate_unreal_export_bundle(str(tmp_path), roots=[tmp_path])

    assert result["valid"] is False
    assert "invalid OpenVDB magic header" in result["errors"][0]
