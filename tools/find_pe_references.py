"""Locate direct and RIP-relative references to selected PE64 addresses."""

from __future__ import annotations

import argparse
from pathlib import Path

import capstone
import pefile


def _runtime_range(pe: pefile.PE, address: int, image_base: int) -> str:
    for entry in getattr(pe, "DIRECTORY_ENTRY_EXCEPTION", ()):
        begin = image_base + int(entry.struct.BeginAddress)
        end = image_base + int(entry.struct.EndAddress)
        if begin <= address < end:
            return f"0x{begin:x}-0x{end:x}"
    return "none"


def find_references(path: Path, targets: list[int]) -> int:
    data = path.read_bytes()
    pe = pefile.PE(data=data, fast_load=False)
    pe.parse_data_directories()
    image_base = int(pe.OPTIONAL_HEADER.ImageBase)
    text = next(
        section
        for section in pe.sections
        if section.Name.rstrip(b"\0").decode("ascii", errors="replace") == ".text"
    )
    raw_start = int(text.PointerToRawData)
    raw_size = int(text.SizeOfRawData)
    text_bytes = data[raw_start : raw_start + raw_size]
    text_va = image_base + int(text.VirtualAddress)
    target_set = set(targets)
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    decoder.skipdata = True
    references: dict[int, list[tuple[int, str, str]]] = {target: [] for target in targets}
    for instruction in decoder.disasm(text_bytes, text_va):
        if instruction.id == 0:
            continue
        resolved = set()
        for operand in instruction.operands:
            if operand.type == capstone.x86.X86_OP_IMM:
                resolved.add(int(operand.imm))
            elif (
                operand.type == capstone.x86.X86_OP_MEM
                and operand.mem.base == capstone.x86.X86_REG_RIP
            ):
                resolved.add(instruction.address + instruction.size + operand.mem.disp)
        for target in target_set.intersection(resolved):
            references[target].append(
                (instruction.address, instruction.mnemonic, instruction.op_str)
            )
    for target in targets:
        print(f"0x{target:x}:")
        for address, mnemonic, operands in references[target]:
            print(
                f"  0x{address:x} {mnemonic} {operands}; "
                f"unwind={_runtime_range(pe, address, image_base)}"
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("addresses", nargs="+", type=lambda value: int(value, 0))
    arguments = parser.parse_args()
    return find_references(arguments.executable.resolve(strict=True), arguments.addresses)


if __name__ == "__main__":
    raise SystemExit(main())
