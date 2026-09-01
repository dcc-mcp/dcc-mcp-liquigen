"""Bounded client for LiquiGen's UI-thread semantic command bridge."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from .project import LiquiGenProjectError, resolve_project_path
from .runtime import RuntimeBinding, runtime_from_env

HOST_COMMAND_INTERFACE = "liquigen.host.command.invoke.v1"
HOST_COMMANDS = (
    "project_open",
    "project_save",
    "play_timeline",
    "pause_timeline",
    "export_all",
    "export_selected",
    "open_command_palette",
    "switch_tab_to_export",
    "switch_tab_to_viewport",
    "toggle_fullscreen_graph",
    "center_graph",
    "reset_graph_zoom",
    "center_graph_on_selection",
    "open_project_path",
    "toggle_project_palette",
    "show_project_palette",
    "return_to_project",
)
GRAPH_SCOPED_COMMANDS = frozenset(
    {
        "export_all",
        "export_selected",
        "center_graph",
        "reset_graph_zoom",
        "center_graph_on_selection",
    }
)
CONSUMER_ACKNOWLEDGED_COMMANDS = GRAPH_SCOPED_COMMANDS | frozenset(
    {
        "play_timeline",
        "pause_timeline",
        "show_project_palette",
        "return_to_project",
    }
)
PROJECT_PATH_COMMANDS = frozenset({"open_project_path"})


class LiquiGenHostCommandError(RuntimeError):
    """The bounded host-command bridge is absent, incompatible, or rejected a command."""


def _candidate_clients() -> tuple[Path, ...]:
    configured = os.environ.get("DCC_MCP_LIQUIGEN_COMMAND_CLIENT", "").strip()
    package_root = Path(__file__).resolve().parent
    project_root = package_root.parents[1]
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        native_root = Path(local_app_data) / "dcc-mcp-liquigen" / "native"
        pointer = native_root / "current.txt"
        try:
            generation = pointer.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            generation = ""
        if len(generation) == 16 and all(
            character in "0123456789abcdef" for character in generation
        ):
            candidates.append(native_root / generation / "dcc_mcp_liquigen_command_client.exe")
        candidates.append(native_root / "dcc_mcp_liquigen_command_client.exe")
    candidates.extend(
        (
            package_root / "native" / "dcc_mcp_liquigen_command_client.exe",
            project_root
            / ".artifacts"
            / "liquigen-command-bridge-build"
            / "Release"
            / "dcc_mcp_liquigen_command_client.exe",
        )
    )
    return tuple(candidates)


def resolve_command_client(required: bool = True) -> Optional[Path]:
    for candidate in _candidate_clients():
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and resolved.name.casefold() == (
            "dcc_mcp_liquigen_command_client.exe"
        ):
            return resolved
    if required:
        raise LiquiGenHostCommandError(
            "LiquiGen semantic command client is not installed; build the native "
            "liquigen-command-bridge or set DCC_MCP_LIQUIGEN_COMMAND_CLIENT"
        )
    return None


def list_host_commands() -> dict[str, object]:
    client = resolve_command_client(required=False)
    return {
        "interface": HOST_COMMAND_INTERFACE,
        "available": client is not None,
        "commands": list(HOST_COMMANDS),
        "command_capabilities": [
            {
                "name": name,
                "scope": (
                    "node_graph"
                    if name in GRAPH_SCOPED_COMMANDS
                    else "project"
                    if name in PROJECT_PATH_COMMANDS
                    else "application"
                ),
                "acknowledgement": (
                    "consumer_acknowledged"
                    if name in CONSUMER_ACKNOWLEDGED_COMMANDS or name in PROJECT_PATH_COMMANDS
                    else "event_delivered"
                ),
            }
            for name in HOST_COMMANDS
        ],
        "client": str(client) if client else None,
        "hash_required": False,
        "requires_cua": False,
        "requires_foreground": False,
        "requires_live_gui_host": True,
        "arbitrary_commands_allowed": False,
        "licensing_commands_allowed": False,
    }


def invoke_host_command(
    command: str,
    timeout_ms: int = 5000,
    project_path: Optional[str] = None,
    *,
    binding: Optional[RuntimeBinding] = None,
    client: Optional[Path] = None,
) -> dict[str, object]:
    selected_command = command.strip()
    if selected_command not in HOST_COMMANDS:
        raise LiquiGenHostCommandError(
            "unsupported LiquiGen host command; use list_host_commands for the whitelist"
        )
    selected_timeout = int(timeout_ms)
    if selected_timeout < 100 or selected_timeout > 60000:
        raise LiquiGenHostCommandError("timeout_ms must be between 100 and 60000")
    selected_binding = binding or runtime_from_env()
    selected_client = client or resolve_command_client(required=True)
    assert selected_client is not None
    resolved_project: Optional[Path] = None
    if selected_command in PROJECT_PATH_COMMANDS:
        if not project_path:
            raise LiquiGenHostCommandError("open_project_path requires project_path")
        try:
            resolved_project = resolve_project_path(project_path)
        except LiquiGenProjectError as error:
            raise LiquiGenHostCommandError(str(error)) from error
    elif project_path is not None:
        raise LiquiGenHostCommandError("project_path is only valid for open_project_path")
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = subprocess.CREATE_NO_WINDOW
    arguments = [
        str(selected_client),
        "--pid",
        str(selected_binding.pid),
        "--hwnd",
        str(selected_binding.window_handle),
        "--command",
        selected_command,
        "--timeout-ms",
        str(selected_timeout),
    ]
    if resolved_project is not None:
        arguments.extend(["--project-path", str(resolved_project)])
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=selected_timeout / 1000.0 + 5.0,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    output = completed.stdout.strip()
    try:
        result = json.loads(output)
    except json.JSONDecodeError as error:
        raise LiquiGenHostCommandError(
            "LiquiGen semantic command client returned invalid JSON"
        ) from error
    if completed.returncode != 0 or result.get("success") is not True:
        reason = str(result.get("error") or result.get("status") or "command rejected")
        raise LiquiGenHostCommandError("LiquiGen host command failed: " + reason)
    if result.get("interface") != HOST_COMMAND_INTERFACE:
        raise LiquiGenHostCommandError("LiquiGen command client interface does not match")
    return {
        **result,
        "delivery": (
            "host_ui_thread_native_project_loader"
            if selected_command in PROJECT_PATH_COMMANDS
            else "host_ui_thread_project_palette_state"
            if selected_command in {"show_project_palette", "return_to_project"}
            else "host_ui_thread_named_command_event"
        ),
        "requires_cua": False,
        "completion_boundary": (
            "native project loader returned success"
            if selected_command in PROJECT_PATH_COMMANDS and result.get("status") == "consumed"
            else "project palette state changed and read back in the LiquiGen host"
            if selected_command in {"show_project_palette", "return_to_project"}
            and result.get("status") == "consumed"
            else "named host command consumed by LiquiGen"
            if selected_command in CONSUMER_ACKNOWLEDGED_COMMANDS
            and result.get("status") == "consumed"
            else "command event delivered; inspect project/export state for operation completion"
        ),
    }


__all__ = [
    "HOST_COMMAND_INTERFACE",
    "HOST_COMMANDS",
    "CONSUMER_ACKNOWLEDGED_COMMANDS",
    "GRAPH_SCOPED_COMMANDS",
    "PROJECT_PATH_COMMANDS",
    "LiquiGenHostCommandError",
    "invoke_host_command",
    "list_host_commands",
    "resolve_command_client",
]
