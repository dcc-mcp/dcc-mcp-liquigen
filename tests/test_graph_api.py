from __future__ import annotations

from pathlib import Path

import pytest

from dcc_mcp_liquigen.graph_api import (
    LiquiGenGraphApiError,
    apply_graph_transaction,
    inspect_project_graph,
    interface_fingerprint,
    list_node_schemas,
    prepare_unreal_water_project,
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
    encode_document,
)


def _s(value: str) -> TaggedValue:
    return TaggedValue(TAG_STRING, value)


def _o(**values: TaggedValue) -> TaggedValue:
    return TaggedValue(TAG_OBJECT, [(_s(key), value) for key, value in values.items()])


def _a(*values: TaggedValue) -> TaggedValue:
    return TaggedValue(TAG_ARRAY, list(values))


def _node(
    node_type: str,
    node_id: int,
    *links: tuple[str, str, int],
    parameters: list[TaggedValue] | None = None,
) -> TaggedValue:
    parameter_name = "emitter_active" if node_type == "Node_Emitter" else "quality"
    parameter_value = (
        TaggedValue(TAG_BOOL, True) if node_type == "Node_Emitter" else TaggedValue(TAG_F64, 1.0)
    )
    return _o(
        type=_s(node_type),
        id=TaggedValue(TAG_I64, node_id),
        disabled=TaggedValue(TAG_BOOL, False),
        on=TaggedValue(TAG_BOOL, True),
        pos=TaggedValue(TAG_F64X2, (0.0, 0.0)),
        label=_s(""),
        parameters=_a(
            *(
                parameters
                or [
                    _o(name=_s(parameter_name), value=parameter_value),
                    _o(name=_s("direction"), value=TaggedValue(TAG_F64X3, (0.0, 0.0, 1.0))),
                ]
            ),
        ),
        links=_a(
            *(
                _o(
                    from_pin=_s(from_pin),
                    to_pin=_s(to_pin),
                    to_node=TaggedValue(TAG_I64, to_node),
                )
                for from_pin, to_pin, to_node in links
            )
        ),
        data=_o(),
        curve_datas=_o(),
    )


def _document(*nodes: TaggedValue, read_only: bool = False) -> bytes:
    return encode_document(
        _o(
            app_id=_s("liquigen"),
            app_version=_s("1.0.5"),
            settings=_o(
                loop=TaggedValue(TAG_BOOL, False),
                read_only=TaggedValue(TAG_BOOL, read_only),
                frames_per_second=TaggedValue(TAG_F64, 60.0),
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
    )


def _installation(tmp_path: Path) -> tuple[Path, Path, Path]:
    install = tmp_path / "install"
    presets = install / "presets_1_0_0"
    workspace = tmp_path / "workspace"
    presets.mkdir(parents=True)
    workspace.mkdir()
    executable = install / "LiquiGen.exe"
    executable.write_bytes(b"host")
    preset = presets / "graph-template.liquigen"
    preset.write_bytes(
        _document(
            _node("Node_Emitter", 20, ("Emitter", "Emitters", 10)),
            _node("Node_Simulation", 10),
            _node("Node_Camera", 30),
        )
    )
    source = workspace / "source.liquigen"
    source.write_bytes(_document(_node("Node_Simulation", 10)))
    return executable, source, workspace


def _parameter(name: str, value: TaggedValue) -> TaggedValue:
    return _o(name=_s(name), value=value)


def _water_installation(
    tmp_path: Path, *, expose_target_engine: bool = True
) -> tuple[Path, Path, Path]:
    install = tmp_path / "install"
    presets = install / "presets_1_0_0"
    workspace = tmp_path / "workspace"
    presets.mkdir(parents=True)
    workspace.mkdir()
    executable = install / "LiquiGen.exe"
    executable.write_bytes(b"host")
    (presets / "vat-template.liquigen").write_bytes(
        _document(
            _node("Node_Simulation", 10, ("Mesh", "Mesh", 40)),
            _node(
                "Node_Export_Mesh",
                40,
                parameters=[
                    _parameter("filename", _s("Template")),
                    _parameter("directory", _s("C:/template")),
                    _parameter("export_kind", _s("Vertex_Animated_Texture")),
                    _parameter("export_velocity", TaggedValue(TAG_BOOL, False)),
                    _parameter("first_frame", TaggedValue(TAG_F64, 0.0)),
                    _parameter("num_frames", TaggedValue(TAG_F64, 64.0)),
                    _parameter("stride_frames", TaggedValue(TAG_F64, 1.0)),
                    _parameter("numbering_offset", TaggedValue(TAG_F64, 0.0)),
                    _parameter("compensate_framerate", TaggedValue(TAG_BOOL, True)),
                    _parameter("vat_max_lookup_width", TaggedValue(TAG_F64, 2048.0)),
                    _parameter("vat_max_texture_width", TaggedValue(TAG_F64, 2048.0)),
                    *(
                        [_parameter("vat_target_engine", _s("Unreal"))]
                        if expose_target_engine
                        else []
                    ),
                ],
            ),
        )
    )
    source = presets / "ball_drop_splash.liquigen"
    source.write_bytes(
        _document(
            _node(
                "Node_Simulation",
                10,
                parameters=[
                    _parameter("appearance.albedo", TaggedValue(TAG_F64X3, (0.08, 0.32, 0.55))),
                    _parameter("appearance.refractive_index", TaggedValue(TAG_F64, 1.33)),
                    _parameter("appearance.emission", TaggedValue(TAG_F64, 0.0)),
                ],
            ),
            _node(
                "Node_Export_Image",
                30,
                parameters=[
                    _parameter("directory", _s("C:/official/read-only")),
                    _parameter("filename", _s("ball_drop_splash")),
                ],
            ),
            read_only=True,
        )
    )
    return executable, source, workspace


def test_prepare_unreal_water_project_preserves_official_appearance_and_adds_vat(tmp_path: Path):
    executable, source, workspace = _water_installation(tmp_path)
    destination = workspace / "ball-drop-water-ue58.liquigen"
    output = workspace / "exports"

    result = prepare_unreal_water_project(
        str(source),
        str(destination),
        str(output),
        executable=str(executable),
        asset_name="LiquiGen_BallDropSplash",
        frame_count=72,
        destination_roots=[workspace],
        source_roots=[source.parent, workspace],
    )
    snapshot = inspect_project_graph(str(destination), roots=[workspace])
    simulation = next(item for item in snapshot["nodes"] if item["type"] == "Node_Simulation")
    mesh_export = next(item for item in snapshot["nodes"] if item["type"] == "Node_Export_Mesh")
    image_export = next(item for item in snapshot["nodes"] if item["type"] == "Node_Export_Image")
    parameters = {item["name"]: item["value"] for item in mesh_export["parameters"]}
    appearance = {item["name"]: item["value"] for item in simulation["parameters"]}

    assert appearance["appearance.albedo"] == [0.08, 0.32, 0.55]
    assert appearance["appearance.refractive_index"] == 1.33
    assert appearance["appearance.emission"] == 0.0
    assert image_export["disabled"] is True
    assert snapshot["settings"]["read_only"] is False
    assert parameters["filename"] == "LiquiGen_BallDropSplash"
    assert parameters["directory"] == str(output)
    assert parameters["export_kind"] == "Vertex_Animated_Texture"
    assert parameters["num_frames"] == 72.0
    assert parameters["vat_target_engine"] == "Unreal"
    assert simulation["links"][-1]["to_node"] == mesh_export["id"]
    assert snapshot["notes"][-1]["text"].startswith("DCC-MCP OFFICIAL WATER PRESET")
    assert result["effect"] == "official_water_preset"
    assert result["source_kind"] == "installed_official_preset"
    assert result["source_preset"] == "ball_drop_splash"
    assert result["appearance_preserved"] is True
    assert result["requires_cua"] is False


def test_prepare_unreal_water_project_backfills_target_engine_for_legacy_versions(
    tmp_path: Path,
):
    executable, source, workspace = _water_installation(tmp_path, expose_target_engine=False)

    result = prepare_unreal_water_project(
        str(source),
        str(workspace / "water-default-target.liquigen"),
        str(workspace / "exports"),
        executable=str(executable),
        destination_roots=[workspace],
        source_roots=[source.parent, workspace],
    )
    snapshot = inspect_project_graph(result["destination"], roots=[workspace])
    mesh_export = next(item for item in snapshot["nodes"] if item["type"] == "Node_Export_Mesh")

    parameters = {item["name"]: item["value"] for item in mesh_export["parameters"]}
    assert parameters["vat_target_engine"] == "Unreal"
    assert result["vat_target_engine"] == "Unreal"
    assert result["vat_target_engine_parameter_available"] is False
    assert result["vat_target_engine_compatibility_mode"] == "legacy_parameter_backfill"


def test_schema_catalog_and_fingerprint_use_named_interfaces(tmp_path: Path):
    executable, _source, _workspace = _installation(tmp_path)

    result = list_node_schemas(str(executable))
    fingerprint = interface_fingerprint(str(executable))

    assert [item["node_type"] for item in result["node_schemas"]] == [
        "Node_Camera",
        "Node_Emitter",
        "Node_Simulation",
    ]
    assert result["connection_signatures"] == [
        {
            "source_node_type": "Node_Emitter",
            "from_pin": "Emitter",
            "target_node_type": "Node_Simulation",
            "to_pin": "Emitters",
        }
    ]
    assert fingerprint["executable_hash_required"] is False
    assert fingerprint["compatibility_policy"] == "interface_names_and_schemas"
    assert fingerprint["node_type_count"] == 3


def test_apply_graph_transaction_creates_connects_animates_and_validates(tmp_path: Path):
    executable, source, workspace = _installation(tmp_path)
    destination = workspace / "result.liquigen"

    result = apply_graph_transaction(
        str(source),
        str(destination),
        [
            {
                "op": "create_node",
                "alias": "burst_01",
                "node_type": "Node_Emitter",
                "position": [100.0, 30.0],
                "label": "Burst 01",
                "parameters": {"direction": [0.0, 0.0, 9.0]},
            },
            {
                "op": "set_keyframes",
                "node": "burst_01",
                "name": "emitter_active",
                "keys": [
                    {"position": 0.0, "value": 1.0},
                    {"position": 7.2, "value": 0.0},
                ],
            },
            {
                "op": "connect",
                "from_node": "burst_01",
                "from_pin": "Emitter",
                "to_node": 10,
                "to_pin": "Emitters",
            },
        ],
        executable=str(executable),
        destination_roots=[workspace],
        source_roots=[workspace],
    )
    snapshot = inspect_project_graph(str(destination), roots=[workspace])

    assert result["validated"] is True
    assert result["operation_count"] == 3
    assert result["overwritten"] is False
    assert snapshot["node_count"] == 2
    emitter = next(item for item in snapshot["nodes"] if item["type"] == "Node_Emitter")
    assert emitter["label"] == "Burst 01"
    assert emitter["links"][0]["to_node"] == 10
    assert emitter["parameters"][0]["automation"]["lanes"][0]["keys"][1]["position"] == 7.2


def test_apply_graph_transaction_rejects_unobserved_connection_pins(tmp_path: Path):
    executable, source, workspace = _installation(tmp_path)

    with pytest.raises(LiquiGenGraphApiError, match="source pin is not available"):
        apply_graph_transaction(
            str(source),
            str(workspace / "invalid.liquigen"),
            [
                {
                    "op": "create_node",
                    "alias": "burst_01",
                    "node_type": "Node_Emitter",
                },
                {
                    "op": "connect",
                    "from_node": "burst_01",
                    "from_pin": "Typo",
                    "to_node": 10,
                    "to_pin": "Emitters",
                },
            ],
            executable=str(executable),
            destination_roots=[workspace],
            source_roots=[workspace],
        )

    assert not (workspace / "invalid.liquigen").exists()


def test_apply_graph_transaction_exposes_annotations_settings_and_camera(tmp_path: Path):
    executable, source, workspace = _installation(tmp_path)
    destination = workspace / "annotated.liquigen"

    result = apply_graph_transaction(
        str(source),
        str(destination),
        [
            {
                "op": "create_node",
                "alias": "camera",
                "node_type": "Node_Camera",
            },
            {
                "op": "create_group",
                "comment": "CHAIN BURSTS",
                "position": [-200.0, -100.0],
                "size": [700.0, 320.0],
                "color_index": 3,
            },
            {
                "op": "create_note",
                "text": "Generated through DCC-MCP",
                "position": [-180.0, -80.0],
                "size": [360.0, 80.0],
            },
            {"op": "set_project_setting", "name": "loop", "value": True},
            {"op": "set_current_camera", "node": "camera"},
        ],
        executable=str(executable),
        destination_roots=[workspace],
        source_roots=[workspace],
    )
    snapshot = inspect_project_graph(str(destination), roots=[workspace])

    assert result["operation_count"] == 5
    assert snapshot["groups"][0]["comment"] == "CHAIN BURSTS"
    assert snapshot["notes"][0]["text"] == "Generated through DCC-MCP"
    assert snapshot["settings"]["loop"] is True
    assert snapshot["current_camera"] == result["aliases"]["camera"]
