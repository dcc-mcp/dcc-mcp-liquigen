import os
import sys
from pathlib import Path

from dcc_mcp_liquigen.runtime import RuntimeBinding
from dcc_mcp_liquigen.server import LiquiGenMcpServer


def test_server_binds_gui_host_and_bundles_typed_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DCC_MCP_DISABLE_DEFAULT_SKILL_PATHS", "1")
    binding = RuntimeBinding(
        pid=os.getpid(),
        window_handle=1,
        executable=sys.executable,
        version="1.0.5",
    )
    server = LiquiGenMcpServer(
        dcc_pid=binding.pid,
        dcc_window_handle=binding.window_handle,
        binding=binding,
        port=0,
        registry_dir=str(tmp_path / "registry"),
    )
    assert server._options.instance_type == "gui"
    assert server.binding == binding
    assert os.environ["DCC_MCP_UI_CONTROL_PROCESS_ID"] == str(binding.pid)
    assert os.environ["DCC_MCP_UI_CONTROL_WINDOW_HANDLE"] == str(binding.window_handle)
    assert server._inprocess_executor_registered is True
    skill = (
        Path(__file__).parents[1]
        / "src"
        / "dcc_mcp_liquigen"
        / "skills"
        / "liquigen-project"
        / "SKILL.md"
    )
    assert skill.is_file()


def test_server_bounds_liquigen_accessibility_scans_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DCC_MCP_DISABLE_DEFAULT_SKILL_PATHS", "1")
    monkeypatch.delenv("DCC_MCP_CUA_MAX_DEPTH", raising=False)
    monkeypatch.delenv("DCC_MCP_CUA_MAX_NODES", raising=False)
    binding = RuntimeBinding(
        pid=os.getpid(),
        window_handle=1,
        executable=sys.executable,
        version="1.0.5",
    )

    LiquiGenMcpServer(
        dcc_pid=binding.pid,
        dcc_window_handle=binding.window_handle,
        binding=binding,
        port=0,
        registry_dir=str(tmp_path / "registry"),
    )

    assert os.environ["DCC_MCP_CUA_MAX_DEPTH"] == "1"
    assert os.environ["DCC_MCP_CUA_MAX_NODES"] == "32"
