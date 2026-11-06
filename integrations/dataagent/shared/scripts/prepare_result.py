"""Assemble a pinned proposal batch without inferring business content."""

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

from check_result import (
    atomic_write,
    diagnostic,
    encode,
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


def assemble(context, fragments):
    items, refs = [], set()
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
            if item["operation"] == "delete":
                item.setdefault("after", None)
            elif item["operation"] not in {"update", "delete"}:
                item["client_ref"] = effective_ref(item, index)
            ref = item.get("client_ref")
            if isinstance(ref, str):
                if ref in refs:
                    fail("client_ref", "不重复的 client_ref", ref)
                refs.add(ref)
            items.append(item)
    # SC-08: only the items; the platform supplies the run and pinned facts.
    return {"items": items}


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


def submit_failure_detail(exc, url, authorization):
    """Keep transport diagnostics bounded and strip credentials and URL details."""
    import re
    from urllib.error import URLError
    from urllib.parse import parse_qsl, urlsplit

    target = "未确定"
    secrets = [authorization] if isinstance(authorization, str) else []
    if secrets:
        secrets.extend(authorization.split())
    try:
        parts = urlsplit(url)
        if parts.scheme in {"http", "https"} and parts.hostname:
            host = parts.hostname
            if ":" in host:
                host = f"[{host}]"
            target = f"{parts.scheme}://{host}:{parts.port or (443 if parts.scheme == 'https' else 80)}"
        secrets.extend([url, parts.path, parts.query, parts.fragment,
                        parts.username, parts.password])
        secrets.extend(parts.path.split("/"))
        secrets.extend(value for _, value in parse_qsl(parts.query))
    except (ValueError, TypeError):
        pass
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, OSError):
        reason = reason.strerror or str(reason)
    elif not isinstance(exc, URLError):
        reason = type(exc).__name__
    reason = re.sub(r"https?://\S+", "[地址已隐藏]", str(reason))
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        reason = reason.replace(secret, "[已隐藏]")
    reason = " ".join(reason.split())
    if len(reason) > 200:
        reason = reason[:197] + "..."
    return f"{type(exc).__name__}: {reason}；目标 {target}"


def platform_submit(pack, candidate, retry_command):
    """Submit to the platform, which checks and stores in one step (SC-05).
    Never duplicate graph rules here: the platform's verdict is the only one."""
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlsplit
    from urllib.request import HTTPRedirectHandler, Request, build_opener

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    submit_file = pack.get("platform_check_file")
    if not submit_file:
        print(error("PLATFORM_SUBMIT_CONFIG_MISSING", "工作包没有平台提交配置", "未提交，最终文件未替换", "重新发起建模以获取提交配置", retry=False))
        return False
    url, authorization = "", None
    try:
        config = json.loads(Path(submit_file).read_bytes())
        url = config["submit_url"]
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("提交地址无效")
        authorization = config["headers"]["Authorization"]
        request = Request(
            url,
            data=candidate.read_bytes(),
            method="POST",
            headers={
                "Authorization": authorization,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        # Submitting can probe query datasets on the business source.
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            report = json.load(response)
        if (
            not isinstance(report, dict)
            or not isinstance(report.get("passed"), bool)
            or type(report.get("reviewable_count")) is not int
            or report["reviewable_count"] < 0
            or not isinstance(report.get("errors"), list)
            or not isinstance(report.get("warnings", []), list)
            or any(
                not isinstance(problem, dict) or not isinstance(problem.get("message"), str)
                for problem in [*report["errors"], *report.get("warnings", [])]
            )
            or report["passed"] != (not report["errors"])
        ):
            raise ValueError("平台未返回有效的提交结果")
    except HTTPError as exc:
        if exc.code < 500:
            print(error("PLATFORM_SUBMIT_REJECTED", f"平台提交请求被拒绝（HTTP {exc.code}）", "未提交，最终文件未替换", "重新发起建模以获取有效运行凭据", retry=False))
            return False
        detail = submit_failure_detail(exc, url, authorization)
        print(error("PLATFORM_SUBMIT_UNAVAILABLE", f"平台暂时不可达（HTTP {exc.code}；{detail}），未完成提交", "最终文件未替换", f"稍后重试 {retry_command}；仍不可达时不交结果，在回答中说明是平台不可用"))
        return False
    except (OSError, ValueError, KeyError, TypeError, URLError) as exc:
        detail = submit_failure_detail(exc, url, authorization)
        print(error("PLATFORM_SUBMIT_UNAVAILABLE", f"平台提交未执行或未完成（{detail}），结果未入库", "最终文件未替换", f"稍后重试 {retry_command}；仍不可达时不交结果，在回答中说明是平台不可用"))
        if isinstance(exc, (URLError, ConnectionError, TimeoutError)):
            print("沙箱可能无法访问平台：检查 DataAgent 沙箱网络是否开启，以及 OntoFoundry 的 ONTOFOUNDRY_PUBLIC_BASE_URL 是否为沙箱可达地址")
        return False
    report_path = candidate.with_suffix(".platform-submit.json")
    atomic_write(report_path, encode(report))
    for warning in report.get("warnings", []):
        print("提示：" + warning["message"])
    if report["passed"]:
        print(f"平台检查通过并已入库：{report['reviewable_count']} 条待审。")
        try:
            kinds = Counter(item.get("target_kind") for item in json.loads(candidate.read_bytes())["items"])
            print("按类型：" + "、".join(f"{kind} {count}" for kind, count in kinds.most_common()))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        print("已完成：直接按收尾第 3 步作答；不必再读结果文件，也不补写 modeling/ 下的文件。")
        return True
    print(f"平台检查未通过，未入库。最终文件未替换。完整报告：{relative(report_path)}")
    if isinstance(report.get("repair_used"), int) and isinstance(report.get("repair_limit"), int):
        print(f"修正轮次：已用 {report['repair_used']}/{report['repair_limit']}（平台计数，本地检查不计）")
    for problem in report["errors"]:
        print(problem["message"])
    print("下一步：修正片段后重试 " + retry_command)
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
        candidate, args.schema, args.context, origins=origins
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
    if not platform_submit(pack, candidate, retry_command):
        return 1
    atomic_write(output, candidate.read_bytes())
    print(f"已保存结果留档：{relative(output)}；提案已入库，等待用户审核")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
