"""Expand modeling/entities.json into the mechanical parts of 01 and 03.

The agent decides which table backs which entity, the title property, which
columns to leave out, display names and descriptions, and which comment lists
are real value domains; this script writes the properties, value types and
their constraints, table datasets (columns filled by the platform) and
single-table mappings (design 2026-11-15 MS-01, MS-03). A daily snapshot
table names its date column in snapshot_date_column: the dataset declares it
and the identifier is the rest of the key (design 2026-11-18 LM-04).

It owns modeling/parts/01-types.json and 03-datasets.json and rewrites them on
every run; anything written by hand goes in 01b-*.json or 03b-*.json, which
merge right after them.
"""

import json
import re
from pathlib import Path

from runpaths import PARTS, HintParser, atomic_write, command, error, plan_not_approved
from table_summary import comment_values, load_tables

ENTITIES = Path("modeling/entities.json")
TYPES_PART = PARTS / "01-types.json"
DATASETS_PART = PARTS / "03-datasets.json"
LINKS_PART = PARTS / "02-links.json"
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SEPARATORS = re.compile(r"[：:，,（(；;]")


class SpecError(ValueError):
    pass


def value_kind(column):
    """The value kind the platform gives each column in the tables file."""
    return column.get("value_kind") or "string"


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


def evidence(basis, table, tables):
    found = []
    for entry in basis if isinstance(basis, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get("material_id") and entry.get("line"):
            match = re.fullmatch(r"\s*(\d+)\s*(?:[-–~]\s*(\d+))?\s*", str(entry["line"]))
            if not match:
                raise SpecError(f"basis 的行号 {entry['line']!r} 应写成 12 或 12-15")
            start, end = int(match.group(1)), int(match.group(2) or match.group(1))
            # The platform quotes the cited lines and checks they exist.
            found.append({"kind": "material", "material_id": entry["material_id"],
                          "locator": {"line_start": start, "line_end": end}})
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


def expand(spec, tables):
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
        skipped = {*(item.get("exclude_columns") or []), item.get("snapshot_date_column")}
        for column in table["columns"]:
            if column["name"] not in skipped:
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
        kinds = {value_kind(c) for c in found}
        if len(kinds) > 1:
            raise SpecError(f"值类型 {vt['name']} 的列 {', '.join(columns)} 基础类型不同（{', '.join(sorted(kinds))}），不能共用")
        first, column = columns[0], found[0]
        values = vt.get("values") or comment_values(column.get("comment"))
        if not values:
            raise SpecError(f"值类型 {vt['name']}：列 {first} 的注释里没有可识别的取值，请写 values")
        ref = "vt_" + vt["name"]
        numeric = value_kind(column) in {"integer", "decimal", "float"}
        if numeric and not all(re.fullmatch(r"-?\d+(\.\d+)?", str(v)) for v in values):
            raise SpecError(f"值类型 {vt['name']} 是数值列，取值 {values} 不全是数字；请写 values")
        quoted = ", ".join(str(v) if numeric else "'" + str(v).replace("'", "''") + "'" for v in values)
        types.append({"operation": "create", "target_kind": "value_type", "client_ref": ref, "after": {
            "name": vt["name"], "display_name": vt.get("display_name") or split_comment(column.get("comment"), True)[0],
            "value_kind": value_kind(column),
            **({"description": vt["description"]} if vt.get("description") else {}),
            "evidence": [{"kind": "table", "ref": first, "quote": column.get("comment") or col}]}})
        types.append({"operation": "create", "target_kind": "rule", "client_ref": ref + "_values", "after": {
            "name": vt["name"] + "_values", "display_name": (vt.get("display_name") or vt["name"]) + "取值",
            "owner_kind": "value_type", "owner_id": {"client_ref": ref}, "rule_kind": "constraint",
            "expression": f"{vt['name']} IN ({quoted})"}})
        for ref_col in columns:
            if ref_col not in column_owner:
                notes.append(f"值类型 {vt['name']} 的列 {ref_col} 不属于任何展开的实体，未绑定")
            bound[ref_col] = (ref, value_kind(column))

    shared_datasets, snapshots, columns_to_props, key_props = {}, {}, {}, {}
    refs = {i["name"]: f"实体 {i['name']} " for i in entities}
    repeated = {n for n in (t["table_name"] for t in tables.values()) if sum(t["table_name"] == n for t in tables.values()) > 1}
    for item in entities:
        name = item["name"]
        obj = {"name": name, "display_name": item.get("display_name")}
        if item.get("description"):
            obj["description"] = item["description"]
        table = backed.get(name)
        obj["evidence"] = evidence(item.get("basis"), table, tables)
        types.append({"operation": "create", "target_kind": "object_type", "client_ref": name, "after": obj})
        if not table:
            notes.append(f"{name} 没有对应的表，属性请写在 01b 片段里")
            continue
        excluded = set(item.get("exclude_columns") or [])
        flags = set(item.get("boolean_columns") or [])
        overrides = item.get("properties") or {}
        snapshot = item.get("snapshot_date_column")
        unknown = (excluded | flags | set(overrides) | {snapshot} - {None}) - {c["name"] for c in table["columns"]}
        if unknown:
            raise SpecError(f"{name} 引用了表 {table['key']} 没有的列：{', '.join(sorted(unknown))}")
        # The snapshot date picks the day; within one day the rest of the key identifies the entity.
        pk = [c for c in table.get("primary_key") or [] if c != snapshot]
        if not pk:
            raise SpecError(f"表 {table['key']} 没有声明主键（或只有快照日期列）；{name} 请在 01b、03b 片段里手写属性和映射")
        if excluded & set(pk):
            raise SpecError(f"{name} 不能排除主键列 {', '.join(sorted(excluded & set(pk)))}；每日快照表的日期列写在 snapshot_date_column")
        if snapshot:
            excluded.add(snapshot)  # declared on the dataset, not a business property
        fields = {}
        columns_to_props[name] = {}
        key_props[name] = []
        for column in table["columns"]:
            col = column["name"]
            if col in excluded:
                continue
            extra = overrides.get(col) or {}
            prop_name = extra.get("name") or col
            bound_to = bound.get(f"{table['key']}.{col}")
            display, description = split_comment(column.get("comment"), covered=bool(bound_to) or col in flags)
            prop = {"name": prop_name, "display_name": extra.get("display_name") or display or col,
                    "owner_type_id": {"client_ref": name}, "value_kind": value_kind(column)}
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
            columns_to_props[name][col] = prop_name
            if col in pk:
                key_props[name].append(prop_name)
        title = item.get("title_property")
        if title:
            title_name = (overrides.get(title) or {}).get("name") or title
            if title_name not in fields:
                raise SpecError(f"{name} 的 title_property {title} 不是展开出的属性")
            obj["title_property_id"] = {"client_ref": f"{name}_{title_name}"}
        ds_ref = shared_datasets.get(table["key"])
        if ds_ref is not None and snapshots.get(table["key"]) != snapshot:
            raise SpecError(f"{name} 与同表 {table['key']} 的其他实体 snapshot_date_column 不一致")
        if ds_ref is None:
            snapshots[table["key"]] = snapshot
            ds_name = table["table_name"]
            if ds_name in repeated:  # the same table name in two schemas or connections
                ds_name = re.sub(r"\W", "_", f"{table.get('schema_name') or table['key']}_{ds_name}")
            ds_ref = shared_datasets[table["key"]] = "ds_" + ds_name
            dataset = {"name": ds_name, "display_name": (item.get("display_name") or name) + "数据",
                       "source_kind": "table", "connection_id": table["connection_id"],
                       "schema_name": table.get("schema_name"), "table_name": table["table_name"]}
            if table.get("dialect"):
                dataset["dialect"] = table["dialect"]
            if snapshot:
                dataset["snapshot_date_column"] = snapshot
            datasets.append({"operation": "create", "target_kind": "dataset", "client_ref": ds_ref, "after": dataset})
        datasets.append({"operation": "create", "target_kind": "mapping", "client_ref": "map_" + name, "after": {
            "type_id": {"client_ref": name}, "binding_mode": "independent",
            "sources": [{"id": "main", "dataset_id": {"client_ref": ds_ref}, "key_columns": list(pk)}],
            "fields": fields}})
    links = expand_links(spec.get("links") or [], tables, columns_to_props, key_props, refs, shared_datasets, datasets)
    used = {t["key"] for t in backed.values()} | {resolve_table(link["via"], tables)["key"] for link in spec.get("links") or [] if link.get("via")}
    skipped = [f"{t['key']} {t['table_name']}" for t in tables.values() if t["key"] not in used]
    if skipped:
        notes.append("未展开为实体的表（有意排除可忽略；关联表等在 02、03b 里手写）：" + "、".join(skipped))
    return types, datasets, notes, links


MULTIPLICITIES = {"one_to_one", "many_to_one", "many_to_many"}  # one-to-many is built from the many side


def as_list(value):
    return [value] if isinstance(value, str) else list(value or [])


def expand_links(specs, tables, columns_to_props, key_props, refs, shared_datasets, datasets):
    """One short entry per link -> link_type items; the agent still names them,
    picks ends, cardinality and readings (design 2026-11-15, compact links)."""
    items = []

    def props(entity, names, what):
        if entity not in columns_to_props:
            raise SpecError(f"关系 {what} 的端点 {entity} 不是展开出的有表实体；这条关系写在 02b-links.json")
        known = columns_to_props[entity]
        found = []
        for name in names:
            prop = name if name in known.values() else known.get(name)
            if prop is None:
                raise SpecError(f"关系 {what}：{entity} 没有属性或列 {name}")
            found.append({"client_ref": f"{entity}_{prop}"})
        return found

    for link in specs:
        name = link.get("name")
        what = name or link.get("display_name") or "?"
        if not IDENTIFIER.match(name or ""):
            raise SpecError(f"关系 {what} 的 name 只能用字母、数字、下划线")
        if name in refs:
            raise SpecError(f"关系 {name} 与{refs[name]}重名，换一个 name")
        refs[name] = f" 关系 {name} "
        if link.get("multiplicity") not in MULTIPLICITIES:
            raise SpecError(f"关系 {name} 的 multiplicity 应为 {'、'.join(sorted(MULTIPLICITIES))}")
        source, target = link.get("from"), link.get("to")
        after = {"name": name, "display_name": link.get("display_name") or name,
                 "source_type_id": {"client_ref": source}, "target_type_id": {"client_ref": target},
                 "multiplicity": link["multiplicity"]}
        for key, field in (("description", "description"), ("reads", "verbalizes"), ("synonyms", "synonyms")):
            if link.get(key):
                after[field] = link[key]
        if link.get("via"):
            table = resolve_table(link["via"], tables)
            if table is None:
                raise SpecError(f"关系 {name} 的关联表 {link['via']} 不在本轮表结构里")
            columns = {c["name"] for c in table["columns"]}
            via_from, via_to = as_list(link.get("via_from")), as_list(link.get("via_to"))
            missing = [c for c in via_from + via_to if c not in columns]
            if missing or not via_from or not via_to:
                raise SpecError(f"关系 {name}：关联表 {table['key']} 需给 via_from、via_to，且是它的列（缺 {', '.join(missing) or '列名'}）")
            source_key = props(source, link.get("from_on") or key_props.get(source, []), name)
            target_key = props(target, link.get("to_on") or key_props.get(target, []), name)
            if len(source_key) != len(via_from) or len(target_key) != len(via_to):
                raise SpecError(f"关系 {name}：via_from、via_to 的列数要与两端的标识（或 from_on、to_on）一致")
            ds_ref = shared_datasets.get(table["key"])
            if ds_ref is None:
                ds_ref = shared_datasets[table["key"]] = "ds_" + table["table_name"]
                datasets.append({"operation": "create", "target_kind": "dataset", "client_ref": ds_ref, "after": {
                    "name": table["table_name"], "display_name": (table.get("comment") or table["table_name"])[:60],
                    "source_kind": "table", "connection_id": table["connection_id"],
                    "schema_name": table.get("schema_name"), "table_name": table["table_name"],
                    **({"dialect": table["dialect"]} if table.get("dialect") else {})}})
            after["data_join"] = {"kind": "mapping_table", "dataset_id": {"client_ref": ds_ref},
                                  "source_columns": via_from, "target_columns": via_to,
                                  "source_key": {"kind": "properties", "property_ids": source_key},
                                  "target_key": {"kind": "properties", "property_ids": target_key}}
        else:
            on = as_list(link.get("on"))
            if not on:
                raise SpecError(f"关系 {name} 缺 on（源端的关联列），或用 via 指定关联表")
            source_props = props(source, on, name)
            target_props = props(target, as_list(link.get("to_on")) or key_props.get(target, []), name)
            if len(source_props) != len(target_props):
                raise SpecError(f"关系 {name}：on 有 {len(source_props)} 列，目标端标识有 {len(target_props)} 个；用 to_on 指明目标属性")
            after["data_join"] = {"kind": "direct", "source_property_ids": source_props, "target_property_ids": target_props}
        items.append({"operation": "create", "target_kind": "link_type", "client_ref": name, "after": after})
    return items


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
        types, datasets, notes, links = expand(spec, tables)
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
    written = [TYPES_PART, DATASETS_PART]
    if "links" in spec:  # only then does the script own 02-links.json
        atomic_write(LINKS_PART, json.dumps(links, ensure_ascii=False, indent=1).encode())
        written.append(LINKS_PART)
    counts = {}
    for item in types + datasets + links:
        counts[item["target_kind"]] = counts.get(item["target_kind"], 0) + 1
    print("已写 " + "、".join(map(str, written)) + "：" + "，".join(f"{k} {v}" for k, v in counts.items()))
    print("这些文件每次运行都会重写；手写的类型、属性放 01b-*.json，特殊关系放 02b-*.json，查询数据集、多表映射放 03b-*.json")
    for note in notes:
        print("- " + note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
