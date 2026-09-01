"""Read-only PE probe for named LiquiGen implementation surfaces.

This is a development aid, not a runtime injector.  It locates literal names,
pointer-table references, code references, and the enclosing Windows unwind
range so an integration profile can be researched without hashing the binary.
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
    rva_start: int
    rva_end: int


def _sections(pe: pefile.PE) -> list[Section]:
    result = []
    for item in pe.sections:
        name = item.Name.rstrip(b"\0").decode("ascii", errors="replace")
        raw_start = int(item.PointerToRawData)
        raw_size = int(item.SizeOfRawData)
        rva_start = int(item.VirtualAddress)
        virtual_size = max(int(item.Misc_VirtualSize), raw_size)
        result.append(
            Section(name, raw_start, raw_start + raw_size, rva_start, rva_start + virtual_size)
        )
    return result


def _raw_to_va(offset: int, image_base: int, sections: list[Section]) -> int:
    for section in sections:
        if section.raw_start <= offset < section.raw_end:
            return image_base + section.rva_start + offset - section.raw_start
    raise ValueError(f"raw offset 0x{offset:x} is not mapped by a PE section")


def _va_to_raw(address: int, image_base: int, sections: list[Section]) -> int | None:
    rva = address - image_base
    for section in sections:
        if section.rva_start <= rva < section.rva_end:
            relative = rva - section.rva_start
            if relative < section.raw_end - section.raw_start:
                return section.raw_start + relative
    return None


def _runtime_range(pe: pefile.PE, address: int, image_base: int) -> tuple[int, int] | None:
    for entry in getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", ()):
        begin = image_base + int(entry.struct.BeginAddress)
        end = image_base + int(entry.struct.EndAddress)
        if begin <= address < end:
            return begin, end
    return None


def _print_pointer_context(
    data: bytes,
    pointer_offset: int,
    image_base: int,
    image_end: int,
    sections: list[Section],
) -> None:
    start = max(0, pointer_offset - 32)
    end = min(len(data), pointer_offset + 40)
    start -= start % 8
    print(f"    pointer-table context raw=0x{pointer_offset:x}")
    for cursor in range(start, end - 7, 8):
        value = struct.unpack_from("<Q", data, cursor)[0]
        classification = ""
        if image_base <= value < image_end:
            raw = _va_to_raw(value, image_base, sections)
            classification = f" image-va raw={None if raw is None else hex(raw)}"
        marker = " <reference>" if cursor == pointer_offset else ""
        print(f"      0x{cursor:08x}: 0x{value:016x}{classification}{marker}")


def probe(path: Path, names: list[str]) -> int:
    data = path.read_bytes()
    pe = pefile.PE(data=data, fast_load=False)
    pe.parse_data_directories()
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    image_end = image_base + int(pe.OPTIONAL_HEADER.SizeOfImage)
    sections = _sections(pe)
    text = next(item for item in sections if item.name == ".text")
    text_bytes = data[text.raw_start : text.raw_end]
    text_va = image_base + text.rva_start

    records: list[tuple[str, int, int, list[int]]] = []
    target_to_records: dict[int, list[int]] = {}
    for name in names:
        needle = name.encode("utf-8") + b"\0"
        offsets: list[int] = []
        cursor = 0
        while True:
            found = data.find(needle, cursor)
            if found < 0:
                break
            offsets.append(found)
            cursor = found + 1
        for offset in offsets:
            literal_va = _raw_to_va(offset, image_base, sections)
            pointer_bytes = struct.pack("<Q", literal_va)
            pointer_cursor = 0
            pointer_offsets: list[int] = []
            while True:
                pointer_found = data.find(pointer_bytes, pointer_cursor)
                if pointer_found < 0:
                    break
                pointer_offsets.append(pointer_found)
                pointer_cursor = pointer_found + 1
            record_index = len(records)
            records.append((name, offset, literal_va, pointer_offsets))
            target_to_records.setdefault(literal_va, []).append(record_index)
            for pointer_offset in pointer_offsets:
                pointer_va = _raw_to_va(pointer_offset, image_base, sections)
                target_to_records.setdefault(pointer_va, []).append(record_index)
                if pointer_offset >= 24:
                    location_va = _raw_to_va(pointer_offset - 24, image_base, sections)
                    target_to_records.setdefault(location_va, []).append(record_index)

    xrefs_by_record: list[list[tuple[int, str, str]]] = [[] for _ in records]
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    decoder.skipdata = True
    for instruction in decoder.disasm(text_bytes, text_va):
        if instruction.id == 0:
            continue
        for operand in instruction.operands:
            if operand.type != capstone.x86.X86_OP_MEM:
                continue
            memory = operand.mem
            if memory.base != capstone.x86.X86_REG_RIP:
                continue
            target = instruction.address + instruction.size + memory.disp
            for record_index in target_to_records.get(target, ()):
                xrefs_by_record[record_index].append(
                    (instruction.address, instruction.mnemonic, instruction.op_str)
                )

    found_names = {item[0] for item in records}
    for name in names:
        if name not in found_names:
            print(f"{name}: literals=0")
    for record_index, (name, offset, literal_va, pointer_offsets) in enumerate(records):
        print(f"{name}:")
        print(f"  literal raw=0x{offset:x} va=0x{literal_va:x}")
        print(f"    absolute-pointer-references={len(pointer_offsets)}")
        for pointer_offset in pointer_offsets[:8]:
            _print_pointer_context(data, pointer_offset, image_base, image_end, sections)
        xrefs = xrefs_by_record[record_index]
        print(f"    code-xrefs={len(xrefs)}")
        for address, mnemonic, operands in xrefs[:32]:
            runtime_range = _runtime_range(pe, address, image_base)
            range_text = (
                "none"
                if runtime_range is None
                else f"0x{runtime_range[0]:x}-0x{runtime_range[1]:x}"
            )
            print(f"      0x{address:x} {mnemonic} {operands}; unwind={range_text}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("names", nargs="+")
    arguments = parser.parse_args()
    return probe(arguments.executable.resolve(strict=True), arguments.names)


if __name__ == "__main__":
    raise SystemExit(main())
