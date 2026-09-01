"""Bounded reader/writer for LiquiGen's tagged project container.

The container is a small self-describing object format used by ``.liquigen``
files.  Values carry one-byte tags; arrays and objects are sentinel-terminated,
and tag ``0x0f`` points backwards to an already serialized value payload.

This module deliberately models only the container.  Graph semantics and
version-specific node schemas live elsewhere.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Iterator, Optional

MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_VALUES = 1_000_000
MAX_DEPTH = 256
MAX_SCALAR_BYTES = 32 * 1024 * 1024

TAG_NULL = 0x00
TAG_BOOL = 0x01
TAG_I8 = 0x02
TAG_I16 = 0x03
TAG_I32 = 0x04
TAG_I64 = 0x05
TAG_I64X2 = 0x06
TAG_I64X3 = 0x07
TAG_I64X4 = 0x08
TAG_F64 = 0x09
TAG_F64X2 = 0x0A
TAG_F64X3 = 0x0B
TAG_F64X4 = 0x0C
TAG_BYTES = 0x0D
TAG_STRING = 0x0E
TAG_REFERENCE = 0x0F
TAG_ARRAY = 0x10
TAG_OBJECT = 0x11
TAG_END = 0x12


class TaggedDocumentError(RuntimeError):
    """The tagged document is malformed or exceeds a bounded contract."""


@dataclass(eq=False)
class TaggedValue:
    """One tagged value.

    ``value`` is a scalar, a list of values, a list of key/value tuples, or the
    referenced canonical ``TaggedValue`` for ``TAG_REFERENCE``.
    """

    tag: int
    value: Any
    source_offset: Optional[int] = None


class _Reader:
    def __init__(self, data: bytes) -> None:
        if not data or len(data) > MAX_DOCUMENT_BYTES:
            raise TaggedDocumentError("document is empty or exceeds the configured limit")
        self.data = data
        self.cursor = 0
        self.values_by_payload_offset: dict[int, TaggedValue] = {}
        self.value_count = 0

    def _take(self, count: int) -> bytes:
        if count < 0 or self.cursor + count > len(self.data):
            raise TaggedDocumentError(f"truncated value at byte offset {self.cursor}")
        result = self.data[self.cursor : self.cursor + count]
        self.cursor += count
        return result

    def _unpack(self, pattern: str) -> tuple[Any, ...]:
        return struct.unpack(pattern, self._take(struct.calcsize(pattern)))

    def read(self, depth: int = 0) -> TaggedValue:
        if depth > MAX_DEPTH:
            raise TaggedDocumentError("document nesting exceeds the configured limit")
        self.value_count += 1
        if self.value_count > MAX_VALUES:
            raise TaggedDocumentError("document value count exceeds the configured limit")
        source_offset = self.cursor
        tag = self._take(1)[0]
        payload_offset = self.cursor

        if tag == TAG_NULL:
            payload: Any = None
        elif tag == TAG_BOOL:
            raw = self._take(1)[0]
            if raw not in (0, 1):
                raise TaggedDocumentError(f"invalid boolean value at byte offset {source_offset}")
            payload = bool(raw)
        elif tag == TAG_I8:
            payload = self._unpack("<b")[0]
        elif tag == TAG_I16:
            payload = self._unpack("<h")[0]
        elif tag == TAG_I32:
            payload = self._unpack("<i")[0]
        elif tag == TAG_I64:
            payload = self._unpack("<q")[0]
        elif tag == TAG_I64X2:
            payload = self._unpack("<qq")
        elif tag == TAG_I64X3:
            payload = self._unpack("<qqq")
        elif tag == TAG_I64X4:
            payload = self._unpack("<qqqq")
        elif tag == TAG_F64:
            payload = self._unpack("<d")[0]
        elif tag == TAG_F64X2:
            payload = self._unpack("<dd")
        elif tag == TAG_F64X3:
            payload = self._unpack("<ddd")
        elif tag == TAG_F64X4:
            payload = self._unpack("<dddd")
        elif tag in (TAG_BYTES, TAG_STRING):
            length = self._unpack("<I")[0]
            if length > MAX_SCALAR_BYTES:
                raise TaggedDocumentError("scalar byte length exceeds the configured limit")
            raw = self._take(length)
            if tag == TAG_BYTES:
                payload = raw
            else:
                try:
                    payload = raw.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise TaggedDocumentError("string value is not valid UTF-8") from error
        elif tag == TAG_REFERENCE:
            target_offset = self._unpack("<I")[0]
            try:
                payload = self.values_by_payload_offset[target_offset]
            except KeyError as error:
                raise TaggedDocumentError(
                    f"reference at byte offset {source_offset} does not point backwards to a value"
                ) from error
        elif tag == TAG_ARRAY:
            payload = []
            placeholder = TaggedValue(tag, payload, source_offset)
            self.values_by_payload_offset[payload_offset] = placeholder
            while True:
                if self.cursor >= len(self.data):
                    raise TaggedDocumentError("unterminated array")
                if self.data[self.cursor] == TAG_END:
                    self.cursor += 1
                    return placeholder
                payload.append(self.read(depth + 1))
        elif tag == TAG_OBJECT:
            payload = []
            placeholder = TaggedValue(tag, payload, source_offset)
            self.values_by_payload_offset[payload_offset] = placeholder
            while True:
                if self.cursor >= len(self.data):
                    raise TaggedDocumentError("unterminated object")
                if self.data[self.cursor] == TAG_END:
                    self.cursor += 1
                    return placeholder
                key = self.read(depth + 1)
                if not isinstance(resolve(key).value, str):
                    raise TaggedDocumentError("object key is not a string")
                payload.append((key, self.read(depth + 1)))
        elif tag == TAG_END:
            raise TaggedDocumentError(
                f"unexpected container terminator at byte offset {source_offset}"
            )
        else:
            raise TaggedDocumentError(f"unknown tag 0x{tag:02x} at byte offset {source_offset}")

        result = TaggedValue(tag, payload, source_offset)
        self.values_by_payload_offset[payload_offset] = result
        return result


class _Writer:
    def __init__(self) -> None:
        self.data = bytearray()
        self.payload_offsets: dict[int, int] = {}
        self.value_count = 0

    def _pack(self, pattern: str, *values: Any) -> None:
        try:
            self.data.extend(struct.pack(pattern, *values))
        except (OverflowError, struct.error) as error:
            raise TaggedDocumentError(
                "scalar value cannot be encoded with its original tag"
            ) from error

    def write(self, value: TaggedValue, depth: int = 0) -> None:
        if depth > MAX_DEPTH:
            raise TaggedDocumentError("document nesting exceeds the configured limit")
        self.value_count += 1
        if self.value_count > MAX_VALUES:
            raise TaggedDocumentError("document value count exceeds the configured limit")
        tag = int(value.tag)
        self.data.append(tag)
        payload_offset = len(self.data)

        if tag == TAG_REFERENCE:
            target = resolve(value)
            try:
                target_offset = self.payload_offsets[id(target)]
            except KeyError as error:
                raise TaggedDocumentError("reference target has not been serialized yet") from error
            self._pack("<I", target_offset)
            return

        self.payload_offsets[id(value)] = payload_offset
        payload = value.value
        if tag == TAG_NULL:
            if payload is not None:
                raise TaggedDocumentError("null value has a non-null payload")
        elif tag == TAG_BOOL:
            self.data.append(1 if bool(payload) else 0)
        elif tag == TAG_I8:
            self._pack("<b", payload)
        elif tag == TAG_I16:
            self._pack("<h", payload)
        elif tag == TAG_I32:
            self._pack("<i", payload)
        elif tag == TAG_I64:
            self._pack("<q", payload)
        elif tag == TAG_I64X2:
            self._pack("<qq", *payload)
        elif tag == TAG_I64X3:
            self._pack("<qqq", *payload)
        elif tag == TAG_I64X4:
            self._pack("<qqqq", *payload)
        elif tag == TAG_F64:
            self._pack("<d", payload)
        elif tag == TAG_F64X2:
            self._pack("<dd", *payload)
        elif tag == TAG_F64X3:
            self._pack("<ddd", *payload)
        elif tag == TAG_F64X4:
            self._pack("<dddd", *payload)
        elif tag in (TAG_BYTES, TAG_STRING):
            raw = bytes(payload) if tag == TAG_BYTES else str(payload).encode("utf-8")
            if len(raw) > MAX_SCALAR_BYTES:
                raise TaggedDocumentError("scalar byte length exceeds the configured limit")
            self._pack("<I", len(raw))
            self.data.extend(raw)
        elif tag == TAG_ARRAY:
            for child in payload:
                self.write(child, depth + 1)
            self.data.append(TAG_END)
        elif tag == TAG_OBJECT:
            for key, child in payload:
                if not isinstance(resolve(key).value, str):
                    raise TaggedDocumentError("object key is not a string")
                self.write(key, depth + 1)
                self.write(child, depth + 1)
            self.data.append(TAG_END)
        else:
            raise TaggedDocumentError(f"tag 0x{tag:02x} cannot be encoded")


def decode_document(data: bytes) -> TaggedValue:
    """Decode one complete bounded document."""

    reader = _Reader(data)
    root = reader.read()
    if reader.cursor != len(data):
        raise TaggedDocumentError("document has trailing bytes")
    return root


def encode_document(root: TaggedValue) -> bytes:
    """Encode a document while preserving reference identity and ordering."""

    writer = _Writer()
    writer.write(root)
    if len(writer.data) > MAX_DOCUMENT_BYTES:
        raise TaggedDocumentError("encoded document exceeds the configured limit")
    return bytes(writer.data)


def resolve(value: TaggedValue) -> TaggedValue:
    """Resolve a reference chain to its canonical value."""

    seen: set[int] = set()
    while value.tag == TAG_REFERENCE:
        identity = id(value)
        if identity in seen:
            raise TaggedDocumentError("reference cycle detected")
        seen.add(identity)
        value = value.value
    return value


def object_items(value: TaggedValue) -> list[tuple[TaggedValue, TaggedValue]]:
    item = resolve(value)
    if item.tag != TAG_OBJECT:
        raise TaggedDocumentError("value is not an object")
    return item.value


def object_get(value: TaggedValue, key: str) -> Optional[TaggedValue]:
    for item_key, item_value in object_items(value):
        if resolve(item_key).value == key:
            return item_value
    return None


def object_require(value: TaggedValue, key: str) -> TaggedValue:
    result = object_get(value, key)
    if result is None:
        raise TaggedDocumentError(f"required object key is missing: {key}")
    return result


def object_set(value: TaggedValue, key: str, child: TaggedValue) -> None:
    items = object_items(value)
    for index, (item_key, _item_value) in enumerate(items):
        if resolve(item_key).value == key:
            items[index] = (item_key, child)
            return
    items.append((TaggedValue(TAG_STRING, key), child))


def array_items(value: TaggedValue) -> list[TaggedValue]:
    item = resolve(value)
    if item.tag != TAG_ARRAY:
        raise TaggedDocumentError("value is not an array")
    return item.value


def walk(value: TaggedValue, path: str = "$") -> Iterator[tuple[str, TaggedValue]]:
    item = resolve(value)
    yield path, item
    if item.tag == TAG_ARRAY:
        for index, child in enumerate(item.value):
            yield from walk(child, f"{path}[{index}]")
    elif item.tag == TAG_OBJECT:
        for key, child in item.value:
            yield from walk(child, f"{path}.{resolve(key).value}")


def clone_value(value: TaggedValue) -> TaggedValue:
    """Deep-clone a subtree, retaining shared references within that subtree."""

    clones: dict[int, TaggedValue] = {}

    def clone(item: TaggedValue) -> TaggedValue:
        canonical = resolve(item)
        identity = id(canonical)
        if identity in clones:
            return TaggedValue(TAG_REFERENCE, clones[identity])
        if canonical.tag == TAG_ARRAY:
            result = TaggedValue(TAG_ARRAY, [])
            clones[identity] = result
            result.value.extend(clone(child) for child in canonical.value)
            return result
        if canonical.tag == TAG_OBJECT:
            result = TaggedValue(TAG_OBJECT, [])
            clones[identity] = result
            result.value.extend((clone(key), clone(child)) for key, child in canonical.value)
            return result
        payload = canonical.value
        if isinstance(payload, bytes):
            payload = bytes(payload)
        elif isinstance(payload, tuple):
            payload = tuple(payload)
        result = TaggedValue(canonical.tag, payload)
        clones[identity] = result
        return result

    return clone(value)


def materialize_references(value: TaggedValue) -> None:
    """Replace references reachable from ``value`` with independent values.

    Official LiquiGen projects currently use references for string interning.
    Materializing before a structural edit prevents a removed or replaced first
    occurrence from leaving a dangling backward offset in the new document.
    """

    active: set[int] = set()

    def expand(item: TaggedValue) -> TaggedValue:
        if item.tag == TAG_REFERENCE:
            canonical = resolve(item)
            identity = id(canonical)
            if identity in active:
                raise TaggedDocumentError("cannot materialize a cyclic reference")
            active.add(identity)
            result = clone_value(canonical)
            result = expand(result)
            active.remove(identity)
            return result
        if item.tag == TAG_ARRAY:
            item.value[:] = [expand(child) for child in item.value]
        elif item.tag == TAG_OBJECT:
            item.value[:] = [(expand(key), expand(child)) for key, child in item.value]
        return item

    expand(value)


def plain_value(value: TaggedValue, *, blob_placeholder: bool = True) -> Any:
    """Return JSON-compatible values for inspection and MCP responses."""

    item = resolve(value)
    if item.tag == TAG_BYTES:
        return {"blob_bytes": len(item.value)} if blob_placeholder else bytes(item.value)
    if item.tag == TAG_ARRAY:
        return [plain_value(child, blob_placeholder=blob_placeholder) for child in item.value]
    if item.tag == TAG_OBJECT:
        return {
            str(resolve(key).value): plain_value(child, blob_placeholder=blob_placeholder)
            for key, child in item.value
        }
    if isinstance(item.value, tuple):
        return list(item.value)
    return item.value


__all__ = [
    "TAG_ARRAY",
    "TAG_BOOL",
    "TAG_F64",
    "TAG_F64X2",
    "TAG_F64X3",
    "TAG_F64X4",
    "TAG_I64",
    "TAG_OBJECT",
    "TAG_REFERENCE",
    "TAG_STRING",
    "TaggedDocumentError",
    "TaggedValue",
    "array_items",
    "clone_value",
    "decode_document",
    "encode_document",
    "materialize_references",
    "object_get",
    "object_items",
    "object_require",
    "object_set",
    "plain_value",
    "resolve",
    "walk",
]
