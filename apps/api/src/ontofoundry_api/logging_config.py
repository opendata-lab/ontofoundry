"""One-line JSON logs to the console and, when a log directory is set, to a daily file.

The format, rotation and field names follow docs/design/2026-11-19-logging-standard.md,
which OpenDataWorks and DataAgent share word for word.
"""

from __future__ import annotations

import contextvars
import gzip
import json
import logging
import logging.handlers
import os
import re
import shutil
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

SERVICE_NAME = "of-backend"
LOG_FILE_NAME = "app.log"
RETENTION_DAYS = 30
MAX_FIELD_CHARS = 8192

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LEVELS = {"WARNING": "WARN", "CRITICAL": "ERROR"}
# Fields a caller may attach with logger.info(..., extra={...}); anything else is ignored.
_EXTRA_FIELDS = (
    "task_id",
    "run_id",
    "session_id",
    "workspace_id",
    "error_code",
    "method",
    "path",
    "status_code",
    "duration_ms",
)
_SECRETS = (
    (re.compile(r"\b(ofpat|ofrun)\.[A-Za-z0-9_.\-]+"), r"\1.***"),
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9_.\-+/=]+"), r"\1 ***"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key)(\"?\s*[:=]\s*\"?)[^\s\"',;&]+"), r"\1\2***"),
    (re.compile(r"(://[^/\s:@]+):[^/\s@]+@"), r"\1:***@"),
)


def valid_request_id(value: str | None) -> str | None:
    return value if value and _REQUEST_ID.match(value) else None


def redact(text: str) -> str:
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text if len(text) <= MAX_FIELD_CHARS else text[:MAX_FIELD_CHARS] + "…(truncated)"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": _LEVELS.get(record.levelname, record.levelname),
            "service": SERVICE_NAME,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            entry["request_id"] = request_id
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value
        if record.exc_info:
            entry["stack_trace"] = redact("".join(traceback.format_exception(*record.exc_info)))
        return json.dumps(entry, ensure_ascii=False, default=str)


def _gzip_rotator(source: str, dest: str) -> None:
    with open(source, "rb") as src, gzip.open(dest, "wb") as out:
        shutil.copyfileobj(src, out)
    os.remove(source)


def daily_file_handler(directory: Path) -> logging.Handler:
    """Rotate at UTC midnight into app.log.YYYY-MM-DD.gz and keep RETENTION_DAYS of them.

    Only one process may write a given file: TimedRotatingFileHandler does not
    coordinate rollover across processes.
    """
    directory.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        directory / LOG_FILE_NAME, when="midnight", utc=True, backupCount=RETENTION_DAYS, encoding="utf-8"
    )
    handler.namer = lambda name: name + ".gz"
    handler.rotator = _gzip_rotator
    return handler


def configure_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    formatter = JsonFormatter()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_dir is not None:
        handlers.append(daily_file_handler(log_dir))
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(level.upper())
    # Python warnings (e.g. deprecations at import) go through the same lines.
    logging.captureWarnings(True)

    # Uvicorn installs its own text handlers before importing the app; route its
    # messages through the root handlers instead. Requests are logged by the
    # app's middleware, so the access logger stays silent.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True
    for name in ("httpx", "httpcore", "sqlalchemy", "alembic", "multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)
