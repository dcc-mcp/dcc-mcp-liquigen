"""Exact-window companion menu for the external LiquiGen adapter.

The companion owns its window and invokes only fixed DCC-MCP tool slugs.  It
does not inject code into, subclass, or synthesize input for LiquiGen.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from .runtime import RuntimeBinding, RuntimeInspector, bind_runtime


class CompanionMenuError(RuntimeError):
    """The companion menu contract is invalid or no longer safely bound."""


@dataclass(frozen=True)
class CompanionAction:
    """One fixed menu action backed by a typed DCC-MCP tool."""

    action_id: str
    label: str
    tool_slug: str
    requires_project_path: bool = False
    requires_export_path: bool = False


@dataclass(frozen=True)
class CompanionSession:
    """Immutable binding between one menu, one host window, and one MCP instance."""

    binding: RuntimeBinding
    instance_id: str
    actions: tuple[CompanionAction, ...]


_ACTIONS = (
    CompanionAction("bridge.status", "Bridge Status", "get_status"),
    CompanionAction("bridge.discover_presets", "Discover Presets", "discover_presets"),
    CompanionAction(
        "bridge.inspect_project",
        "Inspect Project",
        "inspect_project",
        requires_project_path=True,
    ),
    CompanionAction(
        "bridge.validate_project",
        "Validate Project for Unreal",
        "validate_project",
        requires_project_path=True,
    ),
    CompanionAction(
        "bridge.stage_project_copy",
        "Stage Project Copy",
        "stage_project_copy",
        requires_project_path=True,
        requires_export_path=True,
    ),
    CompanionAction(
        "bridge.list_node_schemas",
        "List Node Schemas",
        "list_node_schemas",
    ),
    CompanionAction(
        "bridge.inspect_project_graph",
        "Inspect Project Graph",
        "inspect_project_graph",
        requires_project_path=True,
    ),
    CompanionAction(
        "bridge.build_chain_burst",
        "Build Chain Burst Project",
        "create_liquid_chain_burst_project",
        requires_project_path=True,
        requires_export_path=True,
    ),
    CompanionAction(
        "bridge.plan_chain_burst",
        "Plan Chain Burst",
        "plan_liquid_chain_burst",
        requires_export_path=True,
    ),
    CompanionAction(
        "bridge.validate_export",
        "Validate Unreal Export",
        "validate_unreal_export_bundle",
        requires_export_path=True,
    ),
    CompanionAction(
        "bridge.run_export_workflow",
        "Run, Export && Validate",
        "run_export_workflow",
        requires_project_path=True,
        requires_export_path=True,
    ),
)


def _canonical_instance_id(value: str) -> str:
    selected = value.strip()
    try:
        parsed = uuid.UUID(selected)
    except (AttributeError, ValueError) as error:
        raise CompanionMenuError("DCC-MCP instance ID must be a full UUID") from error
    canonical = str(parsed)
    if canonical != selected.casefold():
        raise CompanionMenuError("DCC-MCP instance ID must use canonical UUID syntax")
    return canonical


def build_companion_session(
    *,
    pid: int,
    window_handle: int,
    instance_id: str,
    executable: Optional[str] = None,
    version: Optional[str] = None,
    inspector: Optional[RuntimeInspector] = None,
) -> CompanionSession:
    """Bind a companion menu to one exact LiquiGen PID/HWND and MCP instance."""

    binding = bind_runtime(
        pid,
        window_handle,
        executable=executable,
        version=version,
        inspector=inspector,
    )
    return CompanionSession(
        binding=binding,
        instance_id=_canonical_instance_id(instance_id),
        actions=_ACTIONS,
    )


def build_tool_command(
    session: CompanionSession,
    *,
    action_id: str,
    arguments: Mapping[str, object],
    cli_path: Path,
) -> list[str]:
    """Build a shell-free CLI invocation for one catalogued action."""

    action = next((item for item in session.actions if item.action_id == action_id), None)
    if action is None:
        raise CompanionMenuError("requested action is not exposed by the companion menu")
    try:
        payload = json.dumps(dict(arguments), separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as error:
        raise CompanionMenuError("menu action arguments must be JSON serializable") from error
    if len(payload.encode("utf-8")) > 64 * 1024:
        raise CompanionMenuError("menu action arguments exceed the 64 KiB limit")
    return [
        str(cli_path),
        "--output",
        "json",
        "--non-interactive",
        "call",
        action.tool_slug,
        "--instance-id",
        session.instance_id,
        "--json",
        payload,
    ]


def arguments_for_action(
    session: CompanionSession,
    action_id: str,
    *,
    project_path: str,
    export_path: str,
) -> dict[str, object]:
    """Map visible fields to the fixed argument schema for one menu action."""

    action = next((item for item in session.actions if item.action_id == action_id), None)
    if action is None:
        raise CompanionMenuError("requested action is not exposed by the companion menu")
    selected_project = project_path.strip()
    selected_export = export_path.strip()
    if action.requires_project_path and not selected_project:
        raise CompanionMenuError("a project path is required for this menu action")
    if action.requires_export_path and not selected_export:
        raise CompanionMenuError("an export path is required for this menu action")
    if action_id == "bridge.inspect_project":
        return {"path": selected_project}
    if action_id == "bridge.validate_project":
        return {"path": selected_project, "require_unreal_export": True}
    if action_id == "bridge.stage_project_copy":
        return {"source": selected_project, "destination": selected_export}
    if action_id == "bridge.list_node_schemas":
        return {"limit": 100}
    if action_id == "bridge.inspect_project_graph":
        return {"path": selected_project, "limit": 200}
    if action_id == "bridge.build_chain_burst":
        output_root = Path(selected_export).expanduser()
        return {
            "source": selected_project,
            "destination": str(output_root / "LiquiGen_ChainBurst_UE58.liquigen"),
            "output_directory": str(output_root / "exports"),
            "burst_count": 5,
            "delay_seconds": 0.18,
            "spacing_m": 2.6,
            "export_profile": "ue_vat",
        }
    if action_id == "bridge.plan_chain_burst":
        return {"output_directory": selected_export}
    if action_id == "bridge.validate_export":
        return {"path": selected_export}
    if action_id == "bridge.run_export_workflow":
        return {
            "project_path": selected_project,
            "output_directory": selected_export,
            "simulate_seconds": 12.0,
            "timeout_seconds": 600.0,
        }
    return {}


def locate_dcc_mcp_cli(explicit: Optional[str] = None) -> Path:
    """Resolve the installed DCC-MCP control-plane executable."""

    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    discovered = shutil.which("dcc-mcp-cli")
    if discovered:
        candidates.append(Path(discovered))
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(Path(local_app_data) / "dcc-mcp" / "bin" / "dcc-mcp-cli.exe")
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    raise CompanionMenuError("dcc-mcp-cli was not found; install the matching DCC-MCP runtime")


def run_tool_action(
    session: CompanionSession,
    *,
    action_id: str,
    project_path: str,
    export_path: str,
    cli_path: Path,
    timeout_seconds: float = 120.0,
) -> str:
    """Revalidate the host binding and invoke one typed tool without a shell."""

    if timeout_seconds <= 0 or timeout_seconds > 600:
        raise CompanionMenuError("menu action timeout must be between 0 and 600 seconds")
    bind_runtime(
        session.binding.pid,
        session.binding.window_handle,
        executable=session.binding.executable,
        version=session.binding.version,
    )
    arguments = arguments_for_action(
        session,
        action_id,
        project_path=project_path,
        export_path=export_path,
    )
    command = build_tool_command(
        session,
        action_id=action_id,
        arguments=arguments,
        cli_path=cli_path,
    )
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            shell=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CompanionMenuError("DCC-MCP menu action could not complete") from error
    output = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0:
        raise CompanionMenuError(output or f"DCC-MCP menu action failed ({completed.returncode})")
    return output


def _target_window_rect(session: CompanionSession) -> tuple[int, int, int, int]:
    if os.name != "nt":
        raise CompanionMenuError("the attached companion menu requires Windows")
    import ctypes
    from ctypes import wintypes

    class Rect(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(Rect)]
    user32.GetWindowRect.restype = wintypes.BOOL
    window = wintypes.HWND(session.binding.window_handle)
    owner = wintypes.DWORD()
    if not user32.IsWindow(window):
        raise CompanionMenuError("LiquiGen HWND is no longer live")
    if user32.GetWindowThreadProcessId(window, ctypes.byref(owner)) == 0:
        raise CompanionMenuError("LiquiGen HWND owner could not be read")
    if int(owner.value) != session.binding.pid:
        raise CompanionMenuError("LiquiGen HWND ownership drifted")
    rectangle = Rect()
    if not user32.GetWindowRect(window, ctypes.byref(rectangle)):
        raise CompanionMenuError("LiquiGen window bounds could not be read")
    return rectangle.left, rectangle.top, rectangle.right, rectangle.bottom


class CompanionMenuApplication:
    """Standard accessible Windows menu bar that follows its bound LiquiGen window."""

    def __init__(
        self,
        session: CompanionSession,
        *,
        cli_path: Path,
        initial_project_path: str = "",
        initial_export_path: str = "",
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self._session = session
        self._cli_path = cli_path
        self._busy = False
        self.root = tk.Tk()
        self.root.title("DCC-MCP · LiquiGen")
        self.root.resizable(False, False)
        try:
            self.root.wm_attributes("-toolwindow", True)
            self.root.wm_attributes("-topmost", True)
        except tk.TclError:
            pass

        menu_bar = tk.Menu(self.root)
        bridge_menu = tk.Menu(menu_bar, tearoff=False)
        for action in session.actions:
            bridge_menu.add_command(
                label=action.label,
                command=lambda action_id=action.action_id: self._start_action(action_id),
            )
        bridge_menu.add_separator()
        bridge_menu.add_command(label="Close Companion", command=self.root.destroy)
        menu_bar.add_cascade(label="DCC-MCP", menu=bridge_menu)
        self.root.configure(menu=menu_bar)

        frame = ttk.Frame(self.root, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            frame,
            text=f"Bound: LiquiGen {session.binding.version} · PID {session.binding.pid}",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Project path").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.project_path = tk.StringVar(value=initial_project_path)
        ttk.Entry(frame, width=58, textvariable=self.project_path).grid(
            row=2, column=0, columnspan=2, sticky="ew"
        )
        ttk.Label(frame, text="Export / destination path").grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )
        self.export_path = tk.StringVar(value=initial_export_path)
        ttk.Entry(frame, width=58, textvariable=self.export_path).grid(
            row=4, column=0, columnspan=2, sticky="ew"
        )
        self.status = tk.StringVar(value="Ready — choose an action from DCC-MCP")
        ttk.Label(frame, textvariable=self.status, wraplength=440).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        self._follow_target()

    def _follow_target(self) -> None:
        try:
            left, top, right, _ = _target_window_rect(self._session)
        except CompanionMenuError as error:
            self.status.set(str(error))
            self.root.after(1200, self.root.destroy)
            return
        width = 480
        x = max(left, right - width - 16)
        y = top + 48
        self.root.geometry(f"{width}x184+{x}+{y}")
        self.root.after(350, self._follow_target)

    def _start_action(self, action_id: str) -> None:
        if self._busy:
            self.status.set("Another DCC-MCP action is still running")
            return
        self._busy = True
        self.status.set(f"Running {action_id}…")
        project_path = self.project_path.get()
        export_path = self.export_path.get()

        def worker() -> None:
            try:
                output = run_tool_action(
                    self._session,
                    action_id=action_id,
                    project_path=project_path,
                    export_path=export_path,
                    cli_path=self._cli_path,
                )
                message = output if len(output) <= 360 else output[:357] + "…"
            except CompanionMenuError as error:
                message = "Failed: " + str(error)
            self.root.after(0, lambda: self._finish_action(message))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_action(self, message: str) -> None:
        self._busy = False
        self.status.set(message)

    def run(self) -> None:
        self.root.mainloop()


def _parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--window-handle", type=int, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--executable")
    parser.add_argument("--version")
    parser.add_argument("--project-path", default="")
    parser.add_argument("--export-path", default="")
    parser.add_argument("--dcc-mcp-cli")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        session = build_companion_session(
            pid=args.pid,
            window_handle=args.window_handle,
            instance_id=args.instance_id,
            executable=args.executable,
            version=args.version,
        )
        cli_path = locate_dcc_mcp_cli(args.dcc_mcp_cli)
        application = CompanionMenuApplication(
            session,
            cli_path=cli_path,
            initial_project_path=args.project_path,
            initial_export_path=args.export_path,
        )
    except CompanionMenuError as error:
        print(json.dumps({"success": False, "error": str(error)}, separators=(",", ":")))
        raise SystemExit(2) from error
    application.run()


if __name__ == "__main__":
    main(sys.argv[1:])


__all__: Sequence[str] = [
    "CompanionAction",
    "CompanionMenuError",
    "CompanionSession",
    "CompanionMenuApplication",
    "arguments_for_action",
    "build_companion_session",
    "build_tool_command",
    "locate_dcc_mcp_cli",
    "main",
    "run_tool_action",
]
