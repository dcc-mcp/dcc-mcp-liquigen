from pathlib import Path

from dcc_mcp_liquigen import skill_tools
from dcc_mcp_liquigen.runtime import RuntimeBinding


def test_status_keeps_semantic_bridge_fail_closed(monkeypatch):
    monkeypatch.setattr(
        skill_tools,
        "runtime_from_env",
        lambda: RuntimeBinding(
            pid=2796,
            window_handle=66075782,
            executable="G:/apps/LiquiGen.exe",
            version="1.0.5",
            title="LiquiGen",
        ),
    )
    monkeypatch.setattr(
        skill_tools,
        "list_host_commands",
        lambda: {
            "interface": "liquigen.host.command.invoke.v1",
            "available": True,
            "commands": ["play_timeline", "pause_timeline", "export_all"],
            "hash_required": False,
            "requires_cua": False,
        },
    )
    monkeypatch.setattr(
        skill_tools,
        "interface_fingerprint",
        lambda _executable: {
            "compatibility_policy": "interface_names_and_schemas",
            "executable_hash_required": False,
            "node_type_count": 25,
            "node_types": ["Node_Emitter", "Node_Simulation"],
            "schema_fingerprint": "f" * 64,
        },
    )

    status = skill_tools.get_status()

    assert status["semantic_ui_bridge"] == {
        "abi_version": 1,
        "contract_tested": True,
        "runtime_attached": False,
        "tested_patterns": ["Invoke", "Value"],
        "requires_authorized_local_attachment": True,
    }
    assert status["compatibility"]["status"] == "compatible_tested"
    assert status["compatibility"]["host_match"]["executable_hash_required"] is False
    assert status["project_binary_writes_supported"] is True
    assert status["native_api_available"] is True
    assert status["host_command_bridge"]["requires_cua"] is False
    assert status["graph_api"]["mode"] == "transactional_project_document"
    assert status["graph_api"]["requires_interactive_desktop"] is False
    assert status["interactive_route"] == (
        "optional dcc-cua viewport acceptance and recording only"
    )


def test_stage_project_copy_accepts_discovered_official_preset(monkeypatch, tmp_path: Path):
    install = tmp_path / "install"
    presets = install / "presets_1_0_0"
    workspace = tmp_path / "workspace"
    presets.mkdir(parents=True)
    workspace.mkdir()
    executable = install / "LiquiGen.exe"
    executable.write_bytes(b"host")
    source = presets / "ball_drop_splash.liquigen"
    source.write_bytes(b"official preset")
    destination = workspace / "chain-burst.liquigen"
    monkeypatch.setenv("DCC_MCP_LIQUIGEN_EXECUTABLE", str(executable))
    monkeypatch.setenv("DCC_MCP_LIQUIGEN_ALLOWED_ROOTS", str(workspace))

    result = skill_tools.stage_project_copy(str(source), str(destination))

    assert result["source"] == str(source.resolve())
    assert result["destination"] == str(destination.resolve())
    assert destination.read_bytes() == b"official preset"
