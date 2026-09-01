"""Development probe for the tagged LiquiGen project container."""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Value:
    offset: int
    tag: int
    value: Any


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.cursor = 0
        self.values: dict[int, Value] = {}
        self.tags: Counter[int] = Counter()

    def take(self, count: int) -> bytes:
        end = self.cursor + count
        if end > len(self.data):
            raise ValueError(f"truncated value at 0x{self.cursor:x}, need {count} bytes")
        result = self.data[self.cursor : end]
        self.cursor = end
        return result

    def unpack(self, pattern: str) -> Any:
        size = struct.calcsize(pattern)
        return struct.unpack(pattern, self.take(size))

    def read(self) -> Value:
        offset = self.cursor
        tag = self.take(1)[0]
        self.tags[tag] += 1
        if tag == 0x00:
            payload: Any = None
        elif tag == 0x01:
            payload = bool(self.take(1)[0])
        elif tag == 0x02:
            payload = self.unpack("<b")[0]
        elif tag == 0x03:
            payload = self.unpack("<h")[0]
        elif tag == 0x04:
            payload = self.unpack("<i")[0]
        elif tag == 0x05:
            payload = self.unpack("<q")[0]
        elif tag == 0x06:
            payload = self.unpack("<qq")
        elif tag == 0x07:
            payload = self.unpack("<qqq")
        elif tag == 0x08:
            payload = self.unpack("<qqqq")
        elif tag == 0x09:
            payload = self.unpack("<d")[0]
        elif tag == 0x0A:
            payload = self.unpack("<dd")
        elif tag == 0x0B:
            payload = self.unpack("<ddd")
        elif tag == 0x0C:
            payload = self.unpack("<dddd")
        elif tag in (0x0D, 0x0E):
            length = self.unpack("<I")[0]
            raw = self.take(length)
            payload = raw if tag == 0x0D else raw.decode("utf-8")
        elif tag == 0x0F:
            target = self.unpack("<I")[0]
            if target not in self.values:
                nearby = sorted(item for item in self.values if target - 64 <= item <= target + 64)
                raise ValueError(
                    f"forward or invalid reference 0x{target:x} at 0x{offset:x}; "
                    f"nearby parsed offsets={[hex(item) for item in nearby]}"
                )
            payload = self.values[target]
        elif tag == 0x10:
            payload = []
            while self.data[self.cursor] != 0x12:
                payload.append(self.read())
            self.cursor += 1
            self.tags[0x12] += 1
        elif tag == 0x11:
            payload = []
            while self.data[self.cursor] != 0x12:
                key = self.read()
                resolved_key = key.value.value if key.tag == 0x0F else key.value
                if not isinstance(resolved_key, str):
                    raise ValueError(
                        f"object key at 0x{key.offset:x} is tag 0x{key.tag:02x}, not a string"
                    )
                payload.append((key, self.read()))
            self.cursor += 1
            self.tags[0x12] += 1
        elif tag == 0x12:
            raise ValueError(f"unexpected container terminator at 0x{offset:x}")
        else:
            raise ValueError(f"unknown tag 0x{tag:02x} at 0x{offset:x}")
        result = Value(offset, tag, payload)
        self.values[offset] = result
        # LiquiGen references the serialized payload address (one byte after
        # the type tag), not the address of the tag itself.
        self.values[offset + 1] = result
        return result


def _resolved(value: Value) -> Value:
    while value.tag == 0x0F:
        value = value.value
    return value


def _object_get(value: Value, name: str) -> Value | None:
    item = _resolved(value)
    if item.tag != 0x11:
        return None
    for key, child in item.value:
        if _resolved(key).value == name:
            return child
    return None


def _walk(value: Value, path: str = "$"):
    item = _resolved(value)
    yield path, item
    if item.tag == 0x10:
        for index, child in enumerate(item.value):
            yield from _walk(child, f"{path}[{index}]")
    elif item.tag == 0x11:
        for key, child in item.value:
            yield from _walk(child, f"{path}.{_resolved(key).value}")


def _plain(value: Value, depth: int = 0) -> Any:
    item = _resolved(value)
    if depth > 16:
        return "<depth-limit>"
    if item.tag == 0x0D:
        return {"blob_bytes": len(item.value)}
    if item.tag == 0x10:
        return [_plain(child, depth + 1) for child in item.value]
    if item.tag == 0x11:
        return {
            str(_resolved(key).value): _plain(child, depth + 1) for key, child in item.value
        }
    return item.value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--dump-graph", action="store_true")
    parser.add_argument("--dump-node", action="append", default=[])
    arguments = parser.parse_args()
    data = arguments.project.resolve(strict=True).read_bytes()
    reader = Reader(data)
    root = reader.read()
    print(f"consumed={reader.cursor} bytes={len(data)} complete={reader.cursor == len(data)}")
    print("tags=" + ", ".join(f"0x{tag:02x}:{count}" for tag, count in sorted(reader.tags.items())))
    graph = _object_get(root, "graph") or _object_get(root, "graph_ctx")
    if graph is None:
        for path, value in _walk(root):
            if path.endswith(".nodes"):
                print(f"nodes_path={path} tag=0x{value.tag:02x} offset=0x{value.offset:x}")
    else:
        print(f"graph_offset=0x{_resolved(graph).offset:x}")
        graph_plain = _plain(graph)
        if arguments.dump_graph:
            print(json.dumps(graph_plain, indent=2, ensure_ascii=False))
        elif arguments.dump_node:
            selected = [
                node
                for node in graph_plain.get("nodes", [])
                if node.get("type") in set(arguments.dump_node)
            ]
            print(json.dumps(selected, indent=2, ensure_ascii=False))
    for path, value in _walk(root):
        if path.endswith(".type") and _resolved(value).tag == 0x0E:
            text = _resolved(value).value
            if isinstance(text, str) and text.startswith("Node_"):
                print(f"{path}={text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
