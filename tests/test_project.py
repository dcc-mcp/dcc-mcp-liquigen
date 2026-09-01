from pathlib import Path

import pytest

import dcc_mcp_liquigen.project as project_module
from dcc_mcp_liquigen.project import (
    LiquiGenProjectError,
    inspect_project,
    stage_project_copy,
    validate_project,
)


def test_inspect_and_validate_unreal_flipbook(synthetic_project: Path):
    roots = [synthetic_project.parent]
    inspected = inspect_project(str(synthetic_project), roots=roots)
    assert inspected["app_id"] == "liquigen"
    assert inspected["project_version"] == 7
    assert inspected["node_types"]["Node_Export_Image"] == 1
    validated = validate_project(str(synthetic_project), require_unreal_export=True, roots=roots)
    assert validated["valid"] is True
    assert validated["errors"] == []


def test_image_flipbook_does_not_require_meshing(synthetic_project: Path):
    assert (
        "Node_Meshing"
        not in inspect_project(str(synthetic_project), roots=[synthetic_project.parent])[
            "node_types"
        ]
    )
    result = validate_project(
        str(synthetic_project), require_unreal_export=True, roots=[synthetic_project.parent]
    )
    assert result["valid"] is True


def test_mesh_export_uses_simulation_mesh_without_obsolete_meshing_node(monkeypatch):
    monkeypatch.setattr(
        project_module,
        "inspect_project",
        lambda *_args, **_kwargs: {
            "app_id": "liquigen",
            "app_version": "1.0.5",
            "node_types": {
                "Node_Simulation": 1,
                "Node_Scene": 1,
                "Node_Export_Mesh": 1,
            },
            "export_tokens": ["Vertex Animated Texture"],
        },
    )

    result = validate_project("ignored.liquigen", require_unreal_export=True)

    assert result["valid"] is True
    assert result["errors"] == []


def test_project_must_stay_inside_allowed_roots(synthetic_project: Path, tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(LiquiGenProjectError, match="outside"):
        inspect_project(str(synthetic_project), roots=[allowed])


def test_stage_copy_is_hash_identical_and_never_overwrites(synthetic_project: Path):
    destination = synthetic_project.parent / "work" / "splash-copy.liquigen"
    destination.parent.mkdir()
    result = stage_project_copy(
        str(synthetic_project), str(destination), roots=[synthetic_project.parent]
    )
    assert result["overwritten"] is False
    assert destination.read_bytes() == synthetic_project.read_bytes()
    with pytest.raises(LiquiGenProjectError, match="already exists"):
        stage_project_copy(
            str(synthetic_project), str(destination), roots=[synthetic_project.parent]
        )


def test_stage_copy_can_read_an_explicit_official_source_root(
    synthetic_project: Path, tmp_path: Path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    destination = workspace / "staged.liquigen"

    result = stage_project_copy(
        str(synthetic_project),
        str(destination),
        roots=[workspace],
        source_roots=[synthetic_project.parent],
    )

    assert result["source"] == str(synthetic_project.resolve())
    assert result["destination"] == str(destination.resolve())
    assert destination.read_bytes() == synthetic_project.read_bytes()


def test_stage_copy_keeps_destination_bound_when_source_root_is_wider(
    synthetic_project: Path, tmp_path: Path
):
    outside_destination = tmp_path / "outside.liquigen"

    with pytest.raises(LiquiGenProjectError, match="destination is outside"):
        stage_project_copy(
            str(synthetic_project),
            str(outside_destination),
            roots=[tmp_path / "allowed"],
            source_roots=[synthetic_project.parent],
        )
