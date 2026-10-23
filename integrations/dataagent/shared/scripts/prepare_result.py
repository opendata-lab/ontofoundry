"""Assemble a pinned proposal batch without inferring business content."""

import json
from copy import deepcopy
from pathlib import Path

from check_result import (
    atomic_write,
    diagnostic,
    encode,
    pinned_targets,
    same_json,
    validate_file,
)
from runpaths import (
    PARTS,
    HintParser,
    command,
    error,
    existing,
    fragment_paths,
    relative,
)


class PrepareInputError(ValueError):
    """A precise fragment diagnostic, before any output is replaced."""


def effective_ref(item, index):
    """The client_ref merging gives an item: its own, or a generated one for a create."""
    if not isinstance(item, dict):
        return None
    if item.get("operation") in {"update", "delete"}:
        return item.get("client_ref")
    return item.get("client_ref", f"{item.get('target_kind')}-{index + 1}")


def assemble(context, fragments):
    items, refs = [], set()
    existing = pinned_targets(context)
    for fragment_index, fragment in enumerate(fragments):
        if not isinstance(fragment, list):
            raise PrepareInputError(
                diagnostic(
                    f"/fragments/{fragment_index}",
                    "PREPARE_INPUT",
                    "items 数组片段",
                    fragment,
                )
            )
        for raw in fragment:
            index = len(items)
            item = deepcopy(raw)

            def fail(field, expected, actual, code="PREPARE_INPUT", index=index, item=item):
                raise PrepareInputError(
                    diagnostic(
                        f"/items/{index}/{field}",
                        code,
                        expected,
                        actual,
                        item,
                    )
                )

            if not isinstance(item, dict):
                fail("", "提案对象", item)
            for field in ("operation", "target_kind"):
                if field not in item:
                    fail(field, "必填字段", "缺失")
            if item["operation"] in {"update", "delete"}:
                target = item.get("target_id")
                found = existing.get((item["target_kind"], target)) if isinstance(target, str) else None
                if found is None:
                    fail("target_id", "固定草稿中的定义或实例基线中的实例 UUID", target, "TARGET_NOT_FOUND")
                before, target_hash = found
                for field, value, code in (
                    ("before", before, "BEFORE_MISMATCH"),
                    ("expected_target_hash", target_hash, "TARGET_HASH_MISMATCH"),
                ):
                    if field in item and not same_json(item[field], value):
                        fail(field, value, item[field], code)
                    item[field] = deepcopy(value)
                if item["operation"] == "delete":
                    item.setdefault("after", None)
            else:
                item.setdefault("before", None)
                item["client_ref"] = effective_ref(item, index)
            ref = item.get("client_ref")
            if isinstance(ref, str):
                if ref in refs:
                    fail("client_ref", "不重复的 client_ref", ref)
                refs.add(ref)
            items.append(item)
    return {**context["run"], "items": items}


def workspace_path(raw):
    path = Path(raw).resolve()
    if not path.is_relative_to(Path.cwd().resolve()):
        raise ValueError("片段、候选与输出路径必须位于当前工作区")
    return path


def fragment_files(raw_paths):
    """Files in order; a directory such as modeling/parts/ expands to its *.json by name."""
    files = []
    for raw in raw_paths:
        path = workspace_path(raw)
        if path.is_dir():
            found = sorted(p for p in path.glob("*.json") if p.is_file())
            if not found:
                raise ValueError(f"片段目录中没有 JSON 片段：{raw}")
            files.extend(found)
        else:
            files.append(path)
    return files


def located(message, origins):
    """Name the fragment file and index behind a merged /items/N pointer."""
    import re

    match = re.search(r"/items/(\d+)", message)
    if not match or int(match.group(1)) >= len(origins):
        return message
    path, index = origins[int(match.group(1))]
    return message.replace(match.group(0), f"{path}#/{index}（合并后 {match.group(0)}）", 1)


def load_inputs(raw_fragments, context_path):
    """Fragments with each merged item's origin, and the context; errors name the file."""
    paths = [p for raw in raw_fragments for p in fragment_paths(raw)]
    fragments, origins = [], []
    try:
        files = fragment_files([str(p) for p in paths])
    except ValueError as exc:
        if "没有 JSON 片段" not in str(exc):
            raise
        raise InputProblem("NO_FRAGMENTS", str(exc), f"modeling/parts/ 现有：{existing(PARTS, '*.json')}",
                           "先把片段写成 modeling/parts/<编号>-<名称>.json 再合并") from None
    for path in files:
        shown = relative(path)
        try:
            fragment = json.loads(path.read_bytes())
        except FileNotFoundError:
            raise InputProblem("FILE_NOT_FOUND", f"片段 {shown} 不存在", f"modeling/parts/ 现有：{existing(PARTS, '*.json')}",
                               "先写片段再合并；片段可写 01、01-types 或路径") from None
        except json.JSONDecodeError as exc:
            raise InputProblem("JSON_INVALID", f"片段 {shown} 第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}", "文件已存在",
                               f"修正该处后先单独检查：{command('check_part.py', '--work-pack', '<工作包>', shown)}") from None
        fragments.append(fragment)
        origins += [(shown, i) for i in range(len(fragment))] if isinstance(fragment, list) else []
    try:
        context = json.loads(Path(context_path).read_bytes())
    except (OSError, ValueError) as exc:
        raise InputProblem("INPUT_UNREADABLE", f"固定上下文 {context_path} 无法读取（{type(exc).__name__}）", "",
                           "路径照工作包的 context_file；文件损坏时重新发起本轮", retry=False) from None
    return fragments, origins, context


class InputProblem(Exception):
    def __init__(self, code, reason, state, next_step=None, retry=True):
        super().__init__(code)
        self.args_ = (code, reason, state, next_step, retry)

    def text(self, outcome):
        code, reason, state, next_step, retry = self.args_
        return error(code, reason, "；".join(x for x in (state, outcome) if x), next_step, retry)


def main():
    parser = HintParser(description="合并片段为提案批次；--work-pack 自动取上下文、Schema 与结果路径")
    parser.add_argument("--work-pack", help="工作包；从中取 context_file、schema_file、result_file")
    parser.add_argument("--context")
    parser.add_argument("--schema")
    parser.add_argument("--output")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument("fragments", nargs="*", help="片段文件、简称（01、01-types）或目录；省略时合并 modeling/parts/")
    args = parser.parse_args()
    outcome = "候选文件未生成，最终文件未替换"
    if "-" in args.fragments:
        print(error("INVALID_ARGUMENT", "片段不能从标准输入读取", outcome,
                    "先写到 modeling/parts/ 再合并：" + command("prepare_result.py", "--work-pack", args.work_pack or "<工作包>")))
        return 2
    try:
        if args.work_pack:
            pack = json.loads(Path(args.work_pack).read_bytes())
            args.context = args.context or pack["context_file"]
            args.schema = args.schema or pack["schema_file"]
            args.output = args.output or pack["result_file"]
    except FileNotFoundError:
        print(error("FILE_NOT_FOUND", f"工作包 {args.work_pack} 不存在", outcome, "路径照 init_workflow 打印的本轮工作包复制"))
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(error("INPUT_UNREADABLE", f"工作包 {args.work_pack} 无法使用（{type(exc).__name__}）", outcome, retry=False))
        return 1
    if not (args.context and args.schema and args.output):
        parser.error("需要 --work-pack <工作包>，或同时给出 --context、--schema、--output")
    raw_fragments = args.fragments or [str(PARTS) + "/"]
    report = Path(args.output + ".errors.json")
    try:
        output = workspace_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        fragments, origins, context = load_inputs(raw_fragments, args.context)
        candidate = output.with_suffix(".pending.json")
        batch = assemble(context, fragments)
        atomic_write(candidate, encode(batch))
    except (InputProblem, PrepareInputError) as exc:
        message = exc.text(outcome) if isinstance(exc, InputProblem) else located(str(exc), origins) + f"\n{outcome}"
        try:
            atomic_write(workspace_path(str(report)), encode({"total": 1, "errors": [message]}))
            saved = f"报告：{report}"
        except (OSError, ValueError):
            saved = "报告未保存"
        print(f"{message}；{saved}")
        return 1
    except ValueError as exc:
        print(error("PATH_OUT_OF_SCOPE", str(exc), outcome, "片段、候选与输出都用工作区相对路径", retry=False))
        return 1
    except OSError as exc:
        print(error("WRITE_FAILED", f"写入 {relative(output) if 'output' in locals() else args.output} 失败：{type(exc).__name__}", outcome, retry=False))
        return 1
    return validate_file(
        candidate, args.schema, args.context, repair=args.repair, publish=output, origins=origins
    )

if __name__ == "__main__":
    raise SystemExit(main())
