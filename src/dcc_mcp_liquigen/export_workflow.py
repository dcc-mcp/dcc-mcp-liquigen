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


def _configured_export_targets(project: Path, roots: Sequence[Path]) -> dict[str, Optional[str]]:
    """Collect every export destination before allowing export_all to reach the host."""

    snapshot = inspect_project_graph(str(project), roots=roots, limit=500)
    if snapshot.get("truncated"):
        raise LiquiGenExportWorkflowError("export plan requires a complete project graph")
    targets: dict[str, Optional[str]] = {}
    for node in snapshot["nodes"]:
        if not str(node.get("type", "")).startswith("Node_Export_"):
            continue
        if node.get("disabled") is True or node.get("on") is False:
            if node.get("type") == "Node_Export_Image":
                raise LiquiGenExportWorkflowError(
                    "export_all requires the paired image exporter to remain enabled; "
                    "use prepare_unreal_water_project and configure its output path"
                )
            continue
        parameters = {
            parameter.get("name"): parameter.get("value")
            for parameter in node.get("parameters", [])
            if isinstance(parameter, dict)
        }
        directory = parameters.get("directory")
        if not isinstance(directory, str) or not directory.strip():
            raise LiquiGenExportWorkflowError("every enabled export node requires a directory")
        # Validate the original path before normalization can hide a relative path or link.
        output = _resolve_output_directory(directory, roots)
        key = _normalized_path(str(output))
        required_type = None
        if node.get("type") == "Node_Export_Mesh":
            required_type = {
                "Vertex_Animated_Texture": "liquigen_vat",
                "Alembic": "alembic_geometry_cache",
            }.get(parameters.get("export_kind"))
        existing_type = targets.get(key)
        if existing_type and required_type and existing_type != required_type:
            raise LiquiGenExportWorkflowError(
                "different mesh export modes require separate output directories"
            )
        targets[key] = required_type or existing_type
    paths = [Path(directory) for directory in targets]
    for index, path in enumerate(paths):
        if any(path in other.parents or other in path.parents for other in paths[index + 1 :]):
            raise LiquiGenExportWorkflowError("export output directories must not overlap")
    return targets


def _output_states(targets: Sequence[str]) -> dict[str, FileState]:
    states = {directory: _file_state(Path(directory)) for directory in targets}
    if sum(len(state) for state in states.values()) > MAX_EXPORT_FILES:
        raise LiquiGenExportWorkflowError("export directories exceed the file-count limit")
    if sum(size for state in states.values() for size, _ in state.values()) > MAX_EXPORT_BYTES:
        raise LiquiGenExportWorkflowError("export directories exceed the byte limit")
    return states


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
    targets = _configured_export_targets(project, selected_roots)
    configured_directories = sorted(targets)
    normalized_output = _normalized_path(str(output))
    if normalized_output not in targets:
        raise LiquiGenExportWorkflowError(
            "output_directory is not configured on an enabled project export node"
        )
    if any(_output_states(configured_directories).values()):
        raise LiquiGenExportWorkflowError(
            "every export output_directory must be empty; use new directories for every export"
        )

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

    run("switch_tab_to_export", timeout_ms=10000)
    if settle_duration:
        sleep(settle_duration)
    before = _output_states(configured_directories)
    if any(before.values()):
        raise LiquiGenExportWorkflowError(
            "an output_directory changed before export; use new directories"
        )
    run("export_all", timeout_ms=30000)
    started_at = monotonic()
    deadline = started_at + timeout
    last_state = _output_states(configured_directories)
    stable_since = monotonic()
    last_validation_error = "export produced no fresh files in every configured directory"

    while monotonic() <= deadline:
        current = _output_states(configured_directories)
        if current != last_state:
            last_state = current
            stable_since = monotonic()
        now = monotonic()
        if all(current.values()) and now - stable_since >= stable_duration:
            exports = []
            for directory, required_bundle_type in targets.items():
                fresh = _fresh_paths(before[directory], current[directory])
                try:
                    bundle = validate_unreal_export_bundle(directory, roots=selected_roots)
                    if bundle["valid"] is not True:
                        raise LiquiGenExportError(
                            "; ".join(str(item) for item in bundle.get("errors", []))
                        )
                    if required_bundle_type and bundle.get("bundle_type") != required_bundle_type:
                        raise LiquiGenExportError(
                            f"expected {required_bundle_type}, got "
                            f"{bundle.get('bundle_type', 'unknown')}"
                        )
                    required = _required_fresh_paths(bundle)
                    if not required or required - fresh:
                        raise LiquiGenExportError("required export assets were not refreshed")
                except LiquiGenExportError as error:
                    last_validation_error = f"{directory}: {error}"
                    break
                exports.append(
                    {"output_directory": directory, "fresh_files": sorted(fresh), "bundle": bundle}
                )
            else:
                # Validation hashes files and can take time; reject files changed during it.
                verified_state = _output_states(configured_directories)
                if verified_state == current and monotonic() <= deadline:
                    selected = next(
                        item for item in exports if item["output_directory"] == normalized_output
                    )
                    return {
                        "interface": EXPORT_WORKFLOW_INTERFACE,
                        "success": True,
                        "project_path": str(project),
                        "output_directory": str(output),
                        "configured_output_directories": configured_directories,
                        "commands": commands,
                        "simulation_seconds": simulation_duration,
                        "elapsed_seconds": round(monotonic() - started_at, 3),
                        "stable_seconds": stable_duration,
                        "settle_seconds": settle_duration,
                        "fresh_files": selected["fresh_files"],
                        "requires_cua": False,
                        "completion_boundary": (
                            "fresh required export assets are stable and bundle validation "
                            "passed in every configured output directory"
                        ),
                        "bundle": selected["bundle"],
                        "exports": exports,
                    }
                last_state = verified_state
                stable_since = monotonic()
                last_validation_error = "export files changed during validation or timeout elapsed"
        else:
            empty = [directory for directory, state in current.items() if not state]
            if empty:
                last_validation_error = "export produced no fresh files in: " + ", ".join(empty)
        sleep(poll_interval)

    raise LiquiGenExportWorkflowError(
        "export did not produce fresh stable valid bundles before timeout; "
        f"last_validation_error={last_validation_error}"
    )


__all__ = [
    "EXPORT_WORKFLOW_INTERFACE",
    "LiquiGenExportWorkflowError",
    "run_export_workflow",
]
