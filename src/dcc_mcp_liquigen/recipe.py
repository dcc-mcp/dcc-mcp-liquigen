"""Replayable LiquiGen recipes for transactional cross-DCC handoff workflows."""

from pathlib import Path
from typing import Any, Dict, List, Optional

_EXPORT_PROFILES: Dict[str, Dict[str, Any]] = {
    "ue_vat": {
        "node_type": "Node_Export_Mesh",
        "parameters": {
            "export_format": "Vertex Animated Texture",
            "vat_target_engine": "Unreal",
        },
        "semantic_role": "primary_runtime_liquid_surface",
        "ue_import_target": "static_mesh_and_vat_textures",
    },
    "alembic": {
        "node_type": "Node_Export_Mesh",
        "parameters": {"export_format": "Alembic"},
        "semantic_role": "primary_cinematic_liquid_surface",
        "ue_import_target": "geometry_cache",
    },
    "flipbook": {
        "node_type": "Node_Export_Image",
        "parameters": {"export_format": "OpenEXR"},
        "semantic_role": "fallback_billboard",
        "ue_import_target": "texture2d_flipbook",
    },
    "vdb_velocity": {
        "node_type": "Node_Export_VDB",
        "parameters": {"fields": ["Velocity staggered", "Velocity centered"]},
        "semantic_role": "velocity_field_auxiliary",
        "ue_import_target": "animated_sparse_volume_texture",
    },
}


def _normalise_output_directory(value: str) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("output_directory must be an absolute path")
    return str(path)


def _step(
    steps: List[Dict[str, Any]],
    *,
    step_id: str,
    title: str,
    operation: str,
    node_type: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    verification: str,
) -> None:
    item: Dict[str, Any] = {
        "index": len(steps) + 1,
        "id": step_id,
        "title": title,
        "operation": operation,
        "node_type": node_type,
        "parameters": parameters or {},
        "verification": verification,
    }
    steps.append(item)


def compile_liquid_chain_burst(
    *,
    output_directory: str,
    burst_count: int = 5,
    delay_seconds: float = 0.18,
    spacing_m: float = 2.6,
    export_profile: str = "ue_vat",
) -> Dict[str, Any]:
    """Compile a deterministic liquid chain-burst plan.

    LiquiGen simulates liquids, so the recipe deliberately does not claim to
    create combustion, fire, or smoke.  A fiery chain explosion should use an
    appropriate gaseous-effects DCC while retaining the same UE handoff shape.
    """

    if not 2 <= burst_count <= 12:
        raise ValueError("burst_count must be between 2 and 12")
    if not 0.05 <= delay_seconds <= 2.0:
        raise ValueError("delay_seconds must be between 0.05 and 2.0")
    if spacing_m <= 0:
        raise ValueError("spacing_m must be greater than zero")
    if export_profile not in _EXPORT_PROFILES:
        allowed = ", ".join(sorted(_EXPORT_PROFILES))
        raise ValueError(f"export_profile must be one of: {allowed}")

    directory = _normalise_output_directory(output_directory)
    export_spec = _EXPORT_PROFILES[export_profile]
    export_parameters = dict(export_spec["parameters"])
    export_parameters["directory"] = directory

    steps: List[Dict[str, Any]] = []
    _step(
        steps,
        step_id="verify_bridge_binding",
        title="Verify exact LiquiGen bridge binding",
        operation="bridge.status",
        parameters={"required_capabilities": ["project.graph.transaction.v1"]},
        verification="The bridge reports the expected runtime, host PID, and HWND.",
    )
    _step(
        steps,
        step_id="stage_ball_drop_preset",
        title="Discover and stage the ball-drop splash preset",
        operation="preset.stage_copy",
        parameters={"preset": "ball_drop_splash"},
        verification="The staged project is writable and its source preset hash is recorded.",
    )
    _step(
        steps,
        step_id="inspect_baseline_graph",
        title="Inspect the baseline project graph",
        operation="project.inspect",
        parameters={"expected_nodes": ["Node_Simulation", "Node_Scene"]},
        verification="The project version and baseline node inventory are captured.",
    )

    centre = (burst_count - 1) / 2.0
    for burst_index in range(burst_count):
        position_x = round((burst_index - centre) * spacing_m, 6)
        start_time = round(burst_index * delay_seconds, 6)
        suffix = f"{burst_index + 1:02d}"
        shape_id = f"burst_shape_{suffix}"
        emitter_id = f"burst_emitter_{suffix}"
        _step(
            steps,
            step_id=f"create_{shape_id}",
            title=f"Create burst source {burst_index + 1}",
            operation="graph.create_node",
            node_type="Node_Shape_Primitive",
            parameters={
                "node_id": shape_id,
                "primitive": "Sphere",
                "position_m": [position_x, 0.0, 1.2],
                "radius_m": 0.75,
            },
            verification=f"{shape_id} exists at the requested position.",
        )
        _step(
            steps,
            step_id=f"create_{emitter_id}",
            title=f"Create timed liquid emitter {burst_index + 1}",
            operation="graph.create_node",
            node_type="Node_Emitter",
            parameters={
                "node_id": emitter_id,
                "start_time_seconds": start_time,
                "duration_seconds": 0.12,
                "initial_velocity_mps": [0.0, 0.0, 9.0],
            },
            verification=f"{emitter_id} reports start time {start_time:.3f}s.",
        )
        _step(
            steps,
            step_id=f"connect_burst_{suffix}",
            title=f"Connect burst {burst_index + 1} to the liquid simulation",
            operation="graph.connect_typed_ports",
            parameters={
                "connections": [
                    {"from": shape_id, "to": emitter_id},
                    {"from": emitter_id, "to": "liquid_simulation"},
                ]
            },
            verification="Both typed graph connections are visible and accepted.",
        )

    _step(
        steps,
        step_id="configure_meshing",
        title="Configure the liquid surface mesher",
        operation="graph.set_parameter",
        node_type="Node_Simulation",
        parameters={"node": "liquid_simulation", "meshing.enabled": True},
        verification="The simulation exposes its liquid mesh output.",
    )
    _step(
        steps,
        step_id="configure_export",
        title=f"Configure {export_profile} export",
        operation="graph.configure_node",
        node_type=str(export_spec["node_type"]),
        parameters=export_parameters,
        verification="The export node shows the requested format and absolute directory.",
    )
    _step(
        steps,
        step_id="simulate_and_export",
        title="Simulate and export the chain burst",
        operation="project.simulate_export",
        parameters={"fail_on_missing_frames": True, "interface_status": "not_exposed"},
        verification="The output bundle passes header, sequence, and manifest validation.",
    )

    return {
        "recipe_version": 1,
        "name": "liquigen-liquid-chain-burst",
        "effect_semantics": "liquid_chain_burst",
        "combustion_supported": False,
        "source_preset": "ball_drop_splash",
        "parameters": {
            "burst_count": burst_count,
            "delay_seconds": delay_seconds,
            "spacing_m": spacing_m,
        },
        "export": {
            "profile": export_profile,
            "node_type": export_spec["node_type"],
            "parameters": export_parameters,
            "semantic_role": export_spec["semantic_role"],
            "ue_import_target": export_spec["ue_import_target"],
        },
        "steps": steps,
        "bridge_capabilities": [
            "exact_host_binding",
            "preset_discovery",
            "safe_project_staging",
            "project_binary_inspection",
            "project_graph_transaction",
            "node_schema_discovery",
            "replayable_node_recipe",
            "typed_graph_operations",
            "semantic_host_commands",
            "fresh_export_workflow",
            "export_bundle_validation",
            "unreal_asset_import",
            "unreal_material_authoring",
            "runtime_verification",
        ],
        "showcase_chapters": [
            {"id": "bridge_diagnostics", "title": "Bridge diagnostics"},
            {"id": "preset_and_project", "title": "Preset and project staging"},
            {"id": "node_graph_build", "title": "Transactional node-graph construction"},
            {"id": "simulation_and_export", "title": "Simulation and export validation"},
            {"id": "unreal_import", "title": "Unreal Engine 5.8 import"},
            {"id": "ue_material_authoring", "title": "Programmatic UE material authoring"},
            {"id": "runtime_verification", "title": "Niagara runtime verification"},
        ],
        "unreal_material_contract": {
            "master_material": "M_LiquiGen_VAT_Master",
            "material_instance": "MI_LiquiGen_ChainBurst",
            "niagara_system": "NS_LiquiGen_ChainBurst",
            "source_metadata": "LiquiGen VAT JSON",
            "user_parameters": [
                "BurstCount",
                "BurstDelay",
                "BurstSpacing",
                "PlayRate",
                "LiquidTint",
                "RefractionStrength",
            ],
        },
        "execution_boundary": {
            "planner_is_read_only": True,
            "graph_mutation_route": "apply_graph_transaction",
            "requires_interactive_desktop": False,
            "binary_project_writes_supported": True,
            "write_policy": "new_path_only_with_full_readback",
            "live_simulate_export_exposed": True,
            "live_simulate_export_route": "run_export_workflow",
            "freshness_policy": "required assets changed, stabilized, and validated",
            "cua_role": "optional viewport acceptance and recording only",
        },
    }


__all__ = ["compile_liquid_chain_burst"]
