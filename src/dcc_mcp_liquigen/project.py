"""Bounded read-only inspection of LiquiGen project files."""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional, Sequence

MAX_PROJECT_BYTES = 64 * 1024 * 1024
MAX_PRESETS = 500
_PROJECT_SUFFIX = ".liquigen"
_NODE_PATTERN = re.compile(rb"Node_[A-Za-z0-9_]+")
_KNOWN_EXPORT_TOKENS = (
    "Flipbook",
    "Mesh Flipbook",
    "Vertex Animated Texture",
    "Alembic",
    "FBX",
    "OBJ",
    "Unreal",
)


class LiquiGenProjectError(RuntimeError):
    """A project path or binary document violates the bounded contract."""


def _split_roots(value: str) -> list[Path]:
    return [Path(item).expanduser().resolve() for item in value.split(os.pathsep) if item.strip()]


def allowed_roots_from_env() -> tuple[Path, ...]:
    value = os.environ.get("DCC_MCP_LIQUIGEN_ALLOWED_ROOTS", "")
    roots = _split_roots(value) if value else [Path.cwd().resolve()]
    return tuple(roots)


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


def _resolve_source(value: str, roots: Sequence[Path]) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise LiquiGenProjectError("project path must not be a symbolic link")
    try:
        path = raw.resolve(strict=True)
    except OSError as error:
        raise LiquiGenProjectError("project file does not exist") from error
    if not _within(path, roots):
        raise LiquiGenProjectError("project path is outside configured allowed roots")
    if not path.is_file() or path.suffix.casefold() != _PROJECT_SUFFIX:
        raise LiquiGenProjectError("project must be a .liquigen file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_PROJECT_BYTES:
        raise LiquiGenProjectError("project size is empty or exceeds the configured limit")
    return path


def resolve_project_path(value: str, roots: Optional[Sequence[Path]] = None) -> Path:
    """Resolve one existing project inside the configured allowed roots."""

    return _resolve_source(value, tuple(roots or allowed_roots_from_env()))


def _resolve_destination(value: str, roots: Sequence[Path]) -> Path:
    raw = Path(value).expanduser()
    if raw.suffix.casefold() != _PROJECT_SUFFIX:
        raise LiquiGenProjectError("destination must end with .liquigen")
    parent = raw.parent.resolve(strict=True)
    path = parent / raw.name
    if not _within(path, roots):
        raise LiquiGenProjectError("destination is outside configured allowed roots")
    if path.exists() or path.is_symlink():
        raise LiquiGenProjectError("destination already exists")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tagged_key(key: str) -> bytes:
    encoded = key.encode("utf-8")
    return b"\x0e" + len(encoded).to_bytes(4, "little") + encoded


def _read_field(data: bytes, key: str) -> object:
    marker = _tagged_key(key)
    offset = data.find(marker)
    if offset < 0:
        return None
    cursor = offset + len(marker)
    if cursor >= len(data):
        return None
    tag = data[cursor]
    cursor += 1
    if tag == 0x0E and cursor + 4 <= len(data):
        length = int.from_bytes(data[cursor : cursor + 4], "little")
        cursor += 4
        if 0 <= length <= 4096 and cursor + length <= len(data):
            try:
                return data[cursor : cursor + length].decode("utf-8")
            except UnicodeError:
                return None
    if tag == 0x05 and cursor + 8 <= len(data):
        return int.from_bytes(data[cursor : cursor + 8], "little")
    if tag == 0x06 and cursor + 16 <= len(data):
        return [
            int.from_bytes(data[cursor : cursor + 8], "little"),
            int.from_bytes(data[cursor + 8 : cursor + 16], "little"),
        ]
    if tag == 0x01 and cursor < len(data):
        return bool(data[cursor])
    return None


def inspect_project(path: str, roots: Optional[Sequence[Path]] = None) -> dict[str, object]:
    selected_roots = tuple(roots or allowed_roots_from_env())
    project = _resolve_source(path, selected_roots)
    data = project.read_bytes()
    node_counts = Counter(match.decode("ascii") for match in _NODE_PATTERN.findall(data))
    export_tokens = [token for token in _KNOWN_EXPORT_TOKENS if token.encode() in data]
    return {
        "path": str(project),
        "bytes": len(data),
        "sha256": _sha256(project),
        "app_id": _read_field(data, "app_id"),
        "app_version": _read_field(data, "app_version"),
        "project_version": _read_field(data, "project_version"),
        "node_count": sum(node_counts.values()),
        "node_types": dict(sorted(node_counts.items())),
        "export_tokens": export_tokens,
        "binary_writes_supported": False,
    }


def validate_project(
    path: str,
    require_unreal_export: bool = False,
    roots: Optional[Sequence[Path]] = None,
) -> dict[str, object]:
    info = inspect_project(path, roots=roots)
    nodes = set(info["node_types"])
    errors: list[str] = []
    warnings: list[str] = []
    if info["app_id"] != "liquigen":
        errors.append("app_id is not liquigen")
    for required in ("Node_Simulation", "Node_Scene"):
        if required not in nodes:
            errors.append("missing required node type: " + required)
    export_nodes = {name for name in nodes if name.startswith("Node_Export_")}
    if not export_nodes:
        errors.append("project has no export node")
    if "Node_Export_Image" in export_nodes:
        for required in ("Node_Render", "Node_Camera"):
            if required not in nodes:
                errors.append("image export is missing required node type: " + required)
    if require_unreal_export:
        tokens = set(info["export_tokens"])
        ue_ready = bool(
            ("Node_Export_Image" in export_nodes and "Flipbook" in tokens)
            or (
                {"Node_Export_Mesh", "Node_Export_Particles"} & export_nodes
                and tokens & {"Vertex Animated Texture", "Mesh Flipbook", "Alembic", "FBX"}
            )
        )
        if not ue_ready:
            errors.append("no recognized Unreal-compatible export mode is selected")
    if info["app_version"] not in {None, "1.0.0", "1.0.5", "1.7.1"}:
        warnings.append("project application version differs from the known LiquiGen family")
    return {**info, "valid": not errors, "errors": errors, "warnings": warnings}


def list_presets(
    executable: str,
    query: str = "",
    limit: int = 100,
) -> dict[str, object]:
    selected_limit = int(limit)
    if selected_limit < 1 or selected_limit > MAX_PRESETS:
        raise LiquiGenProjectError("limit must be between 1 and 500")
    needle = query.strip().casefold()
    roots = preset_roots_from_executable(executable)
    entries = []
    for root in sorted(roots, key=lambda item: item.name.casefold()):
        for project in sorted(root.glob("*.liquigen"), key=lambda item: item.name.casefold()):
            if needle and needle not in project.stem.casefold():
                continue
            entries.append(
                {
                    "name": project.stem,
                    "path": str(project.resolve()),
                    "category": root.name,
                    "bytes": project.stat().st_size,
                    "sha256": _sha256(project),
                }
            )
            if len(entries) >= selected_limit:
                return {"total": len(entries), "presets": entries, "truncated": True}
    return {"total": len(entries), "presets": entries, "truncated": False}


def preset_roots_from_executable(executable: str) -> tuple[Path, ...]:
    """Return only real, in-installation preset directories for the bound LiquiGen host."""

    exe = Path(executable).expanduser().resolve(strict=True)
    if exe.name.casefold() not in {"liquigen", "liquigen.exe"}:
        raise LiquiGenProjectError("executable is not LiquiGen")
    install_root = exe.parent.resolve(strict=True)
    candidates = [
        item
        for item in install_root.iterdir()
        if item.is_dir() and (item.name.startswith("presets") or item.name == "templates")
    ]
    roots: list[Path] = []
    for candidate in sorted(candidates, key=lambda item: item.name.casefold()):
        if candidate.is_symlink():
            continue
        resolved = candidate.resolve(strict=True)
        if _within(resolved, (install_root,)):
            roots.append(resolved)
    return tuple(roots)


def stage_project_copy(
    source: str,
    destination: str,
    roots: Optional[Sequence[Path]] = None,
    source_roots: Optional[Sequence[Path]] = None,
) -> dict[str, object]:
    selected_roots = tuple(roots or allowed_roots_from_env())
    selected_source_roots = tuple(source_roots or selected_roots)
    source_path = _resolve_source(source, selected_source_roots)
    destination_path = _resolve_destination(destination, selected_roots)
    source_hash = _sha256(source_path)
    try:
        with source_path.open("rb") as reader, destination_path.open("xb") as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        try:
            destination_path.unlink()
        except OSError:
            pass
        raise
    destination_hash = _sha256(destination_path)
    if destination_hash != source_hash:
        destination_path.unlink(missing_ok=True)
        raise LiquiGenProjectError("copied project hash does not match source")
    return {
        "source": str(source_path),
        "destination": str(destination_path),
        "bytes": destination_path.stat().st_size,
        "sha256": destination_hash,
        "overwritten": False,
    }


__all__ = [
    "LiquiGenProjectError",
    "allowed_roots_from_env",
    "inspect_project",
    "list_presets",
    "preset_roots_from_executable",
    "stage_project_copy",
    "validate_project",
]
