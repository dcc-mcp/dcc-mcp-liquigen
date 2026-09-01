"""Transactional LiquiGen project graph API backed by official node templates."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from .graph_document import (
    LiquiGenGraphDocument,
    deterministic_node_id,
)
from .project import (
    _resolve_destination,
    _resolve_source,
    _sha256,
    allowed_roots_from_env,
    preset_roots_from_executable,
)
from .tagged_document import (
    TAG_ARRAY,
    TAG_BOOL,
    TAG_F64,
    TAG_F64X2,
    TAG_F64X3,
    TAG_F64X4,
    TAG_I64,
    TAG_OBJECT,
    TAG_STRING,
    TaggedDocumentError,
    TaggedValue,
    array_items,
    decode_document,
    encode_document,
    materialize_references,
    object_get,
    object_require,
    plain_value,
    resolve,
)

MAX_GRAPH_OPERATIONS = 256
MAX_GRAPH_RESULTS = 500


class LiquiGenGraphApiError(RuntimeError):
    """A graph API request is unsafe, invalid, or unsupported."""


@dataclass(frozen=True)
class NodeTemplate:
    node_type: str
    source: Path
    node: TaggedValue


def _project_files(executable: str) -> list[Path]:
    result: list[Path] = []
    for root in preset_roots_from_executable(executable):
        result.extend(sorted(root.glob("*.liquigen"), key=lambda item: item.name.casefold()))
    return result


def _nodes(root: TaggedValue) -> list[TaggedValue]:
    return array_items(object_require(object_require(root, "graph"), "nodes"))


def _plain_field(value: TaggedValue, name: str) -> Any:
    return plain_value(object_require(value, name))


def _type_name(value: TaggedValue) -> str:
    tag = resolve(value).tag
    return {
        TAG_BOOL: "boolean",
        TAG_I64: "integer",
        TAG_F64: "number",
        TAG_F64X2: "vector2",
        TAG_F64X3: "vector3",
        TAG_F64X4: "vector4",
        TAG_STRING: "string",
        TAG_ARRAY: "array",
        TAG_OBJECT: "object",
    }.get(tag, f"tag_0x{tag:02x}")


def load_template_catalog(executable: str) -> tuple[dict[str, NodeTemplate], dict[str, Any]]:
    """Discover graph schemas from installed official projects, keyed by interface name."""

    templates: dict[str, NodeTemplate] = {}
    schemas: dict[str, dict[str, Any]] = {}
    for path in _project_files(executable):
        try:
            document = decode_document(path.read_bytes())
        except (OSError, TaggedDocumentError):
            continue
        nodes = _nodes(document)
        by_id = {int(_plain_field(node, "id")): node for node in nodes}
        for node in nodes:
            node_type = str(_plain_field(node, "type"))
            templates.setdefault(node_type, NodeTemplate(node_type, path, node))
            schema = schemas.setdefault(
                node_type,
                {
                    "node_type": node_type,
                    "parameters": {},
                    "outgoing_pins": set(),
                    "incoming_pins": set(),
                    "outgoing_connections": set(),
                    "incoming_connections": set(),
                    "observed_projects": set(),
                },
            )
            schema["observed_projects"].add(path.name)
            for parameter in array_items(object_require(node, "parameters")):
                name = str(_plain_field(parameter, "name"))
                current = object_get(parameter, "value") or object_get(parameter, "automation")
                if current is None:
                    continue
                schema["parameters"].setdefault(
                    name,
                    {
                        "name": name,
                        "type": _type_name(current),
                        "default": plain_value(current),
                    },
                )
            for link in array_items(object_require(node, "links")):
                schema["outgoing_pins"].add(str(_plain_field(link, "from_pin")))
                target = by_id.get(int(_plain_field(link, "to_node")))
                if target is not None:
                    target_type = str(_plain_field(target, "type"))
                    target_schema = schemas.setdefault(
                        target_type,
                        {
                            "node_type": target_type,
                            "parameters": {},
                            "outgoing_pins": set(),
                            "incoming_pins": set(),
                            "outgoing_connections": set(),
                            "incoming_connections": set(),
                            "observed_projects": set(),
                        },
                    )
                    from_pin = str(_plain_field(link, "from_pin"))
                    to_pin = str(_plain_field(link, "to_pin"))
                    target_schema["incoming_pins"].add(to_pin)
                    schema["outgoing_connections"].add((from_pin, target_type, to_pin))
                    target_schema["incoming_connections"].add((node_type, from_pin, to_pin))

    normalized = {}
    for node_type, schema in schemas.items():
        normalized[node_type] = {
            "node_type": node_type,
            "parameters": [schema["parameters"][key] for key in sorted(schema["parameters"])],
            "outgoing_pins": sorted(schema["outgoing_pins"]),
            "incoming_pins": sorted(schema["incoming_pins"]),
            "outgoing_connections": [
                {
                    "from_pin": from_pin,
                    "target_node_type": target_type,
                    "to_pin": to_pin,
                }
                for from_pin, target_type, to_pin in sorted(schema["outgoing_connections"])
            ],
            "incoming_connections": [
                {
                    "source_node_type": source_type,
                    "from_pin": from_pin,
                    "to_pin": to_pin,
                }
                for source_type, from_pin, to_pin in sorted(schema["incoming_connections"])
            ],
            "observed_projects": sorted(schema["observed_projects"]),
        }
    return templates, normalized


def list_node_schemas(executable: str, query: str = "", limit: int = 100) -> dict[str, Any]:
    if not 1 <= int(limit) <= MAX_GRAPH_RESULTS:
        raise LiquiGenGraphApiError("limit must be between 1 and 500")
    _templates, schemas = load_template_catalog(executable)
    needle = query.strip().casefold()
    selected = [
        schema for key, schema in sorted(schemas.items()) if not needle or needle in key.casefold()
    ]
    visible = selected[: int(limit)]
    connection_signatures = [
        {
            "source_node_type": schema["node_type"],
            **connection,
        }
        for schema in visible
        for connection in schema["outgoing_connections"]
    ]
    return {
        "interface": "liquigen.node.schema.catalog.v1",
        "total": len(selected),
        "node_schemas": visible,
        "truncated": len(selected) > int(limit),
        "connection_signature_count": len(connection_signatures),
        "connection_signatures": connection_signatures,
        "source": "installed_official_projects",
    }


def inspect_project_graph(
    path: str,
    *,
    roots: Optional[Sequence[Path]] = None,
    node_type: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    if not 1 <= int(limit) <= MAX_GRAPH_RESULTS:
        raise LiquiGenGraphApiError("limit must be between 1 and 500")
    selected_roots = tuple(roots or allowed_roots_from_env())
    project = _resolve_source(path, selected_roots)
    document = decode_document(project.read_bytes())
    graph = LiquiGenGraphDocument(document)
    snapshot = graph.snapshot()
    if node_type:
        snapshot["nodes"] = [item for item in snapshot["nodes"] if item["type"] == node_type]
    total = len(snapshot["nodes"])
    snapshot["nodes"] = snapshot["nodes"][: int(limit)]
    return {
        "interface": "liquigen.project.graph.snapshot.v1",
        "path": str(project),
        "sha256": _sha256(project),
        "total": total,
        "truncated": total > int(limit),
        **snapshot,
    }


def _resolve_selector(selector: Any, aliases: dict[str, int]) -> int:
    if isinstance(selector, bool):
        raise LiquiGenGraphApiError("node selector must be an integer ID or transaction alias")
    if isinstance(selector, int):
        return selector
    if isinstance(selector, str):
        if selector in aliases:
            return aliases[selector]
        digits = selector[1:] if selector.startswith("-") else selector
        if digits and digits.isascii() and digits.isdigit():
            return int(selector)
    raise LiquiGenGraphApiError(f"unknown node selector: {selector!r}")


def _position(value: Any) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise LiquiGenGraphApiError("node position must contain exactly two numbers")
    return float(value[0]), float(value[1])


def _operation_name(operation: dict[str, Any]) -> str:
    name = operation.get("op")
    if not isinstance(name, str) or not name:
        raise LiquiGenGraphApiError("every graph operation requires a nonempty op name")
    return name


def apply_graph_transaction(
    source: str,
    destination: str,
    operations: list[dict[str, Any]],
    *,
    executable: str,
    expected_source_sha256: str = "",
    destination_roots: Optional[Sequence[Path]] = None,
    source_roots: Optional[Sequence[Path]] = None,
) -> dict[str, Any]:
    """Apply one all-or-nothing graph transaction to a new project path."""

    if not 1 <= len(operations) <= MAX_GRAPH_OPERATIONS:
        raise LiquiGenGraphApiError("operations must contain between 1 and 256 items")
    selected_destination_roots = tuple(destination_roots or allowed_roots_from_env())
    selected_source_roots = tuple(source_roots or selected_destination_roots)
    source_path = _resolve_source(source, selected_source_roots)
    destination_path = _resolve_destination(destination, selected_destination_roots)
    source_hash = _sha256(source_path)
    if expected_source_sha256 and source_hash.casefold() != expected_source_sha256.casefold():
        raise LiquiGenGraphApiError("source project changed since the transaction was planned")

    templates, schemas = load_template_catalog(executable)
    document = decode_document(source_path.read_bytes())
    graph = LiquiGenGraphDocument(document)
    aliases: dict[str, int] = {}
    results = []
    namespace = source_hash

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise LiquiGenGraphApiError(f"operation {index} must be an object")
        name = _operation_name(operation)
        if name == "create_node":
            node_type = str(operation.get("node_type", ""))
            alias = str(operation.get("alias", ""))
            if not alias or len(alias) > 128 or alias in aliases:
                raise LiquiGenGraphApiError("create_node alias must be unique and 1-128 characters")
            try:
                template = templates[node_type]
            except KeyError as error:
                raise LiquiGenGraphApiError(
                    f"node type is not available in installed official projects: {node_type}"
                ) from error
            node_id = deterministic_node_id(namespace, alias, set(graph.node_ids()))
            graph.create_node(
                template.node,
                node_id=node_id,
                position=_position(operation.get("position", [0.0, 0.0])),
                label=str(operation.get("label", alias)),
                parameters=dict(operation.get("parameters", {})),
            )
            aliases[alias] = node_id
            result = {"op": name, "alias": alias, "node_id": node_id, "changed": True}
        elif name == "clone_node":
            source_id = _resolve_selector(operation.get("node"), aliases)
            alias = str(operation.get("alias", ""))
            if not alias or len(alias) > 128 or alias in aliases:
                raise LiquiGenGraphApiError("clone_node alias must be unique and 1-128 characters")
            node_id = deterministic_node_id(namespace, alias, set(graph.node_ids()))
            graph.create_node(
                graph.find_node(source_id),
                node_id=node_id,
                position=_position(operation.get("position", [0.0, 0.0])),
                label=str(operation.get("label", alias)),
                parameters=dict(operation.get("parameters", {})),
            )
            aliases[alias] = node_id
            result = {"op": name, "alias": alias, "node_id": node_id, "changed": True}
        elif name == "delete_node":
            node_id = _resolve_selector(operation.get("node"), aliases)
            changed = graph.delete_node(node_id).changed
            result = {"op": name, "node_id": node_id, "changed": changed}
        elif name == "set_parameter":
            node_id = _resolve_selector(operation.get("node"), aliases)
            changed = graph.set_parameter(
                node_id, str(operation["name"]), operation["value"]
            ).changed
            result = {"op": name, "node_id": node_id, "changed": changed}
        elif name == "add_parameter":
            node_id = _resolve_selector(operation.get("node"), aliases)
            changed = graph.add_parameter(
                node_id, str(operation["name"]), operation["value"]
            ).changed
            result = {"op": name, "node_id": node_id, "changed": changed}
        elif name == "set_keyframes":
            node_id = _resolve_selector(operation.get("node"), aliases)
            changed = graph.set_parameter_keyframes(
                node_id,
                str(operation["name"]),
                list(operation["keys"]),
                loop_mode=str(operation.get("loop_mode", "None")),
            ).changed
            result = {"op": name, "node_id": node_id, "changed": changed}
        elif name == "clear_keyframes":
            node_id = _resolve_selector(operation.get("node"), aliases)
            changed = graph.clear_parameter_keyframes(
                node_id,
                str(operation["name"]),
                operation["value"],
            ).changed
            result = {"op": name, "node_id": node_id, "changed": changed}
        elif name == "set_node_state":
            node_id = _resolve_selector(operation.get("node"), aliases)
            changed = graph.set_node_state(
                node_id,
                label=operation.get("label"),
                position=(_position(operation["position"]) if "position" in operation else None),
                disabled=operation.get("disabled"),
                on=operation.get("on"),
            ).changed
            result = {"op": name, "node_id": node_id, "changed": changed}
        elif name == "create_group":
            group_index = graph.create_group(
                comment=str(operation.get("comment", "")),
                color_index=int(operation.get("color_index", 0)),
                position=_position(operation.get("position", [0.0, 0.0])),
                size=_position(operation.get("size", [200.0, 110.0])),
            )
            result = {"op": name, "group_index": group_index, "changed": True}
        elif name == "update_group":
            group_index = int(operation["group_index"])
            changed = graph.update_group(
                group_index,
                comment=operation.get("comment"),
                color_index=operation.get("color_index"),
                position=(_position(operation["position"]) if "position" in operation else None),
                size=(_position(operation["size"]) if "size" in operation else None),
            ).changed
            result = {"op": name, "group_index": group_index, "changed": changed}
        elif name == "delete_group":
            group_index = int(operation["group_index"])
            changed = graph.delete_group(group_index).changed
            result = {"op": name, "group_index": group_index, "changed": changed}
        elif name == "create_note":
            note_index = graph.create_note(
                text=str(operation.get("text", "")),
                position=_position(operation.get("position", [0.0, 0.0])),
                size=_position(operation.get("size", [320.0, 80.0])),
            )
            result = {"op": name, "note_index": note_index, "changed": True}
        elif name == "update_note":
            note_index = int(operation["note_index"])
            changed = graph.update_note(
                note_index,
                text=operation.get("text"),
                position=(_position(operation["position"]) if "position" in operation else None),
                size=(_position(operation["size"]) if "size" in operation else None),
            ).changed
            result = {"op": name, "note_index": note_index, "changed": changed}
        elif name == "delete_note":
            note_index = int(operation["note_index"])
            changed = graph.delete_note(note_index).changed
            result = {"op": name, "note_index": note_index, "changed": changed}
        elif name == "set_project_setting":
            setting = str(operation["name"])
            changed = graph.set_project_setting(setting, operation["value"]).changed
            result = {"op": name, "name": setting, "changed": changed}
        elif name == "set_current_camera":
            node_id = _resolve_selector(operation.get("node"), aliases)
            changed = graph.set_current_camera(node_id).changed
            result = {"op": name, "node_id": node_id, "changed": changed}
        elif name in {"connect", "disconnect"}:
            from_node = _resolve_selector(operation.get("from_node"), aliases)
            to_node = _resolve_selector(operation.get("to_node"), aliases)
            from_pin = str(operation["from_pin"])
            to_pin = str(operation["to_pin"])
            if name == "connect":
                source_type = str(_plain_field(graph.find_node(from_node), "type"))
                target_type = str(_plain_field(graph.find_node(to_node), "type"))
                source_pins = set(schemas.get(source_type, {}).get("outgoing_pins", []))
                target_pins = set(schemas.get(target_type, {}).get("incoming_pins", []))
                if from_pin not in source_pins:
                    raise LiquiGenGraphApiError(
                        f"source pin is not available on {source_type}: {from_pin}"
                    )
                if to_pin not in target_pins:
                    raise LiquiGenGraphApiError(
                        f"target pin is not available on {target_type}: {to_pin}"
                    )
                signatures = {
                    (
                        item["from_pin"],
                        item["target_node_type"],
                        item["to_pin"],
                    )
                    for item in schemas.get(source_type, {}).get("outgoing_connections", [])
                }
                if (from_pin, target_type, to_pin) not in signatures:
                    raise LiquiGenGraphApiError(
                        "connection signature is not observed in installed official projects: "
                        f"{source_type}.{from_pin} -> {target_type}.{to_pin}"
                    )
            method = graph.connect if name == "connect" else graph.disconnect
            changed = method(
                from_node,
                from_pin,
                to_node,
                to_pin,
            ).changed
            result = {
                "op": name,
                "from_node": from_node,
                "from_pin": from_pin,
                "to_node": to_node,
                "to_pin": to_pin,
                "changed": changed,
            }
        else:
            raise LiquiGenGraphApiError(f"unsupported graph operation: {name}")
        results.append({"index": index, **result})

    graph.validate_links()
    materialize_references(document)
    encoded = encode_document(document)
    try:
        with destination_path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        readback = decode_document(destination_path.read_bytes())
        LiquiGenGraphDocument(readback).validate_links()
    except BaseException:
        destination_path.unlink(missing_ok=True)
        raise
    return {
        "interface": "liquigen.project.graph.transaction.v1",
        "source": str(source_path),
        "destination": str(destination_path),
        "source_sha256": source_hash,
        "destination_sha256": _sha256(destination_path),
        "bytes": destination_path.stat().st_size,
        "operation_count": len(results),
        "operations": results,
        "aliases": aliases,
        "node_count": len(graph.nodes),
        "validated": True,
        "overwritten": False,
    }


def interface_fingerprint(executable: str) -> dict[str, Any]:
    """Return name/schema capability evidence without hashing the LiquiGen binary."""

    _templates, schemas = load_template_catalog(executable)
    names = sorted(schemas)
    payload = "\n".join(
        f"{name}:{','.join(item['incoming_pins'])}:{','.join(item['outgoing_pins'])}:"
        + ",".join(
            f"{connection['from_pin']}->{connection['target_node_type']}.{connection['to_pin']}"
            for connection in item["outgoing_connections"]
        )
        for name, item in sorted(schemas.items())
    )
    return {
        "compatibility_policy": "interface_names_and_schemas",
        "executable_hash_required": False,
        "node_type_count": len(names),
        "node_types": names,
        "schema_fingerprint": hashlib.sha256(payload.encode()).hexdigest(),
    }


def _path_is_within(path: Path, roots: Sequence[Path]) -> bool:
    candidate = os.path.normcase(str(path.resolve(strict=False)))
    for root in roots:
        normalized = os.path.normcase(str(root.resolve(strict=False)))
        try:
            if os.path.commonpath((candidate, normalized)) == normalized:
                return True
        except ValueError:
            continue
    return False


def _parameter_snapshot(node: TaggedValue, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for parameter in array_items(object_require(node, "parameters")):
        name = str(_plain_field(parameter, "name"))
        if prefix and not name.startswith(prefix):
            continue
        value = object_get(parameter, "value") or object_get(parameter, "automation")
        if value is not None:
            result[name] = plain_value(value)
    return result


def prepare_unreal_water_project(
    source: str,
    destination: str,
    output_directory: str,
    *,
    executable: str,
    asset_name: str = "LiquiGen_BallDropSplash",
    frame_count: int = 64,
    destination_roots: Optional[Sequence[Path]] = None,
    source_roots: Optional[Sequence[Path]] = None,
) -> dict[str, Any]:
    """Preserve an installed official water preset and add one UE VAT export route."""

    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", asset_name):
        raise LiquiGenGraphApiError(
            "asset_name must start with a letter and contain only letters, digits, or underscores"
        )
    if not 1 <= int(frame_count) <= 4096:
        raise LiquiGenGraphApiError("frame_count must be between 1 and 4096")
    export_path = Path(output_directory).expanduser()
    if not export_path.is_absolute():
        raise LiquiGenGraphApiError("output_directory must be an absolute path")

    selected_destination_roots = tuple(destination_roots or allowed_roots_from_env())
    selected_source_roots = tuple(source_roots or selected_destination_roots)
    if not _path_is_within(export_path, selected_destination_roots):
        raise LiquiGenGraphApiError("output_directory is outside configured allowed roots")
    source_path = _resolve_source(source, selected_source_roots)
    official_roots = preset_roots_from_executable(executable)
    if not _path_is_within(source_path, official_roots):
        raise LiquiGenGraphApiError("source must be an installed official LiquiGen preset")

    document = decode_document(source_path.read_bytes())
    graph = LiquiGenGraphDocument(document)
    simulations = graph.nodes_of_type("Node_Simulation")
    if len(simulations) != 1:
        raise LiquiGenGraphApiError("source project must contain exactly one Node_Simulation")
    image_exports = graph.nodes_of_type("Node_Export_Image")
    if not image_exports:
        raise LiquiGenGraphApiError("official source preset must contain a Node_Export_Image")
    mesh_exports = graph.nodes_of_type("Node_Export_Mesh")
    if len(mesh_exports) > 1:
        raise LiquiGenGraphApiError("source project must contain at most one Node_Export_Mesh")

    _templates, schemas = load_template_catalog(executable)
    mesh_schema = schemas.get("Node_Export_Mesh")
    if mesh_schema is None:
        raise LiquiGenGraphApiError(
            "installed LiquiGen version does not expose Node_Export_Mesh in official projects"
        )
    required_parameters = {
        "filename",
        "directory",
        "export_kind",
        "export_velocity",
        "first_frame",
        "num_frames",
        "stride_frames",
        "numbering_offset",
        "compensate_framerate",
        "vat_max_lookup_width",
        "vat_max_texture_width",
    }
    available_parameters = {item["name"] for item in mesh_schema["parameters"]}
    image_schema = schemas.get("Node_Export_Image")
    if image_schema is None:
        raise LiquiGenGraphApiError(
            "installed LiquiGen version does not expose Node_Export_Image in official projects"
        )
    available_image_parameters = {item["name"] for item in image_schema["parameters"]}
    missing_image_parameters = sorted({"directory", "filename"} - available_image_parameters)
    if missing_image_parameters:
        raise LiquiGenGraphApiError(
            "installed LiquiGen version is missing paired image export parameters: "
            + ", ".join(missing_image_parameters)
        )
    missing_parameters = sorted(required_parameters - available_parameters)
    if missing_parameters:
        raise LiquiGenGraphApiError(
            "installed LiquiGen version is missing UE VAT parameters: "
            + ", ".join(missing_parameters)
        )

    simulation_id = int(_plain_field(simulations[0], "id"))
    appearance_before = _parameter_snapshot(simulations[0], "appearance.")
    target: int | str
    operations: list[dict[str, Any]] = []
    settings = object_get(document, "settings")
    if settings is not None and object_get(settings, "read_only") is not None:
        operations.append({"op": "set_project_setting", "name": "read_only", "value": False})
    if mesh_exports:
        target = int(_plain_field(mesh_exports[0], "id"))
        operations.append({"op": "set_node_state", "node": target, "disabled": False, "on": True})
    else:
        target = "ue_vat_export"
        operations.append(
            {
                "op": "create_node",
                "alias": target,
                "node_type": "Node_Export_Mesh",
                "position": [920.0, 240.0],
                "label": "UE 5.8 Water VAT Export",
            }
        )

    export_parameters: dict[str, Any] = {
        "filename": asset_name,
        "directory": str(export_path),
        "export_kind": "Vertex_Animated_Texture",
        "export_velocity": False,
        "first_frame": 0.0,
        "num_frames": float(frame_count),
        "stride_frames": 1.0,
        "numbering_offset": 0.0,
        "compensate_framerate": True,
        "vat_max_lookup_width": 2048.0,
        "vat_max_texture_width": 2048.0,
    }
    target_engine_parameter_available = "vat_target_engine" in available_parameters
    if target_engine_parameter_available:
        export_parameters["vat_target_engine"] = "Unreal"
    operations.extend(
        {"op": "set_parameter", "node": target, "name": name, "value": value}
        for name, value in export_parameters.items()
    )
    if not target_engine_parameter_available:
        operations.append(
            {
                "op": "add_parameter",
                "node": target,
                "name": "vat_target_engine",
                "value": "Unreal",
            }
        )
    for image_export in image_exports:
        image_export_id = int(_plain_field(image_export, "id"))
        operations.append(
            {
                "op": "set_node_state",
                "node": image_export_id,
                "disabled": False,
                "on": True,
            }
        )
        paired_image_parameters: dict[str, Any] = {
            "directory": str(export_path),
            "filename": f"{asset_name}_$(safename)",
        }
        if "first_frame" in available_image_parameters:
            paired_image_parameters["first_frame"] = 0.0
        if "unbounded_num_frames" in available_image_parameters:
            paired_image_parameters["unbounded_num_frames"] = float(frame_count)
        operations.extend(
            {
                "op": "set_parameter",
                "node": image_export_id,
                "name": name,
                "value": value,
            }
            for name, value in paired_image_parameters.items()
        )
    operations.extend(
        [
            {
                "op": "connect",
                "from_node": simulation_id,
                "from_pin": "Mesh",
                "to_node": target,
                "to_pin": "Mesh",
            },
            {
                "op": "create_group",
                "comment": "DCC-MCP · OFFICIAL WATER TO UE 5.8",
                "color_index": 4,
                "position": [680.0, 100.0],
                "size": [470.0, 300.0],
            },
            {
                "op": "create_note",
                "text": (
                    "DCC-MCP OFFICIAL WATER PRESET\n"
                    "1 · Keep the official simulation, collider, camera, and water appearance\n"
                    "2 · Route Simulation.Mesh into the UE 5.8 VAT exporter\n"
                    "3 · Export canonical FBX, position, rotation, lookup, and metadata assets\n"
                    "4 · Import through dcc-mcp-unreal and bind a translucent water material"
                ),
                "position": [660.0, -80.0],
                "size": [610.0, 145.0],
            },
        ]
    )

    result = apply_graph_transaction(
        str(source_path),
        destination,
        operations,
        executable=executable,
        destination_roots=selected_destination_roots,
        source_roots=selected_source_roots,
    )
    destination_path = Path(str(result["destination"]))
    readback = LiquiGenGraphDocument(decode_document(destination_path.read_bytes()))
    readback_simulations = readback.nodes_of_type("Node_Simulation")
    appearance_after = _parameter_snapshot(readback_simulations[0], "appearance.")
    if appearance_after != appearance_before:
        destination_path.unlink(missing_ok=True)
        raise LiquiGenGraphApiError("official simulation appearance changed during preparation")

    return {
        **result,
        "effect": "official_water_preset",
        "source_kind": "installed_official_preset",
        "source_preset": source_path.stem,
        "asset_name": asset_name,
        "frame_count": int(frame_count),
        "output_directory": str(export_path),
        "appearance_preserved": True,
        "paired_image_export_enabled": True,
        "derived_project_writable": True,
        "vat_target_engine": "Unreal",
        "vat_target_engine_parameter_available": target_engine_parameter_available,
        "vat_target_engine_compatibility_mode": (
            "declared_parameter"
            if target_engine_parameter_available
            else "legacy_parameter_backfill"
        ),
        "graph_mutation_route": "transactional_project_document",
        "requires_cua": False,
    }


def create_liquid_chain_burst_project(
    source: str,
    destination: str,
    output_directory: str,
    *,
    executable: str,
    burst_count: int = 5,
    delay_seconds: float = 0.18,
    spacing_m: float = 2.6,
    export_profile: str = "ue_vat",
    destination_roots: Optional[Sequence[Path]] = None,
    source_roots: Optional[Sequence[Path]] = None,
) -> dict[str, Any]:
    """Compile and execute a connected, timed liquid-chain-burst graph."""

    if not 2 <= int(burst_count) <= 12:
        raise LiquiGenGraphApiError("burst_count must be between 2 and 12")
    if not 0.05 <= float(delay_seconds) <= 2.0:
        raise LiquiGenGraphApiError("delay_seconds must be between 0.05 and 2.0")
    if float(spacing_m) <= 0:
        raise LiquiGenGraphApiError("spacing_m must be greater than zero")
    if export_profile not in {"ue_vat", "alembic", "flipbook"}:
        raise LiquiGenGraphApiError("export_profile must be ue_vat, alembic, or flipbook")
    export_path = Path(output_directory).expanduser()
    if not export_path.is_absolute():
        raise LiquiGenGraphApiError("output_directory must be an absolute path")

    selected_destination_roots = tuple(destination_roots or allowed_roots_from_env())
    selected_source_roots = tuple(source_roots or selected_destination_roots)
    source_path = _resolve_source(source, selected_source_roots)
    document = decode_document(source_path.read_bytes())
    graph = LiquiGenGraphDocument(document)
    simulations = graph.nodes_of_type("Node_Simulation")
    if len(simulations) != 1:
        raise LiquiGenGraphApiError("source project must contain exactly one Node_Simulation")
    simulation_id = int(_plain_field(simulations[0], "id"))
    image_exports = graph.nodes_of_type("Node_Export_Image")
    if not image_exports:
        raise LiquiGenGraphApiError("source project must contain a Node_Export_Image")
    image_export_id = int(_plain_field(image_exports[0], "id"))
    settings = object_get(document, "settings")
    frames_per_second = 60.0
    if settings is not None:
        fps = object_get(settings, "frames_per_second")
        if fps is not None:
            frames_per_second = float(plain_value(fps))

    operations: list[dict[str, Any]] = [
        {
            "op": "set_project_setting",
            "name": "read_only",
            "value": False,
        },
        {
            "op": "set_project_setting",
            "name": "loop",
            "value": True,
        },
        {
            "op": "set_project_setting",
            "name": "loop_region",
            "value": [
                0.0,
                round((int(burst_count) - 1) * float(delay_seconds) + 2.0, 6),
            ],
        },
        {
            "op": "create_group",
            "comment": "DCC-MCP · KEYFRAMED CHAIN BURSTS",
            "color_index": 3,
            "position": [-165.0, -235.0],
            "size": [505.0, round(int(burst_count) * 105.0 + 155.0, 3)],
        },
        {
            "op": "create_note",
            "text": (
                "DCC-MCP GENERATED GRAPH\n"
                "1 · Primitive shapes define each burst source\n"
                "2 · Keyframed emitters stagger the chain timing\n"
                "3 · Typed links feed the shared liquid simulation\n"
                "4 · Render + Image/Mesh Export nodes provide UE flipbook and VAT assets"
            ),
            "position": [-165.0, -385.0],
            "size": [620.0, 125.0],
        },
        {
            "op": "set_parameter",
            "node": simulation_id,
            "name": "appearance.coloring_source",
            "value": "Single_Color",
        },
        {
            "op": "set_parameter",
            "node": simulation_id,
            "name": "appearance.albedo",
            "value": [1.0, 0.16, 0.015],
        },
        {
            "op": "set_parameter",
            "node": simulation_id,
            "name": "appearance.transmission",
            "value": [1.0, 0.04, 0.0],
        },
        {
            "op": "set_parameter",
            "node": simulation_id,
            "name": "appearance.absorption_strength",
            "value": 4.0,
        },
        {
            "op": "set_parameter",
            "node": simulation_id,
            "name": "appearance.emission",
            "value": 4.0,
        },
        {
            "op": "set_parameter",
            "node": simulation_id,
            "name": "appearance.emission_color",
            "value": [1.0, 0.035, 0.0],
        },
        {
            "op": "set_parameter",
            "node": simulation_id,
            "name": "appearance.roughness",
            "value": 0.16,
        },
        {
            "op": "set_parameter",
            "node": image_export_id,
            "name": "image_mode",
            "value": "Flipbook",
        },
        {
            "op": "set_parameter",
            "node": image_export_id,
            "name": "sizes.flipbook_col_row",
            "value": [8.0, 8.0],
        },
        {
            "op": "set_parameter",
            "node": image_export_id,
            "name": "sizes.sprite_size",
            "value": [256.0, 256.0],
        },
        {
            "op": "set_parameter",
            "node": image_export_id,
            "name": "sizes.flipbook_size",
            "value": [2048.0, 2048.0],
        },
        {
            "op": "set_parameter",
            "node": image_export_id,
            "name": "unbounded_num_frames",
            "value": 64.0,
        },
        {
            "op": "set_parameter",
            "node": image_export_id,
            "name": "directory",
            "value": str(export_path),
        },
        {
            "op": "set_parameter",
            "node": image_export_id,
            "name": "filename",
            "value": "LiquiGen_ChainBurst_$(safename)",
        },
    ]
    centre = (int(burst_count) - 1) / 2.0
    duration_frames = max(2.0, round(0.12 * frames_per_second, 6))
    for index in range(int(burst_count)):
        suffix = f"{index + 1:02d}"
        shape = f"burst_shape_{suffix}"
        emitter = f"burst_emitter_{suffix}"
        world_x = round((index - centre) * float(spacing_m), 6)
        start_frame = round(index * float(delay_seconds) * frames_per_second, 6)
        keys = []
        if start_frame > 0:
            keys.append({"position": 0.0, "value": 0.0, "interpolation": "Constant"})
        keys.extend(
            [
                {"position": start_frame, "value": 1.0, "interpolation": "Constant"},
                {
                    "position": round(start_frame + duration_frames, 6),
                    "value": 0.0,
                    "interpolation": "Constant",
                },
            ]
        )
        graph_y = round(-180.0 + index * 105.0, 3)
        operations.extend(
            [
                {
                    "op": "create_node",
                    "alias": shape,
                    "node_type": "Node_Shape_Primitive",
                    "position": [-120.0, graph_y],
                    "label": f"Burst {suffix} Source",
                    "parameters": {
                        "type": "Sphere",
                        "position": [world_x, 0.0, 1.2],
                        "sphere_radius": 0.75,
                    },
                },
                {
                    "op": "create_node",
                    "alias": emitter,
                    "node_type": "Node_Emitter",
                    "position": [95.0, graph_y],
                    "label": f"Burst {suffix} @ {start_frame / frames_per_second:.2f}s",
                    "parameters": {
                        "emission_location": "Volume",
                        "emission_mode": "Fill",
                        "fill_just_once": True,
                        "reset_previous": False,
                        "lifetime_range": [2.0, 3.0],
                        "dynamic_viscosity": 1.0016,
                        "velocity_speed": round(11.0 + index * 0.8, 6),
                        "velocity_direction_when_volume": "Fixed",
                        "velocity_fixed_direction": [0.0, 0.0, 1.0],
                    },
                },
                {
                    "op": "set_keyframes",
                    "node": emitter,
                    "name": "emitter_active",
                    "keys": keys,
                },
                {
                    "op": "connect",
                    "from_node": shape,
                    "from_pin": "Shape",
                    "to_node": emitter,
                    "to_pin": "Shapes",
                },
                {
                    "op": "connect",
                    "from_node": emitter,
                    "from_pin": "Emitter",
                    "to_node": simulation_id,
                    "to_pin": "Emitters",
                },
            ]
        )

    if export_profile in {"ue_vat", "alembic"}:
        export_kind = "Vertex_Animated_Texture" if export_profile == "ue_vat" else "Alembic"
        operations.extend(
            [
                {
                    "op": "create_node",
                    "alias": "mesh_export",
                    "node_type": "Node_Export_Mesh",
                    "position": [910.0, 255.0],
                    "label": (
                        "UE 5.8 VAT Export" if export_profile == "ue_vat" else "Alembic Export"
                    ),
                    "parameters": {
                        "filename": "LiquiGen_ChainBurst",
                        "directory": str(export_path),
                        "export_kind": export_kind,
                        "first_frame": 0.0,
                        "num_frames": 64.0,
                        "stride_frames": 1.0,
                        "vat_max_lookup_width": 2048.0,
                        "vat_max_texture_width": 2048.0,
                    },
                },
                {
                    "op": "connect",
                    "from_node": simulation_id,
                    "from_pin": "Mesh",
                    "to_node": "mesh_export",
                    "to_pin": "Mesh",
                },
            ]
        )
        if export_profile == "ue_vat":
            operations.append(
                {
                    "op": "add_parameter",
                    "node": "mesh_export",
                    "name": "vat_target_engine",
                    "value": "Unreal",
                }
            )

    result = apply_graph_transaction(
        str(source_path),
        destination,
        operations,
        executable=executable,
        destination_roots=selected_destination_roots,
        source_roots=selected_source_roots,
    )
    return {
        **result,
        "effect": "liquid_chain_burst",
        "burst_count": int(burst_count),
        "delay_seconds": float(delay_seconds),
        "spacing_m": float(spacing_m),
        "frames_per_second": frames_per_second,
        "export_profile": export_profile,
        "output_directory": str(export_path),
        "graph_mutation_route": "transactional_project_document",
        "requires_cua": False,
    }


__all__ = [
    "LiquiGenGraphApiError",
    "apply_graph_transaction",
    "create_liquid_chain_burst_project",
    "inspect_project_graph",
    "interface_fingerprint",
    "list_node_schemas",
    "load_template_catalog",
    "prepare_unreal_water_project",
]
