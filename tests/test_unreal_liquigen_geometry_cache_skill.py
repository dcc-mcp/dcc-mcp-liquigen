from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from dcc_mcp_core import validate_skill

SKILL = Path(__file__).resolve().parents[1] / "skills" / "unreal-liquigen-geometry-cache"


@pytest.fixture
def importer():
    spec = importlib.util.spec_from_file_location(
        "geometry_cache_import_test", SKILL / "scripts" / "import_cache.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main.__wrapped__


@pytest.fixture
def request_args(tmp_path):
    archive = tmp_path / "fluid.abc"
    archive.write_bytes(b"Ogawa fixture")
    return dict(
        source=str(archive),
        destination="/Game/LiquiGen/Test",
        asset_name="Fluid",
        scale=[100, 100, 100],
        rotation=[0, 0, 0],
    )


def test_geometry_cache_skill_contract_is_valid():
    report = validate_skill(str(SKILL))
    assert not report.has_errors, [issue.message for issue in report.issues]


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": "relative.abc"},
        {"destination": "/Engine/Test"},
        {"destination": "/Game/../Test"},
        {"destination": "/Game//Test"},
        {"destination": "/Game/Test/"},
        {"asset_name": "../Fluid"},
        {"scale": [1, 0, 1]},
        {"scale": [1, float("nan"), 1]},
        {"rotation": [0, float("inf"), 0]},
        {"rotation": [False, 0, 0]},
        {"rotation": [0, 0]},
        {"import_velocities": "false"},
    ],
)
def test_invalid_input_is_rejected_before_any_editor_access(
    importer, request_args, overrides, monkeypatch
):
    # No editor APIs are exposed: validation must finish before accessing them.
    monkeypatch.setitem(sys.modules, "unreal", SimpleNamespace())
    with pytest.raises(ValueError):
        importer(**{**request_args, **overrides})


def test_wrong_archive_is_rejected_before_any_editor_access(importer, request_args, monkeypatch):
    Path(request_args["source"]).write_bytes(b"not an Alembic archive")
    monkeypatch.setitem(sys.modules, "unreal", SimpleNamespace())
    with pytest.raises(ValueError, match="Ogawa"):
        importer(**request_args)


def test_existing_destination_is_rejected_before_import(importer, request_args, monkeypatch):
    checked = []

    def exists(path):
        checked.append(path)
        return True

    monkeypatch.setitem(
        sys.modules,
        "unreal",
        SimpleNamespace(EditorAssetLibrary=SimpleNamespace(does_directory_exist=exists)),
    )
    with pytest.raises(ValueError, match="new asset folder"):
        importer(**request_args)
    assert checked == [request_args["destination"]]


@pytest.fixture
def unreal_import(monkeypatch):
    unreal = Mock()
    unreal.GeometryCache = type("GeometryCache", (), {})
    asset = unreal.GeometryCache()
    asset.get_path_name = lambda: "/Game/LiquiGen/Test/Fluid.Fluid"
    unreal.EditorAssetLibrary.does_directory_exist.return_value = False
    unreal.EditorAssetLibrary.load_asset.return_value = asset
    unreal.AssetImportTask.return_value.imported_object_paths = [asset.get_path_name()]
    component = unreal.new_object.return_value
    component.get_duration.return_value = 6.0
    component.get_number_of_frames.return_value = 180
    component.get_number_of_tracks.return_value = 1
    monkeypatch.setitem(sys.modules, "unreal", unreal)
    return unreal


@pytest.mark.parametrize("path_count", [1, 2, 3])
def test_import_accepts_one_distinct_cache(importer, request_args, unreal_import, path_count):
    task = unreal_import.AssetImportTask.return_value
    task.imported_object_paths *= path_count

    result = importer(**request_args)

    unreal_import.AssetToolsHelpers.get_asset_tools().import_asset_tasks.assert_called_once_with(
        [task]
    )
    unreal_import.EditorAssetLibrary.load_asset.assert_called_once_with(
        task.imported_object_paths[0]
    )
    unreal_import.new_object.return_value.set_geometry_cache.assert_called_once_with(
        unreal_import.EditorAssetLibrary.load_asset.return_value
    )
    assert result["success"] is True
    assert result["context"]["frame_count"] == 180
    assert result["context"]["duration_seconds"] == 6.0
    assert result["context"]["visual_acceptance"] is False
    assert task.replace_existing is False


@pytest.mark.parametrize(
    "paths",
    [[], ["/Game/Test/A.A", "/Game/Test/B.B"], ["/Game/Test/A.A"] * 2 + ["/Game/Test/B.B"]],
)
def test_import_rejects_zero_or_multiple_distinct_assets(
    importer, request_args, unreal_import, paths
):
    unreal_import.AssetImportTask.return_value.imported_object_paths = paths
    with pytest.raises(RuntimeError, match="expected one Geometry Cache asset"):
        importer(**request_args)
    unreal_import.EditorAssetLibrary.load_asset.assert_not_called()
    unreal_import.new_object.assert_not_called()


def test_duplicate_paths_do_not_skip_asset_type_check(importer, request_args, unreal_import):
    unreal_import.AssetImportTask.return_value.imported_object_paths *= 2
    unreal_import.EditorAssetLibrary.load_asset.return_value = object()
    with pytest.raises(RuntimeError, match="did not produce a Geometry Cache"):
        importer(**request_args)


@pytest.mark.parametrize("frames,duration", [(1, 6.0), (180, 0.0)])
def test_duplicate_paths_do_not_skip_animation_check(
    importer, request_args, unreal_import, frames, duration
):
    unreal_import.AssetImportTask.return_value.imported_object_paths *= 2
    component = unreal_import.new_object.return_value
    component.get_number_of_frames.return_value = frames
    component.get_duration.return_value = duration
    with pytest.raises(RuntimeError, match="no animated sample range"):
        importer(**request_args)
