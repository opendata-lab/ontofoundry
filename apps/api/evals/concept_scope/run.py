"""Run the plan step of each scenario on a live platform and score the concept list.

With --extract, scenarios that have extraction.json also get the confirming
reply; the resulting proposal batch is scored for properties, relations,
instances, mappings and metrics (score_extraction.py).

This calls the platform's HTTP API like the browser does, so it spends model
tokens: run it off-peak and only with the user's agreement. The agent receives
materials (and linked tables) only; gold.json never leaves this machine.

    cd apps/api
    set -a; . <api env>; set +a        # ONTOFOUNDRY_DATABASE_URL for reading the saved plan
    .venv/bin/python evals/concept_scope/run.py --api http://<ip>:8000 --origin http://<ip>:5199 \
        --output-dir evals/concept_scope/results/<日期-说明> [--scenario wind_inspection ...]

Each scenario keeps its score, the saved plan, the full conversation and the
final answer, so a run can be presented or re-scored later without rerunning.

Table scenarios need the schema from tables.sql on a MySQL server reachable as
EVAL_MYSQL_HOST/EVAL_MYSQL_PORT/EVAL_MYSQL_USER/EVAL_MYSQL_PASSWORD (read only).
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import score  # noqa: E402
from score_extraction import score_extraction  # noqa: E402

ROOT = Path(__file__).resolve().parent / "scenarios"
SETS = {"public": ROOT, "heldout": ROOT.parent / "heldout"}
ACTIVE = {"queued", "running", "waiting_permission"}


class Platform:
    def __init__(self, api, origin):
        self.api, self.origin = api.rstrip("/") + "/api/v1", origin

    def call(self, method, path, body=None, raw=None, content_type="application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(
            self.api + path, data=data, method=method,
            headers={"Origin": self.origin, "Content-Type": content_type},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"{method} {path} -> {exc.code} {exc.read()[:400].decode(errors='replace')}") from exc


def prepare(platform, name, gold, stamp, root=ROOT):
    folder = root / name
    space = platform.call("POST", "/workspaces", {
        "name": f"概念评测 {name} {stamp}", "slug": f"eval-{name.replace('_', '-')}-{stamp}",
        "description": "概念范围评测（虚构材料）",
    })
    base = f"/workspaces/{space['id']}"
    materials = [
        platform.call("POST", base + "/materials?name=" + urllib.parse.quote(path.name),
                      raw=path.read_bytes(), content_type="text/markdown")["id"]
        for path in sorted((folder / "materials").glob("*.md"))
    ]
    links = []
    if gold.get("schema"):
        connection = platform.call("POST", base + "/connections", {
            "name": "评测只读库", "kind": "mysql",
            "host": os.environ.get("EVAL_MYSQL_HOST", "127.0.0.1"),
            "port": int(os.environ.get("EVAL_MYSQL_PORT", "3306")),
            "username": os.environ["EVAL_MYSQL_USER"], "password": os.environ["EVAL_MYSQL_PASSWORD"],
        })
        jobs = f"{base}/connections/{connection['id']}/assets/sync-jobs"
        job = platform.call("POST", f"{jobs}?schema_name={gold['schema']}", {"scope": "selected", "tables": gold["tables"]})
        while job["state"] in ("queued", "running"):
            time.sleep(1)
            job = platform.call("GET", f"{jobs}/{job['id']}")
        if job["state"] != "succeeded":
            raise SystemExit(f"{name}：同步表失败 {job['state']}")
        links = [{"connection_id": connection["id"], "schema_name": gold["schema"], "table_name": t} for t in gold["tables"]]
    session = platform.call("POST", base + "/sessions", {"title": f"概念评测 {name}"})
    session = platform.call("PUT", f"{base}/sessions/{session['id']}", {
        "revision": session["revision"], "draft": session["draft"],
        "material_ids": materials, "linked_tables": links,
    })
    return space["id"], session["id"]


def run_turn(platform, workspace_id, session_id, prompt, timeout_s=900):
    base = f"/workspaces/{workspace_id}/sessions/{session_id}"
    started = time.monotonic()
    platform.call("POST", base + "/agent-conversation/messages", {"content": prompt, "metadata": {"mode": "model"}})
    seen_active = False
    while time.monotonic() - started < timeout_s:
        time.sleep(10)
        state = platform.call("GET", base)
        seen_active = seen_active or state["task_status"] in ACTIVE
        if seen_active and state["task_status"] not in ACTIVE:
            return state, round(time.monotonic() - started)
    raise SystemExit("运行超时")


def latest_batch(platform, workspace_id, session_id):
    base = f"/workspaces/{workspace_id}/sessions/{session_id}/proposal-batches"
    page = platform.call("GET", base + "?limit=1")["items"]
    return platform.call("GET", f"{base}/{page[0]['id']}") if page else {"items": []}


def extract(platform, workspace_id, session_id, extraction, gold, out):
    """Confirm the plan, then score and archive the proposal batch."""
    state, seconds = run_turn(platform, workspace_id, session_id, extraction["confirm_reply"], timeout_s=1800)
    batch = latest_batch(platform, workspace_id, session_id)
    datasets = (state.get("draft") or {}).get("datasets") or []
    result = score_extraction(gold, extraction, batch.get("items") or [], datasets)
    totals, answer = usage(conversation(platform, workspace_id, session_id))
    summary = {**result, "result_state": state.get("result_state"), "seconds": seconds, **totals}
    write(out / "extraction-score.json", summary)
    write(out / "batch.json", batch)
    write(out / "extraction-answer.md", answer)
    return summary


def saved_plan(session_id):
    engine = sa.create_engine(os.environ["ONTOFOUNDRY_DATABASE_URL"])
    with engine.connect() as connection:
        manifest = connection.execute(
            sa.text("SELECT run_manifest_json FROM modeling_sessions WHERE id = :id"), {"id": session_id}
        ).scalar()
    engine.dispose()
    return (manifest or {}).get("prior_plan") or {}


def conversation(platform, workspace_id, session_id):
    return platform.call("GET", f"/workspaces/{workspace_id}/sessions/{session_id}/agent-conversation")


def usage(record):
    last = (record.get("messages") or [{}])[-1]
    totals = {"turns": 0, "input": 0, "cache": 0, "output": 0, "tool_errors": 0}
    for event in last.get("records") or []:
        kind = event.get("event_type")
        if kind == "turn.started":
            totals["turns"] += 1
        elif kind == "usage.updated":
            used = event["data"]["usage"]
            totals["input"] += used.get("input_tokens", 0)
            totals["cache"] += used.get("cache_read_input_tokens", 0)
            totals["output"] += used.get("output_tokens", 0)
        elif kind == "tool.completed" and event.get("data", {}).get("is_error"):
            totals["tool_errors"] += 1
    return totals, last.get("content") or ""


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="跑各场景的计划轮并给概念清单打分，完整保存过程数据")
    parser.add_argument("--api", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--set", choices=sorted(SETS), default="public", help="public 为公开场景；heldout 为不公开的留出场景")
    parser.add_argument("--level", choices=["basic", "advanced"], help="只跑某个难度的公开场景")
    parser.add_argument("--scenario", action="append", help="场景目录名，可重复；默认全部")
    parser.add_argument("--output-dir", required=True, help="结果目录，如 evals/concept_scope/results/2026-10-22-baseline")
    parser.add_argument("--extract", action="store_true", help="计划轮后回复确认，继续给抽取轮的提案打分（只跑有 extraction.json 的场景）")
    parser.add_argument("--score-only", help="不重跑，只给已有的 workspace_id:session_id 打分并存档（需配合单个 --scenario）")
    args = parser.parse_args()
    platform = Platform(args.api, args.origin)
    out = Path(args.output_dir)
    root = SETS[args.set]
    names = args.scenario or sorted(p.name for p in root.iterdir() if (p / "gold.json").is_file())
    if args.extract:
        names = [n for n in names if (root / n / "extraction.json").is_file()]
    if args.level:
        names = [n for n in names if json.loads((root / n / "gold.json").read_text(encoding="utf-8")).get("level", "basic") == args.level]
    stamp = datetime.now().strftime("%m%d%H%M")
    write(out / "meta.json", {"started_at": datetime.now().isoformat(timespec="seconds"), "commit": commit(),
                              "api": args.api, "set": args.set, "scenarios": names, "score_only": bool(args.score_only),
                              "extract": args.extract})
    results = []
    for name in names:
        gold = json.loads((root / name / "gold.json").read_text(encoding="utf-8"))
        if args.score_only:
            workspace_id, session_id = args.score_only.split(":")
            state, seconds = platform.call("GET", f"/workspaces/{workspace_id}/sessions/{session_id}"), None
        else:
            workspace_id, session_id = prepare(platform, name, gold, stamp, root)
            state, seconds = run_turn(platform, workspace_id, session_id, gold["prompt"])
        plan = saved_plan(session_id)
        result = score(gold, plan.get("entities"))
        record = conversation(platform, workspace_id, session_id)
        totals, answer = usage(record)
        summary = {**result, "workspace_id": workspace_id, "session_id": session_id,
                   "result_state": state.get("result_state"), "seconds": seconds, **totals}
        write(out / name / "score.json", summary)
        write(out / name / "plan.json", plan)
        write(out / name / "conversation.json", record)
        write(out / name / "answer.md", answer)
        print(f"{name}: 准确率 {result['precision']} 召回率 {result['recall']} "
              f"错误 {result['errors'] or '无'} 漏掉 {result['missed'] or '无'} 轮数 {totals['turns']}")
        if args.extract and not args.score_only:
            extraction = json.loads((root / name / "extraction.json").read_text(encoding="utf-8"))
            done = extract(platform, workspace_id, session_id, extraction, gold, out / name)
            summary["extraction"] = {k: v for k, v in done.items() if k != "details"}
            write(out / name / "conversation.json", conversation(platform, workspace_id, session_id))
            print(f"{name} 抽取: " + " ".join(f"{k} {done[k]['found']}/{done[k]['expected']}"
                                             for k in ("properties", "relations", "instances", "mappings", "metrics")))
        results.append({k: v for k, v in summary.items() if k != "details"})
    write(out / "summary.json", results)


if __name__ == "__main__":
    main()
