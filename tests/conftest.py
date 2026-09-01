from pathlib import Path

import pytest


def tagged_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return b"\x0e" + len(encoded).to_bytes(4, "little") + encoded


@pytest.fixture
def synthetic_project(tmp_path: Path) -> Path:
    data = b"\x11" + tagged_string("app_id") + tagged_string("liquigen")
    data += tagged_string("app_version") + tagged_string("1.0.0")
    data += tagged_string("project_version") + b"\x05" + (7).to_bytes(8, "little")
    data += b"Node_Simulation Node_Scene Node_Camera Node_Render Node_Export_Image Flipbook"
    path = tmp_path / "splash.liquigen"
    path.write_bytes(data)
    return path


def write_png_header(path: Path, width: int, height: int) -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    return path
