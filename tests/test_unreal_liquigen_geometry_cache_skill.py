from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

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
