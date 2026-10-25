"""Deterministic, derived reading inputs; authoritative files stay intact."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ontofoundry_api.db_models import MaterialRecord, utc_now
from ontofoundry_api.services.dataagent import DataAgentError
from ontofoundry_api.services.material_store import store_text_material

PACK_LIMIT = 8 * 1024
READ_LIMIT = 8 * 1024
EXAMPLES = {
    "固定抽取包": "python <技能目录>/scripts/show_example.py --part 01（依次 01–05）；另读 --guide、--values",
    "增量": "先 show_element.py --work-pack <工作包> <英文标识或id>；再 show_example.py --incremental-guide、--part update（修改删除加 --part edit）",
    "类型": "references/extract-types.md",
    "映射": "references/extract-mappings.md",
    "指标规则": "references/extract-metrics-rules.md",
    "事实": "entity-extraction/references/extract-facts.md（实例抽取技能）",
    "查写法": "python <技能目录>/scripts/show_example.py <target_kind> --operation create",
}


def encode(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def material_index(material: dict, content: bytes, path: str) -> dict:
    if not path or hashlib.sha256(content).hexdigest() != material["sha256"]:
        raise DataAgentError("材料路径或 SHA256 与本轮固定输入不一致", status_code=422)
    try:
        lines = len(content.decode("utf-8").splitlines())
    except UnicodeDecodeError:
        raise DataAgentError("材料不是 UTF-8 文本", status_code=422) from None
    return {
        **material,
        "path": path,
        "bytes": len(content),
        "lines": lines,
        "original_range": [1, lines],
        "read": "全文" if len(content) <= READ_LIMIT else "按原行号分段",
    }


def execution_input(run_token: str, repair_used: int = 0) -> dict:
    return {
        "repair_limit": 2,
        "repair_used": repair_used,
        "budget_file": f"output/ontofoundry-budget-{run_token}.json",
    }


def build_work_pack(
    context: dict,
    materials: list[dict],
    *,
    context_file: str,
    schema_file: str,
    mcp_config_file: str | None = None,
    tables: list[dict] | None = None,
    tables_file: str | None = None,
    scenario_facts: dict | None = None,
    prior_plan_file: str | None = None,
) -> tuple[dict, list[bytes]]:
    """Keep all index entries, spilling oversized indices to bounded pages."""
    if any(not m.get("path") or "lines" not in m for m in materials):
        raise DataAgentError("本轮材料索引不完整", status_code=422)
    entries = []
    for collection, elements in sorted(context["draft"].items()):
        if not isinstance(elements, list):
            continue
        for index, element in sorted(enumerate(elements), key=lambda pair: pair[1]["id"]):
            summary = (
                # Datasets stay compact; full columns are read at the pointer.
                {
                    **{k: element[k] for k in ("id", "name", "display_name", "source_kind", "schema_name", "table_name") if element.get(k) is not None},
                    "column_count": len(element.get("columns") or []),
                }
                if collection == "datasets"
                else {
                    key: element[key]
                    for key in (
                        "id",
                        "name",
                        "display_name",
                        "extends",
                        "owner_type_id",
                        "type_id",
                    )
                    if key in element
                }
            )
            entries.append(
                {
                    "collection": collection,
                    "pointer": f"/draft/{collection}/{index}",
                    **summary,
                }
            )
    pack = {
        "run": context["run"],
        "execution": context["execution"],
        "result_file": f"output/ontofoundry-result-{context['run']['run_token']}.json",
        "needs_input_file": f"output/ontofoundry-needs-input-{context['run']['run_token']}.json",
        "context_file": context_file,
        "schema_file": schema_file,
        "materials": sorted(materials, key=lambda m: m["id"]),
        "examples": EXAMPLES,
        "elements": entries,
        "read_back": "已有元素用 show_element.py --work-pack <工作包> <英文标识或id> 精确取定义、hash、引用者，按返回参数分页；不读 context 全文、源码或 Schema。完整上下文交给检查器。",
    }
    if mcp_config_file:
        pack["mcp_config_file"] = mcp_config_file
    pack["workflow_dir"] = "modeling/"
    if scenario_facts:
        pack["scenario_facts"] = scenario_facts
    if prior_plan_file:
        # The confirmed plan from the previous run; this turn's message is the reply.
        pack["prior_plan_file"] = prior_plan_file
    if tables:
        # Linked registered tables: a catalog only; columns live in tables_file.
        pack["tables"] = tables
        pack["tables_file"] = tables_file
    if len(encode(pack)) <= PACK_LIMIT:
        return pack, []
    # No index entries disappear: the page list replaces the inline index.
    rows = (
        [{"material": m} for m in pack.pop("materials")]
        + [{"table": t} for t in pack.pop("tables", [])]
        + [{"element": e} for e in pack.pop("elements")]
    )
    pages, page = [], []
    for row in rows:
        if len(encode(row)) > 6000:
            # A very wide dataset is still available at its precise pointer.
            if "element" in row:
                entry = row["element"]
                row = {
                    "element": {k: entry[k] for k in ("collection", "pointer", "id")},
                    "read_full_at_pointer": True,
                }
            elif "table" in row:
                # The full comment stays in tables_file.
                row = {"table": {**row["table"], "comment": row["table"]["comment"][:200]}}
            else:
                raise DataAgentError("材料索引单项过大", status_code=422)
        if len(encode([*page, row])) > 6000:
            pages.append(encode(page))
            page = []
        page.append(row)
    if page:
        pages.append(encode(page))
    pack["index_pages"] = []
    pack["index_entry_count"] = len(rows)
    pack["read_back"] += " 索引已分页，所有页均须按需回读；未读页不代表没有相关元素。"
    return pack, pages


async def upload_work_pack(
    client, topic_id: str, run_token: str, pack: dict, pages: list[bytes]
) -> str:
    """Upload a bounded index tree even when the graph has thousands of pages."""
    if pages:
        links = []
        for index, page in enumerate(pages):
            uploaded = await client.upload(
                topic_id,
                f"ontofoundry-index-{run_token}-{index}.json",
                page,
                "application/json",
            )
            links.append(uploaded["rel_path"])
        level = 0
        while len(encode(links)) > 6000:
            groups, group = [], []
            for link in links:
                if len(encode([*group, link])) > 6000:
                    groups.append(group)
                    group = []
                group.append(link)
            if group:
                groups.append(group)
            next_links = []
            for index, group in enumerate(groups):
                uploaded = await client.upload(
                    topic_id,
                    f"ontofoundry-index-{run_token}-level-{level}-{index}.json",
                    encode({"index_pages": group}),
                    "application/json",
                )
                next_links.append(uploaded["rel_path"])
            if len(next_links) >= len(links):
                raise DataAgentError("索引路径过长，无法生成有界索引", status_code=422)
            links = next_links
            level += 1
        uploaded = await client.upload(
            topic_id,
            f"ontofoundry-index-{run_token}-root.json",
            encode({"index_pages": links}),
            "application/json",
        )
        pack["index_pages"] = [uploaded["rel_path"]]
    content = encode(pack)
    if len(content) > PACK_LIMIT:
        raise DataAgentError("工作包超过 8 KiB，请按完整输入索引检查规模", status_code=422)
    uploaded = await client.upload(
        topic_id, f"ontofoundry-work-pack-{run_token}.json", content, "application/json"
    )
    return str(uploaded["rel_path"])


def scenario_facts(
    draft: dict,
    manifest: dict,
    previous: dict,
    tables: list[dict] | None,
) -> dict:
    """Objective facts for choosing a modeling scenario; the agent decides.

    Additions are reported only against a previous proposals run of this
    session, which is the only recorded baseline.
    """
    facts: dict = {
        "draft_empty": not any(
            draft.get(c) for c in ("object_types", "link_types", "metrics", "datasets", "value_types")
        )
    }
    if not previous.get("input_files"):
        return facts
    before = {m["id"] for m in previous.get("materials") or []}
    facts["new_material_ids"] = [m["id"] for m in manifest.get("materials") or [] if m["id"] not in before]
    seen = {(t.get("connection"), t.get("table")) for t in previous["input_files"].get("tables") or []}
    facts["new_table_keys"] = [
        t["key"] for t in tables or [] if (t.get("connection"), t.get("table")) not in seen
    ]
    return facts


def linked_tables_payload(details: list[dict]) -> tuple[list[dict], bytes]:
    """Catalog entries for the work pack and the full structure file."""
    catalog, full = [], []
    ordered = sorted(
        details,
        key=lambda item: (item["connection"].id, item["schema_name"] or "", item["table"]["name"]),
    )
    for number, item in enumerate(ordered, 1):
        table, connection = item["table"], item["connection"]
        ref = f"{item['schema_name']}.{table['name']}" if item["schema_name"] else table["name"]
        # The key is the only way to select a table, so same-named tables never collide.
        key = f"t{number}"
        catalog.append(
            {
                "key": key,
                "table": ref,
                "connection": connection.name,
                "kind": table.get("kind", "table"),
                "comment": table.get("comment") or "",
                "column_count": len(table.get("columns", [])),
            }
        )
        full.append(
            {
                "key": key,
                "table": ref,
                "connection_id": connection.id,
                "connection": connection.name,
                "dialect": connection.kind,
                "schema_name": item["schema_name"],
                "table_name": table["name"],
                "kind": table.get("kind", "table"),
                "comment": table.get("comment") or "",
                "primary_key": table.get("primary_key") or [c["name"] for c in table.get("columns", []) if c.get("primary_key")],
                "foreign_keys": [
                    {k: f.get(k) for k in ("constrained_columns", "referred_schema", "referred_table", "referred_columns")}
                    for f in sorted(table.get("foreign_keys", []), key=lambda f: encode({
                        k: f.get(k) for k in ("constrained_columns", "referred_schema", "referred_table", "referred_columns")
                    }))
                ],
                "columns": [
                    {"name": c["name"], "type": c.get("type"), "nullable": c.get("nullable"), "comment": c.get("comment") or ""}
                    for c in table.get("columns", [])
                ],
            }
        )
    # Dict insertion order fixes keys; physical column and key-column order is retained.
    return catalog, json.dumps({"tables": full}, indent=2, ensure_ascii=False).encode("utf-8")


def store_linked_tables_receipt(
    db, settings, workspace_id: str, linked_tables: list[dict],
) -> tuple[list[dict], MaterialRecord]:
    """Pin registered structure as ordinary material in the caller's transaction."""
    from ontofoundry_api.services.dataset_sources import linked_table_details

    details = linked_table_details(db, workspace_id, linked_tables)
    catalog, content = linked_tables_payload(details)
    connections = {item["connection"].id: item["connection"].name for item in details}
    label = next(iter(connections.values())) if len(connections) == 1 else f"多连接（{len(connections)}）"
    label = label.replace("/", "／").replace("\\", "＼")[:200]
    name = f"表结构收据 · {label} · {utc_now().date().isoformat()}"
    material = store_text_material(
        db, settings, workspace_id, name, content.decode("utf-8"), origin="table_receipt",
    )
    return catalog, material
