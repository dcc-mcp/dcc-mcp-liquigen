import json
import subprocess
from pathlib import Path

import pytest

from dcc_mcp_liquigen.host_commands import (
    HOST_COMMANDS,
    LiquiGenHostCommandError,
    invoke_host_command,
    list_host_commands,
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


def test_host_command_catalog_is_bounded_and_hash_free(monkeypatch, tmp_path: Path):
    client = tmp_path / "dcc_mcp_liquigen_command_client.exe"
    client.write_bytes(b"client")
    monkeypatch.setenv("DCC_MCP_LIQUIGEN_COMMAND_CLIENT", str(client))

    result = list_host_commands()

    assert result["available"] is True
    assert result["commands"] == list(HOST_COMMANDS)
    assert result["hash_required"] is False
    assert result["requires_cua"] is False
    assert result["arbitrary_commands_allowed"] is False
    assert result["licensing_commands_allowed"] is False
    assert "switch_tab_to_export" in result["commands"]
    assert "reset_graph_zoom" in result["commands"]
    assert "open_project_path" in result["commands"]
    assert "toggle_project_palette" in result["commands"]
    assert "show_project_palette" in result["commands"]
    assert "return_to_project" in result["commands"]
    assert next(
        item for item in result["command_capabilities"] if item["name"] == "export_all"
    ) == {
        "name": "export_all",
        "scope": "node_graph",
        "acknowledgement": "consumer_acknowledged",
    }
    assert next(
        item for item in result["command_capabilities"] if item["name"] == "open_project_path"
    ) == {
        "name": "open_project_path",
        "scope": "project",
        "acknowledgement": "consumer_acknowledged",
    }
    assert next(
        item for item in result["command_capabilities"] if item["name"] == "pause_timeline"
    ) == {
        "name": "pause_timeline",
        "scope": "application",
        "acknowledgement": "consumer_acknowledged",
    }
    assert next(
        item for item in result["command_capabilities"] if item["name"] == "return_to_project"
    ) == {
        "name": "return_to_project",
        "scope": "application",
        "acknowledgement": "consumer_acknowledged",
    }


def test_resolve_command_client_uses_versioned_local_install(monkeypatch, tmp_path: Path):
    generation = "0123456789abcdef"
    native = tmp_path / "dcc-mcp-liquigen" / "native"
    client = native / generation / "dcc_mcp_liquigen_command_client.exe"
    client.parent.mkdir(parents=True)
    client.write_bytes(b"client")
    (native / "current.txt").write_text(generation, encoding="ascii")
    monkeypatch.delenv("DCC_MCP_LIQUIGEN_COMMAND_CLIENT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from dcc_mcp_liquigen.host_commands import resolve_command_client

    assert resolve_command_client() == client.resolve()


def test_invoke_host_command_passes_exact_binding_and_reads_json(monkeypatch, tmp_path: Path):
    client = tmp_path / "dcc_mcp_liquigen_command_client.exe"
    client.write_bytes(b"client")
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        payload = {
            "success": True,
            "interface": "liquigen.host.command.invoke.v1",
            "command": "pause_timeline",
            "status": "injected",
            "pid": 86184,
            "hwnd": 25306976,
        }
        return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = invoke_host_command(
        "pause_timeline", timeout_ms=1200, binding=_binding(), client=client
    )

    assert result["success"] is True
    assert result["requires_cua"] is False
    assert result["delivery"] == "host_ui_thread_named_command_event"
    assert calls[0][0][1:] == [
        "--pid",
        "86184",
        "--hwnd",
        "25306976",
        "--command",
        "pause_timeline",
        "--timeout-ms",
        "1200",
    ]


def test_invoke_host_command_rejects_arbitrary_name(tmp_path: Path):
    with pytest.raises(LiquiGenHostCommandError, match="unsupported"):
        invoke_host_command("arbitrary_native_call", binding=_binding(), client=tmp_path / "x.exe")


def test_open_project_path_passes_allowed_absolute_project(monkeypatch, tmp_path: Path):
    client = tmp_path / "dcc_mcp_liquigen_command_client.exe"
    client.write_bytes(b"client")
    project = tmp_path / "chain-burst.liquigen"
    project.write_bytes(b"project")
    monkeypatch.setenv("DCC_MCP_LIQUIGEN_ALLOWED_ROOTS", str(tmp_path))
    calls = []

    def fake_run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        payload = {
            "success": True,
            "interface": "liquigen.host.command.invoke.v1",
            "command": "open_project_path",
            "status": "consumed",
            "pid": 86184,
            "hwnd": 25306976,
        }
        return subprocess.CompletedProcess(arguments, 0, json.dumps(payload), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = invoke_host_command(
        "open_project_path",
        timeout_ms=30000,
        project_path=str(project),
        binding=_binding(),
        client=client,
    )

    assert result["delivery"] == "host_ui_thread_native_project_loader"
    assert result["completion_boundary"] == "native project loader returned success"
    assert calls[0][0][-2:] == ["--project-path", str(project.resolve())]


def test_open_project_path_requires_path(tmp_path: Path):
    with pytest.raises(LiquiGenHostCommandError, match="requires project_path"):
        invoke_host_command(
            "open_project_path",
            binding=_binding(),
            client=tmp_path / "dcc_mcp_liquigen_command_client.exe",
        )
