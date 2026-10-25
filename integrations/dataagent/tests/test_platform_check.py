"""The merge tool calls the run endpoint with real HTTP and bounded credentials."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared/scripts"))
import prepare_result as prepare


@pytest.fixture
def platform():
    class Handler(BaseHTTPRequestHandler):
        status = 200
        report: ClassVar[dict] = {
            "passed": True,
            "contract_errors": [],
            "unacceptable_groups": [],
            "reviewable_count": 1,
            "unacceptable_count": 0,
        }
        requests: ClassVar[list] = []

        def do_POST(self):
            type(self).requests.append(
                (
                    self.path,
                    self.headers["Authorization"],
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            self.send_response(type(self).status)
            self.end_headers()
            self.wfile.write(json.dumps(type(self).report).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", Handler
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def inputs(tmp_path, monkeypatch, origin):
    monkeypatch.chdir(tmp_path)
    batch = {
        "workspace_id": "11111111-1111-4111-8111-111111111111",
        "run_token": "fictional-run",
        "items": [],
    }
    candidate = Path("candidate.json")
    candidate.write_text(json.dumps(batch))
    Path("mcp.json").write_text(
        json.dumps(
            {
                "url": origin
                + f"/prefix/api/v1/ontology/workspaces/{batch['workspace_id']}/mcp",
                "headers": {"Authorization": "Bearer ofrun.fictional-secret"},
            }
        )
    )
    return {"mcp_config_file": "mcp.json"}, batch, candidate


def test_platform_success_uses_pinned_url_headers_and_exact_result(
    tmp_path, monkeypatch, capsys, platform
):
    origin, handler = platform
    pack, batch, candidate = inputs(tmp_path, monkeypatch, origin)
    assert prepare.platform_check(
        pack,
        batch,
        candidate,
        '"$DATAAGENT_PYTHON_BIN" prepare_result.py --work-pack pack.json',
    )
    assert handler.requests == [
        (
            f"/prefix/api/v1/ontology/workspaces/{batch['workspace_id']}/runs/fictional-run/proposal-check",
            "Bearer ofrun.fictional-secret",
            batch,
        )
    ]
    output = capsys.readouterr().out
    assert "平台检查通过" in output and "ofrun." not in output


def test_platform_diagnostics_are_tool_output(tmp_path, monkeypatch, capsys, platform):
    origin, handler = platform
    handler.report = {
        "passed": False,
        "reviewable_count": 1,
        "unacceptable_count": 2,
        "contract_errors": [
            {
                "code": "RESULT_CONTEXT_MISMATCH",
                "message": "错误 [RESULT_CONTEXT_MISMATCH]：固定上下文不一致。下一步：修正片段。",
            }
        ],
        "unacceptable_groups": [
            {
                "reason": "错误 [PROPOSAL_GROUP_UNACCEPTABLE]：目标列不唯一。下一步：修正关系。"
            }
        ],
    }
    pack, batch, candidate = inputs(tmp_path, monkeypatch, origin)
    assert not prepare.platform_check(pack, batch, candidate, "copyable-retry-command")
    output = capsys.readouterr().out
    assert "错误 [RESULT_CONTEXT_MISMATCH]" in output and "目标列不唯一" in output
    assert "copyable-retry-command" in output and "平台检查通过" not in output
    assert Path("candidate.platform-check.json").is_file()


@pytest.mark.parametrize(
    "status,allowed,code",
    [(401, False, "PLATFORM_CHECK_REJECTED"), (503, True, "PLATFORM_CHECK_SKIPPED")],
)
def test_platform_http_errors_are_explicit(
    tmp_path, monkeypatch, capsys, platform, status, allowed, code
):
    origin, handler = platform
    handler.status = status
    pack, batch, candidate = inputs(tmp_path, monkeypatch, origin)
    assert (
        prepare.platform_check(pack, batch, candidate, "copyable-retry-command")
        == allowed
    )
    output = capsys.readouterr().out
    assert code in output and "平台检查通过" not in output and "ofrun." not in output


def test_missing_config_skips_without_claiming_success(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert prepare.platform_check({}, {}, Path("unused.json"), "copyable-retry-command")
    output = capsys.readouterr().out
    assert "提示 [PLATFORM_CHECK_SKIPPED]" in output and "平台检查通过" not in output


def test_main_preserves_final_result_when_platform_rejects(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    Path("parts.json").write_text("[]")
    Path("context.json").write_text(
        json.dumps({"run": {}, "draft": {}, "element_hashes": {}})
    )
    Path("final.json").write_text("previous-result")
    monkeypatch.setattr(prepare, "validate_file", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(prepare, "platform_check", lambda *_args: False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_result.py",
            "--context",
            "context.json",
            "--schema",
            "schema.json",
            "--output",
            "final.json",
            "parts.json",
        ],
    )
    assert prepare.main() == 1
    assert Path("final.json").read_text() == "previous-result"
    assert Path("final.pending.json").is_file()


@pytest.mark.parametrize(
    "report",
    [
        [],
        {"passed": True},
        {
            "passed": True,
            "contract_errors": [],
            "unacceptable_groups": [],
            "reviewable_count": 1,
            "unacceptable_count": 2,
        },
    ],
)
def test_invalid_platform_reply_never_claims_a_pass(
    tmp_path, monkeypatch, capsys, platform, report
):
    origin, handler = platform
    handler.report = report
    pack, batch, candidate = inputs(tmp_path, monkeypatch, origin)
    assert prepare.platform_check(pack, batch, candidate, "copyable-retry-command")
    output = capsys.readouterr().out
    assert "提示 [PLATFORM_CHECK_SKIPPED]" in output and "平台检查通过" not in output
