"""Strict JSON decoding and real pointers/line spans in the formatted artifact."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


def escape_pointer(part) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 键重复：{key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"JSON 不接受非有限常量：{value}")


@dataclass
class SourceDocument:
    value: object
    sha256: str
    formatted: str
    formatted_sha256: str
    spans: dict[str, tuple[int, int]]

    @classmethod
    def parse(cls, raw: bytes):
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_object, parse_constant=_constant
        )
        lines: list[str] = []
        spans = {}

        def write(node, pointer, depth, prefix="", suffix=""):
            start = len(lines) + 1
            indent = "  " * depth
            if isinstance(node, (dict, list)) and node:
                is_dict = isinstance(node, dict)
                lines.append(indent + prefix + ("{" if is_dict else "["))
                items = list(node.items()) if is_dict else list(enumerate(node))
                for i, (key, child) in enumerate(items):
                    write(
                        child,
                        pointer + "/" + escape_pointer(key),
                        depth + 1,
                        json.dumps(key, ensure_ascii=False) + ": " if is_dict else "",
                        "," if i + 1 < len(items) else "",
                    )
                lines.append(indent + ("}" if is_dict else "]") + suffix)
            else:
                lines.append(
                    indent
                    + prefix
                    + json.dumps(node, ensure_ascii=False, allow_nan=False)
                    + suffix
                )
            spans[pointer] = (start, len(lines))

        write(value, "", 0)
        formatted = "\n".join(lines) + "\n"
        return cls(
            value,
            hashlib.sha256(raw).hexdigest(),
            formatted,
            hashlib.sha256(formatted.encode()).hexdigest(),
            spans,
        )

    def get(self, pointer):
        node = self.value
        for part in pointer.split("/")[1:] if pointer else []:
            key = part.replace("~1", "/").replace("~0", "~")
            node = node[int(key)] if isinstance(node, list) else node[key]
        return node

    def locator(self, pointer):
        start, end = self.spans[pointer]
        return {
            "sha256": self.sha256,
            "json_pointer": pointer,
            "formatted_sha256": self.formatted_sha256,
            "line_start": start,
            "line_end": end,
        }

    def original(self, pointer):
        return json.dumps(self.get(pointer), ensure_ascii=False, indent=2)


def parse_document(raw, report):
    try:
        return SourceDocument.parse(raw)
    except (UnicodeError, ValueError, RecursionError) as error:
        locator = {"sha256": report.source_sha256}
        if isinstance(error, json.JSONDecodeError):
            locator.update(line=error.lineno, column=error.colno)
        report.add(
            outcome="error",
            construct="document",
            source_path="document",
            locator=locator,
            message=f"文件不是有效的 UTF-8 JSON：{error}",
        )
        return None
