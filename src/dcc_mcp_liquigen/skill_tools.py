"""Typed functions called by bundled LiquiGen Skill scripts."""

from __future__ import annotations

import os

from .compatibility import BASE_INTERFACES, assess_compatibility
from .export_bundle import validate_unreal_export_bundle
from .export_workflow import run_export_workflow
from .graph_api import (
    apply_graph_transaction as _apply_graph_transaction,
)
from .graph_api import (
    create_liquid_chain_burst_project as _create_liquid_chain_burst_project,
)
from .graph_api import (
    inspect_project_graph as _inspect_project_graph,
)
from .graph_api import (
    interface_fingerprint,
)
from .graph_api import (
    list_node_schemas as _list_node_schemas,
)
from .graph_api import (
    prepare_unreal_water_project as _prepare_unreal_water_project,
)
from .host_commands import invoke_host_command, list_host_commands
from .project import (
    allowed_roots_from_env,
    inspect_project,
    list_presets,
    preset_roots_from_executable,
    validate_project,
)
from .project import stage_project_copy as _stage_project_copy
from .recipe import compile_liquid_chain_burst
from .runtime import runtime_from_env


def get_status() -> dict[str, object]:
    binding = runtime_from_env()
    graph_interfaces = interface_fingerprint(binding.executable)
    return {
        "ready": True,
        "binding": binding.as_dict(),
        "native_api_available": list_host_commands()["available"],
        "documented_headless_cli_available": False,
        "project_binary_writes_supported": True,
        "graph_api": {
            "available": True,
            "mode": "transactional_project_document",
            "interface": "liquigen.project.graph.transaction.v1",
            "requires_interactive_desktop": False,
            "destination_policy": "new_path_only",
            "operations": [
                "create_node",
                "clone_node",
                "delete_node",
                "add_parameter",
                "set_parameter",
                "set_keyframes",
                "clear_keyframes",
                "set_node_state",
                "create_group",
                "update_group",
                "delete_group",
                "create_note",
                "update_note",
                "delete_note",
                "set_project_setting",
                "set_current_camera",
                "connect",
                "disconnect",
            ],
            **graph_interfaces,
        },
        "compatibility": assess_compatibility(binding, interfaces=BASE_INTERFACES),
        "semantic_ui_bridge": {
            "abi_version": 1,
            "contract_tested": True,
            "runtime_attached": False,
            "tested_patterns": ["Invoke", "Value"],
            "requires_authorized_local_attachment": True,
        },
        "host_command_bridge": list_host_commands(),
        "interactive_route": "optional dcc-cua viewport acceptance and recording only",
    }


def discover_presets(query: str = "", limit: int = 100) -> dict[str, object]:
    executable = os.environ.get("DCC_MCP_LIQUIGEN_EXECUTABLE")
    if not executable:
        executable = runtime_from_env().executable
    return list_presets(executable, query=query, limit=limit)


def stage_project_copy(source: str, destination: str) -> dict[str, object]:
    """Stage a workspace project or one official preset exposed by the bound installation."""

    executable = os.environ.get("DCC_MCP_LIQUIGEN_EXECUTABLE")
    if not executable:
        executable = runtime_from_env().executable
    destination_roots = allowed_roots_from_env()
    source_roots = (*destination_roots, *preset_roots_from_executable(executable))
    return _stage_project_copy(
        source,
        destination,
        roots=destination_roots,
        source_roots=source_roots,
    )


def list_node_schemas(query: str = "", limit: int = 100) -> dict[str, object]:
    executable = os.environ.get("DCC_MCP_LIQUIGEN_EXECUTABLE")
    if not executable:
        executable = runtime_from_env().executable
    return _list_node_schemas(executable, query=query, limit=limit)


def inspect_project_graph(path: str, node_type: str = "", limit: int = 200) -> dict[str, object]:
    return _inspect_project_graph(path, node_type=node_type, limit=limit)


def apply_graph_transaction(
    source: str,
    destination: str,
    operations: list[dict[str, object]],
    expected_source_sha256: str = "",
) -> dict[str, object]:
    executable = os.environ.get("DCC_MCP_LIQUIGEN_EXECUTABLE")
    if not executable:
        executable = runtime_from_env().executable
    destination_roots = allowed_roots_from_env()
    source_roots = (*destination_roots, *preset_roots_from_executable(executable))
    return _apply_graph_transaction(
        source,
        destination,
        operations,
        executable=executable,
        expected_source_sha256=expected_source_sha256,
        destination_roots=destination_roots,
        source_roots=source_roots,
    )


def create_liquid_chain_burst_project(
    source: str,
    destination: str,
    output_directory: str,
    burst_count: int = 5,
    delay_seconds: float = 0.18,
    spacing_m: float = 2.6,
    export_profile: str = "ue_vat",
) -> dict[str, object]:
    executable = os.environ.get("DCC_MCP_LIQUIGEN_EXECUTABLE")
    if not executable:
        executable = runtime_from_env().executable
    destination_roots = allowed_roots_from_env()
    source_roots = (*destination_roots, *preset_roots_from_executable(executable))
    return _create_liquid_chain_burst_project(
        source,
        destination,
        output_directory,
        executable=executable,
        burst_count=burst_count,
        delay_seconds=delay_seconds,
        spacing_m=spacing_m,
        export_profile=export_profile,
        destination_roots=destination_roots,
        source_roots=source_roots,
    )


def prepare_unreal_water_project(
    source: str,
    destination: str,
    output_directory: str,
    asset_name: str = "LiquiGen_BallDropSplash",
    frame_count: int = 64,
) -> dict[str, object]:
    executable = os.environ.get("DCC_MCP_LIQUIGEN_EXECUTABLE")
    if not executable:
        executable = runtime_from_env().executable
    destination_roots = allowed_roots_from_env()
    source_roots = (*destination_roots, *preset_roots_from_executable(executable))
    return _prepare_unreal_water_project(
        source,
        destination,
        output_directory,
        executable=executable,
        asset_name=asset_name,
        frame_count=frame_count,
        destination_roots=destination_roots,
        source_roots=source_roots,
    )


__all__ = [
    "apply_graph_transaction",
    "compile_liquid_chain_burst",
    "create_liquid_chain_burst_project",
    "discover_presets",
    "get_status",
    "inspect_project_graph",
    "inspect_project",
    "invoke_host_command",
    "list_host_commands",
    "list_node_schemas",
    "prepare_unreal_water_project",
    "run_export_workflow",
    "stage_project_copy",
    "validate_project",
    "validate_unreal_export_bundle",
]
