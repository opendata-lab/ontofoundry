"""Expand modeling/entities.json into the mechanical parts of 01 and 03.

The agent decides which table backs which entity, the title property, which
columns to leave out, display names and descriptions, and which comment lists
are real value domains; this script writes the properties, value types and
their constraints, table datasets (columns filled by the platform) and
single-table mappings (design 2026-11-15 MS-01, MS-03).

It owns modeling/parts/01-types.json and 03-datasets.json and rewrites them on
every run; anything written by hand goes in 01b-*.json or 03b-*.json, which
merge right after them.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from check_result import atomic_write
from runpaths import PARTS, HintParser, command, error, plan_not_approved
from table_summary import comment_values, load_tables

ENTITIES = Path("modeling/entities.json")
TYPES_PART = PARTS / "01-types.json"
DATASETS_PART = PARTS / "03-datasets.json"
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SEPARATORS = re.compile(r"[：:，,（(；;]")
KINDS = [
    ({"boolean", "bool"}, "boolean"),
    ({"tinyint", "smallint", "mediumint", "int", "integer", "bigint", "int2", "int4", "int8", "largeint", "year"}, "integer"),
    ({"decimal", "numeric", "number", "money"}, "decimal"),
    ({"float", "double", "real", "float4", "float8"}, "float"),
    ({"date"}, "date"),
    ({"datetime", "datetime2", "timestamp", "timestamptz"}, "datetime"),
]


class SpecError(ValueError):
    pass


def value_kind(physical_type):
    """Same classification as the platform's physical_value_kind; unknown types read as text."""
    name = re.split(r"[\s(]", (physical_type or "").strip().lower())[0]
    return next((kind for names, kind in KINDS if name in names), "string")


def split_comment(comment, covered=False):
    """'会员，散客为空' -> ('会员', '散客为空').

    covered: the tail is already said elsewhere (a bound value type, a boolean
    column), so it is not repeated; an open list such as 原因：促销/临期 stays.
    """
    comment = " ".join((comment or "").split())
    match = SEPARATORS.search(comment)
    if not match:
        return comment, ""
    head, rest = comment[: match.start()].strip(), comment[match.end():].strip(" ）)")
    return head or comment, "" if covered else rest


def material_lines(pack):
    lines = {}
    for material in pack.get("materials") or []:
        if material.get("path") and material.get("id"):
            try:
                lines[material["id"]] = Path(material["path"]).read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                lines[material["id"]] = []
    return lines


def evidence(basis, table, texts, tables):
    found = []
    for entry in basis if isinstance(basis, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get("material_id") and entry.get("line"):
            match = re.fullmatch(r"\s*(\d+)\s*(?:[-–~]\s*(\d+))?\s*", str(entry["line"]))
            if not match:
                raise SpecError(f"basis 的行号 {entry['line']!r} 应写成 12 或 12-15")
            start, end = int(match.group(1)), int(match.group(2) or match.group(1))
            text = texts.get(entry["material_id"], [])
            if text and not 0 < start <= end <= len(text):
                raise SpecError(f"basis 行号 {entry['line']} 超出材料 {entry['material_id']} 的 {len(text)} 行")
            quote = " ".join(line.strip() for line in text[start - 1:end]) if text else ""
            found.append({"kind": "material", "material_id": entry["material_id"],
                          "locator": {"line_start": start, "line_end": end}, "quote": quote[:2000]})
        elif entry.get("table"):
            source = resolve_table(entry["table"], tables)
            if source is None:
                raise SpecError(f"basis 的表 {entry['table']} 不在本轮表结构里")
            found.append({"kind": "table", "ref": source["key"], "quote": source.get("comment") or source["table_name"]})
    if not found and table:
        found.append({"kind": "table", "ref": table["key"], "quote": table.get("comment") or table["table_name"]})
    return found


def resolve_table(key, tables):
    """A table by key (t2), name (stores) or qualified name (shop.stores)."""
    if key in tables:
        return tables[key]
    return next((t for t in tables.values() if key in (t.get("table_name"), t.get("table"))), None)


def source_table(item, tables):
    key = item.get("table") or (item["tables"][0] if len(item.get("tables") or []) == 1 else None)
    if key is None:
        return None
    table = resolve_table(key, tables)
    if table is None:
        raise SpecError(f"{item['name']} 的表 {key} 不在本轮表结构里；可用 {', '.join(list(tables)[:40])}")
    return table


def expand(spec, tables, texts):
    types, datasets, notes = [], [], []
    names = {}  # English names share one namespace across object and value types (case-insensitive)

    def claim(name, what):
        if not IDENTIFIER.match(name or ""):
            raise SpecError(f"{what} 的英文标识 {name!r} 只能用字母、数字、下划线，且不以数字开头")
        if name.lower() in names:
            raise SpecError(f"英文标识 {name} 被 {names[name.lower()]} 和 {what} 同时使用；实体类型与值类型共用标识，改其中一个")
        names[name.lower()] = what

    entities = [i for i in spec.get("items") or [] if i.get("status", "new") == "new"]
    backed = {}
    for item in entities:
        claim(item.get("name"), f"实体 {item.get('display_name') or item.get('name')}")
        table = source_table(item, tables)
        if table:
            backed[item["name"]] = table
    column_owner = {}
    for name, table in backed.items():
        item = next(i for i in entities if i["name"] == name)
        for column in table["columns"]:
            if column["name"] not in set(item.get("exclude_columns") or []):
                column_owner.setdefault(f"{table['key']}.{column['name']}", []).append(name)

    bound = {}
    for vt in spec.get("value_types") or []:
        claim(vt.get("name"), f"值类型 {vt.get('display_name') or vt.get('name')}")
        columns = vt.get("columns") or ([vt["column"]] if vt.get("column") else [])
        if not columns:
            raise SpecError(f"值类型 {vt['name']} 缺 columns（如 [\"t2.status\"]）")
        found = []
        for ref_col in columns:
            key, _, col = ref_col.partition(".")
            column = next((c for c in (tables.get(key) or {}).get("columns", []) if c["name"] == col), None)
            if column is None:
                raise SpecError(f"值类型 {vt['name']} 的列 {ref_col} 不存在")
            found.append(column)
        kinds = {value_kind(c.get("type")) for c in found}
        if len(kinds) > 1:
            raise SpecError(f"值类型 {vt['name']} 的列 {', '.join(columns)} 基础类型不同（{', '.join(sorted(kinds))}），不能共用")
        first, column = columns[0], found[0]
        values = vt.get("values") or comment_values(column.get("comment"))
        if not values:
            raise SpecError(f"值类型 {vt['name']}：列 {first} 的注释里没有可识别的取值，请写 values")
        ref = "vt_" + vt["name"]
        numeric = value_kind(column.get("type")) in {"integer", "decimal", "float"}
        if numeric and not all(re.fullmatch(r"-?\d+(\.\d+)?", str(v)) for v in values):
            raise SpecError(f"值类型 {vt['name']} 是数值列，取值 {values} 不全是数字；请写 values")
        quoted = ", ".join(str(v) if numeric else "'" + str(v).replace("'", "''") + "'" for v in values)
        types.append({"operation": "create", "target_kind": "value_type", "client_ref": ref, "after": {
            "name": vt["name"], "display_name": vt.get("display_name") or split_comment(column.get("comment"), True)[0],
            "value_kind": value_kind(column.get("type")),
            **({"description": vt["description"]} if vt.get("description") else {}),
            "evidence": [{"kind": "table", "ref": first, "quote": column.get("comment") or col}]}})
        types.append({"operation": "create", "target_kind": "rule", "client_ref": ref + "_values", "after": {
            "name": vt["name"] + "_values", "display_name": (vt.get("display_name") or vt["name"]) + "取值",
            "owner_kind": "value_type", "owner_id": {"client_ref": ref}, "rule_kind": "constraint",
            "expression": f"{vt['name']} IN ({quoted})"}})
        for ref_col in columns:
            if ref_col not in column_owner:
                notes.append(f"值类型 {vt['name']} 的列 {ref_col} 不属于任何展开的实体，未绑定")
            bound[ref_col] = (ref, value_kind(column.get("type")))

    shared_datasets = {}
    refs = {i["name"]: f"实体 {i['name']} " for i in entities}
    repeated = {n for n in (t["table_name"] for t in tables.values()) if sum(t["table_name"] == n for t in tables.values()) > 1}
    for item in entities:
        name = item["name"]
        obj = {"name": name, "display_name": item.get("display_name")}
        if item.get("description"):
            obj["description"] = item["description"]
        table = backed.get(name)
        obj["evidence"] = evidence(item.get("basis"), table, texts, tables)
        types.append({"operation": "create", "target_kind": "object_type", "client_ref": name, "after": obj})
        if not table:
            notes.append(f"{name} 没有对应的表，属性请写在 01b 片段里")
            continue
        excluded = set(item.get("exclude_columns") or [])
        flags = set(item.get("boolean_columns") or [])
        overrides = item.get("properties") or {}
        unknown = (excluded | flags | set(overrides)) - {c["name"] for c in table["columns"]}
        if unknown:
            raise SpecError(f"{name} 引用了表 {table['key']} 没有的列：{', '.join(sorted(unknown))}")
        pk = table.get("primary_key") or []
        if not pk:
            raise SpecError(f"表 {table['key']} 没有声明主键；{name} 请在 01b、03b 片段里手写属性和映射")
        if excluded & set(pk):
            raise SpecError(f"{name} 不能排除主键列 {', '.join(sorted(excluded & set(pk)))}")
        fields = {}
        for column in table["columns"]:
            col = column["name"]
            if col in excluded:
                continue
            extra = overrides.get(col) or {}
            prop_name = extra.get("name") or col
            bound_to = bound.get(f"{table['key']}.{col}")
            display, description = split_comment(column.get("comment"), covered=bool(bound_to) or col in flags)
            prop = {"name": prop_name, "display_name": extra.get("display_name") or display or col,
                    "owner_type_id": {"client_ref": name}, "value_kind": value_kind(column.get("type"))}
            if not IDENTIFIER.match(prop_name):
                raise SpecError(f"{name}.{col} 不能直接作英文标识，请在 properties 里给 name")
            if col in flags:
                prop["value_kind"] = "boolean"
            if "value_kind" in extra:
                prop["value_kind"] = extra["value_kind"]
            if bound_to:  # the value type fixes the base kind
                prop["value_type_id"] = {"client_ref": bound_to[0]}
                prop["value_kind"] = bound_to[1]
            for key in ("required", "unique", "synonyms"):
                if key in extra:
                    prop[key] = extra[key]
            if col in pk:  # identifiers are fixed by the key, not by overrides
                prop.update(identifier=True, required=True, unique=len(pk) == 1)
            if extra.get("description") or description:
                prop["description"] = extra.get("description") or description
            prop_ref = f"{name}_{prop_name}"
            if prop_ref in refs:
                raise SpecError(f"{name}.{prop_name} 生成的 client_ref {prop_ref} 与{refs[prop_ref]}重名；在 properties 里给该列另起 name")
            refs[prop_ref] = f" {name}.{prop_name} "
            types.append({"operation": "create", "target_kind": "property", "client_ref": prop_ref, "after": prop})
            fields[prop_name] = {"kind": "column", "source_id": "main", "column": col}
        title = item.get("title_property")
        if title:
            title_name = (overrides.get(title) or {}).get("name") or title
            if title_name not in fields:
                raise SpecError(f"{name} 的 title_property {title} 不是展开出的属性")
            obj["title_property_id"] = {"client_ref": f"{name}_{title_name}"}
        ds_ref = shared_datasets.get(table["key"])
        if ds_ref is None:
            ds_name = table["table_name"]
            if ds_name in repeated:  # the same table name in two schemas or connections
                ds_name = re.sub(r"\W", "_", f"{table.get('schema_name') or table['key']}_{ds_name}")
            ds_ref = shared_datasets[table["key"]] = "ds_" + ds_name
            dataset = {"name": ds_name, "display_name": (item.get("display_name") or name) + "数据",
                       "source_kind": "table", "connection_id": table["connection_id"],
                       "schema_name": table.get("schema_name"), "table_name": table["table_name"]}
            if table.get("dialect"):
                dataset["dialect"] = table["dialect"]
            datasets.append({"operation": "create", "target_kind": "dataset", "client_ref": ds_ref, "after": dataset})
        datasets.append({"operation": "create", "target_kind": "mapping", "client_ref": "map_" + name, "after": {
            "type_id": {"client_ref": name}, "binding_mode": "independent",
            "sources": [{"id": "main", "dataset_id": {"client_ref": ds_ref}, "key_columns": list(pk)}],
            "fields": fields}})
    used = {t["key"] for t in backed.values()}
    skipped = [f"{t['key']} {t['table_name']}" for t in tables.values() if t["key"] not in used]
    if skipped:
        notes.append("未展开为实体的表（有意排除可忽略；关联表等在 02、03b 里手写）：" + "、".join(skipped))
    return types, datasets, notes


def main():
    parser = HintParser(description="按 modeling/entities.json 展开 01-types 与 03-datasets 的机械部分并检查")
    parser.add_argument("--work-pack", required=True)
    args = parser.parse_args()
    if refusal := plan_not_approved():
        print(refusal)
        return 2
    try:
        pack = json.loads(Path(args.work_pack).read_bytes())
        tables = {t["key"]: t for t in load_tables(pack["tables_file"])}
        spec = json.loads(ENTITIES.read_bytes())
        types, datasets, notes = expand(spec, tables, material_lines(pack))
    except SpecError as exc:
        print(error("SPEC_INVALID", str(exc), "未写任何片段", "改 modeling/entities.json 后重新运行：" + command("expand_tables.py", "--work-pack", args.work_pack)))
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(error("INPUT_UNREADABLE", f"读取工作包、表结构或 {ENTITIES} 失败：{type(exc).__name__} {exc}", "未写任何片段",
                    "先按概念清单模板写 modeling/entities.json；路径照 init_workflow 打印的复制"))
        return 1
    PARTS.mkdir(parents=True, exist_ok=True)
    atomic_write(TYPES_PART, json.dumps(types, ensure_ascii=False, indent=1).encode())
    atomic_write(DATASETS_PART, json.dumps(datasets, ensure_ascii=False, indent=1).encode())
    counts = {}
    for item in types + datasets:
        counts[item["target_kind"]] = counts.get(item["target_kind"], 0) + 1
    print(f"已写 {TYPES_PART}、{DATASETS_PART}：" + "，".join(f"{k} {v}" for k, v in counts.items()))
    print("这两个文件每次运行都会重写；手写的类型、属性放 01b-*.json，查询数据集、多表映射放 03b-*.json")
    for note in notes:
        print("- " + note)
    sys.stdout.flush()
    checked = subprocess.run([sys.executable, str(Path(__file__).with_name("check_part.py")), "--work-pack", args.work_pack,
                              str(TYPES_PART), str(DATASETS_PART)], check=False)
    return checked.returncode


if __name__ == "__main__":
    raise SystemExit(main())
