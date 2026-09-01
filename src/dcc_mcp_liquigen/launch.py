"""Lightbox-friendly launcher for one licensed LiquiGen instance."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path
from typing import Optional, Sequence

from .runtime import process_is_alive
from .server import start_server, stop_server


class LiquiGenLaunchError(RuntimeError):
    """LiquiGen could not be started or its exact top-level window was not found."""


def _find_main_window(pid: int) -> int:
    if os.name != "nt":
        raise LiquiGenLaunchError("automatic window discovery is only supported on Windows")
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    found: list[int] = []

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        owner = wintypes.DWORD()
        if user32.IsWindowVisible(hwnd) and user32.GetWindowThreadProcessId(
            hwnd, ctypes.byref(owner)
        ):
            if int(owner.value) == pid:
                found.append(int(hwnd))
                return False
        return True

    user32.EnumWindows(callback, 0)
    if not found:
        raise LiquiGenLaunchError("LiquiGen top-level window was not found")
    return found[0]


def launch_and_start_server(
    executable: str,
    *,
    hook_dll: Optional[str] = None,
    version: Optional[str] = None,
    allowed_roots: Sequence[str] = (),
    wait_seconds: float = 30.0,
    port: Optional[int] = None,
) -> int:
    """Start LiquiGen, bind its exact PID/HWND, and run the adapter until exit."""
    path = Path(executable).expanduser().resolve(strict=True)
    if path.name.casefold() != "liquigen.exe":
        raise LiquiGenLaunchError("executable must be LiquiGen.exe")
    child_environment = os.environ.copy()
    if hook_dll:
        hook = Path(hook_dll).expanduser().resolve(strict=True)
        if hook.suffix.casefold() != ".dll" or not hook.is_file():
            raise LiquiGenLaunchError("hook_dll must be an existing DLL file")
        child_environment["DCC_MCP_LIQUIGEN_COMMAND_HOOK_DLL"] = str(hook)
        os.environ["DCC_MCP_LIQUIGEN_COMMAND_HOOK_DLL"] = str(hook)
    process = subprocess.Popen([str(path)], close_fds=True, env=child_environment)
    try:
        deadline = time.monotonic() + max(1.0, wait_seconds)
        hwnd = 0
        while time.monotonic() < deadline and process_is_alive(process.pid):
            try:
                hwnd = _find_main_window(process.pid)
                break
            except LiquiGenLaunchError:
                time.sleep(0.25)
        if not hwnd:
            raise LiquiGenLaunchError("LiquiGen started but its main window was not ready")
        if allowed_roots:
            os.environ["DCC_MCP_LIQUIGEN_ALLOWED_ROOTS"] = os.pathsep.join(
                str(Path(root).expanduser().resolve(strict=True)) for root in allowed_roots
            )
        start_server(
            dcc_pid=process.pid,
            dcc_window_handle=hwnd,
            executable=str(path),
            dcc_version=version,
            port=port,
        )
        process.wait()
        return process.returncode or 0
    finally:
        stop_server()


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--hook-dll")
    parser.add_argument("--version")
    parser.add_argument("--allowed-root", action="append", default=[])
    parser.add_argument("--wait-seconds", type=float, default=30.0)
    parser.add_argument("--port", type=int)
    args = parser.parse_args(list(argv) if argv is not None else None)
    raise SystemExit(
        launch_and_start_server(
            args.executable,
            hook_dll=args.hook_dll,
            version=args.version,
            allowed_roots=args.allowed_root,
            wait_seconds=args.wait_seconds,
            port=args.port,
        )
    )


__all__ = ["LiquiGenLaunchError", "launch_and_start_server", "main"]
