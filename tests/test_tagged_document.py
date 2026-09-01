import struct

import pytest

from dcc_mcp_liquigen.tagged_document import (
    TAG_ARRAY,
    TAG_BOOL,
    TAG_F64,
    TAG_F64X3,
    TAG_I64,
    TAG_OBJECT,
    TAG_REFERENCE,
    TAG_STRING,
    TaggedDocumentError,
    TaggedValue,
    clone_value,
    decode_document,
    encode_document,
    materialize_references,
    object_require,
    object_set,
    plain_value,
    resolve,
)


def _string(value: str) -> bytes:
    encoded = value.encode()
    return bytes([TAG_STRING]) + len(encoded).to_bytes(4, "little") + encoded


def test_round_trip_preserves_backward_reference_offsets_byte_for_byte():
    shared = _string("Node_Emitter")
    # References point to the payload offset one byte after the original tag.
    data = bytearray([TAG_OBJECT])
    data += _string("type")
    shared_offset = len(data) + 1
    data += shared
    data += _string("aliases")
    data += bytes([TAG_ARRAY, TAG_REFERENCE]) + shared_offset.to_bytes(4, "little")
    data += bytes([TAG_REFERENCE]) + shared_offset.to_bytes(4, "little") + bytes([0x12, 0x12])

    root = decode_document(bytes(data))

    assert encode_document(root) == bytes(data)
    aliases = object_require(root, "aliases")
    assert [resolve(item).value for item in resolve(aliases).value] == [
        "Node_Emitter",
        "Node_Emitter",
    ]


def test_clone_retains_internal_sharing_and_encodes_after_original_document_is_gone():
    shared = TaggedValue(TAG_STRING, "Emitter")
    source = TaggedValue(
        TAG_OBJECT,
        [
            (TaggedValue(TAG_STRING, "name"), shared),
            (TaggedValue(TAG_STRING, "again"), TaggedValue(TAG_REFERENCE, shared)),
        ],
    )

    cloned = clone_value(source)
    encoded = encode_document(cloned)
    decoded = decode_document(encoded)

    assert plain_value(decoded) == {"name": "Emitter", "again": "Emitter"}
    assert resolve(object_require(decoded, "name")) is resolve(object_require(decoded, "again"))


def test_scalar_and_vector_tags_round_trip():
    root = TaggedValue(
        TAG_ARRAY,
        [
            TaggedValue(TAG_BOOL, True),
            TaggedValue(TAG_I64, -123),
            TaggedValue(TAG_F64, 2.5),
            TaggedValue(TAG_F64X3, (1.0, 2.0, 3.0)),
        ],
    )

    assert plain_value(decode_document(encode_document(root))) == [True, -123, 2.5, [1, 2, 3]]


def test_decoder_rejects_forward_reference_and_trailing_bytes():
    with pytest.raises(TaggedDocumentError, match="does not point backwards"):
        decode_document(bytes([TAG_REFERENCE]) + struct.pack("<I", 99))
    with pytest.raises(TaggedDocumentError, match="trailing"):
        decode_document(bytes([TAG_BOOL, 1, TAG_BOOL, 0]))


def test_materialize_repairs_reference_when_first_occurrence_is_replaced():
    shared = TaggedValue(TAG_STRING, "old")
    root = TaggedValue(
        TAG_OBJECT,
        [
            (TaggedValue(TAG_STRING, "first"), shared),
            (TaggedValue(TAG_STRING, "second"), TaggedValue(TAG_REFERENCE, shared)),
        ],
    )
    object_set(root, "first", TaggedValue(TAG_STRING, "new"))

    materialize_references(root)
    decoded = decode_document(encode_document(root))

    assert plain_value(decoded) == {"first": "new", "second": "old"}
