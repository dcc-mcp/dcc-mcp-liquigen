"""Disassemble one PE64 unwind range and locate direct code references.

This is a read-only development aid for researching named LiquiGen interfaces.
It deliberately operates on the file image and never attaches to a process.
"""

from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path

import capstone
import pefile


@dataclass(frozen=True)
class Section:
    name: str
    raw_start: int
    raw_end: int
    va_start: int
    va_end: int


def _sections(pe: pefile.PE) -> list[Section]:
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    result = []
    for item in pe.sections:
        raw_start = int(item.PointerToRawData)
        raw_size = int(item.SizeOfRawData)
        virtual_size = max(int(item.Misc_VirtualSize), raw_size)
        va_start = image_base + int(item.VirtualAddress)
        result.append(
            Section(
                item.Name.rstrip(b"\0").decode("ascii", errors="replace"),
                raw_start,
                raw_start + raw_size,
                va_start,
                va_start + virtual_size,
            )
        )
    return result


def _va_to_raw(address: int, sections: list[Section]) -> int | None:
    for section in sections:
        if section.va_start <= address < section.va_end:
            relative = address - section.va_start
            if relative < section.raw_end - section.raw_start:
                return section.raw_start + relative
    return None


def _section_name(address: int, sections: list[Section]) -> str:
    for section in sections:
        if section.va_start <= address < section.va_end:
            return section.name
    return "unmapped"


def _runtime_range(pe: pefile.PE, address: int) -> tuple[int, int]:
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    for entry in getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", ()):
        begin = image_base + int(entry.struct.BeginAddress)
        end = image_base + int(entry.struct.EndAddress)
        if begin <= address < end:
            return begin, end
    raise ValueError(f"address 0x{address:x} is not covered by a PE unwind range")


def _decoder() -> capstone.Cs:
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    return decoder


def _annotation(
    instruction: capstone.CsInsn,
    data: bytes,
    sections: list[Section],
) -> str:
    annotations = []
    for operand in instruction.operands:
        target: int | None = None
        if operand.type == capstone.x86.X86_OP_IMM:
            value = int(operand.imm)
            if value >= 0x10000:
                target = value
        elif operand.type == capstone.x86.X86_OP_MEM:
            memory = operand.mem
            if memory.base == capstone.x86.X86_REG_RIP:
                target = instruction.address + instruction.size + memory.disp
        if target is None:
            continue
        section = _section_name(target, sections)
        detail = f"0x{target:x} [{section}]"
        raw = _va_to_raw(target, sections)
        if raw is not None and raw + 8 <= len(data):
            value = struct.unpack_from("<Q", data, raw)[0]
            value_section = _section_name(value, sections)
            if value_section != "unmapped":
                detail += f" -> 0x{value:x} [{value_section}]"
        annotations.append(detail)
    return "; ".join(dict.fromkeys(annotations))


def _direct_xrefs(
    decoder: capstone.Cs,
    text_bytes: bytes,
    text_va: int,
    target: int,
    pe: pefile.PE,
) -> list[tuple[int, str, str, tuple[int, int]]]:
    result = []
    for instruction in decoder.disasm(text_bytes, text_va):
        if instruction.mnemonic not in {"call", "jmp"} or not instruction.operands:
            continue
        operand = instruction.operands[0]
        if operand.type != capstone.x86.X86_OP_IMM or int(operand.imm) != target:
            continue
        result.append(
            (
                instruction.address,
                instruction.mnemonic,
                instruction.op_str,
                _runtime_range(pe, instruction.address),
            )
        )
    return result


def inspect(
    path: Path,
    address: int,
    show_xrefs: bool,
    only_xrefs: bool,
    fallback_length: int,
) -> int:
    data = path.read_bytes()
    pe = pefile.PE(data=data, fast_load=False)
    pe.parse_data_directories()
    sections = _sections(pe)
    try:
        begin, end = _runtime_range(pe, address)
    except ValueError:
        if fallback_length <= 0:
            raise
        begin, end = address, address + fallback_length
    begin_raw = _va_to_raw(begin, sections)
    if begin_raw is None:
        raise ValueError(f"function start 0x{begin:x} is not file-backed")
    code = data[begin_raw : begin_raw + end - begin]
    decoder = _decoder()

    if not only_xrefs:
        print(f"function=0x{begin:x}-0x{end:x} selected=0x{address:x}")
        for instruction in decoder.disasm(code, begin):
            marker = "=>" if instruction.address == address else "  "
            annotation = _annotation(instruction, data, sections)
            suffix = f" ; {annotation}" if annotation else ""
            print(
                f"{marker} 0x{instruction.address:016x}  "
                f"{instruction.mnemonic:<8} {instruction.op_str}{suffix}"
            )

    if show_xrefs:
        text = next(section for section in sections if section.name == ".text")
        text_bytes = data[text.raw_start : text.raw_end]
        print("direct-xrefs:")
        for xref, mnemonic, operands, runtime_range in _direct_xrefs(
            decoder, text_bytes, text.va_start, address, pe
        ):
            print(
                f"  0x{xref:x} {mnemonic} {operands}; "
                f"unwind=0x{runtime_range[0]:x}-0x{runtime_range[1]:x}"
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("address", type=lambda value: int(value, 0))
    parser.add_argument("--xrefs", action="store_true")
    parser.add_argument("--only-xrefs", action="store_true")
    parser.add_argument("--length", type=lambda value: int(value, 0), default=0)
    arguments = parser.parse_args()
    if arguments.only_xrefs:
        arguments.xrefs = True
    return inspect(
        arguments.executable.resolve(strict=True),
        arguments.address,
        arguments.xrefs,
        arguments.only_xrefs,
        arguments.length,
    )


if __name__ == "__main__":
    raise SystemExit(main())
