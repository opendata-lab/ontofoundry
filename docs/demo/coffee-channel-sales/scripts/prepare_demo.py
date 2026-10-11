"""Prepare the 咖啡渠道销售 demo workspace against a running OntoFoundry + DataAgent.

Every stage is idempotent: it looks up what already exists before creating it.

    python prepare_demo.py model      # workspace, material, real DataAgent modeling run
    python prepare_demo.py publish    # accept all proposals of the prepared session, publish
    python prepare_demo.py data       # read-only connection, table mappings, relation joins
    python prepare_demo.py token      # service token + DataAgent MCP import file
    python prepare_demo.py check      # answer the demo questions through MCP
    python prepare_demo.py standby    # backup session for the live step, proposals pending
    python prepare_demo.py ossie      # two empty spaces for the live Ossie import scenario

Environment: OF_API (default http://127.0.0.1:8000), OF_MYSQL_PASSWORD (read-only
user password, default of_readonly_demo).
"""

from __future__ import annotations

import functools
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal
from pathlib import Path

print = functools.partial(print, flush=True)  # noqa: A001 - progress in logs
API = os.environ.get("OF_API", "http://127.0.0.1:8000").rstrip("/")
HERE = Path(__file__).resolve().parent
CASE = HERE.parent
OUT = CASE / "generated"
SLUG = "coffee-channel-sales"
NAME = "咖啡渠道销售"
DESCRIPTION = "渠道客户、订单、订单明细与商品的销售本体，对接销售业务库，可通过 MCP 问数。"
PREPARED_TITLE = "渠道销售本体（演示预备）"
MATERIAL = CASE / "materials" / "01-渠道销售业务说明.md"
RETURNS_MATERIAL = CASE / "materials" / "02-售后退货规则.md"
RETURNS_LOG = CASE / "materials" / "03-2026年1月退货登记.md"
STANDBY_TOPDOWN = "售后退货（备用）"
STANDBY_BOTTOMUP = "销售业务库映射（备用）"
# Same words the presenter types into 业务场景描述, so live and backup match.
RETURNS_PROMPT = (
    "目标范围：售后退货。复用已发布的客户和订单，补充退货相关的对象、属性、关系和规则，"
    "并把退货登记中的每一笔退货抽取为实例。"
)
TABLE_NAMES = ["customers", "orders", "order_items", "products"]
TABLES_PROMPT = (
    "目标范围：把销售业务库的四张表对接到已发布本体。复用已有的客户、订单、订单明细和商品，"
    "补全缺少的属性，为每个对象建立数据映射，并按关联字段为关系配置数据连接。"
)
MODEL_PROMPT = (
    "请根据《渠道销售业务说明》构建渠道销售本体：识别业务对象、属性、对象之间的关系和业务规则。"
    "对象和属性使用中文名称，同时给出英文技术标识。"
)


def call(method: str, path: str, body=None, *, raw: bytes | None = None, headers=None):
    data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
    request = urllib.request.Request(API + path, data=data, method=method)
    request.add_header("Accept", "application/json")
    if raw is None and body is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            text = response.read().decode()
            return json.loads(text) if text else None
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {path} -> {exc.code}: {exc.read().decode()[:800]}") from None


def workspace() -> dict:
    for item in call("GET", "/api/v1/workspaces")["items"]:
        if item["slug"] == SLUG:
            return item
    print("创建工作空间", NAME)
    return call("POST", "/api/v1/workspaces",
                {"name": NAME, "slug": SLUG, "description": DESCRIPTION})


def ws_path(ws: dict, suffix: str) -> str:
    return f"/api/v1/workspaces/{ws['id']}{suffix}"


def material(ws: dict, path: Path) -> dict:
    for item in call("GET", ws_path(ws, "/materials"))["items"]:
        if item["name"] == path.name:
            return item
    print("上传材料", path.name)
    return call("POST", ws_path(ws, "/materials?name=" + urllib.parse.quote(path.name)),
                raw=path.read_bytes(), headers={"Content-Type": "text/markdown"})


def session_by_title(ws: dict, title: str) -> dict | None:
    for item in call("GET", ws_path(ws, "/sessions"))["items"]:
        if item["title"] == title:
            return call("GET", ws_path(ws, "/sessions/" + item["id"]))
    return None


def wait_for_run(ws: dict, session_id: str) -> dict:
    last = None
    while True:
        # Reading the conversation snapshot is what reconciles the run with
        # DataAgent and imports its proposals once it ends.
        call("GET", ws_path(ws, f"/sessions/{session_id}/agent-conversation"))
        item = call("GET", ws_path(ws, "/sessions/" + session_id))
        state = (item.get("task_status"), item.get("task_detail"))
        if state != last:
            print("  状态:", *state)
            last = state
        if item.get("task_status") not in {"submitting", "queued", "running"}:
            return item
        time.sleep(5)


def run_modeling(docs: list[dict], title: str, prompt: str) -> None:
    ws = workspace()
    item = session_by_title(ws, title)
    if item is None:
        item = call("POST", ws_path(ws, "/sessions"), {"title": title})
    if item.get("task_status") in {"submitting", "queued", "running"}:
        print("建模进行中，继续等待", item["id"])
        done = wait_for_run(ws, item["id"])
        print("结束:", done.get("task_status"), done.get("task_detail"))
        return
    if item.get("task_status") == "finished":
        print(title, "已完成建模:", item["id"])
        return
    wanted = [d["id"] for d in docs]
    if set(wanted) - set(item["material_ids"]):
        item = call("PUT", ws_path(ws, "/sessions/" + item["id"]), {
            "revision": item["revision"], "draft": item["draft"],
            "material_ids": list(dict.fromkeys([*item["material_ids"], *wanted])),
        })
    print("提交 DataAgent 建模，会话", title, item["id"])
    call("POST", ws_path(ws, f"/sessions/{item['id']}/agent-conversation/messages"),
         {"content": prompt, "metadata": {"mode": "model"}})
    done = wait_for_run(ws, item["id"])
    print("结束:", done.get("task_status"), done.get("task_detail"))


def stage_model() -> None:
    run_modeling([material(workspace(), MATERIAL)], PREPARED_TITLE, MODEL_PROMPT)


def table_material(ws: dict) -> dict:
    item = connection(ws)
    return call("POST", ws_path(ws, f"/connections/{item['id']}/table-material"),
                {"tables": TABLE_NAMES})


def stage_standby() -> None:
    """Backups for the two live runs, both modeled with proposals left pending."""
    ws = workspace()
    run_modeling([material(ws, RETURNS_MATERIAL), material(ws, RETURNS_LOG)],
                 STANDBY_TOPDOWN, RETURNS_PROMPT)
    run_modeling([table_material(ws)], STANDBY_BOTTOMUP, TABLES_PROMPT)


def all_proposals(ws: dict, session: dict) -> list[dict]:
    base = ws_path(ws, f"/sessions/{session['id']}/proposal-batches")
    proposals = []
    for batch in call("GET", base)["items"]:
        detail = call("GET", f"{base}/{batch['id']}")
        proposals.extend(detail.get("items") or [])
    return proposals


def stage_publish() -> None:
    ws = workspace()
    session = session_by_title(ws, PREPARED_TITLE)
    if session is None or session.get("task_status") != "finished":
        raise SystemExit("建模尚未成功完成，先（重新）运行 model 阶段")
    pending = [p for p in all_proposals(ws, session) if p.get("status") in {"pending", "open", None}]
    if pending:
        print("接受提案", len(pending), "条")
        call("POST", ws_path(ws, f"/sessions/{session['id']}/proposal-decisions"), {
            "idempotency_key": str(uuid.uuid4()),
            "expected_session_revision": session["revision"],
            "decisions": [{"proposal_id": p["id"], "decision": "accept"} for p in pending],
        })
        session = call("GET", ws_path(ws, "/sessions/" + session["id"]))
    preview = call("POST", ws_path(ws, f"/sessions/{session['id']}/preview"),
                   {"expected_session_revision": session["revision"]})
    if preview.get("conflicts"):
        raise SystemExit("存在冲突，请在发布页处理: " + json.dumps(preview["conflicts"])[:400])
    result = call("POST", ws_path(ws, f"/sessions/{session['id']}/publish"), {
        "expected_session_revision": session["revision"],
        "expected_current_version_id": preview.get("current_version_id"),
        "expected_merged_snapshot_sha256": preview["merged_snapshot_sha256"],
        "message": "根据《渠道销售业务说明》自动建模",
    })
    print("已发布 v%s" % result["version"]["version"])


CONNECTION = {
    "name": "销售业务库", "kind": "mysql", "host": "127.0.0.1", "port": 3306,
    "database": "demo_analytics", "username": "of_readonly",
}
# Object technical name -> (table, {property technical name: column}).
TABLES = {
    "Customer": ("customers", {"customer_id": "id", "customer_name": "customer_name",
                               "city": "city", "sign_date": "signup_date"}),
    "Order": ("orders", {"order_id": "id", "order_time": "order_date",
                         "order_status": "order_status", "order_amount": "total_amount"}),
    "Product": ("products", {"product_id": "id", "product_name": "product_name",
                             "category": "category", "standard_price": "unit_price"}),
    "OrderLine": ("order_items", {"line_id": "id", "quantity": "quantity",
                                  "unit_price": "unit_price", "line_amount": "line_amount"}),
}
# Foreign key column on the "many" table pointing at the "one" table's id.
FOREIGN_KEYS = {
    ("Customer", "Order"): "customer_id",
    ("Order", "OrderLine"): "order_id",
    ("Product", "OrderLine"): "product_id",
}
DATA_SESSION_TITLE = "配置数据映射（演示预备）"
# The database keys are integers. 客户编号 is left as the model typed it: the
# demo fixes it by hand (see the demo script, step 4).
INTEGER_IDS = {"order_id", "product_id", "line_id"}


def connection(ws: dict) -> dict:
    existing = {c["name"]: c for c in call("GET", ws_path(ws, "/connections"))["items"]}
    if CONNECTION["name"] not in existing:
        print("创建只读数据连接", CONNECTION["name"])
        existing[CONNECTION["name"]] = call("POST", ws_path(ws, "/connections"), {
            **CONNECTION, "password": os.environ.get("OF_MYSQL_PASSWORD", "of_readonly_demo")})
    item = existing[CONNECTION["name"]]
    print("连接测试:", call("POST", ws_path(ws, f"/connections/{item['id']}/test"), {}))
    return item


def stage_connect() -> None:
    connection(workspace())


def stage_data() -> None:
    """Fallback only: map the tables by script instead of bottom-up modeling."""
    ws = workspace()
    connection(ws)

    session = session_by_title(ws, DATA_SESSION_TITLE) or call(
        "POST", ws_path(ws, "/sessions"), {"title": DATA_SESSION_TITLE})
    draft = session["draft"]
    types = {t["technical_name"]: t for t in draft["object_types"]}
    props = {}
    for prop in draft["properties"]:
        props.setdefault(prop["owner_ref"]["ref"], {})[prop["technical_name"]] = prop
    form = session["legacy_mapping_form"]
    mappings = []
    joins = {}
    for technical, (table, columns) in TABLES.items():
        owner = types[technical]
        known = props.get(owner["id"], {})
        missing = set(columns) - set(known)
        if missing:
            raise SystemExit(f"{owner['name']} 缺少属性 {sorted(missing)}，请核对建模结果")
        old = next((m for m in form["mappings"] if m["type_id"] == owner["id"]), None)
        mappings.append({
            "id": old["id"] if old else str(uuid.uuid4()),
            "type_id": owner["id"], "connection_alias": CONNECTION["name"],
            "table_name": table, "schema_name": CONNECTION["database"],
            "key_column": "id", "fields": columns,
        })
    by_id = {t["id"]: t["technical_name"] for t in draft["object_types"]}
    for link in draft["link_types"]:
        owner = link["owner_ref"]["ref"]
        if len(link["roles"]) != 1 or link["roles"][0]["concept"]["kind"] != "object_type":
            continue
        other = link["roles"][0]["concept"]["ref"]
        ends = (by_id[owner], by_id[other])
        if ends in FOREIGN_KEYS:
            joins[link["id"]] = {"owner_columns": ["id"], "role_columns": [FOREIGN_KEYS[ends]]}
        elif ends[::-1] in FOREIGN_KEYS:
            joins[link["id"]] = {"owner_columns": [FOREIGN_KEYS[ends[::-1]]], "role_columns": ["id"]}
        else:
            raise SystemExit(f"关系 {link['name']} 的两端 {ends} 没有对应外键")
        print("  关系", link["name"], ends, joins[link["id"]])
    for prop in draft["properties"]:
        if prop["technical_name"] in INTEGER_IDS:
            prop["value_kind"] = "integer"
            prop["roles"][0]["concept"] = {"kind": "builtin", "ref": "Integer"}
    session = call("PUT", ws_path(ws, "/sessions/" + session["id"]),
                   {"revision": session["revision"], "draft": draft, "legacy_mappings": mappings, "legacy_joins": joins})
    publish_session(ws, session, "对接销售业务库：四个业务对象与三条关系")


def publish_session(ws: dict, session: dict, message: str) -> None:
    preview = call("POST", ws_path(ws, f"/sessions/{session['id']}/preview"),
                   {"expected_session_revision": session["revision"]})
    if preview.get("conflicts"):
        raise SystemExit("存在冲突，请在发布页处理: " + json.dumps(preview["conflicts"])[:400])
    result = call("POST", ws_path(ws, f"/sessions/{session['id']}/publish"), {
        "expected_session_revision": session["revision"],
        "expected_current_version_id": preview.get("current_version_id"),
        "expected_merged_snapshot_sha256": preview["merged_snapshot_sha256"],
        "message": message,
    })
    print("已发布 v%s" % result["version"]["version"])


TOKEN_NAME = "DataAgent 问数助手"
MCP_PROTOCOL = "2025-11-25"


def mcp_url(ws: dict) -> str:
    return f"{API}/api/v1/ontology/workspaces/{ws['id']}/mcp"


def stage_token() -> None:
    ws = workspace()
    for item in call("GET", ws_path(ws, "/service-tokens"))["items"]:
        if item["name"] == TOKEN_NAME:
            call("DELETE", ws_path(ws, "/service-tokens/" + item["id"]))
    created = call("POST", ws_path(ws, "/service-tokens"),
                   {"name": TOKEN_NAME, "scopes": ["ontology:read", "instances:read"]})
    OUT.mkdir(exist_ok=True)
    config = {"mcpServers": {"ontofoundry": {
        "type": "http", "url": mcp_url(ws),
        "headers": {"Authorization": "Bearer " + created["token"]}}}}
    target = OUT / "mcp-config.json"
    target.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    print("已签发令牌，MCP 配置写入", target)


def mcp(ws: dict, token: str, name: str, arguments: dict) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}
    answer = call("POST", mcp_url(ws).removeprefix(API), body, headers={
        "Authorization": "Bearer " + token, "MCP-Protocol-Version": MCP_PROTOCOL,
        "Accept": "application/json, text/event-stream"})
    if "error" in answer:
        raise SystemExit(f"{name} 失败: {answer['error']}")
    result = answer["result"]
    if result.get("isError"):
        raise SystemExit(f"{name} 失败: {result['content'][0]['text'][:400]}")
    return result.get("structuredContent") or json.loads(result["content"][0]["text"])


def every_row(ws, token, version, type_id, q=""):
    rows, cursor = [], None
    while True:
        page = mcp(ws, token, "search_objects", {
            "version_id": version, "source": "database", "type_id": type_id, "q": q,
            "limit": 100, **({"cursor": cursor} if cursor else {})})
        rows += page["items"]
        cursor = page.get("next_cursor")
        if not cursor:
            return rows


def stage_check() -> None:
    ws = workspace()
    token = json.loads((OUT / "mcp-config.json").read_text())["mcpServers"]["ontofoundry"][
        "headers"]["Authorization"].removeprefix("Bearer ")
    version = mcp(ws, token, "get_ontology_version", {})
    vid = version["version_id"]
    types = {t["name"]: t["id"] for t in mcp(ws, token, "list_ontology_elements",
                                             {"kind": "object_type", "version_id": vid})["items"]}
    mapping_elements = mcp(ws, token, "list_ontology_elements", {"kind": "mapping", "version_id": vid})["items"]
    if len(mapping_elements) != 4:
        raise SystemExit("简单映射视图应有 4 个可查询概念，请检查原生语义层")
    print("版本", version.get("version"), "对象", sorted(types), "可查询映射", len(mapping_elements))
    customer = every_row(ws, token, vid, types["客户"], "星海贸易")[0]
    print("Q1 星海贸易:", json.dumps(customer.get("values") or customer, ensure_ascii=False)[:300])
    product = every_row(ws, token, vid, types["商品"], "经典手冲壶")[0]
    print("Q2 经典手冲壶:", json.dumps(product.get("values") or product, ensure_ascii=False)[:300])
    orders = every_row(ws, token, vid, types["订单"])
    total = sum(Decimal(str((o.get("values") or o)["order_amount"])) for o in orders)
    print("Q3 订单数", len(orders), "总金额", total)
    first = orders[0]
    graph = mcp(ws, token, "expand_object_graph", {"ref": first["ref"], "depth": 1,
                                                    "version_id": vid})
    print("Q4 订单邻域:", json.dumps(graph, ensure_ascii=False)[:600])


# Second scenario: real hand-built Ossie models. REDACTED stays empty for a live
# import; REDACTED账户模型 is imported ahead so incremental modeling can run on it.
OSSIE_ROOT = Path("/Users/guoruping/project/bigdata/onedata/skills")
ACCOUNT_FILE = OSSIE_ROOT / "account-ossie-skill/assets/REDACTED"
FREEZE_MATERIAL = CASE.parent / "ossie-import" / "materials" / "REDACTED冻结管理办法.md"
FREEZE_TITLE = "账户冻结（备用）"
FREEZE_PROMPT = (
    "目标范围：REDACTED冻结。基于已发布的账户模型增量建模：复用已有的金融期货交易所、"
    "结算会员和专用资金账户，补充冻结相关的对象、属性、关系和规则，并抽取冻结登记中的记录。"
)
OSSIE_SPACES = [
    ("account-model", "REDACTED账户模型",
     "手工建模的 Apache Ossie 账户模型 v2：会员、账户、结算与担保关系。"),
    ("REDACTED", "REDACTED",
     "手工建模的 Apache Ossie REDACTED本体，含逻辑语义模型与标准映射。"),
]


def space(slug: str) -> dict | None:
    return next((w for w in call("GET", "/api/v1/workspaces")["items"] if w["slug"] == slug), None)


def stage_ossie() -> None:
    for slug, name, description in OSSIE_SPACES:
        if not space(slug):
            call("POST", "/api/v1/workspaces", {"name": name, "slug": slug, "description": description})
            print("创建空间", name)
    account = space("account-model")
    if not account.get("current_version"):
        session = call("POST", ws_path(account, "/imports/ossie"),
                       {"document": json.loads(ACCOUNT_FILE.read_text()), "mode": "replace",
                        "title": "导入 account_model_v2"})
        publish_session(account, session, "导入手工模型 account_model_v2")
    global workspace
    keep = workspace
    workspace = lambda: space("account-model")  # noqa: E731 - reuse run_modeling for this space
    try:
        run_modeling([material(account, FREEZE_MATERIAL)], FREEZE_TITLE, FREEZE_PROMPT)
    finally:
        workspace = keep

STAGES = {"model": stage_model, "publish": stage_publish, "data": stage_data,
          "connect": stage_connect,
          "token": stage_token, "check": stage_check,
          "standby": stage_standby, "ossie": stage_ossie}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
        raise SystemExit(__doc__)
    STAGES[sys.argv[1]]()
