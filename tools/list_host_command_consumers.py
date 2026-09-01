"""List statically discoverable LiquiGen named-command consumer call sites.

This read-only development aid resolves the common ``lea rdx, <OdinString>``
sequence before LiquiGen's named-command consumer.  It is deliberately scoped
to PE file inspection and never attaches to a running process.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import capstone
import pefile


def _raw_offset(pe: pefile.PE, address: int) -> int | None:
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    rva = address - image_base
    for section in pe.sections:
        begin = int(section.VirtualAddress)
        size = max(int(section.Misc_VirtualSize), int(section.SizeOfRawData))
        if begin <= rva < begin + size:
            relative = rva - begin
            if relative < int(section.SizeOfRawData):
                return int(section.PointerToRawData) + relative
    return None


def _odin_string(data: bytes, pe: pefile.PE, address: int) -> str | None:
    raw = _raw_offset(pe, address)
    if raw is None or raw + 16 > len(data):
        return None
    pointer, size = struct.unpack_from("<QQ", data, raw)
    string_raw = _raw_offset(pe, pointer)
    if string_raw is None or size == 0 or size > 256 or string_raw + size > len(data):
        return None
    value = data[string_raw : string_raw + size]
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def inspect(path: Path, consumer: int) -> int:
    data = path.read_bytes()
    pe = pefile.PE(data=data, fast_load=False)
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    text = next(section for section in pe.sections if section.Name.rstrip(b"\0") == b".text")
    raw_start = int(text.PointerToRawData)
    raw_size = int(text.SizeOfRawData)
    text_address = image_base + int(text.VirtualAddress)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    decoder.skipdata = True
    recent: list[capstone.CsInsn] = []
    for instruction in decoder.disasm(data[raw_start : raw_start + raw_size], text_address):
        if instruction.id == 0:
            recent.clear()
            continue
        if (
            instruction.mnemonic == "call"
            and instruction.operands
            and instruction.operands[0].type == capstone.x86.X86_OP_IMM
            and int(instruction.operands[0].imm) == consumer
        ):
            resolved = None
            source_address = None
            for candidate in reversed(recent[-12:]):
                if candidate.mnemonic != "lea" or len(candidate.operands) != 2:
                    continue
                destination, source = candidate.operands
                if (
                    destination.type == capstone.x86.X86_OP_REG
                    and destination.reg == capstone.x86.X86_REG_RDX
                    and source.type == capstone.x86.X86_OP_MEM
                    and source.mem.base == capstone.x86.X86_REG_RIP
                ):
                    source_address = candidate.address + candidate.size + source.mem.disp
                    resolved = _odin_string(data, pe, source_address)
                    break
            label = resolved if resolved is not None else "<dynamic>"
            source = f"0x{source_address:x}" if source_address is not None else "-"
            print(f"0x{instruction.address:x}\t{source}\t{label}")
        recent.append(instruction)
        if len(recent) > 16:
            recent.pop(0)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--consumer", type=lambda value: int(value, 0), default=0x140076400)
    arguments = parser.parse_args()
    return inspect(arguments.executable.resolve(strict=True), arguments.consumer)


if __name__ == "__main__":
    raise SystemExit(main())
