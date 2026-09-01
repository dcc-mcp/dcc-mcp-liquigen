"""Generate a deterministic, transparent explosion flipbook for proxy-only UE tests.

This is deliberately synthetic test media. It must never be labelled as a LiquiGen export.
"""

from __future__ import annotations

import binascii
import math
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


def _pixel(frame: int, x: int, y: int, cell_size: int) -> tuple[int, int, int, int]:
    progress = frame / 63.0
    nx = (x + 0.5) / cell_size * 2.0 - 1.0
    ny = (y + 0.5) / cell_size * 2.0 - 1.0 + progress * 0.14
    theta = math.atan2(ny, nx)
    distance = math.hypot(nx, ny)

    radius = 0.20 + 0.58 * math.sin(min(1.0, progress * 1.15) * math.pi / 2.0)
    billow = 1.0 + 0.13 * math.sin(theta * 5.0 + frame * 0.31)
    billow += 0.07 * math.sin(theta * 9.0 - frame * 0.19)
    normalized = distance / max(0.001, radius * billow)
    if normalized >= 1.0:
        return 0, 0, 0, 0

    density = (1.0 - normalized * normalized) ** 1.7
    ring = math.exp(-((normalized - 0.68) / 0.22) ** 2)
    heat = (1.0 - progress) ** 1.45
    red = 48.0 + 190.0 * heat + 34.0 * ring
    green = 42.0 + 122.0 * heat + 58.0 * ring * heat
    blue = 36.0 + 30.0 * heat
    alpha = 255.0 * density * (1.0 - 0.55 * progress)
    return tuple(max(0, min(255, round(channel))) for channel in (red, green, blue, alpha))


def write_explosion_proxy_atlas(
    path: Path, columns: int = 8, rows: int = 8, cell_size: int = 128
) -> Path:
    """Write an RGBA PNG with 64 expanding fire-to-smoke proxy frames."""
    if columns != 8 or rows != 8:
        raise ValueError("the proxy generator currently requires an 8x8 atlas")
    if cell_size <= 0:
        raise ValueError("cell_size must be positive")
    width = columns * cell_size
    height = rows * cell_size
    scanlines = bytearray()
    for atlas_y in range(height):
        scanlines.append(0)
        tile_y, local_y = divmod(atlas_y, cell_size)
        for atlas_x in range(width):
            tile_x, local_x = divmod(atlas_x, cell_size)
            frame = tile_y * columns + tile_x
            scanlines.extend(_pixel(frame, local_x, local_y, cell_size))
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
        raise SystemExit("usage: generate_explosion_proxy_atlas.py <absolute-output.png>")
    target = Path(sys.argv[1]).expanduser().resolve()
    write_explosion_proxy_atlas(target)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
