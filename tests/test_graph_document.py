from dcc_mcp_liquigen.graph_document import (
    LiquiGenGraphDocument,
    deterministic_node_id,
)
from dcc_mcp_liquigen.tagged_document import (
    TAG_ARRAY,
    TAG_BOOL,
    TAG_F64,
    TAG_F64X2,
    TAG_F64X3,
    TAG_I64,
    TAG_OBJECT,
    TAG_STRING,
    TaggedValue,
    decode_document,
    encode_document,
    object_require,
    plain_value,
)


def _s(value: str) -> TaggedValue:
    return TaggedValue(TAG_STRING, value)


def _o(**values: TaggedValue) -> TaggedValue:
    return TaggedValue(TAG_OBJECT, [(_s(key), value) for key, value in values.items()])


def _a(*values: TaggedValue) -> TaggedValue:
    return TaggedValue(TAG_ARRAY, list(values))


def _node(node_type: str, node_id: int, parameter_name: str = "strength") -> TaggedValue:
    return _o(
        type=_s(node_type),
        id=TaggedValue(TAG_I64, node_id),
        disabled=TaggedValue(TAG_BOOL, False),
        on=TaggedValue(TAG_BOOL, True),
        pos=TaggedValue(TAG_F64X2, (0.0, 0.0)),
        label=_s(""),
        parameters=_a(
            _o(name=_s(parameter_name), value=TaggedValue(TAG_F64, 1.0)),
            _o(name=_s("direction"), value=TaggedValue(TAG_F64X3, (0.0, 0.0, 1.0))),
            _o(name=_s("enabled"), value=TaggedValue(TAG_BOOL, True)),
        ),
        links=_a(),
        data=_o(),
        curve_datas=_o(),
    )


def _root(*nodes: TaggedValue) -> TaggedValue:
    return _o(
        app_id=_s("liquigen"),
        app_version=_s("1.0.5"),
        settings=_o(
            loop=TaggedValue(TAG_BOOL, False),
            frames_per_second=TaggedValue(TAG_F64, 60.0),
            loop_region=_a(
                TaggedValue(TAG_F64, 0.0),
                TaggedValue(TAG_F64, 2.0),
            ),
        ),
        current_camera=TaggedValue(TAG_I64, -1),
        default_camera=_node("Node_Camera", -1),
        graph=_o(
            id=TaggedValue(TAG_I64, 1),
            nodes=_a(*nodes),
            groups=_a(),
            notes=_a(),
        ),
    )


def test_graph_create_configure_connect_animate_and_round_trip():
    target = _node("Node_Simulation", 10)
    template = _node("Node_Emitter", 20)
    graph = LiquiGenGraphDocument(_root(target))

    created = graph.create_node(
        template,
        node_id=30,
        position=(120.0, 40.0),
        label="Burst 01",
        parameters={"strength": 4.5, "direction": [0.0, 0.0, 9.0]},
    )
    graph.connect(30, "Emitter", 10, "Emitters")
    graph.set_parameter_keyframes(
        30,
        "enabled",
        [
            {"position": 0.0, "value": 1.0},
            {"position": 7.2, "value": 0.0},
        ],
    )
    graph.validate_links()

    decoded = decode_document(encode_document(graph.root))
    result = LiquiGenGraphDocument(decoded).snapshot()

    assert result["node_count"] == 2
    emitter = next(item for item in result["nodes"] if item["id"] == 30)
    assert emitter["label"] == "Burst 01"
    assert emitter["position"] == [120.0, 40.0]
    assert emitter["links"] == [{"from_pin": "Emitter", "to_pin": "Emitters", "to_node": 10}]
    enabled = next(item for item in emitter["parameters"] if item["name"] == "enabled")
    assert enabled["automation"]["lanes"][0]["keys"][1]["position"] == 7.2
    assert "value" not in enabled
    assert plain_value(created)["type"] == "Node_Emitter"


def test_clear_parameter_keyframes_restores_a_static_value():
    graph = LiquiGenGraphDocument(_root(_node("Node_Emitter", 20)))
    graph.set_parameter_keyframes(
        20,
        "enabled",
        [
            {"position": 0.0, "value": 1.0},
            {"position": 7.2, "value": 0.0},
        ],
    )

    graph.clear_parameter_keyframes(20, "enabled", True)

    parameter = next(
        item for item in graph.snapshot()["nodes"][0]["parameters"] if item["name"] == "enabled"
    )
    assert parameter == {"name": "enabled", "value": True}


def test_delete_node_removes_incoming_links():
    source = _node("Node_Emitter", 20)
    target = _node("Node_Simulation", 10)
    graph = LiquiGenGraphDocument(_root(source, target))
    graph.connect(20, "Emitter", 10, "Emitters")

    graph.delete_node(10)
    graph.validate_links()

    assert graph.snapshot()["nodes"][0]["links"] == []


def test_deterministic_node_id_uses_name_contract_not_binary_hash():
    first = deterministic_node_id("project-a", "burst-01", set())
    second = deterministic_node_id("project-a", "burst-01", set())
    collision_avoided = deterministic_node_id("project-a", "burst-01", {first})

    assert first == second
    assert collision_avoided != first
    assert first != 0


def test_graph_nodes_remain_under_original_graph_object():
    graph = LiquiGenGraphDocument(_root(_node("Node_Simulation", 10)))
    graph.create_node(_node("Node_Emitter", 20), node_id=30, position=(1.0, 2.0))

    nodes = object_require(object_require(graph.root, "graph"), "nodes")
    assert len(nodes.value) == 2


def test_graph_exposes_groups_notes_settings_and_camera_selection():
    graph = LiquiGenGraphDocument(_root(_node("Node_Camera", 30)))

    group_index = graph.create_group(
        comment="CHAIN BURSTS",
        color_index=2,
        position=(-120.0, -40.0),
        size=(640.0, 280.0),
    )
    note_index = graph.create_note(
        text="Generated through DCC-MCP",
        position=(-100.0, -20.0),
        size=(300.0, 80.0),
    )
    graph.update_group(group_index, comment="CHAIN EXPLOSION")
    graph.update_note(note_index, text="Node graph generated through DCC-MCP")
    graph.set_project_setting("loop", True)
    graph.set_project_setting("loop_region", [0.0, 3.5])
    graph.set_current_camera(30)

    result = LiquiGenGraphDocument(decode_document(encode_document(graph.root))).snapshot()
    assert result["group_count"] == 1
    assert result["groups"][0]["comment"] == "CHAIN EXPLOSION"
    assert result["note_count"] == 1
    assert result["notes"][0]["text"] == "Node graph generated through DCC-MCP"
    assert result["settings"]["loop"] is True
    assert result["settings"]["loop_region"] == [0.0, 3.5]
    assert result["current_camera"] == 30
    assert result["default_camera"]["type"] == "Node_Camera"
