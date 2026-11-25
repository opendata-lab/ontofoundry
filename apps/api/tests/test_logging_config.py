"""One-line JSON logs, request ids and the daily file (docs/design/2026-11-19-logging-standard.md)."""

from __future__ import annotations

import json
import logging
import sys

from ontofoundry_api.logging_config import (
    JsonFormatter,
    configure_logging,
    daily_file_handler,
    redact,
    request_id_var,
)


def _record(message: str, *args, **extra) -> logging.LogRecord:
    record = logging.LogRecord("ontofoundry_api.test", logging.WARNING, __file__, 1, message, args, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_a_record_is_one_line_of_json_with_the_standard_fields():
    token = request_id_var.set("req-1")
    try:
        line = JsonFormatter().format(_record("hello %s\nworld", "there", task_id="t-1", unknown="x"))
    finally:
        request_id_var.reset(token)

    assert "\n" not in line
    entry = json.loads(line)
    assert entry["level"] == "WARN"
    assert entry["service"] == "of-backend"
    assert entry["logger"] == "ontofoundry_api.test"
    assert entry["message"] == "hello there\nworld"
    assert entry["request_id"] == "req-1"
    assert entry["task_id"] == "t-1"
    assert "unknown" not in entry
    assert entry["timestamp"].endswith("Z")


def test_a_stack_trace_stays_inside_the_line():
    try:
        raise ValueError("boom password=hunter2")
    except ValueError:
        record = _record("failed")
        record.exc_info = sys.exc_info()
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError" in entry["stack_trace"]
    assert "hunter2" not in entry["stack_trace"]


def test_credentials_are_redacted():
    text = redact(
        "Bearer abc.def ofpat.SECRET ofrun.SECRET password=hunter2 "
        "postgresql+psycopg://user:pw@db:5432/x api_key: k-123 "
        "access_token=s1 client_secret=s2 {'password': 's3'} Authorization: Basic s4 "
        "https://mcp.invalid/sse?access_token=s5&x=1"
    )
    for secret in ("abc.def", "SECRET", "hunter2", ":pw@", "k-123", "s1", "s2", "s3", "s4", "s5"):
        assert secret not in text
    assert "user:***@db" in text
    # Usage counts are not secrets.
    assert redact("max_tokens=4096") == "max_tokens=4096"


def test_long_messages_are_truncated():
    assert len(redact("x" * 20000)) < 8300


def test_the_daily_file_is_created_and_written(tmp_path):
    handler = daily_file_handler(tmp_path / "of-backend")
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("ontofoundry_api.file_test")
    logger.addHandler(handler)
    try:
        logger.warning("to file")
    finally:
        logger.removeHandler(handler)
        handler.close()
    lines = (tmp_path / "of-backend" / "app.log").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["message"] == "to file"
    assert handler.backupCount == 30
    assert handler.namer("app.log.2026-11-18") == "app.log.2026-11-18.gz"


def test_configure_routes_uvicorn_through_the_root_handlers(tmp_path):
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    try:
        configure_logging("INFO", tmp_path)
        assert logging.getLogger("uvicorn.error").handlers == []
        assert logging.getLogger("uvicorn.error").propagate
        assert logging.getLogger("uvicorn.access").disabled
        assert any(getattr(h, "baseFilename", "").endswith("app.log") for h in root.handlers)
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in saved[0]:
            root.addHandler(handler)
        root.setLevel(saved[1])
        logging.captureWarnings(False)


def test_requests_get_an_id_and_one_completion_line(client, caplog):
    caplog.set_level(logging.INFO, logger="ontofoundry_api.request")

    passed = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert passed.headers["X-Request-ID"] == "abc-123"

    replaced = client.get("/api/v1/workspaces", headers={"X-Request-ID": "bad id with spaces"})
    generated = replaced.headers["X-Request-ID"]
    assert generated != "bad id with spaces" and len(generated) == 32

    lines = [r for r in caplog.records if r.name == "ontofoundry_api.request"]
    # /healthz is polled every 10s by Compose and is not logged.
    assert [(r.path, r.status_code) for r in lines] == [("/api/v1/workspaces", replaced.status_code)]
    assert lines[0].method == "GET" and lines[0].duration_ms >= 0


def test_calls_to_dataagent_carry_the_request_id():
    from ontofoundry_api.services.dataagent import DataAgentClient

    client = DataAgentClient("http://agent.invalid", prefix="/api", website_id="w", access_key="", username="s")
    assert "X-Request-ID" not in client.headers
    token = request_id_var.set("req-42")
    try:
        assert client.headers["X-Request-ID"] == "req-42"
    finally:
        request_id_var.reset(token)


def _middleware_app():
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse

    from ontofoundry_api.logging_config import RequestContextMiddleware

    app = FastAPI()
    events: list[str] = []

    @app.get("/boom")
    async def boom():
        raise RuntimeError("password=hunter2 exploded")

    @app.get("/stream")
    async def stream():
        async def body():
            events.append("body started")
            yield b"a"
            events.append("body finished")

        return StreamingResponse(body())

    app.add_middleware(RequestContextMiddleware, logger=logging.getLogger("ontofoundry_api.request"), skip_path_suffix="/healthz")
    return app, events


def test_an_unhandled_error_keeps_its_request_id():
    from fastapi.testclient import TestClient

    app, _ = _middleware_app()
    lines: list[dict] = []

    class Formatted(logging.Handler):
        # Formatted while the request context is still active, as a real handler is.
        def emit(self, record):
            lines.append(json.loads(JsonFormatter().format(record)))

    handler = Formatted()
    request_logger = logging.getLogger("ontofoundry_api.request")
    request_logger.addHandler(handler)
    request_logger.setLevel(logging.INFO)
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/boom", headers={"X-Request-ID": "req-500"})
    finally:
        request_logger.removeHandler(handler)
        request_logger.setLevel(logging.NOTSET)

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-500"
    error, done = lines
    assert (error["message"], error["request_id"]) == ("unhandled error", "req-500")
    assert "RuntimeError" in error["stack_trace"] and "hunter2" not in error["stack_trace"]
    assert (done["message"], done["request_id"], done["status_code"]) == ("request completed", "req-500", 500)


def test_a_streaming_response_is_logged_when_it_ends(caplog):
    from fastapi.testclient import TestClient

    app, events = _middleware_app()
    caplog.set_level(logging.INFO, logger="ontofoundry_api.request")

    class Recorder(logging.Handler):
        def emit(self, record):
            if record.getMessage() == "request completed":
                events.append("completed logged")

    recorder = Recorder()
    logging.getLogger("ontofoundry_api.request").addHandler(recorder)
    try:
        response = TestClient(app).get("/stream")
    finally:
        logging.getLogger("ontofoundry_api.request").removeHandler(recorder)
    assert response.text == "a"
    assert events == ["body started", "body finished", "completed logged"]


def test_cors_allows_and_exposes_the_request_id(client):
    preflight = client.options(
        "/api/v1/workspaces",
        headers={"Origin": "http://localhost:5174", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-request-id"},
    )
    assert preflight.status_code == 200
    response = client.get("/api/v1/workspaces", headers={"Origin": "http://localhost:5174"})
    assert "x-request-id" in response.headers.get("access-control-expose-headers", "").lower()
