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
    notice,
    plan_not_approved,
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


def material_hashes(pack, context=None):
    """Material id -> sha256 for evidence the agent left unhashed: this run's
    materials from the work pack, earlier materials from evidence the draft and
    instance baseline already carry."""
    hashes = {}

    def recorded(value):
        if isinstance(value, dict):
            if value.get("kind") == "material" and value.get("material_id") and value.get("material_sha256"):
                hashes.setdefault(str(value["material_id"]), value["material_sha256"])
            for child in value.values():
                recorded(child)
        elif isinstance(value, list):
            for child in value:
                recorded(child)

    recorded([(context or {}).get("draft"), (context or {}).get("instance_baseline")])
    hashes.update({str(m["id"]): m["sha256"] for m in (pack or {}).get("materials") or [] if m.get("id") and m.get("sha256")})
    return hashes


def fill_material_hashes(value, hashes):
    """Evidence names a material by id; its hash is a fact of the run, not the agent's to copy."""
    if isinstance(value, dict):
        if value.get("kind") == "material" and value.get("material_id") and not value.get("material_sha256"):
            sha = hashes.get(str(value["material_id"]))
            if sha:
                value["material_sha256"] = sha
        for child in value.values():
            fill_material_hashes(child, hashes)
    elif isinstance(value, list):
        for child in value:
            fill_material_hashes(child, hashes)


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
            fill_material_hashes(item, context.get("material_hashes") or {})

            def fail(
                field, expected, actual, code="PREPARE_INPUT", index=index, item=item
            ):
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
                found = (
                    existing.get((item["target_kind"], target))
                    if isinstance(target, str)
                    else None
                )
                if found is None:
                    fail(
                        "target_id",
                        "固定草稿中的定义或实例基线中的实例 UUID",
                        target,
                        "TARGET_NOT_FOUND",
                    )
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
    return message.replace(
        match.group(0), f"{path}#/{index}（合并后 {match.group(0)}）", 1
    )


def load_inputs(raw_fragments, context_path):
    """Fragments with each merged item's origin, and the context; errors name the file."""
    paths = [p for raw in raw_fragments for p in fragment_paths(raw)]
    fragments, origins = [], []
    try:
        files = fragment_files([str(p) for p in paths])
    except ValueError as exc:
        if "没有 JSON 片段" not in str(exc):
            raise
        raise InputProblem(
            "NO_FRAGMENTS",
            str(exc),
            f"modeling/parts/ 现有：{existing(PARTS, '*.json')}",
            "先把片段写成 modeling/parts/<编号>-<名称>.json 再合并",
        ) from None
    for path in files:
        shown = relative(path)
        try:
            fragment = json.loads(path.read_bytes())
        except FileNotFoundError:
            raise InputProblem(
                "FILE_NOT_FOUND",
                f"片段 {shown} 不存在",
                f"modeling/parts/ 现有：{existing(PARTS, '*.json')}",
                "先写片段再合并；片段可写 01、01-types 或路径",
            ) from None
        except json.JSONDecodeError as exc:
            raise InputProblem(
                "JSON_INVALID",
                f"片段 {shown} 第 {exc.lineno} 行第 {exc.colno} 列：{exc.msg}",
                "文件已存在",
                f"修正该处后先单独检查：{command('check_part.py', '--work-pack', '<工作包>', shown)}",
            ) from None
        fragments.append(fragment)
        origins += (
            [(shown, i) for i in range(len(fragment))]
            if isinstance(fragment, list)
            else []
        )
    try:
        context = json.loads(Path(context_path).read_bytes())
    except (OSError, ValueError) as exc:
        raise InputProblem(
            "INPUT_UNREADABLE",
            f"固定上下文 {context_path} 无法读取（{type(exc).__name__}）",
            "",
            "路径照工作包的 context_file；文件损坏时重新发起本轮",
            retry=False,
        ) from None
    return fragments, origins, context


class InputProblem(Exception):
    def __init__(self, code, reason, state, next_step=None, retry=True):
        super().__init__(code)
        self.args_ = (code, reason, state, next_step, retry)

    def text(self, outcome):
        code, reason, state, next_step, retry = self.args_
        return error(
            code, reason, "；".join(x for x in (state, outcome) if x), next_step, retry
        )


def platform_check(pack, batch, candidate, retry_command):
    """Use the run's uploaded MCP address and credential; never duplicate graph rules."""
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote, urlsplit, urlunsplit
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        config = json.loads(Path(pack.get("platform_check_file") or pack["mcp_config_file"]).read_bytes())
        parts = urlsplit(config["url"])
        expected = (
            "/api/v1/ontology/workspaces/"
            + quote(batch["workspace_id"], safe="")
            + "/mcp"
        )
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or not parts.path.endswith(expected)
        ):
            raise ValueError("MCP 地址与本轮工作空间不一致")
        path = (
            parts.path.removesuffix("/mcp")
            + "/runs/"
            + quote(batch["run_token"], safe="")
            + "/proposal-check"
        )
        url = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        credential = config["headers"]["Authorization"]
        request = Request(
            url,
            data=candidate.read_bytes(),
            method="POST",
            headers={
                "Authorization": credential,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            report = json.load(response)
        if (
            not isinstance(report, dict)
            or not isinstance(report.get("passed"), bool)
            or any(
                type(report.get(key)) is not int or report[key] < 0
                for key in ("reviewable_count", "unacceptable_count")
            )
            or not isinstance(report.get("contract_errors"), list)
            or not isinstance(report.get("unacceptable_groups"), list)
            or any(
                not isinstance(problem, dict)
                or not isinstance(problem.get("message"), str)
                for problem in report["contract_errors"]
            )
            or any(
                not isinstance(group, dict) or not isinstance(group.get("reason"), str)
                for group in report["unacceptable_groups"]
            )
            or report["passed"]
            != (
                not report["contract_errors"]
                and not report["unacceptable_groups"]
                and not report["unacceptable_count"]
            )
        ):
            raise ValueError("平台未返回有效的检查结果")
    except HTTPError as exc:
        if exc.code < 500:
            print(
                error(
                    "PLATFORM_CHECK_REJECTED",
                    f"平台检查请求被拒绝（HTTP {exc.code}）",
                    "最终文件未替换",
                    "重新发起建模以获取有效运行凭据",
                    retry=False,
                )
            )
            return False
        print(
            notice(
                "PLATFORM_CHECK_SKIPPED",
                f"平台暂时不可达（HTTP {exc.code}），未完成平台检查",
                retry_command,
            )
        )
        return True
    except (OSError, ValueError, KeyError, TypeError, URLError) as exc:
        print(
            notice(
                "PLATFORM_CHECK_SKIPPED",
                f"平台检查未执行或未完成（{type(exc).__name__}），不能确认候选图合法",
                retry_command,
            )
        )
        return True
    report_path = candidate.with_suffix(".platform-check.json")
    atomic_write(report_path, encode(report))
    if report["passed"]:
        print(f"平台检查通过：{report['reviewable_count']} 条可审。仅检查，未入库。")
        return True
    print(
        f"平台检查未通过：{report['reviewable_count']} 条可审，{report['unacceptable_count']} 条不可接受。最终文件未替换。完整报告：{relative(report_path)}"
    )
    for problem in report["contract_errors"]:
        print(problem["message"])
    for group in report["unacceptable_groups"]:
        print(group["reason"])
    print("下一步：修正片段后执行 " + retry_command)
    return False


def main():
    parser = HintParser(
        description="合并片段为提案批次；--work-pack 自动取上下文、Schema 与结果路径"
    )
    parser.add_argument(
        "--work-pack", help="工作包；从中取 context_file、schema_file、result_file"
    )
    parser.add_argument("--context")
    parser.add_argument("--schema")
    parser.add_argument("--output")
    parser.add_argument("--repair", action="store_true")
    parser.add_argument(
        "fragments",
        nargs="*",
        help="片段文件、简称（01、01-types）或目录；省略时合并 modeling/parts/",
    )
    args = parser.parse_args()
    if refusal := plan_not_approved():
        print(refusal)
        return 1
    outcome = "候选文件未生成，最终文件未替换"
    if "-" in args.fragments:
        print(
            error(
                "INVALID_ARGUMENT",
                "片段不能从标准输入读取",
                outcome,
                "先写到 modeling/parts/ 再合并："
                + command(
                    "prepare_result.py", "--work-pack", args.work_pack or "<工作包>"
                ),
            )
        )
        return 2
    pack = {}
    try:
        if args.work_pack:
            pack = json.loads(Path(args.work_pack).read_bytes())
            args.context = args.context or pack["context_file"]
            args.schema = args.schema or pack["schema_file"]
            args.output = args.output or pack["result_file"]
    except FileNotFoundError:
        print(
            error(
                "FILE_NOT_FOUND",
                f"工作包 {args.work_pack} 不存在",
                outcome,
                "路径照 init_workflow 打印的本轮工作包复制",
            )
        )
        return 1
    except (OSError, ValueError, KeyError) as exc:
        print(
            error(
                "INPUT_UNREADABLE",
                f"工作包 {args.work_pack} 无法使用（{type(exc).__name__}）",
                outcome,
                retry=False,
            )
        )
        return 1
    if not (args.context and args.schema and args.output):
        parser.error(
            "需要 --work-pack <工作包>，或同时给出 --context、--schema、--output"
        )
    raw_fragments = args.fragments or [str(PARTS) + "/"]
    report = Path(args.output + ".errors.json")
    try:
        output = workspace_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        fragments, origins, context = load_inputs(raw_fragments, args.context)
        candidate = output.with_suffix(".pending.json")
        context["material_hashes"] = material_hashes(pack if args.work_pack else None, context)
        batch = assemble(context, fragments)
        atomic_write(candidate, encode(batch))
    except (InputProblem, PrepareInputError) as exc:
        message = (
            exc.text(outcome)
            if isinstance(exc, InputProblem)
            else located(str(exc), origins) + f"\n{outcome}"
        )
        try:
            atomic_write(
                workspace_path(str(report)), encode({"total": 1, "errors": [message]})
            )
            saved = f"报告：{report}"
        except (OSError, ValueError):
            saved = "报告未保存"
        print(f"{message}；{saved}")
        return 1
    except ValueError as exc:
        print(
            error(
                "PATH_OUT_OF_SCOPE",
                str(exc),
                outcome,
                "片段、候选与输出都用工作区相对路径",
                retry=False,
            )
        )
        return 1
    except OSError as exc:
        print(
            error(
                "WRITE_FAILED",
                f"写入 {relative(output) if 'output' in locals() else args.output} 失败：{type(exc).__name__}",
                outcome,
                retry=False,
            )
        )
        return 1
    checked = validate_file(
        candidate, args.schema, args.context, repair=args.repair, origins=origins
    )
    if checked:
        return checked
    retry_command = (
        command("prepare_result.py", "--work-pack", args.work_pack)
        if args.work_pack
        else command(
            "prepare_result.py",
            "--context",
            args.context,
            "--schema",
            args.schema,
            "--output",
            args.output,
            *args.fragments,
        )
    )
    if not platform_check(pack, batch, candidate, retry_command):
        return 1
    atomic_write(output, candidate.read_bytes())
    print(f"已保存最终结果：{relative(output)}；等待平台入库与用户审核")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
