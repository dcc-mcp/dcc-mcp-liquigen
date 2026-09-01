"""Exact LiquiGen process/window identity checks."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Protocol


class LiquiGenRuntimeError(RuntimeError):
    """The requested LiquiGen runtime binding is absent or has drifted."""


@dataclass(frozen=True)
class RuntimeBinding:
    pid: int
    window_handle: int
    executable: str
    version: str
    title: str = "LiquiGen"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _windows_process_path(pid: int) -> Path:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        raise LiquiGenRuntimeError("LiquiGen PID is not live or cannot be inspected")
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            raise LiquiGenRuntimeError("LiquiGen executable identity could not be read")
        return Path(buffer.value).resolve()
    finally:
        kernel32.CloseHandle(handle)


def process_path(pid: int) -> Path:
    if pid <= 0:
        raise LiquiGenRuntimeError("LiquiGen PID must be positive")
    if os.name == "nt":
        return _windows_process_path(pid)
    proc = Path("/proc") / str(pid) / "exe"
    try:
        return proc.resolve(strict=True)
    except OSError as error:
        raise LiquiGenRuntimeError("LiquiGen PID is not live or cannot be inspected") from error


def _validate_window_owner(pid: int, window_handle: int) -> None:
    if window_handle <= 0:
        raise LiquiGenRuntimeError("LiquiGen native window handle must be positive")
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    hwnd = wintypes.HWND(window_handle)
    if not user32.IsWindow(hwnd):
        raise LiquiGenRuntimeError("LiquiGen HWND is not a live native window")
    owner = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    if int(owner.value) != pid:
        raise LiquiGenRuntimeError("LiquiGen HWND is owned by a different process")


def _window_title(pid: int, window_handle: int) -> str:
    _validate_window_owner(pid, window_handle)
    if os.name != "nt":
        return "LiquiGen"
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    hwnd = wintypes.HWND(window_handle)
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return "LiquiGen"
    buffer = ctypes.create_unicode_buffer(length + 1)
    if user32.GetWindowTextW(hwnd, buffer, len(buffer)) <= 0:
        raise LiquiGenRuntimeError("LiquiGen HWND title could not be read")
    return buffer.value


class RuntimeInspector(Protocol):
    """Operating-system boundary used to bind one exact LiquiGen window."""

    def process_path(self, pid: int) -> Path: ...

    def window_title(self, pid: int, window_handle: int) -> str: ...


class _NativeRuntimeInspector:
    def process_path(self, pid: int) -> Path:
        return process_path(pid)

    def window_title(self, pid: int, window_handle: int) -> str:
        return _window_title(pid, window_handle)


def detect_version(executable: Path, explicit: Optional[str] = None) -> str:
    selected = (explicit or os.environ.get("DCC_MCP_LIQUIGEN_VERSION", "")).strip()
    if selected:
        return selected
    match = re.search(r"(?i)[\\/]liquigen[\\/](\d+\.\d+\.\d+)(?:[\\/]|$)", str(executable))
    if match:
        return match.group(1)
    for parent in executable.parents:
        package_file = parent / "package.py"
        if not package_file.is_file() or package_file.stat().st_size > 1024 * 1024:
            continue
        try:
            text = package_file.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeError):
            continue
        match = re.search(r"(?m)^version\s*=\s*['\"]([^'\"]+)['\"]", text)
        if match:
            return match.group(1)
    return "unknown"


def bind_runtime(
    pid: int,
    window_handle: int,
    executable: Optional[str] = None,
    version: Optional[str] = None,
    title: Optional[str] = None,
    inspector: Optional[RuntimeInspector] = None,
) -> RuntimeBinding:
    native = inspector or _NativeRuntimeInspector()
    actual = native.process_path(int(pid))
    if executable:
        expected = Path(executable).expanduser().resolve(strict=True)
        if os.path.normcase(str(expected)) != os.path.normcase(str(actual)):
            raise LiquiGenRuntimeError("LiquiGen PID executable does not match the requested path")
    if actual.name.casefold() not in {"liquigen", "liquigen.exe"}:
        raise LiquiGenRuntimeError("Bound process is not the LiquiGen executable")
    resolved_title = (title or "").strip() or native.window_title(int(pid), int(window_handle))
    return RuntimeBinding(
        pid=int(pid),
        window_handle=int(window_handle),
        executable=str(actual),
        version=detect_version(actual, version),
        title=resolved_title,
    )


def runtime_from_env() -> RuntimeBinding:
    try:
        pid = int(os.environ["DCC_MCP_LIQUIGEN_PID"])
        hwnd = int(os.environ["DCC_MCP_LIQUIGEN_WINDOW_HANDLE"])
    except (KeyError, ValueError) as error:
        raise LiquiGenRuntimeError(
            "DCC_MCP_LIQUIGEN_PID and DCC_MCP_LIQUIGEN_WINDOW_HANDLE are required"
        ) from error
    return bind_runtime(
        pid,
        hwnd,
        os.environ.get("DCC_MCP_LIQUIGEN_EXECUTABLE"),
        os.environ.get("DCC_MCP_LIQUIGEN_VERSION"),
    )


def process_is_alive(pid: int) -> bool:
    try:
        process_path(pid)
    except LiquiGenRuntimeError:
        return False
    return True


__all__ = [
    "LiquiGenRuntimeError",
    "RuntimeBinding",
    "RuntimeInspector",
    "bind_runtime",
    "process_is_alive",
    "runtime_from_env",
]
