"""Run the plan step of each scenario on a live platform and score the concept list.

Runs go out in plan mode. The agent submits its concept list as a plan card
(ExitPlanMode) and the run waits; the list is scored from that plan and the
run is cancelled. With --extract, scenarios that have extraction.json get the
plan approved instead (a confirm_reply other than “确认” is sent first as a
revision note), and the proposal batch the same run produces is scored for
properties, relations, instances, mappings and metrics (score_extraction.py).
Question cards are answered with their recommended options.

This calls the platform's HTTP API like the browser does, so it spends model
tokens: run it off-peak and only with the user's agreement. The agent receives
materials (and linked tables) only; gold.json never leaves this machine.

    cd apps/api
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

import re

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import score  # noqa: E402
from score_extraction import score_extraction  # noqa: E402

ROOT = Path(__file__).resolve().parent / "scenarios"
SETS = {"public": ROOT, "heldout": ROOT.parent / "heldout"}
ACTIVE = {"queued", "running", "waiting_input", "waiting_permission"}
RECOMMENDED = re.compile(r"\s*[（(](推荐|Recommended|recommended)[）)]\s*$")


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
    """Send a plan-mode message; return when the run ends or waits on a plan card."""
    base = f"/workspaces/{workspace_id}/sessions/{session_id}"
    platform.call("POST", base + "/agent-conversation/messages",
                  {"content": prompt, "metadata": {"mode": "model"}, "settings": {"permission_mode": "plan"}})
    return wait(platform, workspace_id, session_id, timeout_s)


def wait(platform, workspace_id, session_id, timeout_s, answered=()):
    """Poll until the run ends or shows a plan card not answered yet.

    Question cards are answered on the spot with their recommended options,
    the same answers the timeout policy would give.
    """
    base = f"/workspaces/{workspace_id}/sessions/{session_id}"
    started = time.monotonic()
    seen_active = False
    while time.monotonic() - started < timeout_s:
        time.sleep(10)
        state = platform.call("GET", base)
        status = state["task_status"]
        seen_active = seen_active or status in ACTIVE
        if status == "waiting_input":
            card = pending(conversation(platform, workspace_id, session_id), "question_request")
            if card:
                interact(platform, workspace_id, session_id, state, "question", card["request_id"],
                         {"answers": recommended_answers(card.get("questions") or [])})
            continue
        if status == "waiting_permission":
            card = pending(conversation(platform, workspace_id, session_id), "permission_request")
            if card and card.get("request_id") not in answered:
                return state, card, round(time.monotonic() - started)
            continue
        if seen_active and status not in ACTIVE:
            return state, None, round(time.monotonic() - started)
    raise SystemExit("运行超时")


def interact(platform, workspace_id, session_id, state, kind, request_id, payload):
    platform.call("POST", f"/workspaces/{workspace_id}/sessions/{session_id}/agent-conversation/interactions",
                  {"task_id": state["dataagent_task_id"], "kind": kind, "request_id": request_id, "payload": payload})


def pending(record, record_type):
    """The newest unanswered card of this type in the conversation."""
    answered_type = {"question_request": "question_answer", "permission_request": "permission_decision"}[record_type]
    requests, answered = {}, set()
    for message in record.get("messages") or []:
        for event in message.get("records") or []:
            data = event.get("data") or {}
            if event.get("record_type") == record_type:
                requests[data.get("request_id")] = data
            elif event.get("record_type") == answered_type:
                answered.add(data.get("request_id"))
    open_cards = [data for request_id, data in requests.items() if request_id not in answered]
    return open_cards[-1] if open_cards else None


def recommended_answers(questions):
    answers = []
    for question in questions:
        labels = [o.get("label", "") if isinstance(o, dict) else str(o) for o in question.get("options") or []]
        picks = [label for o, label in zip(question.get("options") or [], labels)
                 if (isinstance(o, dict) and o.get("recommended") is True) or RECOMMENDED.search(label)]
        picks = picks if question.get("multiSelect") else picks[:1]
        answers.append({"header": question.get("header", ""), "question": question.get("question", ""),
                        "selected": picks, "other": "", "skipped": not picks})
    return answers


def plan_entities(markdown):
    """The concept table of a plan as {items: [{display_name, name}]}.

    The plan card is free Markdown; the first table whose header names the
    concept is read row by row, its first cell split on ／ or / into Chinese
    name and identifier (a separate 英文标识 column is used when present).
    """
    rows = [line.strip().strip("|").split("|") for line in markdown.splitlines() if line.strip().startswith("|")]
    if not rows:
        return {"items": []}
    header = [cell.strip() for cell in rows[0]]
    english = next((i for i, cell in enumerate(header) if "英文" in cell or "标识" in cell), None)
    items = []
    for cells in rows[1:]:
        cells = [cell.strip().strip("`*") for cell in cells]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        parts = [part.strip().strip("`*") for part in re.split(r"[／/]", cells[0]) if part.strip()]
        item = {"display_name": parts[0] if parts else ""}
        if english is not None and english < len(cells) and english != 0:
            item["name"] = cells[english]
        elif len(parts) > 1:
            item["name"] = parts[1]
        items.append(item)
    return {"items": items}


def latest_batch(platform, workspace_id, session_id):
    base = f"/workspaces/{workspace_id}/sessions/{session_id}/proposal-batches"
    page = platform.call("GET", base + "?limit=1")["items"]
    return platform.call("GET", f"{base}/{page[0]['id']}") if page else {"items": []}


def extract(platform, workspace_id, session_id, state, card, extraction, gold, out):
    """Approve the plan (after any revision note), then score and archive the proposal batch."""
    reply = extraction["confirm_reply"].strip()
    answered = {card["request_id"]}
    seconds = 0
    if reply not in {"确认", "确认。"}:
        interact(platform, workspace_id, session_id, state, "permission", card["request_id"],
                 {"decision": "deny", "note": reply})
        state, card, seconds = wait(platform, workspace_id, session_id, 1800, answered)
        if card is None:
            raise SystemExit("调整计划后运行结束，没有再次提交计划")
        answered.add(card["request_id"])
    interact(platform, workspace_id, session_id, state, "permission", card["request_id"], {"decision": "allow"})
    state, extra, more = wait(platform, workspace_id, session_id, 1800, answered)
    if extra is not None:
        raise SystemExit("批准后又提交了新计划")
    seconds += more
    batch = latest_batch(platform, workspace_id, session_id)
    datasets = (state.get("draft") or {}).get("datasets") or []
    result = score_extraction(gold, extraction, batch.get("items") or [], datasets)
    totals, answer = usage(conversation(platform, workspace_id, session_id))
    summary = {**result, "result_state": state.get("result_state"), "seconds": seconds, **totals}
    write(out / "extraction-score.json", summary)
    write(out / "batch.json", batch)
    write(out / "extraction-answer.md", answer)
    return summary


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
    parser.add_argument("--extract", action="store_true", help="批准计划卡片，继续给同一运行产出的提案打分（只跑有 extraction.json 的场景）")
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
            card = pending(conversation(platform, workspace_id, session_id), "permission_request")
        else:
            workspace_id, session_id = prepare(platform, name, gold, stamp, root)
            state, card, seconds = run_turn(platform, workspace_id, session_id, gold["prompt"])
        plan_md = (card or {}).get("summary") or ""
        entities = plan_entities(plan_md)
        result = score(gold, entities)
        record = conversation(platform, workspace_id, session_id)
        totals, answer = usage(record)
        summary = {**result, "workspace_id": workspace_id, "session_id": session_id,
                   "result_state": state.get("result_state"), "seconds": seconds, **totals}
        write(out / name / "score.json", summary)
        write(out / name / "plan.md", plan_md)
        write(out / name / "plan.json", entities)
        write(out / name / "conversation.json", record)
        write(out / name / "answer.md", answer)
        print(f"{name}: 准确率 {result['precision']} 召回率 {result['recall']} "
              f"错误 {result['errors'] or '无'} 漏掉 {result['missed'] or '无'} 轮数 {totals['turns']}")
        if args.extract and not args.score_only and card:
            extraction = json.loads((root / name / "extraction.json").read_text(encoding="utf-8"))
            done = extract(platform, workspace_id, session_id, state, card, extraction, gold, out / name)
            summary["extraction"] = {k: v for k, v in done.items() if k != "details"}
            write(out / name / "conversation.json", conversation(platform, workspace_id, session_id))
            print(f"{name} 抽取: " + " ".join(f"{k} {done[k]['found']}/{done[k]['expected']}"
                                             for k in ("properties", "relations", "instances", "mappings", "metrics")))
        elif card and not args.score_only:
            # Only the plan is scored: stop the run instead of letting it wait.
            platform.call("POST", f"/workspaces/{workspace_id}/sessions/{session_id}/agent-conversation/cancel",
                          {"task_id": state["dataagent_task_id"]})
        results.append({k: v for k, v in summary.items() if k != "details"})
    write(out / "summary.json", results)


if __name__ == "__main__":
    main()
