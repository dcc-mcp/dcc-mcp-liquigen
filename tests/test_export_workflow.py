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
        "dcc_mcp_liquigen.export_workflow._configured_export_directories",
        lambda _project, _roots: [str(output)],
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
        "play_timeline",
        "pause_timeline",
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
        "dcc_mcp_liquigen.export_workflow._configured_export_directories",
        lambda _project, _roots: [str(output)],
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
        "dcc_mcp_liquigen.export_workflow._configured_export_directories",
        lambda _project, _roots: [str(tmp_path / "somewhere-else")],
    )

    with pytest.raises(LiquiGenExportWorkflowError, match="not configured"):
        run_export_workflow(
            str(project),
            str(output),
            binding=_binding(),
            roots=[tmp_path],
        )
