"""Read-only probe for LiquiGen's named command registry.

The probe is intentionally bounded to one verified LiquiGen PID/HWND pair and
one known interface profile. It never writes process memory or invokes a
command. The output is development evidence for a future semantic command
bridge, not a supported JangaFX API.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from ctypes import wintypes


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_ALL = 0x03
MAX_COMMANDS = 4096
MAX_COMMAND_NAME_BYTES = 256

# LiquiGen 1.0.5 research profile. The executable hash is deliberately not part
# of the contract; the name, window ownership, structural probes, and function
# signature must all match at runtime.
GLOBAL_APP_STATE_RVA = 0x0182B3E0
COMMAND_PALETTE_OFFSET = 0x20
UI_CONTEXT_OFFSET = 0x18
TRIGGERED_COMMANDS_OFFSET = 0x188
COMMAND_REGISTRY_OFFSET = 0x18
COMMAND_TABLE_HEADER_OFFSET = 0x80
COMMAND_TABLE_COUNT_OFFSET = 0x88
DISPATCHER_RVA = 0x00197790
DISPATCHER_SIGNATURE = bytes.fromhex("41 56 56 57 53 48 81 EC C8 00 00 00")


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HMODULE),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
]
psapi.EnumProcessModulesEx.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD


class ProbeError(RuntimeError):
    """The target does not satisfy the bounded command-registry contract."""


class ProcessReader:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if not self.handle:
            raise ProbeError(f"OpenProcess failed: {ctypes.get_last_error()}")

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> ProcessReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def read(self, address: int, size: int) -> bytes:
        if address <= 0 or size <= 0 or size > 1024 * 1024:
            raise ProbeError("refusing an invalid or unbounded memory read")
        buffer = ctypes.create_string_buffer(size)
        completed = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
            self.handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(completed),
        ):
            raise ProbeError(
                f"ReadProcessMemory(0x{address:x}, {size}) failed: "
                f"{ctypes.get_last_error()}"
            )
        if completed.value != size:
            raise ProbeError(f"short memory read at 0x{address:x}")
        return buffer.raw

    def u64(self, address: int) -> int:
        return int.from_bytes(self.read(address, 8), "little")

    def image_path(self) -> str:
        buffer = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(
            self.handle, 0, buffer, ctypes.byref(length)
        ):
            raise ProbeError(f"QueryFullProcessImageNameW failed: {ctypes.get_last_error()}")
        return buffer.value

    def module_base(self) -> int:
        module = wintypes.HMODULE()
        needed = wintypes.DWORD()
        if not psapi.EnumProcessModulesEx(
            self.handle,
            ctypes.byref(module),
            ctypes.sizeof(module),
            ctypes.byref(needed),
            LIST_MODULES_ALL,
        ):
            raise ProbeError(f"EnumProcessModulesEx failed: {ctypes.get_last_error()}")
        if needed.value < ctypes.sizeof(module) or not module.value:
            raise ProbeError("target process has no readable main module")
        return int(module.value)


def _verify_window(pid: int, hwnd: int) -> int:
    owner_pid = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
    if not thread_id or owner_pid.value != pid:
        raise ProbeError("HWND does not belong to the requested PID")
    return int(thread_id)


def _checked_pointer(value: int, label: str) -> int:
    if value < 0x10000 or value > 0x00007FFFFFFFFFFF:
        raise ProbeError(f"{label} pointer is not a canonical user address")
    return value


def _decode_triggered_commands(reader: ProcessReader, ui_context: int) -> list[str]:
    map_address = ui_context + TRIGGERED_COMMANDS_OFFSET
    header = reader.u64(map_address)
    if not header:
        return []
    capacity = 1 << (header & 0x3F)
    if capacity <= 0 or capacity > MAX_COMMANDS:
        raise ProbeError("triggered-command map has an invalid capacity")
    table_base = _checked_pointer(header & ~0x3F, "triggered-command table")
    control_base = table_base + capacity * 24
    names = []
    for index in range(capacity):
        if reader.u64(control_base + index * 8) == 0:
            continue
        string_pointer = reader.u64(table_base + index * 16)
        string_length = reader.u64(table_base + index * 16 + 8)
        if not 0 < string_length <= MAX_COMMAND_NAME_BYTES:
            continue
        try:
            names.append(reader.read(string_pointer, string_length).decode("utf-8"))
        except (ProbeError, UnicodeError):
            continue
    return sorted(names)


def probe(pid: int, hwnd: int, diagnostics: bool = False) -> dict[str, object]:
    thread_id = _verify_window(pid, hwnd)
    with ProcessReader(pid) as reader:
        image_path = reader.image_path()
        if os.path.basename(image_path).casefold() != "liquigen.exe":
            raise ProbeError("target executable is not LiquiGen.exe")
        module_base = reader.module_base()
        signature = reader.read(module_base + DISPATCHER_RVA, len(DISPATCHER_SIGNATURE))
        if signature != DISPATCHER_SIGNATURE:
            raise ProbeError("semantic command dispatcher signature does not match this profile")

        app_state = _checked_pointer(
            reader.u64(module_base + GLOBAL_APP_STATE_RVA), "application state"
        )
        palette_state = _checked_pointer(
            reader.u64(app_state + COMMAND_PALETTE_OFFSET), "command palette state"
        )
        ui_context = _checked_pointer(reader.u64(app_state + UI_CONTEXT_OFFSET), "UI context")
        registry = palette_state + COMMAND_REGISTRY_OFFSET
        header = reader.u64(registry + COMMAND_TABLE_HEADER_OFFSET)
        count = reader.u64(registry + COMMAND_TABLE_COUNT_OFFSET)
        exponent = header & 0x3F
        capacity = 0 if header == 0 else 1 << exponent
        table_base = header & ~0x3F
        if diagnostics:
            print(
                json.dumps(
                    {
                        "module_base": hex(module_base),
                        "app_state": hex(app_state),
                        "palette_state": hex(palette_state),
                        "ui_context": hex(ui_context),
                        "registry": hex(registry),
                        "table_header": hex(header),
                        "table_count": count,
                        "palette_qwords": [
                            hex(reader.u64(palette_state + offset))
                            for offset in range(0, 0x120, 8)
                        ],
                        "triggered_commands_header": hex(
                            reader.u64(ui_context + TRIGGERED_COMMANDS_OFFSET)
                        ),
                        "triggered_commands_count": reader.u64(
                            ui_context + TRIGGERED_COMMANDS_OFFSET + 8
                        ),
                        "triggered_commands": _decode_triggered_commands(
                            reader, ui_context
                        ),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        if header == 0 and count == 0:
            capacity = 0
            commands = []
        elif capacity <= 0 or capacity > MAX_COMMANDS or count > capacity:
            raise ProbeError(
                f"command table shape is invalid: count={count}, capacity={capacity}"
            )
        else:
            _checked_pointer(table_base, "command table")

            key_base = table_base
            value_base = table_base + capacity * 16
            control_base = value_base + capacity * 32
            commands = []
            for index in range(capacity):
                control = reader.u64(control_base + index * 8)
                if control == 0:
                    continue
                string_pointer = reader.u64(key_base + index * 16)
                string_length = reader.u64(key_base + index * 16 + 8)
                if not 0 < string_length <= MAX_COMMAND_NAME_BYTES:
                    continue
                try:
                    name = reader.read(string_pointer, string_length).decode("utf-8")
                except (ProbeError, UnicodeError):
                    continue
                callback_context = reader.u64(value_base + index * 32 + 16)
                callback = reader.u64(value_base + index * 32 + 24)
                if not callback:
                    continue
                commands.append(
                    {
                        "name": name,
                        "callback_in_main_module": (
                            module_base <= callback < module_base + 0x2000000
                        ),
                        "has_context": bool(callback_context),
                    }
                )
        triggered_commands = _decode_triggered_commands(reader, ui_context)

    commands.sort(key=lambda item: str(item["name"]))
    if len(commands) != count:
        raise ProbeError(
            f"decoded command count does not match table count: {len(commands)} != {count}"
        )
    return {
        "interface": "liquigen.host.command-surface.probe.v1",
        "pid": pid,
        "hwnd": hwnd,
        "ui_thread_id": thread_id,
        "image_name": os.path.basename(image_path),
        "profile": "liquigen-1.0.5-command-registry-v1",
        "hash_required": False,
        "registry_initialized": capacity > 0,
        "command_count": count,
        "commands": commands,
        "triggered_commands": triggered_commands,
        "read_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--hwnd", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--diagnostics", action="store_true")
    arguments = parser.parse_args()
    print(
        json.dumps(
            probe(arguments.pid, arguments.hwnd, diagnostics=arguments.diagnostics),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
