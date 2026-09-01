"""Run one bounded LiquiGen simulation/export workflow without CUA."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional, Sequence

from .export_bundle import (
    MAX_EXPORT_BYTES,
    MAX_EXPORT_FILES,
    LiquiGenExportError,
    validate_unreal_export_bundle,
)
from .graph_api import inspect_project_graph
from .host_commands import invoke_host_command
from .project import allowed_roots_from_env, resolve_project_path
from .runtime import RuntimeBinding

EXPORT_WORKFLOW_INTERFACE = "liquigen.export.run_and_wait.v1"


class LiquiGenExportWorkflowError(RuntimeError):
    """The semantic host workflow failed or did not produce a fresh stable bundle."""


FileState = dict[str, tuple[int, int]]
CommandRunner = Callable[..., dict[str, object]]


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


def _resolve_output_directory(value: str, roots: Sequence[Path]) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raise LiquiGenExportWorkflowError("output_directory must be absolute")
    if raw.is_symlink():
        raise LiquiGenExportWorkflowError("output_directory must not be a symbolic link")
    if raw.exists():
        try:
            result = raw.resolve(strict=True)
        except OSError as error:
            raise LiquiGenExportWorkflowError("output_directory cannot be resolved") from error
        if not result.is_dir():
            raise LiquiGenExportWorkflowError("output_directory must be a directory")
    else:
        try:
            parent = raw.parent.resolve(strict=True)
        except OSError as error:
            raise LiquiGenExportWorkflowError("output_directory parent does not exist") from error
        result = parent / raw.name
        if not _within(result, roots):
            raise LiquiGenExportWorkflowError(
                "output_directory is outside configured allowed roots"
            )
        result.mkdir()
    if not _within(result, roots):
        raise LiquiGenExportWorkflowError("output_directory is outside configured allowed roots")
    return result


def _file_state(directory: Path) -> FileState:
    state: FileState = {}
    total_bytes = 0
    for item in sorted(directory.rglob("*")):
        if item.is_symlink():
            raise LiquiGenExportWorkflowError("export directory must not contain links")
        if not item.is_file():
            continue
        if len(state) >= MAX_EXPORT_FILES:
            raise LiquiGenExportWorkflowError("export directory exceeds the file-count limit")
        stat = item.stat()
        total_bytes += stat.st_size
        if total_bytes > MAX_EXPORT_BYTES:
            raise LiquiGenExportWorkflowError("export directory exceeds the byte limit")
        state[item.relative_to(directory).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return state


def _normalized_path(value: str) -> str:
    return os.path.normcase(str(Path(value).expanduser().resolve(strict=False)))


def _configured_export_directories(project: Path, roots: Sequence[Path]) -> list[str]:
    snapshot = inspect_project_graph(str(project), roots=roots)
    directories: list[str] = []
    for node in snapshot["nodes"]:
        if not str(node.get("type", "")).startswith("Node_Export_"):
            continue
        if node.get("disabled") is True or node.get("on") is False:
            continue
        for parameter in node.get("parameters", []):
            if parameter.get("name") == "directory" and isinstance(parameter.get("value"), str):
                directories.append(str(parameter["value"]))
    return sorted(set(directories), key=str.casefold)


def _required_export_bundle_type(project: Path, roots: Sequence[Path]) -> Optional[str]:
    """Return the primary enabled export contract that must actually finish."""

    snapshot = inspect_project_graph(str(project), roots=roots)
    for node in snapshot["nodes"]:
        if node.get("type") != "Node_Export_Mesh":
            continue
        if node.get("disabled") is True or node.get("on") is False:
            continue
        parameters = {
            parameter.get("name"): parameter.get("value")
            for parameter in node.get("parameters", [])
            if isinstance(parameter, dict)
        }
        if parameters.get("export_kind") == "Vertex_Animated_Texture":
            return "liquigen_vat"
    return None


def _fresh_paths(before: FileState, current: FileState) -> set[str]:
    return {path for path, state in current.items() if before.get(path) != state}


def _required_fresh_paths(bundle: dict[str, object]) -> set[str]:
    bundle_type = bundle.get("bundle_type")
    if bundle_type == "liquigen_vat":
        vat = bundle.get("vat")
        if isinstance(vat, dict) and isinstance(vat.get("assets"), dict):
            return {str(path) for path in vat["assets"].values()}
    suffixes = {
        "image_flipbook": {".png", ".tga", ".exr"},
        "alembic_geometry_cache": {".abc"},
        "openvdb_sequence": {".vdb"},
    }.get(str(bundle_type), set())
    return {
        str(item["path"])
        for item in bundle.get("files", [])
        if isinstance(item, dict)
        and isinstance(item.get("path"), str)
        and Path(str(item["path"])).suffix.casefold() in suffixes
    }


def run_export_workflow(
    project_path: str,
    output_directory: str,
    simulate_seconds: float = 12.0,
    timeout_seconds: float = 600.0,
    stable_seconds: float = 3.0,
    poll_interval_seconds: float = 0.5,
    settle_seconds: float = 2.0,
    *,
    binding: Optional[RuntimeBinding] = None,
    roots: Optional[Sequence[Path]] = None,
    command_runner: CommandRunner = invoke_host_command,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, object]:
    """Open, simulate, export, wait for fresh stable files, then validate them."""

    simulation_duration = float(simulate_seconds)
    timeout = float(timeout_seconds)
    stable_duration = float(stable_seconds)
    poll_interval = float(poll_interval_seconds)
    settle_duration = float(settle_seconds)
    if not 0.0 <= simulation_duration <= 300.0:
        raise LiquiGenExportWorkflowError("simulate_seconds must be between 0 and 300")
    if not 1.0 <= timeout <= 1800.0:
        raise LiquiGenExportWorkflowError("timeout_seconds must be between 1 and 1800")
    if not 0.5 <= stable_duration <= 30.0:
        raise LiquiGenExportWorkflowError("stable_seconds must be between 0.5 and 30")
    if not 0.1 <= poll_interval <= min(stable_duration, 5.0):
        raise LiquiGenExportWorkflowError(
            "poll_interval_seconds must be between 0.1 and stable_seconds"
        )
    if not 0.0 <= settle_duration <= 30.0:
        raise LiquiGenExportWorkflowError("settle_seconds must be between 0 and 30")

    selected_roots = tuple(roots or allowed_roots_from_env())
    project = resolve_project_path(project_path, selected_roots)
    output = _resolve_output_directory(output_directory, selected_roots)
    configured_directories = _configured_export_directories(project, selected_roots)
    normalized_output = _normalized_path(str(output))
    if normalized_output not in {_normalized_path(item) for item in configured_directories}:
        raise LiquiGenExportWorkflowError(
            "output_directory is not configured on an enabled project export node"
        )
    if _file_state(output):
        raise LiquiGenExportWorkflowError(
            "output_directory must be empty; use a new directory for every export"
        )
    required_bundle_type = _required_export_bundle_type(project, selected_roots)

    commands: list[dict[str, object]] = []

    def run(command: str, **arguments: object) -> dict[str, object]:
        result = command_runner(command, binding=binding, **arguments)
        commands.append(result)
        return result

    run("open_project_path", timeout_ms=30000, project_path=str(project))
    if settle_duration:
        sleep(settle_duration)
    run("reset_graph_zoom", timeout_ms=10000)
    if simulation_duration:
        run("reset_simulation", timeout_ms=10000)
        run("reset_timeline", timeout_ms=10000)
        run("play_timeline", timeout_ms=10000)
        try:
            sleep(simulation_duration)
        finally:
            run("pause_timeline", timeout_ms=10000)
        if settle_duration:
            sleep(settle_duration)

    before = _file_state(output)
    if before:
        raise LiquiGenExportWorkflowError(
            "output_directory changed before export; use another new directory"
        )
    run("switch_tab_to_export", timeout_ms=10000)
    if settle_duration:
        sleep(settle_duration)
    run("export_all", timeout_ms=30000)
    started_at = monotonic()
    deadline = started_at + timeout
    last_state = _file_state(output)
    stable_since = monotonic()
    last_validation_error = "export produced no fresh files"

    while monotonic() <= deadline:
        current = _file_state(output)
        if current != last_state:
            last_state = current
            stable_since = monotonic()
        fresh = _fresh_paths(before, current)
        now = monotonic()
        if fresh and now - stable_since >= stable_duration:
            try:
                bundle = validate_unreal_export_bundle(str(output), roots=selected_roots)
            except LiquiGenExportError as error:
                last_validation_error = str(error)
            else:
                if bundle["valid"] is True:
                    if required_bundle_type and bundle.get("bundle_type") != required_bundle_type:
                        last_validation_error = (
                            f"expected {required_bundle_type}, got "
                            f"{bundle.get('bundle_type', 'unknown')}"
                        )
                        sleep(poll_interval)
                        continue
                    required = _required_fresh_paths(bundle)
                    stale_required = sorted(required - fresh)
                    if required and not stale_required:
                        return {
                            "interface": EXPORT_WORKFLOW_INTERFACE,
                            "success": True,
                            "project_path": str(project),
                            "output_directory": str(output),
                            "configured_output_directories": configured_directories,
                            "commands": commands,
                            "simulation_seconds": simulation_duration,
                            "elapsed_seconds": round(now - started_at, 3),
                            "stable_seconds": stable_duration,
                            "settle_seconds": settle_duration,
                            "fresh_files": sorted(fresh),
                            "requires_cua": False,
                            "completion_boundary": (
                                "fresh required export assets are stable and bundle "
                                "validation passed"
                            ),
                            "bundle": bundle,
                        }
                    last_validation_error = (
                        "required export assets were not refreshed: "
                        + ", ".join(stale_required or sorted(required))
                    )
                else:
                    last_validation_error = "; ".join(
                        str(item) for item in bundle.get("errors", [])
                    )
        sleep(poll_interval)

    fresh = sorted(_fresh_paths(before, _file_state(output)))
    raise LiquiGenExportWorkflowError(
        "export did not produce a fresh stable valid bundle before timeout; "
        f"fresh_files={fresh!r}; last_validation_error={last_validation_error}"
    )


__all__ = [
    "EXPORT_WORKFLOW_INTERFACE",
    "LiquiGenExportWorkflowError",
    "run_export_workflow",
]
