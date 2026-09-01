from __future__ import annotations

import importlib.util
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "examples" / "ue58_receiver" / "generate_explosion_proxy_atlas.py"


def _generator_module():
    spec = importlib.util.spec_from_file_location("explosion_proxy_generator_test", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _decode_rgba_png(path: Path) -> tuple[int, int, bytes]:
    payload = path.read_bytes()
    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    compressed = bytearray()
    width = height = 0
    while offset < len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        data = payload[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height = struct.unpack(">II", data[:8])
        elif kind == b"IDAT":
            compressed.extend(data)
        elif kind == b"IEND":
            break
    rows = zlib.decompress(bytes(compressed))
    assert all(rows[y * (width * 4 + 1)] == 0 for y in range(height))
    pixels = b"".join(
        rows[y * (width * 4 + 1) + 1 : (y + 1) * (width * 4 + 1)] for y in range(height)
    )
    return width, height, pixels


def test_explosion_proxy_has_transparent_edges_and_evolving_core(tmp_path: Path) -> None:
    module = _generator_module()
    atlas = module.write_explosion_proxy_atlas(tmp_path / "explosion.png", cell_size=32)
    width, height, pixels = _decode_rgba_png(atlas)
    assert (width, height) == (256, 256)

    def rgba(x: int, y: int) -> tuple[int, int, int, int]:
        start = (y * width + x) * 4
        return tuple(pixels[start : start + 4])

    assert rgba(0, 0)[3] == 0
    early_core = rgba(16, 16)
    late_core = rgba(7 * 32 + 16, 7 * 32 + 16)
    assert early_core[3] > 200
    assert early_core[0] > early_core[2]
    assert late_core[3] > 20
    assert late_core[0] < early_core[0]
