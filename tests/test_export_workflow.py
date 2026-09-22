import os
from pathlib import Path

import pytest

from dcc_mcp_liquigen.export_workflow import (
    LiquiGenExportWorkflowError,
    run_export_workflow,
)
from dcc_mcp_liquigen.runtime import RuntimeBinding


def _binding() -> RuntimeBinding:
    return RuntimeBinding(
        pid=86184,
        window_handle=25306976,
        executable="G:/apps/LiquiGen.exe",
        version="1.0.5",
        title="LiquiGen",
    )


def _png(path: Path) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00"
    )


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, duration: float) -> None:
        self.value += duration


def test_run_export_workflow_uses_semantic_commands_and_requires_fresh_bundle(
    monkeypatch, tmp_path: Path
):
    project = tmp_path / "chain-burst.liquigen"
    project.write_bytes(b"project")
    output = tmp_path / "export"
    output.mkdir()
    calls = []

    monkeypatch.setattr(
        "dcc_mcp_liquigen.export_workflow._configured_export_targets",
        lambda _project, _roots: {os.path.normcase(str(output.resolve())): None},
    )

    def command_runner(command, **arguments):
        calls.append((command, arguments))
        if command == "export_all":
            _png(output / "chain.png")
        return {"success": True, "command": command, "status": "consumed"}

    clock = _Clock()
    result = run_export_workflow(
        str(project),
        str(output),
        simulate_seconds=2.0,
        timeout_seconds=10.0,
        stable_seconds=1.0,
        poll_interval_seconds=0.25,
        binding=_binding(),
        roots=[tmp_path],
        command_runner=command_runner,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )

    assert result["success"] is True
    assert result["requires_cua"] is False
    assert result["fresh_files"] == ["chain.png"]
    assert result["bundle"]["bundle_type"] == "image_flipbook"
    assert [item[0] for item in calls] == [
        "open_project_path",
        "reset_graph_zoom",
        "reset_simulation",
        "reset_timeline",
        "play_timeline",
        "pause_timeline",
        "switch_tab_to_export",
        "export_all",
    ]
    assert calls[0][1]["project_path"] == str(project.resolve())


def test_run_export_workflow_rejects_nonempty_output_directory(monkeypatch, tmp_path: Path):
    project = tmp_path / "chain-burst.liquigen"
    project.write_bytes(b"project")
    output = tmp_path / "export"
    output.mkdir()
    _png(output / "old.png")
    monkeypatch.setattr(
        "dcc_mcp_liquigen.export_workflow._configured_export_targets",
        lambda _project, _roots: {os.path.normcase(str(output.resolve())): None},
    )
    with pytest.raises(LiquiGenExportWorkflowError, match="must be empty"):
        run_export_workflow(
            str(project),
            str(output),
            simulate_seconds=0,
            timeout_seconds=1.0,
            stable_seconds=0.5,
            poll_interval_seconds=0.25,
            binding=_binding(),
            roots=[tmp_path],
        )


def test_run_export_workflow_rejects_unconfigured_directory(monkeypatch, tmp_path: Path):
    project = tmp_path / "chain-burst.liquigen"
    project.write_bytes(b"project")
    output = tmp_path / "export"
    output.mkdir()
    monkeypatch.setattr(
        "dcc_mcp_liquigen.export_workflow._configured_export_targets",
        lambda _project, _roots: {str(tmp_path / "somewhere-else"): None},
    )

    with pytest.raises(LiquiGenExportWorkflowError, match="not configured"):
        run_export_workflow(
            str(project),
            str(output),
            binding=_binding(),
            roots=[tmp_path],
        )


@pytest.mark.parametrize("required_type", ["liquigen_vat", "alembic_geometry_cache"])
def test_run_export_workflow_does_not_accept_flipbook_when_vat_is_enabled(
    monkeypatch, tmp_path: Path, required_type: str
):
    project = tmp_path / "water.liquigen"
    project.write_bytes(b"project")
    output = tmp_path / "export"
    output.mkdir()
    monkeypatch.setattr(
        "dcc_mcp_liquigen.export_workflow._configured_export_targets",
        lambda _project, _roots: {os.path.normcase(str(output.resolve())): required_type},
    )

    def command_runner(command, **_arguments):
        if command == "export_all":
            _png(output / "water.png")
        return {"success": True, "command": command, "status": "consumed"}

    clock = _Clock()
    with pytest.raises(LiquiGenExportWorkflowError, match="expected " + required_type):
        run_export_workflow(
            str(project),
            str(output),
            simulate_seconds=0,
            timeout_seconds=1.0,
            stable_seconds=0.5,
            poll_interval_seconds=0.25,
            binding=_binding(),
            roots=[tmp_path],
            command_runner=command_runner,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )


def test_disabled_image_export_is_rejected_before_host_commands(monkeypatch, tmp_path):
    project = tmp_path / "source.liquigen"
    project.write_bytes(b"fixture")
    output = tmp_path / "out"
    output.mkdir()
    monkeypatch.setattr(
        "dcc_mcp_liquigen.export_workflow.inspect_project_graph",
        lambda *args, **kwargs: {
            "nodes": [{"type": "Node_Export_Image", "disabled": True, "on": True}]
        },
    )

    def unexpected_command(*args, **kwargs):
        pytest.fail("invalid export plan reached the host")

    with pytest.raises(LiquiGenExportWorkflowError, match="paired image exporter"):
        run_export_workflow(
            str(project), str(output), roots=[tmp_path], command_runner=unexpected_command
        )


def _export_node(directory, kind="Node_Export_Image", **parameters):
    return {
        "type": kind,
        "parameters": [
            {"name": "directory", "value": str(directory)},
            *({"name": name, "value": value} for name, value in parameters.items()),
        ],
    }


def _workflow_fixture(monkeypatch, tmp_path, nodes):
    project = tmp_path / "source.liquigen"
    project.write_bytes(b"fixture")
    monkeypatch.setattr(
        "dcc_mcp_liquigen.export_workflow.inspect_project_graph",
        lambda *args, **kwargs: {"nodes": nodes, "truncated": False},
    )
    clock = _Clock()
    arguments = {
        "project_path": str(project),
        "output_directory": str(tmp_path / "primary"),
        "roots": [tmp_path],
        "binding": _binding(),
        "simulate_seconds": 0,
        "settle_seconds": 0,
        "timeout_seconds": 3,
        "stable_seconds": 0.5,
        "poll_interval_seconds": 0.25,
        "sleep": clock.sleep,
        "monotonic": clock.monotonic,
    }
    return arguments, clock


def test_export_waits_for_delayed_secondary_directory(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    secondary = tmp_path / "mesh"
    arguments, clock = _workflow_fixture(
        monkeypatch,
        tmp_path,
        [
            _export_node(primary),
            _export_node(secondary, "Node_Export_Mesh", export_kind="Alembic"),
        ],
    )

    def command_runner(command, **kwargs):
        if command == "export_all":
            _png(primary / "preview.png")
        return {"success": True}

    def sleep(duration):
        clock.sleep(duration)
        if clock.value >= 1 and not (secondary / "surface.abc").exists():
            (secondary / "surface.abc").write_bytes(b"fixture-alembic")

    arguments.update(command_runner=command_runner, sleep=sleep)
    result = run_export_workflow(**arguments)
    assert result["bundle"]["bundle_type"] == "image_flipbook"
    assert result["fresh_files"] == ["preview.png"]
    assert [item["bundle"]["bundle_type"] for item in result["exports"]] == [
        "image_flipbook",
        "alembic_geometry_cache",
    ]
    assert result["elapsed_seconds"] >= 1.5


@pytest.mark.parametrize("secondary_mode", ["absent", "wrong_type"])
def test_secondary_export_must_complete_even_when_primary_is_valid(
    monkeypatch, tmp_path, secondary_mode
):
    primary = tmp_path / "primary"
    secondary = tmp_path / "mesh"
    arguments, _ = _workflow_fixture(
        monkeypatch,
        tmp_path,
        [_export_node(primary), _export_node(secondary, "Node_Export_Mesh", export_kind="Alembic")],
    )

    def command_runner(command, **kwargs):
        if command == "export_all":
            _png(primary / "preview.png")
            if secondary_mode == "wrong_type":
                _png(secondary / "wrong.png")
        return {"success": True}

    arguments["command_runner"] = command_runner
    reason = "no fresh files in:" if secondary_mode == "absent" else "expected alembic"
    with pytest.raises(LiquiGenExportWorkflowError, match=reason):
        run_export_workflow(**arguments)


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("outside", "outside configured allowed roots"),
        ("relative", "must be absolute"),
        ("missing", "requires a directory"),
        ("nonempty", "must be empty"),
        ("overlap", "must not overlap"),
        ("conflicting_modes", "separate output directories"),
    ],
)
def test_all_export_targets_are_preflighted_before_host_commands(
    monkeypatch, tmp_path, case, reason
):
    primary = tmp_path / "primary"
    secondary = tmp_path / "secondary"
    if case == "outside":
        secondary = tmp_path.parent / (tmp_path.name + "-outside")
    elif case == "relative":
        secondary = Path("relative-export")
    elif case == "missing":
        secondary = ""
    elif case == "nonempty":
        secondary.mkdir()
        _png(secondary / "existing.png")
    elif case == "overlap":
        secondary = primary / "nested"
    nodes = [_export_node(primary), _export_node(secondary)]
    if case == "conflicting_modes":
        nodes = [
            _export_node(primary, "Node_Export_Mesh", export_kind=mode)
            for mode in ("Alembic", "Vertex_Animated_Texture")
        ]
    arguments, _ = _workflow_fixture(monkeypatch, tmp_path, nodes)

    def unexpected_command(*args, **kwargs):
        pytest.fail("invalid secondary destination reached the host")

    arguments["command_runner"] = unexpected_command
    with pytest.raises(LiquiGenExportWorkflowError, match=reason):
        run_export_workflow(**arguments)
    if case == "outside":
        assert not secondary.exists()
    if case == "nonempty":
        assert (secondary / "existing.png").exists()


def test_truncated_graph_cannot_authorize_export_all(monkeypatch, tmp_path):
    arguments, _ = _workflow_fixture(monkeypatch, tmp_path, [])
    monkeypatch.setattr(
        "dcc_mcp_liquigen.export_workflow.inspect_project_graph",
        lambda *args, **kwargs: {"nodes": [], "truncated": True},
    )
    with pytest.raises(LiquiGenExportWorkflowError, match="complete project graph"):
        run_export_workflow(**arguments)


def test_secondary_output_is_rechecked_immediately_before_export(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    secondary = tmp_path / "secondary"
    arguments, _ = _workflow_fixture(
        monkeypatch, tmp_path, [_export_node(primary), _export_node(secondary)]
    )
    calls = []

    def command_runner(command, **kwargs):
        calls.append(command)
        if command == "switch_tab_to_export":
            _png(secondary / "concurrent.png")
        return {"success": True}

    arguments["command_runner"] = command_runner
    with pytest.raises(LiquiGenExportWorkflowError, match="changed before export"):
        run_export_workflow(**arguments)
    assert "export_all" not in calls


def test_files_changed_during_validation_require_another_stable_interval(monkeypatch, tmp_path):
    from dcc_mcp_liquigen.export_bundle import validate_unreal_export_bundle

    primary = tmp_path / "primary"
    arguments, clock = _workflow_fixture(monkeypatch, tmp_path, [_export_node(primary)])
    validations = []

    def command_runner(command, **kwargs):
        if command == "export_all":
            _png(primary / "preview.png")
        return {"success": True}

    def validate(directory, **kwargs):
        result = validate_unreal_export_bundle(directory, **kwargs)
        validations.append(clock.value)
        if len(validations) == 1:
            _png(primary / "later.png")
        return result

    monkeypatch.setattr("dcc_mcp_liquigen.export_workflow.validate_unreal_export_bundle", validate)
    arguments["command_runner"] = command_runner
    result = run_export_workflow(**arguments)
    assert result["fresh_files"] == ["later.png", "preview.png"]
    assert validations[1] - validations[0] >= 0.5


def test_export_file_limit_applies_across_directories(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    secondary = tmp_path / "secondary"
    arguments, _ = _workflow_fixture(
        monkeypatch, tmp_path, [_export_node(primary), _export_node(secondary)]
    )
    monkeypatch.setattr("dcc_mcp_liquigen.export_workflow.MAX_EXPORT_FILES", 1)

    def command_runner(command, **kwargs):
        if command == "export_all":
            _png(primary / "preview.png")
            _png(secondary / "preview.png")
        return {"success": True}

    arguments["command_runner"] = command_runner
    with pytest.raises(
        LiquiGenExportWorkflowError, match="directories exceed the file-count limit"
    ):
        run_export_workflow(**arguments)


def test_completed_mesh_does_not_hide_missing_paired_image_output(monkeypatch, tmp_path):
    primary = tmp_path / "primary"
    secondary = tmp_path / "images"
    arguments, _ = _workflow_fixture(
        monkeypatch,
        tmp_path,
        [_export_node(primary, "Node_Export_Mesh", export_kind="Alembic"), _export_node(secondary)],
    )

    def command_runner(command, **kwargs):
        if command == "export_all":
            (primary / "surface.abc").write_bytes(b"fixture-alembic")
        return {"success": True}

    arguments["command_runner"] = command_runner
    with pytest.raises(LiquiGenExportWorkflowError, match="no fresh files in:"):
        run_export_workflow(**arguments)
