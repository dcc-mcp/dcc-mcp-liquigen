"""Pure validation and layout helpers for the Unreal LiquiGen showcase."""

from __future__ import annotations

import re

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,63}$")


def game_asset_path(value: str) -> str:
    path = str(value).strip().replace("\\", "/").rstrip("/")
    if not path.startswith("/Game/") or ".." in path.split("/"):
        raise ValueError("asset path must be a normalized /Game/... path")
    return path


def asset_prefix(value: str) -> str:
    prefix = str(value).strip()
    if not _NAME.fullmatch(prefix):
        raise ValueError(
            "asset_prefix must start with a letter and contain only letters, digits, or underscores"
        )
    return prefix


def chain_config(count: int, delay_seconds: float, spacing_cm: float) -> dict[str, float | int]:
    count = int(count)
    delay_seconds = float(delay_seconds)
    spacing_cm = float(spacing_cm)
    if count < 2 or count > 12:
        raise ValueError("chain_count must be between 2 and 12")
    if delay_seconds < 0.05 or delay_seconds > 2.0:
        raise ValueError("delay_seconds must be between 0.05 and 2.0")
    if spacing_cm < 1.0 or spacing_cm > 5000.0:
        raise ValueError("spacing_cm must be between 1 and 5000")
    return {"count": count, "delay_seconds": delay_seconds, "spacing_cm": spacing_cm}


def effect_scale(value: float) -> float:
    scale = float(value)
    if scale < 0.1 or scale > 10.0:
        raise ValueError("effect_scale must be between 0.1 and 10.0")
    return scale


def blast_diameter(value: float) -> float:
    diameter = float(value)
    if diameter < 100.0 or diameter > 5000.0:
        raise ValueError("blast_diameter_cm must be between 100 and 5000")
    return diameter


def procedural_layer_specs(
    blast_diameter_cm: float,
) -> tuple[
    tuple[
        str,
        str,
        float,
        tuple[float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        float,
    ],
    ...,
]:
    """Scale the three Niagara layers from one explicit world-space diameter."""
    diameter = blast_diameter(blast_diameter_cm)
    return (
        (
            "Core",
            "core",
            0.55,
            (diameter * 0.62, diameter * 0.62),
            (diameter * 0.28, diameter * 0.28, diameter * 0.20),
            (0.0, 0.0, diameter * 0.15),
            1.0,
        ),
        (
            "Plume",
            "plume",
            1.15,
            (diameter * 0.46, diameter * 0.46),
            (diameter * 0.48, diameter * 0.48, diameter * 0.38),
            (0.0, 0.0, diameter * 0.42),
            1.4,
        ),
        (
            "Sparks",
            "sparks",
            0.90,
            (diameter * 0.06, diameter * 0.32),
            (diameter * 0.60, diameter * 0.58, diameter * 0.34),
            (diameter * 0.55, 0.0, diameter * 0.70),
            1.8,
        ),
    )


def chain_offsets(count: int, spacing_cm: float) -> list[tuple[float, float, float]]:
    config = chain_config(count, 0.18, spacing_cm)
    midpoint = (int(config["count"]) - 1) / 2.0
    spacing = float(config["spacing_cm"])
    return [
        (
            (stage - midpoint) * spacing,
            (1.0 if stage % 2 else -1.0) * spacing * 0.18,
            0.0,
        )
        for stage in range(int(config["count"]))
    ]


def water_cascade_offsets(
    count: int, spacing_cm: float, vertical_drop_cm: float
) -> list[tuple[float, float, float]]:
    """Lay out a descending, slightly staggered cascade from LiquiGen stage timing."""
    config = chain_config(count, 0.18, spacing_cm)
    vertical_drop = float(vertical_drop_cm)
    if vertical_drop < 25.0 or vertical_drop > 2000.0:
        raise ValueError("vertical_drop_cm must be between 25 and 2000")
    midpoint = (int(config["count"]) - 1) / 2.0
    spacing = float(config["spacing_cm"])
    return [
        (
            (stage - midpoint) * spacing,
            (1.0 if stage % 2 else -1.0) * spacing * 0.14,
            (int(config["count"]) - 1 - stage) * vertical_drop,
        )
        for stage in range(int(config["count"]))
    ]


def procedural_water_layer_specs(
    splash_diameter_cm: float,
) -> tuple[
    tuple[
        str,
        str,
        float,
        tuple[float, float],
        tuple[float, float, float],
        tuple[float, float, float],
        float,
    ],
    ...,
]:
    """Describe the sheet, foam, and droplet layers of one procedural splash."""
    diameter = blast_diameter(splash_diameter_cm)
    return (
        (
            "Sheet",
            "sheet",
            1.55,
            (diameter * 0.12, diameter * 0.42),
            (diameter * 0.12, diameter * 0.10, diameter * 0.06),
            (diameter * 0.12, 0.0, -diameter * 0.38),
            0.35,
        ),
        (
            "Foam",
            "foam",
            0.85,
            (diameter * 0.09, diameter * 0.09),
            (diameter * 0.20, diameter * 0.18, diameter * 0.06),
            (diameter * 0.28, 0.0, diameter * 0.48),
            0.65,
        ),
        (
            "Droplets",
            "droplets",
            1.10,
            (diameter * 0.025, diameter * 0.12),
            (diameter * 0.30, diameter * 0.28, diameter * 0.10),
            (diameter * 0.50, diameter * 0.08, diameter * 0.72),
            1.4,
        ),
    )
