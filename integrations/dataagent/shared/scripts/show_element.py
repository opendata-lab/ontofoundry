"""Exact, bounded element reads without the API package or runtime services."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from check_result import TARGET_KINDS, pinned_targets

LIMIT = 8192
PAGE_BYTES = 3000
TOKEN = re.compile(
    r"(?P<space>\s+)|(?P<comment>--[^\n]*|/\*[\s\S]*?\*/)|"
    r"(?P<string>'(?:''|\\.|[^'\\])*')|"
    r'(?P<quoted>"(?:""|[^"])*"|`(?:``|[^`])*`)|'
    r"(?P<param>:[A-Za-z_]\w*|@[A-Za-z_]\w*|\$[A-Za-z_0-9]\w*)|"
    r"(?P<word>[A-Za-z_]\w*)|(?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|"
    r"(?P<symbol>.)"
)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class ElementIndex:
    def __init__(self, context):
        self.context = context
        targets = pinned_targets(context)
        self.elements = {identity: (kind, e) for (kind, identity), (e, _) in targets.items()}
        self.hashes = {identity: h for (_, identity), (_, h) in targets.items()}

    def lineage(self, identity):
        seen = set()
        while identity and identity not in seen:
            seen.add(identity)
            yield identity
            identity = self.elements[identity][1].get("extends")

    def member(self, kind, owner, name, reverse=False):
        key = "owner_type_id" if kind == "property" else "target_type_id" if reverse else "source_type_id"
        for ancestor in self.lineage(owner):
            matches = [e for k, e in self.elements.values() if k == kind and e.get(key) == ancestor and e["name"].casefold() == name.casefold()]
            if len(matches) == 1:
                return matches[0]
        return None

    def selectors(self, identity):
        kind, element = self.elements[identity]
        name = element.get("name")
        aliases = {identity}
        if name:
            aliases.update((name, f"{kind}:{name}"))
            owner = element.get("owner_type_id") if kind == "property" else element.get("source_type_id") if kind == "link_type" else None
            if owner:
                qualified = self.elements[owner][1]["name"] + "." + name
                aliases.update((qualified, f"{kind}:{qualified}"))
        aliases.add(f"{kind}:{identity}")
        return aliases

    def exact_selector(self, identity):
        kind, element = self.elements[identity]
        if "name" in element:
            owner = element.get("owner_type_id") if kind == "property" else element.get("source_type_id") if kind == "link_type" else None
            name = (self.elements[owner][1]["name"] + "." if owner else "") + element["name"]
            candidate = f"{kind}:{name}"
            if sum(candidate in self.selectors(i) for i in self.elements) == 1:
                return candidate
        return f"{kind}:{identity}"

    def find(self, selector):
        if selector in self.elements:
            return selector, None
        kind, separator, identity = selector.partition(":")
        if separator and identity in self.elements and self.elements[identity][0] == kind:
            return identity, None
        matches = [i for i in self.elements if selector in self.selectors(i)]
        if len(matches) == 1:
            return matches[0], None
        candidates = matches or [i for i, (k, _) in self.elements.items() if kind not in TARGET_KINDS or kind == k]
        return None, {
            "查询": selector, **({"code": "TARGET_NOT_FOUND"} if not matches else {}), "错误": "英文标识有歧义" if matches else "元素不存在（仅支持精确英文标识或 id）",
            "候选精确写法": sorted(self.exact_selector(i) for i in candidates),
        }

    def expression_refs(self, expression):
        # Match the domain expression tokenizer, ignoring literals and comments.
        tokens = [(m.lastgroup, m.group()) for m in TOKEN.finditer(expression) if m.lastgroup not in {"space", "comment"}]

        def name(token):
            kind, text = token
            return text[1:-1].replace(text[0] * 2, text[0]) if kind == "quoted" else text

        roots = {e["name"].casefold(): e for k, e in self.elements.values() if k == "object_type"}
        refs, start = set(), 0
        while start < len(tokens):
            first = tokens[start]
            root = roots.get(name(first).casefold()) if first[0] in {"word", "quoted"} else None
            end = start + 1
            if not root or end >= len(tokens) or tokens[end][1] != ".":
                start += 1
                continue
            current, found = root["id"], {root["id"]}
            existence = start >= 2 and tokens[start - 1][1] == "(" and tokens[start - 2][1].upper() == "EXISTS"
            while end + 1 < len(tokens) and tokens[end][1] == ".":
                part = tokens[end + 1]
                reverse = part[1].upper() == "REVERSE" and end + 4 < len(tokens) and tokens[end + 2][1] == "(" and tokens[end + 4][1] == ")"
                if reverse:
                    part = tokens[end + 3]
                if part[0] not in {"word", "quoted"}:
                    break
                end += 5 if reverse else 2
                more = end < len(tokens) and tokens[end][1] == "."
                prop = self.member("property", current, name(part)) if not more and not reverse and not existence else None
                link = self.member("link_type", current, name(part), reverse)
                if prop:
                    found.add(prop["id"])
                elif link:
                    found.add(link["id"])
                    current = link["source_type_id" if reverse else "target_type_id"]
                else:
                    break
            refs |= found
            start = end
        return refs

    def reverse_refs(self):
        reverse = defaultdict(set)

        reference_fields = {
            "extends", "title_property_id", "owner_type_id", "value_type_id",
            "source_type_id", "target_type_id", "owner_id", "dataset_id", "type_id",
            "property_id", "link_type_id", "numerator_id", "denominator_id",
            "property_ids", "source_property_ids", "target_property_ids",
        }

        def ids(value):
            # Evidence, SQL and free text never become references by coincidence.
            if isinstance(value, dict):
                found = set()
                for key, child in value.items():
                    if key in {"id", "evidence", "description", "query_sql", "expression", "values"}:
                        continue
                    if key in reference_fields:
                        values = child if isinstance(child, list) else [child]
                        found |= {v for v in values if isinstance(v, str) and v in self.elements}
                    elif key == "inherited_link_bindings":
                        found |= set(child) & self.elements.keys()
                    if isinstance(child, (dict, list)):
                        found |= ids(child)
                return found
            if isinstance(value, list):
                return set().union(*(ids(v) for v in value))
            return set()

        for identity, (kind, element) in self.elements.items():
            refs = ids(element)
            if kind in {"mapping", "material_object"}:
                for name in element.get("fields" if kind == "mapping" else "values", {}):
                    prop = self.member("property", element["type_id"], name)
                    if prop:
                        refs.add(prop["id"])
            expressions = [element["expression"]] if kind == "rule" else []
            if kind == "object_type":
                expressions += [b["expression"] for b in element.get("derived_by", []) if b["kind"] == "expression"]
            for expression in expressions:
                refs |= self.expression_refs(expression)
            if kind == "mapping" and element.get("binding_mode") == "shared_parent":
                ancestors = set(self.lineage(element["type_id"])) - {element["type_id"]}
                refs |= {i for i, (k, e) in self.elements.items() if k == "mapping" and e["type_id"] in ancestors}
            if kind == "material_link":
                refs |= {element["source_id"], element["target_id"]}
            joins = [(element.get("data_join"), element)] if kind == "link_type" else []
            if kind == "mapping":
                joins += [(join, {"source_type_id": element["type_id"], "target_type_id": self.elements[link_id][1]["target_type_id"]}) for link_id, join in element.get("inherited_link_bindings", {}).items()]
            for join, endpoints in joins:
                if not join or join["kind"] != "mapping_table":
                    continue
                for side in ("source", "target"):
                    if join[f"{side}_key"]["kind"] == "mapping_key":
                        ancestors = set(self.lineage(endpoints[f"{side}_type_id"]))
                        refs |= {i for i, (k, e) in self.elements.items() if k == "mapping" and e["type_id"] in ancestors}
            for target in refs:
                reverse[target].add(identity)
        return reverse

    def query(self, selectors):
        identities, errors = [], []
        for selector in selectors:
            identity, error = self.find(selector)
            if error:
                errors.append(error)
            elif identity not in identities:
                identities.append(identity)
        if errors:
            return {"errors": errors}, 1
        reverse = self.reverse_refs()
        return {"elements": [{
            "kind": self.elements[i][0], "selector": self.exact_selector(i),
            "definition": self.elements[i][1], "hash": self.hashes[i],
            "referenced_by": [{"id": r, **({"name": self.elements[r][1]["name"]} if "name" in self.elements[r][1] else {})} for r in sorted(reverse[i])],
        } for i in identities]}, 0


def bounded(value, page=None, expected_hash=None):
    content = encode(value)
    digest = hashlib.sha256(content.encode()).hexdigest()
    if expected_hash and expected_hash != digest:
        raise ValueError("查询内容已变化；请移除 --page/--sha256 重新查询")
    if len((content + "\n").encode()) <= LIMIT and page is None:
        return content
    chunks, current, size = [], [], 0
    for char in content:
        width = len(char.encode())
        if size + width > PAGE_BYTES:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += width
    chunks.append("".join(current))
    result = {"分页": {"sha256": digest, "pages": len(chunks), "参数": f"保留原查询参数，每次加 --page N --sha256 {digest}，N=1..{len(chunks)}", "重组": "依次拼接各页 text 后解析 JSON；不截断定义"}}
    if page is not None:
        if not 1 <= page <= len(chunks):
            raise ValueError(f"页码超出范围；--page 1..{len(chunks)}")
        result.update(page=page, text=chunks[page - 1])
    output = encode(result)
    if len((output + "\n").encode()) > LIMIT:
        raise ValueError("分页输出超限")
    return output


def main():
    parser = argparse.ArgumentParser(description="精确读取已有元素、固定 hash 与直接引用者；不支持中文名称或模糊匹配")
    parser.add_argument("--work-pack", required=True)
    parser.add_argument("selectors", nargs="+", help="id、英文标识、kind:标识、实体.属性/关系；无英文标识的元素用 id")
    parser.add_argument("--page", type=int)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    try:
        pack = json.loads(Path(args.work_pack).read_bytes())
        context = json.loads(Path(pack["context_file"]).read_bytes())
        value, status = ElementIndex(context).query(args.selectors)
        output = bounded(value, args.page, args.sha256)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        output, status = encode({"错误": "无法查询元素", "原因": str(exc)[:500]}), 1
    print(output)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
