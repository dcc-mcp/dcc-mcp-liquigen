"""Generate an explicit smoke-only PNG atlas for the UE receiver test."""

from __future__ import annotations

import binascii
import struct
import sys
import zlib
from pathlib import Path


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_smoke_atlas(path: Path, columns: int = 8, rows: int = 8, cell_size: int = 16) -> Path:
    """Write a valid RGBA PNG whose tile colors make grid orientation visible."""
    if columns <= 0 or rows <= 0 or cell_size <= 0:
        raise ValueError("columns, rows, and cell_size must be positive")
    width = columns * cell_size
    height = rows * cell_size
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)
        tile_y = y // cell_size
        for x in range(width):
            tile_x = x // cell_size
            local_x = x % cell_size
            local_y = y % cell_size
            border = local_x in {0, cell_size - 1} or local_y in {0, cell_size - 1}
            red = (tile_x * 31) % 256
            green = (tile_y * 31) % 256
            blue = ((tile_y * columns + tile_x) * 17) % 256
            alpha = 255 if border else 180
            scanlines.extend((red, green, blue, alpha))
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9))
        + _chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: generate_smoke_atlas.py <absolute-output.png>")
    target = Path(sys.argv[1]).expanduser().resolve()
    write_smoke_atlas(target)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
