"""Validate bounded LiquiGen output bundles for Unreal handoff."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Optional, Sequence

from .project import allowed_roots_from_env

MAX_EXPORT_FILES = 512
MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024
_IMAGE_SUFFIXES = {".png", ".tga", ".exr"}
_OPENVDB_MAGIC = (0x56444220).to_bytes(4, "little")


class LiquiGenExportError(RuntimeError):
    """An export bundle violates the bounded UE handoff contract."""


def _within(path: Path, roots: Sequence[Path]) -> bool:
    candidate = os.path.normcase(str(path))
    for root in roots:
        normalized = os.path.normcase(str(root))
        try:
            if os.path.commonpath((candidate, normalized)) == normalized:
                return True
        except ValueError:
            continue
    return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_dimensions(path: Path) -> Optional[tuple[int, int]]:
    with path.open("rb") as stream:
        header = stream.read(32)
    if path.suffix.casefold() == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(header) < 24 or header[12:16] != b"IHDR":
            raise LiquiGenExportError("PNG export has no valid IHDR header")
        return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    if path.suffix.casefold() == ".tga" and len(header) >= 16:
        return int.from_bytes(header[12:14], "little"), int.from_bytes(header[14:16], "little")
    if path.suffix.casefold() == ".exr":
        if not header.startswith(b"v/1\x01"):
            raise LiquiGenExportError("EXR export has an invalid magic header")
        return None
    return None


def _validate_openvdb_header(path: Path) -> None:
    with path.open("rb") as stream:
        if stream.read(4) != _OPENVDB_MAGIC:
            raise LiquiGenExportError(
                "VDB export has an invalid OpenVDB magic header: " + path.name
            )


def _vat_number(metadata: dict[str, object], key: str) -> float:
    value = metadata.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LiquiGenExportError(f"VAT metadata field is not numeric: {key}")
    result = float(value)
    if not math.isfinite(result):
        raise LiquiGenExportError(f"VAT metadata field is not finite: {key}")
    return result


def _canonical_vat_contract(files: Sequence[Path], base: Path) -> Optional[dict[str, object]]:
    info_files = [item for item in files if item.name.casefold().endswith("_info.json")]
    if not info_files:
        return None
    if len(info_files) != 1:
        raise LiquiGenExportError("VAT bundle must contain exactly one *_info.json file")
    info = info_files[0]
    try:
        payload = json.loads(info.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LiquiGenExportError("VAT metadata is not valid UTF-8 JSON: " + info.name) from error
    if isinstance(payload, list) and len(payload) == 1:
        metadata = payload[0]
    else:
        metadata = payload
    if not isinstance(metadata, dict):
        raise LiquiGenExportError("VAT metadata must contain one object")

    stem = info.name[: -len("_info.json")]
    expected = {
        "geometry": f"{stem}.fbx",
        "info": info.name,
        "lookup": f"{stem}_lookup.exr",
        "position": f"{stem}_pos.exr",
        "rotation": f"{stem}_rot.exr",
    }
    available = {item.name.casefold(): item for item in files}
    missing = [name for name in expected.values() if name.casefold() not in available]
    if missing:
        raise LiquiGenExportError("VAT bundle is missing canonical files: " + ", ".join(missing))

    axis_system = metadata.get("Axis System")
    frame_count = metadata.get("Frame Count")
    source_fps = _vat_number(metadata, "Houdini FPS")
    raw_two_position_textures = metadata.get("Two Position Textures")
    if not isinstance(axis_system, str) or not axis_system.strip():
        raise LiquiGenExportError("VAT metadata field is invalid: Axis System")
    if isinstance(frame_count, bool) or not isinstance(frame_count, int) or frame_count <= 0:
        raise LiquiGenExportError("VAT metadata field is invalid: Frame Count")
    if source_fps <= 0:
        raise LiquiGenExportError("VAT metadata field is invalid: Houdini FPS")
    if isinstance(raw_two_position_textures, bool):
        two_position_textures = raw_two_position_textures
    elif isinstance(raw_two_position_textures, int) and raw_two_position_textures in {0, 1}:
        two_position_textures = bool(raw_two_position_textures)
    else:
        raise LiquiGenExportError("VAT metadata field is invalid: Two Position Textures")

    return {
        "axis_system": axis_system,
        "bounds_min": [
            _vat_number(metadata, "Bound Min X"),
            _vat_number(metadata, "Bound Min Y"),
            _vat_number(metadata, "Bound Min Z"),
        ],
        "bounds_max": [
            _vat_number(metadata, "Bound Max X"),
            _vat_number(metadata, "Bound Max Y"),
            _vat_number(metadata, "Bound Max Z"),
        ],
        "frame_count": frame_count,
        "source_fps": source_fps,
        "two_position_textures": two_position_textures,
        "assets": {
            role: available[name.casefold()].relative_to(base).as_posix()
            for role, name in expected.items()
        },
    }


def validate_unreal_export_bundle(
    path: str,
    columns: Optional[int] = None,
    rows: Optional[int] = None,
    roots: Optional[Sequence[Path]] = None,
) -> dict[str, object]:
    selected_roots = tuple(roots or allowed_roots_from_env())
    raw = Path(path).expanduser()
    if raw.is_symlink():
        raise LiquiGenExportError("export path must not be a symbolic link")
    try:
        target = raw.resolve(strict=True)
    except OSError as error:
        raise LiquiGenExportError("export path does not exist") from error
    if not _within(target, selected_roots):
        raise LiquiGenExportError("export path is outside configured allowed roots")
    if target.is_file():
        files = [target]
        base = target.parent
    elif target.is_dir():
        base = target
        files = []
        for item in sorted(target.rglob("*")):
            if item.is_symlink():
                raise LiquiGenExportError("export bundle must not contain links")
            if item.is_file():
                files.append(item)
                if len(files) > MAX_EXPORT_FILES:
                    raise LiquiGenExportError("export bundle exceeds the file-count limit")
    else:
        raise LiquiGenExportError("export path must be a file or directory")
    if not files:
        raise LiquiGenExportError("export bundle is empty")

    total_bytes = 0
    entries = []
    suffixes = set()
    for item in files:
        size = item.stat().st_size
        if size <= 0:
            raise LiquiGenExportError("export bundle contains an empty file")
        total_bytes += size
        if total_bytes > MAX_EXPORT_BYTES:
            raise LiquiGenExportError("export bundle exceeds the byte limit")
        suffixes.add(item.suffix.casefold())
        entries.append(
            {
                "path": item.relative_to(base).as_posix(),
                "bytes": size,
                "sha256": _sha256(item),
            }
        )

    images = [item for item in files if item.suffix.casefold() in _IMAGE_SUFFIXES]
    metadata_files = [item for item in files if item.suffix.casefold() == ".json"]
    errors: list[str] = []
    warnings: list[str] = []
    vat = None
    vdb_files = [item for item in files if item.suffix.casefold() == ".vdb"]
    if vdb_files and suffixes == {".vdb"}:
        bundle_type = "openvdb_sequence"
        warnings.append(
            "LiquiGen VDB exports contain velocity fields; treat this bundle as auxiliary "
            "data, not the primary liquid surface renderer"
        )
        for vdb_file in vdb_files:
            try:
                _validate_openvdb_header(vdb_file)
            except LiquiGenExportError as error:
                errors.append(str(error))
    elif ".fbx" in suffixes and images and metadata_files:
        bundle_type = "liquigen_vat"
        try:
            vat = _canonical_vat_contract(files, base)
        except LiquiGenExportError as error:
            errors.append(str(error))
        if vat is None:
            warnings.append(
                "VAT bundle uses a non-canonical metadata/name layout; Unreal material "
                "authoring requires a LiquiGen *_info.json bundle"
            )
            for metadata in metadata_files:
                try:
                    json.loads(metadata.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError):
                    errors.append("VAT metadata is not valid UTF-8 JSON: " + metadata.name)
    elif ".abc" in suffixes:
        bundle_type = "alembic_geometry_cache"
    elif images and suffixes.issubset(_IMAGE_SUFFIXES):
        bundle_type = "image_flipbook"
    else:
        bundle_type = "unsupported"
        errors.append(
            "bundle is not a recognized LiquiGen OpenVDB, flipbook, VAT, or Alembic export"
        )

    grid = None
    if columns is not None or rows is not None:
        if columns is None or rows is None or int(columns) <= 0 or int(rows) <= 0:
            raise LiquiGenExportError("columns and rows must be positive and supplied together")
        grid = {"columns": int(columns), "rows": int(rows)}
        if bundle_type != "image_flipbook":
            warnings.append("grid dimensions are only checked for image flipbooks")
        for image in images if bundle_type == "image_flipbook" else []:
            dimensions = _image_dimensions(image)
            if dimensions is None:
                warnings.append("EXR dimensions require Unreal-side verification: " + image.name)
                continue
            width, height = dimensions
            if width % int(columns) or height % int(rows):
                errors.append(
                    "image dimensions are not divisible by the requested grid: " + image.name
                )
    else:
        for image in images:
            _image_dimensions(image)

    ue_targets = {
        "openvdb_sequence": ("animated_sparse_volume_texture", "sparse_volume_material"),
        "image_flipbook": ("texture2d_flipbook", "particle_subuv_material"),
        "liquigen_vat": ("static_mesh_and_vat_textures", "vertex_animation_material"),
        "alembic_geometry_cache": ("geometry_cache", "surface_material"),
    }
    semantic_roles = {
        "openvdb_sequence": ("velocity_field_auxiliary", False),
        "image_flipbook": ("fallback_billboard", True),
        "liquigen_vat": ("primary_runtime_liquid_surface", True),
        "alembic_geometry_cache": ("primary_cinematic_liquid_surface", True),
    }
    ue_import_target, material_template = ue_targets.get(bundle_type, (None, None))
    semantic_role, recommended_surface_renderer = semantic_roles.get(bundle_type, (None, False))
    return {
        "path": str(target),
        "bundle_type": bundle_type,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "files": entries,
        "grid": grid,
        "ue_import_target": ue_import_target,
        "material_template": material_template,
        "vat": vat,
        "semantic_role": semantic_role,
        "recommended_surface_renderer": recommended_surface_renderer,
        "ue_runtime_acceptance_required": True,
    }


__all__ = ["LiquiGenExportError", "validate_unreal_export_bundle"]
