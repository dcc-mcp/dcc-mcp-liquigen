from pathlib import Path

import pytest

from dcc_mcp_liquigen.companion_menu import (
    CompanionMenuError,
    arguments_for_action,
    build_companion_session,
    build_tool_command,
)


class FakeInspector:
    def __init__(self, executable: Path, title: str = "LiquiGen") -> None:
        self.executable = executable
        self.title = title

    def process_path(self, pid: int) -> Path:
        assert pid == 2796
        return self.executable

    def window_title(self, pid: int, window_handle: int) -> str:
        assert (pid, window_handle) == (2796, 66075782)
        return self.title


def test_companion_session_binds_one_liquigen_window_and_whitelists_tools(tmp_path: Path):
    executable = tmp_path / "LiquiGen.exe"
    executable.write_bytes(b"synthetic executable identity")

    session = build_companion_session(
        pid=2796,
        window_handle=66075782,
        instance_id="762677c2-3d38-43cc-9978-fdb3768e9741",
        version="1.0.5",
        inspector=FakeInspector(executable),
    )

    assert session.binding.pid == 2796
    assert session.binding.window_handle == 66075782
    assert session.instance_id == "762677c2-3d38-43cc-9978-fdb3768e9741"
    assert [(action.action_id, action.tool_slug) for action in session.actions] == [
        ("bridge.status", "get_status"),
        ("bridge.discover_presets", "discover_presets"),
        ("bridge.inspect_project", "inspect_project"),
        ("bridge.validate_project", "validate_project"),
        ("bridge.stage_project_copy", "stage_project_copy"),
        ("bridge.list_node_schemas", "list_node_schemas"),
        ("bridge.inspect_project_graph", "inspect_project_graph"),
        ("bridge.build_chain_burst", "create_liquid_chain_burst_project"),
        ("bridge.plan_chain_burst", "plan_liquid_chain_burst"),
        ("bridge.validate_export", "validate_unreal_export_bundle"),
        ("bridge.run_export_workflow", "run_export_workflow"),
    ]


def test_companion_session_rejects_non_uuid_instance_binding(tmp_path: Path):
    executable = tmp_path / "LiquiGen.exe"
    executable.write_bytes(b"synthetic executable identity")

    with pytest.raises(CompanionMenuError, match="instance ID"):
        build_companion_session(
            pid=2796,
            window_handle=66075782,
            instance_id="not-a-runtime-instance",
            inspector=FakeInspector(executable),
        )


def test_tool_command_is_shell_free_and_cannot_select_an_unlisted_tool(tmp_path: Path):
    executable = tmp_path / "LiquiGen.exe"
    executable.write_bytes(b"synthetic executable identity")
    session = build_companion_session(
        pid=2796,
        window_handle=66075782,
        instance_id="762677c2-3d38-43cc-9978-fdb3768e9741",
        inspector=FakeInspector(executable),
    )

    command = build_tool_command(
        session,
        action_id="bridge.plan_chain_burst",
        arguments={"burst_count": 5},
        cli_path=Path("C:/tools/dcc-mcp-cli.exe"),
    )

    assert command == [
        "C:\\tools\\dcc-mcp-cli.exe",
        "--output",
        "json",
        "--non-interactive",
        "call",
        "plan_liquid_chain_burst",
        "--instance-id",
        "762677c2-3d38-43cc-9978-fdb3768e9741",
        "--json",
        '{"burst_count":5}',
    ]
    with pytest.raises(CompanionMenuError, match="not exposed"):
        build_tool_command(
            session,
            action_id="bridge.run_script",
            arguments={"script": "arbitrary"},
            cli_path=Path("C:/tools/dcc-mcp-cli.exe"),
        )


def test_menu_maps_path_fields_to_bounded_action_arguments(tmp_path: Path):
    executable = tmp_path / "LiquiGen.exe"
    executable.write_bytes(b"synthetic executable identity")
    session = build_companion_session(
        pid=2796,
        window_handle=66075782,
        instance_id="762677c2-3d38-43cc-9978-fdb3768e9741",
        inspector=FakeInspector(executable),
    )

    assert arguments_for_action(session, "bridge.status", project_path="", export_path="") == {}
    assert (
        arguments_for_action(session, "bridge.discover_presets", project_path="", export_path="")
        == {}
    )
    assert arguments_for_action(
        session,
        "bridge.inspect_project",
        project_path="C:/workspace/chain.liquigen",
        export_path="",
    ) == {"path": "C:/workspace/chain.liquigen"}
    assert arguments_for_action(
        session,
        "bridge.validate_project",
        project_path="C:/workspace/chain.liquigen",
        export_path="",
    ) == {"path": "C:/workspace/chain.liquigen", "require_unreal_export": True}
    assert arguments_for_action(
        session,
        "bridge.stage_project_copy",
        project_path="C:/workspace/source.liquigen",
        export_path="C:/workspace/staged.liquigen",
    ) == {
        "source": "C:/workspace/source.liquigen",
        "destination": "C:/workspace/staged.liquigen",
    }
    assert arguments_for_action(
        session,
        "bridge.list_node_schemas",
        project_path="",
        export_path="",
    ) == {"limit": 100}
    assert arguments_for_action(
        session,
        "bridge.inspect_project_graph",
        project_path="C:/workspace/chain.liquigen",
        export_path="",
    ) == {"path": "C:/workspace/chain.liquigen", "limit": 200}
    assert arguments_for_action(
        session,
        "bridge.build_chain_burst",
        project_path="C:/workspace/source.liquigen",
        export_path="C:/workspace/chain-burst",
    ) == {
        "source": "C:/workspace/source.liquigen",
        "destination": "C:\\workspace\\chain-burst\\LiquiGen_ChainBurst_UE58.liquigen",
        "output_directory": "C:\\workspace\\chain-burst\\exports",
        "burst_count": 5,
        "delay_seconds": 0.18,
        "spacing_m": 2.6,
        "export_profile": "ue_vat",
    }
    assert arguments_for_action(
        session,
        "bridge.plan_chain_burst",
        project_path="",
        export_path="C:/workspace/exports/chain",
    ) == {"output_directory": "C:/workspace/exports/chain"}
    assert arguments_for_action(
        session,
        "bridge.validate_export",
        project_path="",
        export_path="C:/workspace/exports/chain",
    ) == {"path": "C:/workspace/exports/chain"}
    assert arguments_for_action(
        session,
        "bridge.run_export_workflow",
        project_path="C:/workspace/chain.liquigen",
        export_path="C:/workspace/exports/chain",
    ) == {
        "project_path": "C:/workspace/chain.liquigen",
        "output_directory": "C:/workspace/exports/chain",
        "simulate_seconds": 12.0,
        "timeout_seconds": 600.0,
    }
    with pytest.raises(CompanionMenuError, match="project path"):
        arguments_for_action(session, "bridge.inspect_project", project_path=" ", export_path="")
    with pytest.raises(CompanionMenuError, match="export path"):
        arguments_for_action(session, "bridge.validate_export", project_path="", export_path=" ")
