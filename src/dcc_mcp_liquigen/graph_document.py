"""Version-tolerant graph operations for decoded LiquiGen projects."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable, Optional

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
    TaggedValue,
    array_items,
    clone_value,
    object_get,
    object_items,
    object_require,
    object_set,
    plain_value,
    resolve,
)


class LiquiGenGraphError(RuntimeError):
    """A graph operation violates the project or transaction contract."""


def _string(value: str) -> TaggedValue:
    return TaggedValue(TAG_STRING, value)


def _boolean(value: bool) -> TaggedValue:
    return TaggedValue(TAG_BOOL, bool(value))


def _integer(value: int) -> TaggedValue:
    return TaggedValue(TAG_I64, int(value))


def _number(value: float) -> TaggedValue:
    number = float(value)
    if not math.isfinite(number):
        raise LiquiGenGraphError("numeric values must be finite")
    return TaggedValue(TAG_F64, number)


def _vector(values: Iterable[float]) -> TaggedValue:
    result = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in result):
        raise LiquiGenGraphError("numeric values must be finite")
    tags = {2: TAG_F64X2, 3: TAG_F64X3, 4: TAG_F64X4}
    try:
        tag = tags[len(result)]
    except KeyError as error:
        raise LiquiGenGraphError("numeric vectors must have two, three, or four values") from error
    return TaggedValue(tag, result)


def _array(values: Iterable[TaggedValue]) -> TaggedValue:
    return TaggedValue(TAG_ARRAY, list(values))


def _object(entries: Iterable[tuple[str, TaggedValue]]) -> TaggedValue:
    return TaggedValue(TAG_OBJECT, [(_string(key), value) for key, value in entries])


def _plain_scalar(value: Any, *, existing: Optional[TaggedValue] = None) -> TaggedValue:
    current = resolve(existing) if existing is not None else None
    if isinstance(value, bool):
        if current is not None and current.tag != TAG_BOOL:
            raise LiquiGenGraphError("parameter type mismatch: expected the existing boolean type")
        return _boolean(value)
    if isinstance(value, str):
        if current is not None and current.tag != TAG_STRING:
            raise LiquiGenGraphError("parameter type mismatch: expected the existing string type")
        return _string(value)
    if isinstance(value, int) and not isinstance(value, bool):
        if current is not None and current.tag == TAG_F64:
            return _number(value)
        if current is not None and current.tag != TAG_I64:
            raise LiquiGenGraphError("parameter type mismatch: expected the existing integer type")
        return _integer(value)
    if isinstance(value, float):
        if current is not None and current.tag != TAG_F64:
            raise LiquiGenGraphError("parameter type mismatch: expected the existing floating type")
        return _number(value)
    if isinstance(value, (list, tuple)):
        if current is not None and current.tag == TAG_ARRAY:
            existing_items = array_items(current)
            if len(value) != len(existing_items):
                raise LiquiGenGraphError("parameter array length does not match the existing value")
            return _array(
                _plain_scalar(item, existing=existing_items[index])
                for index, item in enumerate(value)
            )
        if current is not None and current.tag not in (TAG_F64X2, TAG_F64X3, TAG_F64X4):
            raise LiquiGenGraphError("parameter type mismatch: expected the existing vector type")
        result = _vector(value)
        if current is not None and result.tag != current.tag:
            raise LiquiGenGraphError("parameter vector length does not match the existing value")
        return result
    raise LiquiGenGraphError(
        "only boolean, string, integer, float, and numeric-vector values are supported"
    )


def _field_plain(value: TaggedValue, key: str) -> Any:
    return plain_value(object_require(value, key))


def _set_field_plain(value: TaggedValue, key: str, child: Any) -> None:
    existing = object_get(value, key)
    object_set(value, key, _plain_scalar(child, existing=existing))


def _remove_field(value: TaggedValue, key: str) -> None:
    items = object_items(value)
    items[:] = [(item_key, child) for item_key, child in items if resolve(item_key).value != key]


def _finite_pair(value: Iterable[float], label: str) -> tuple[float, float]:
    result = tuple(float(item) for item in value)
    if len(result) != 2 or any(not math.isfinite(item) for item in result):
        raise LiquiGenGraphError(f"{label} must contain exactly two finite numbers")
    return result[0], result[1]


def deterministic_node_id(namespace: str, alias: str, occupied: set[int]) -> int:
    """Return a stable signed 64-bit ID without relying on a host version or hash."""

    for nonce in range(1024):
        digest = hashlib.sha256(f"{namespace}\0{alias}\0{nonce}".encode()).digest()
        candidate = int.from_bytes(digest[:8], "little", signed=True)
        if candidate != 0 and candidate not in occupied:
            return candidate
    raise LiquiGenGraphError("could not allocate a unique deterministic node ID")


@dataclass
class GraphMutationResult:
    operation: str
    node_id: Optional[int] = None
    changed: bool = True


class LiquiGenGraphDocument:
    """Mutable graph view backed by a decoded tagged document."""

    def __init__(self, root: TaggedValue) -> None:
        self.root = root
        self.graph = object_require(root, "graph")
        self.nodes_value = object_require(self.graph, "nodes")
        self.nodes = array_items(self.nodes_value)
        self.groups = array_items(object_require(self.graph, "groups"))
        self.notes = array_items(object_require(self.graph, "notes"))
        self._validate_identity()

    def _validate_identity(self) -> None:
        if _field_plain(self.root, "app_id") != "liquigen":
            raise LiquiGenGraphError("project app_id is not liquigen")
        ids = self.node_ids()
        if len(ids) != len(set(ids)):
            raise LiquiGenGraphError("project contains duplicate node IDs")

    def node_ids(self) -> list[int]:
        return [int(_field_plain(node, "id")) for node in self.nodes]

    def find_node(self, node_id: int) -> TaggedValue:
        selected = int(node_id)
        for node in self.nodes:
            if int(_field_plain(node, "id")) == selected:
                return node
        raise LiquiGenGraphError(f"node does not exist: {selected}")

    def nodes_of_type(self, node_type: str) -> list[TaggedValue]:
        return [node for node in self.nodes if _field_plain(node, "type") == node_type]

    def node_snapshot(self, node: TaggedValue) -> dict[str, Any]:
        data = plain_value(node)
        return {
            "id": int(data["id"]),
            "type": str(data["type"]),
            "label": str(data.get("label", "")),
            "disabled": bool(data.get("disabled", False)),
            "on": bool(data.get("on", True)),
            "position": data.get("pos", [0.0, 0.0]),
            "parameters": data.get("parameters", []),
            "links": data.get("links", []),
        }

    def snapshot(self) -> dict[str, Any]:
        result = {
            "graph_id": int(_field_plain(self.graph, "id")),
            "node_count": len(self.nodes),
            "group_count": len(self.groups),
            "note_count": len(self.notes),
            "nodes": [self.node_snapshot(node) for node in self.nodes],
            "groups": [plain_value(group) for group in self.groups],
            "notes": [plain_value(note) for note in self.notes],
        }
        settings = object_get(self.root, "settings")
        if settings is not None:
            result["settings"] = plain_value(settings)
        current_camera = object_get(self.root, "current_camera")
        if current_camera is not None:
            result["current_camera"] = int(plain_value(current_camera))
        default_camera = object_get(self.root, "default_camera")
        if default_camera is not None:
            result["default_camera"] = self.node_snapshot(default_camera)
        for name in ("app_version", "project_version", "tags"):
            value = object_get(self.root, name)
            if value is not None:
                result[name] = plain_value(value)
        return result

    def create_group(
        self,
        *,
        comment: str,
        color_index: int,
        position: Iterable[float],
        size: Iterable[float],
    ) -> int:
        selected_size = _finite_pair(size, "group size")
        if selected_size[0] <= 0 or selected_size[1] <= 0:
            raise LiquiGenGraphError("group size must be positive")
        self.groups.append(
            _object(
                [
                    ("comment", _string(str(comment))),
                    ("color_idx", _integer(int(color_index))),
                    ("pos", _vector(_finite_pair(position, "group position"))),
                    ("size", _vector(selected_size)),
                ]
            )
        )
        return len(self.groups) - 1

    def update_group(
        self,
        index: int,
        *,
        comment: Optional[str] = None,
        color_index: Optional[int] = None,
        position: Optional[Iterable[float]] = None,
        size: Optional[Iterable[float]] = None,
    ) -> GraphMutationResult:
        try:
            group = self.groups[int(index)]
        except (IndexError, TypeError) as error:
            raise LiquiGenGraphError(f"graph group does not exist: {index}") from error
        if int(index) < 0:
            raise LiquiGenGraphError(f"graph group does not exist: {index}")
        if comment is not None:
            _set_field_plain(group, "comment", str(comment))
        if color_index is not None:
            _set_field_plain(group, "color_idx", int(color_index))
        if position is not None:
            _set_field_plain(group, "pos", list(_finite_pair(position, "group position")))
        if size is not None:
            selected_size = _finite_pair(size, "group size")
            if selected_size[0] <= 0 or selected_size[1] <= 0:
                raise LiquiGenGraphError("group size must be positive")
            _set_field_plain(group, "size", list(selected_size))
        return GraphMutationResult("update_group")

    def delete_group(self, index: int) -> GraphMutationResult:
        selected = int(index)
        if selected < 0 or selected >= len(self.groups):
            raise LiquiGenGraphError(f"graph group does not exist: {index}")
        del self.groups[selected]
        return GraphMutationResult("delete_group")

    def create_note(
        self,
        *,
        text: str,
        position: Iterable[float],
        size: Iterable[float],
    ) -> int:
        selected_size = _finite_pair(size, "note size")
        if selected_size[0] <= 0 or selected_size[1] <= 0:
            raise LiquiGenGraphError("note size must be positive")
        self.notes.append(
            _object(
                [
                    ("text", _string(str(text))),
                    ("pos", _vector(_finite_pair(position, "note position"))),
                    ("size", _vector(selected_size)),
                ]
            )
        )
        return len(self.notes) - 1

    def update_note(
        self,
        index: int,
        *,
        text: Optional[str] = None,
        position: Optional[Iterable[float]] = None,
        size: Optional[Iterable[float]] = None,
    ) -> GraphMutationResult:
        selected = int(index)
        if selected < 0 or selected >= len(self.notes):
            raise LiquiGenGraphError(f"graph note does not exist: {index}")
        note = self.notes[selected]
        if text is not None:
            _set_field_plain(note, "text", str(text))
        if position is not None:
            _set_field_plain(note, "pos", list(_finite_pair(position, "note position")))
        if size is not None:
            selected_size = _finite_pair(size, "note size")
            if selected_size[0] <= 0 or selected_size[1] <= 0:
                raise LiquiGenGraphError("note size must be positive")
            _set_field_plain(note, "size", list(selected_size))
        return GraphMutationResult("update_note")

    def delete_note(self, index: int) -> GraphMutationResult:
        selected = int(index)
        if selected < 0 or selected >= len(self.notes):
            raise LiquiGenGraphError(f"graph note does not exist: {index}")
        del self.notes[selected]
        return GraphMutationResult("delete_note")

    def set_project_setting(self, name: str, value: Any) -> GraphMutationResult:
        settings = object_get(self.root, "settings")
        if settings is None or object_get(settings, name) is None:
            raise LiquiGenGraphError(f"project setting does not exist: {name}")
        _set_field_plain(settings, name, value)
        return GraphMutationResult("set_project_setting")

    def set_current_camera(self, node_id: int) -> GraphMutationResult:
        selected = int(node_id)
        camera_ids = {
            int(_field_plain(node, "id"))
            for node in self.nodes
            if _field_plain(node, "type") == "Node_Camera"
        }
        default_camera = object_get(self.root, "default_camera")
        if default_camera is not None:
            camera_ids.add(int(_field_plain(default_camera, "id")))
        if selected not in camera_ids:
            raise LiquiGenGraphError(f"camera node does not exist: {selected}")
        current = object_get(self.root, "current_camera")
        if current is None:
            raise LiquiGenGraphError("project does not expose current_camera")
        object_set(self.root, "current_camera", _integer(selected))
        return GraphMutationResult("set_current_camera", selected)

    def create_node(
        self,
        template: TaggedValue,
        *,
        node_id: int,
        position: tuple[float, float],
        label: str = "",
        parameters: Optional[dict[str, Any]] = None,
    ) -> TaggedValue:
        occupied = set(self.node_ids())
        selected_id = int(node_id)
        if selected_id == 0 or selected_id in occupied:
            raise LiquiGenGraphError("new node ID must be nonzero and unique")
        node = clone_value(template)
        _set_field_plain(node, "id", selected_id)
        _set_field_plain(node, "pos", list(position))
        _set_field_plain(node, "label", label)
        links = object_require(node, "links")
        array_items(links).clear()
        self.nodes.append(node)
        for name, value in (parameters or {}).items():
            self.set_parameter(selected_id, name, value)
        return node

    def delete_node(self, node_id: int) -> GraphMutationResult:
        selected_id = int(node_id)
        before = len(self.nodes)
        self.nodes[:] = [
            node for node in self.nodes if int(_field_plain(node, "id")) != selected_id
        ]
        if len(self.nodes) == before:
            raise LiquiGenGraphError(f"node does not exist: {selected_id}")
        for node in self.nodes:
            links = array_items(object_require(node, "links"))
            links[:] = [link for link in links if int(_field_plain(link, "to_node")) != selected_id]
        return GraphMutationResult("delete_node", selected_id)

    def set_node_state(
        self,
        node_id: int,
        *,
        label: Optional[str] = None,
        position: Optional[tuple[float, float]] = None,
        disabled: Optional[bool] = None,
        on: Optional[bool] = None,
    ) -> GraphMutationResult:
        node = self.find_node(node_id)
        if label is not None:
            _set_field_plain(node, "label", label)
        if position is not None:
            _set_field_plain(node, "pos", list(position))
        if disabled is not None:
            _set_field_plain(node, "disabled", disabled)
        if on is not None:
            _set_field_plain(node, "on", on)
        return GraphMutationResult("set_node_state", int(node_id))

    def _parameter(self, node: TaggedValue, name: str) -> TaggedValue:
        parameters = array_items(object_require(node, "parameters"))
        for parameter in parameters:
            if _field_plain(parameter, "name") == name:
                return parameter
        raise LiquiGenGraphError(f"node parameter does not exist: {name}")

    def set_parameter(self, node_id: int, name: str, value: Any) -> GraphMutationResult:
        parameter = self._parameter(self.find_node(node_id), name)
        existing = object_get(parameter, "value")
        if existing is None:
            raise LiquiGenGraphError(
                "animated parameter must be cleared before setting a static value"
            )
        object_set(parameter, "value", _plain_scalar(value, existing=existing))
        return GraphMutationResult("set_parameter", int(node_id))

    def add_parameter(self, node_id: int, name: str, value: Any) -> GraphMutationResult:
        node = self.find_node(node_id)
        parameters = array_items(object_require(node, "parameters"))
        if any(_field_plain(parameter, "name") == name for parameter in parameters):
            raise LiquiGenGraphError(f"node parameter already exists: {name}")
        parameters.append(
            _object(
                [
                    ("name", _string(name)),
                    ("value", _plain_scalar(value)),
                ]
            )
        )
        return GraphMutationResult("add_parameter", int(node_id))

    def set_parameter_keyframes(
        self,
        node_id: int,
        name: str,
        keys: list[dict[str, Any]],
        *,
        loop_mode: str = "None",
    ) -> GraphMutationResult:
        if not 1 <= len(keys) <= 4096:
            raise LiquiGenGraphError("keyframe count must be between 1 and 4096")
        last_position = -math.inf
        key_values = []
        for item in keys:
            position = float(item["position"])
            value = float(item["value"])
            if not math.isfinite(position) or not math.isfinite(value) or position < last_position:
                raise LiquiGenGraphError("keyframes must have finite, nondecreasing positions")
            last_position = position
            interpolation = str(item.get("interpolation", "Constant"))
            if interpolation not in {"Constant", "Linear", "Smooth"}:
                raise LiquiGenGraphError(
                    "keyframe interpolation must be Constant, Linear, or Smooth"
                )
            handle_type = "Auto_Clamped" if interpolation != "Linear" else "Linear"
            tangent_mode = "Constant" if interpolation == "Constant" else "Free"

            def tangent(delta: float, mode: str = tangent_mode) -> TaggedValue:
                return _object(
                    [
                        ("mode", _string(mode)),
                        ("delta_time", _number(delta)),
                        ("delta_value", _number(0.0)),
                    ]
                )

            key_values.append(
                _object(
                    [
                        ("value", _number(value)),
                        ("position", _number(position)),
                        ("handle_type", _string(handle_type)),
                        ("tangent_left", tangent(-3.0)),
                        ("tangent_right", tangent(3.0)),
                    ]
                )
            )
        automation = _object(
            [
                ("disabled", _boolean(False)),
                (
                    "lanes",
                    _array(
                        [
                            _object(
                                [
                                    ("visible", _boolean(True)),
                                    ("loop_mode", _string(loop_mode)),
                                    ("keys", _array(key_values)),
                                ]
                            )
                        ]
                    ),
                ),
            ]
        )
        parameter = self._parameter(self.find_node(node_id), name)
        _remove_field(parameter, "value")
        object_set(parameter, "automation", automation)
        return GraphMutationResult("set_parameter_keyframes", int(node_id))

    def clear_parameter_keyframes(
        self,
        node_id: int,
        name: str,
        value: Any,
    ) -> GraphMutationResult:
        parameter = self._parameter(self.find_node(node_id), name)
        automation = object_get(parameter, "automation")
        if automation is None:
            raise LiquiGenGraphError("parameter does not contain keyframe automation")
        _remove_field(parameter, "automation")
        object_set(parameter, "value", _plain_scalar(value))
        return GraphMutationResult("clear_parameter_keyframes", int(node_id))

    def connect(
        self,
        from_node: int,
        from_pin: str,
        to_node: int,
        to_pin: str,
    ) -> GraphMutationResult:
        source = self.find_node(from_node)
        self.find_node(to_node)
        links = array_items(object_require(source, "links"))
        requested = (str(from_pin), str(to_pin), int(to_node))
        for link in links:
            current = (
                str(_field_plain(link, "from_pin")),
                str(_field_plain(link, "to_pin")),
                int(_field_plain(link, "to_node")),
            )
            if current == requested:
                return GraphMutationResult("connect", int(from_node), changed=False)
        links.append(
            _object(
                [
                    ("from_pin", _string(requested[0])),
                    ("to_pin", _string(requested[1])),
                    ("to_node", _integer(requested[2])),
                ]
            )
        )
        return GraphMutationResult("connect", int(from_node))

    def disconnect(
        self,
        from_node: int,
        from_pin: str,
        to_node: int,
        to_pin: str,
    ) -> GraphMutationResult:
        source = self.find_node(from_node)
        links = array_items(object_require(source, "links"))
        before = len(links)
        links[:] = [
            link
            for link in links
            if not (
                str(_field_plain(link, "from_pin")) == str(from_pin)
                and str(_field_plain(link, "to_pin")) == str(to_pin)
                and int(_field_plain(link, "to_node")) == int(to_node)
            )
        ]
        return GraphMutationResult("disconnect", int(from_node), changed=len(links) != before)

    def validate_links(self) -> None:
        ids = set(self.node_ids())
        for node in self.nodes:
            for link in array_items(object_require(node, "links")):
                target = int(_field_plain(link, "to_node"))
                if target not in ids:
                    raise LiquiGenGraphError(f"link targets a missing node: {target}")


__all__ = [
    "GraphMutationResult",
    "LiquiGenGraphDocument",
    "LiquiGenGraphError",
    "deterministic_node_id",
]
