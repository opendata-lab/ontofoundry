from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from typing import Any

from dataagent_backend.core.agent_visibility import normalize_agent_visibility
from dataagent_backend.core.data_scope import normalize_data_scope
from dataagent_backend.core.database import connect_dataagent, dataagent_schema
from dataagent_backend.core.mcp_admin_service import available_mcp_servers as list_available_mcp_servers

DEFAULT_AGENT_ID = "agent_ontofoundry"
DEFAULT_AGENT_NAME = "OntoFoundry 建模助手"

# Session-level platform permission modes. Legacy values (the removed
# ``inherit`` or anything unknown) normalize to ``default``.
PERMISSION_MODES: tuple[str, ...] = ("default", "acceptEdits", "plan", "bypassPermissions")
DEFAULT_PERMISSION_MODE = "default"

SAFE_AGENT_TOOLS = ["Skill", "Bash", "Read", "LS", "Glob", "Grep"]

RESERVED_ENV_KEYS = {"PATH", "HOME", "VIRTUAL_ENV", "TZ"}
RESERVED_ENV_PREFIXES = (
    "ANTHROPIC_",
    "DATAAGENT_",
    "MYSQL_",
    "DORIS_",
    "REDIS_",
)
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _to_iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value) if value is not None else ""


def _safe_json_load(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return fallback


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _dedupe_strings(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        iterable: list[Any] = [values]
    elif isinstance(values, (list, tuple, set)):
        iterable = list(values)
    else:
        iterable = []

    result: list[str] = []
    seen: set[str] = set()
    for value in iterable:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _validate_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("agent name is required")
    if len(text) > 128:
        raise ValueError("agent name must be at most 128 characters")
    return text


def normalize_permission_mode(permission_mode: Any) -> str:
    """Coerce any stored/requested value to a valid platform permission mode.

    The removed legacy ``inherit`` value and any unknown input collapse to
    ``default``.
    """
    requested = str(permission_mode or "").strip()
    if requested in PERMISSION_MODES:
        return requested
    return DEFAULT_PERMISSION_MODE


def _validate_tools(values: Any) -> list[str]:
    tools = _dedupe_strings(values)
    allowed = set(SAFE_AGENT_TOOLS)
    unknown = [tool for tool in tools if tool not in allowed]
    if unknown:
        raise ValueError(f"unsupported allowed tool: {unknown[0]}")
    return tools


def _validate_members(values: Any, available: set[str], *, label: str) -> list[str]:
    selected = _dedupe_strings(values)
    unknown = [item for item in selected if item not in available]
    if unknown:
        raise ValueError(f"unknown {label}: {unknown[0]}")
    return selected


def _validate_max_turns(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        turns = int(value)
    except Exception as exc:
        raise ValueError("max_turns must be an integer") from exc
    if turns < 0:
        raise ValueError("max_turns must be greater than or equal to 0")
    if turns > 200:
        raise ValueError("max_turns must be at most 200")
    return turns


def _validate_env_vars(value: Any) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("env_vars must be an object")

    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip()
        upper_key = key.upper()
        if not key or not ENV_KEY_RE.match(key):
            raise ValueError(f"invalid environment variable name: {key}")
        if upper_key in RESERVED_ENV_KEYS or any(upper_key.startswith(prefix) for prefix in RESERVED_ENV_PREFIXES):
            raise ValueError(f"reserved environment variable: {key}")
        normalized[key] = str(raw_value or "")
    return dict(sorted(normalized.items()))


def _validate_preset_questions(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()[:200]
        if text:
            result.append(text)
        if len(result) >= 3:
            break
    return result


def available_mcp_servers() -> list[dict[str, Any]]:
    return list_available_mcp_servers()


def available_mcp_server_ids() -> set[str]:
    return {str(item.get("id") or "") for item in available_mcp_servers() if str(item.get("id") or "")}


def normalize_agent_profile_payload(
    payload: dict[str, Any],
    *,
    available_skill_folders: set[str],
    available_mcp_server_ids: set[str],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = dict(payload or {})
    base = dict(existing or {})
    has_existing = bool(existing)

    name = _validate_name(data.get("name", base.get("name") if has_existing else ""))
    description = str(data.get("description", base.get("description") or "") or "").strip()
    system_prompt = str(data.get("system_prompt", base.get("system_prompt") or "") or "").strip()
    allowed_tools = _validate_tools(data.get("allowed_tools", base.get("allowed_tools") or list(SAFE_AGENT_TOOLS)))
    mcp_server_ids = _validate_members(
        data.get("mcp_server_ids", base.get("mcp_server_ids") or []),
        available_mcp_server_ids,
        label="mcp server",
    )
    skill_folders = _validate_members(
        data.get("skill_folders", base.get("skill_folders") or []),
        available_skill_folders,
        label="skill folder",
    )
    max_turns = _validate_max_turns(data.get("max_turns", base.get("max_turns") or 0))
    env_vars = _validate_env_vars(data.get("env_vars", base.get("env_vars") or {}))
    data_scope = normalize_data_scope(data.get("data_scope", base.get("data_scope") or {}))
    visibility = normalize_agent_visibility(
        data.get("visibility", base.get("visibility") or {}), strict=True
    )
    raw_questions = data.get("preset_questions", base.get("preset_questions") or [])
    preset_questions = _validate_preset_questions(raw_questions)

    return {
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "allowed_tools": allowed_tools,
        "mcp_server_ids": mcp_server_ids,
        "skill_folders": skill_folders,
        "max_turns": max_turns,
        "env_vars": env_vars,
        "data_scope": data_scope,
        "visibility": visibility,
        "preset_questions": preset_questions,
    }


def build_agent_snapshot(profile: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        "agent_id": str(profile.get("agent_id") or DEFAULT_AGENT_ID),
        "name": str(profile.get("name") or DEFAULT_AGENT_NAME),
        "description": str(profile.get("description") or ""),
        "system_prompt": str(profile.get("system_prompt") or ""),
        "allowed_tools": _dedupe_strings(profile.get("allowed_tools")),
        "mcp_server_ids": _dedupe_strings(profile.get("mcp_server_ids")),
        "skill_folders": _dedupe_strings(profile.get("skill_folders")),
        "max_turns": int(profile.get("max_turns") or 0),
        "env_vars": _validate_env_vars(profile.get("env_vars") or {}),
        "data_scope": normalize_data_scope(profile.get("data_scope") or {}),
        "is_default": bool(profile.get("is_default")),
        "is_builtin": bool(profile.get("is_builtin")),
    }
    preset_questions = _validate_preset_questions(profile.get("preset_questions") or [])
    if preset_questions:
        snapshot["preset_questions"] = preset_questions
    return snapshot


def agent_summary_from_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    payload = snapshot or default_agent_payload()
    return {
        "agent_id": str(payload.get("agent_id") or DEFAULT_AGENT_ID),
        "name": str(payload.get("name") or DEFAULT_AGENT_NAME),
        "description": str(payload.get("description") or ""),
        "is_default": bool(payload.get("is_default")),
        "is_builtin": bool(payload.get("is_builtin")),
    }


def normalize_agent_snapshot(raw: Any) -> dict[str, Any]:
    payload = _safe_json_load(raw, None)
    if not isinstance(payload, dict):
        payload = default_agent_payload()
    if not payload.get("agent_id"):
        payload["agent_id"] = DEFAULT_AGENT_ID
    if not payload.get("name"):
        payload["name"] = DEFAULT_AGENT_NAME
    return build_agent_snapshot(payload)


def default_agent_payload() -> dict[str, Any]:
    return {
        "agent_id": DEFAULT_AGENT_ID,
        "name": DEFAULT_AGENT_NAME,
        "description": "基于会话材料和当前草稿进行 Apache Ossie 本体建模与概念澄清。",
        "system_prompt": (
            "你是 OntoFoundry 本体建模助手。OntoFoundry 会在每轮把当前本体 JSON "
            "和新增 Markdown 材料放入话题工作区，并在消息里给出相对路径。"
            "先读取这些文件再回答；普通问答只解释，明确的建模请求才生成方案。"
            "模型变更只能作为待审查提案，不能声称已经发布或已被用户接受。"
            "需要完整机器可读交付时，把合法的 Apache Ossie JSON 写入 output/。"
        ),
        "allowed_tools": list(SAFE_AGENT_TOOLS),
        "mcp_server_ids": [],
        "skill_folders": ["md2ossie"],
        "max_turns": 0,
        "env_vars": {},
        "data_scope": {"allowed_scopes": []},
        "preset_questions": [
            "结合已上传文档生成本体模型",
            "帮我澄清一个业务概念",
            "检查当前本体中的对象、属性与关系是否完整",
        ],
        "is_default": True,
        "is_builtin": True,
    }


def _new_agent_id() -> str:
    return f"agent_{uuid.uuid4().hex[:24]}"


class AgentProfileStore:
    def __init__(self):
        self._ready = False
        self._ready_lock = threading.Lock()

    def _connect(self, database: str | None):
        del database
        return connect_dataagent()

    def _schema_name(self) -> str:
        return dataagent_schema()

    def init_schema(self):
        if self._ready:
            return
        with self._ready_lock:
            if self._ready:
                return
            self._ready = True

    def _ensure_ready(self):
        if not self._ready:
            self.init_schema()

    def _normalize_row(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        item = {
            "agent_id": str(row.get("agent_id") or ""),
            "name": str(row.get("name") or ""),
            "description": str(row.get("description") or ""),
            "system_prompt": str(row.get("system_prompt") or ""),
            "allowed_tools": _dedupe_strings(_safe_json_load(row.get("allowed_tools_json"), [])),
            "mcp_server_ids": _dedupe_strings(_safe_json_load(row.get("mcp_server_ids_json"), [])),
            "skill_folders": _dedupe_strings(_safe_json_load(row.get("skill_folders_json"), [])),
            "max_turns": int(row.get("max_turns") or 0),
            "env_vars": _validate_env_vars(_safe_json_load(row.get("env_vars_json"), {})),
            "data_scope": normalize_data_scope(_safe_json_load(row.get("data_scope_json"), {})),
            "visibility": normalize_agent_visibility(_safe_json_load(row.get("visibility_json"), {})),
            "preset_questions": _validate_preset_questions(_safe_json_load(row.get("preset_questions_json"), [])),
            "is_default": bool(row.get("is_default")),
            "is_builtin": bool(row.get("is_builtin")),
            "created_at": _to_iso(row.get("created_at")),
            "updated_at": _to_iso(row.get("updated_at")),
        }
        return item

    def list_profiles(self) -> list[dict[str, Any]]:
        self._ensure_ready()
        conn = self._connect(database=self._schema_name())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_id, name, description, system_prompt,
                           allowed_tools_json, mcp_server_ids_json, skill_folders_json,
                           max_turns, env_vars_json, data_scope_json, visibility_json,
                           preset_questions_json,
                           is_default, is_builtin, created_at, updated_at
                    FROM da_agent_profile
                    ORDER BY is_builtin DESC, is_default DESC, updated_at DESC, created_at DESC
                    """
                )
                rows = cur.fetchall() or []
        finally:
            conn.close()
        return [item for item in (self._normalize_row(row) for row in rows) if item]

    def get_profile(self, agent_id: str) -> dict[str, Any] | None:
        self._ensure_ready()
        conn = self._connect(database=self._schema_name())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_id, name, description, system_prompt,
                           allowed_tools_json, mcp_server_ids_json, skill_folders_json,
                           max_turns, env_vars_json, data_scope_json, visibility_json,
                           preset_questions_json,
                           is_default, is_builtin, created_at, updated_at
                    FROM da_agent_profile
                    WHERE agent_id = %s
                    LIMIT 1
                    """,
                    (agent_id,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        return self._normalize_row(row)

    def save_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        self._ensure_ready()
        agent_id = str(profile.get("agent_id") or "").strip() or _new_agent_id()
        is_default = bool(profile.get("is_default"))
        is_builtin = bool(profile.get("is_builtin"))
        conn = self._connect(database=self._schema_name())
        try:
            with conn.cursor() as cur:
                if is_default:
                    cur.execute("UPDATE da_agent_profile SET is_default = 0 WHERE agent_id <> %s", (agent_id,))
                cur.execute(
                    """
                    INSERT INTO da_agent_profile (
                        agent_id, name, description, system_prompt,
                        allowed_tools_json, mcp_server_ids_json, skill_folders_json,
                        max_turns, env_vars_json, data_scope_json, visibility_json,
                        preset_questions_json,
                        is_default, is_builtin
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (agent_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        system_prompt = EXCLUDED.system_prompt,
                        allowed_tools_json = EXCLUDED.allowed_tools_json,
                        mcp_server_ids_json = EXCLUDED.mcp_server_ids_json,
                        skill_folders_json = EXCLUDED.skill_folders_json,
                        max_turns = EXCLUDED.max_turns,
                        env_vars_json = EXCLUDED.env_vars_json,
                        data_scope_json = EXCLUDED.data_scope_json,
                        visibility_json = EXCLUDED.visibility_json,
                        preset_questions_json = EXCLUDED.preset_questions_json,
                        is_default = EXCLUDED.is_default,
                        is_builtin = EXCLUDED.is_builtin,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        agent_id,
                        str(profile.get("name") or ""),
                        str(profile.get("description") or ""),
                        str(profile.get("system_prompt") or ""),
                        _json_dump(_dedupe_strings(profile.get("allowed_tools"))),
                        _json_dump(_dedupe_strings(profile.get("mcp_server_ids"))),
                        _json_dump(_dedupe_strings(profile.get("skill_folders"))),
                        int(profile.get("max_turns") or 0),
                        _json_dump(_validate_env_vars(profile.get("env_vars") or {})),
                        _json_dump(normalize_data_scope(profile.get("data_scope") or {})),
                        _json_dump(normalize_agent_visibility(profile.get("visibility") or {})),
                        _json_dump(_validate_preset_questions(profile.get("preset_questions") or [])),
                        1 if is_default else 0,
                        1 if is_builtin else 0,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        return self.get_profile(agent_id) or {}

    def delete_profile(self, agent_id: str) -> bool:
        self._ensure_ready()
        profile = self.get_profile(agent_id)
        if not profile:
            return False
        if profile.get("is_builtin"):
            raise ValueError("built-in agent cannot be deleted")
        if self.count_topic_references(agent_id) > 0:
            raise ValueError("agent is referenced by topics")
        conn = self._connect(database=self._schema_name())
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM da_agent_profile WHERE agent_id = %s", (agent_id,))
            conn.commit()
        finally:
            conn.close()
        return True

    def count_topic_references(self, agent_id: str) -> int:
        self._ensure_ready()
        conn = self._connect(database=self._schema_name())
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS total FROM da_agent_topic WHERE agent_id = %s", (agent_id,))
                row = cur.fetchone() or {}
        finally:
            conn.close()
        return int(row.get("total") or 0)

    def backfill_default_bindings(self, default_snapshot: dict[str, Any]) -> None:
        self._ensure_ready()
        snapshot_json = _json_dump(build_agent_snapshot(default_snapshot))
        conn = self._connect(database=self._schema_name())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE da_agent_topic
                    SET agent_id = %s,
                        agent_snapshot_json = %s
                    WHERE agent_id IS NULL
                       OR agent_id = ''
                       OR agent_snapshot_json IS NULL
                       OR agent_snapshot_json = ''
                    """,
                    (DEFAULT_AGENT_ID, snapshot_json),
                )
                cur.execute(
                    """
                    UPDATE da_agent_task
                    SET agent_id = %s,
                        agent_snapshot_json = %s
                    WHERE agent_id IS NULL
                       OR agent_id = ''
                       OR agent_snapshot_json IS NULL
                       OR agent_snapshot_json = ''
                    """,
                    (DEFAULT_AGENT_ID, snapshot_json),
                )
            conn.commit()
        finally:
            conn.close()

    def remove_noncanonical_builtin_profiles(self, default_snapshot: dict[str, Any]) -> None:
        """Move old built-in bindings to the sole OntoFoundry built-in."""
        self._ensure_ready()
        snapshot_json = _json_dump(build_agent_snapshot(default_snapshot))
        conn = self._connect(database=self._schema_name())
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE da_agent_topic SET agent_id = %s, agent_snapshot_json = %s "
                    "WHERE agent_id IN ("
                    "SELECT agent_id FROM da_agent_profile WHERE is_builtin = 1 AND agent_id <> %s"
                    ")",
                    (DEFAULT_AGENT_ID, snapshot_json, DEFAULT_AGENT_ID),
                )
                cur.execute(
                    "UPDATE da_agent_task SET agent_id = %s, agent_snapshot_json = %s "
                    "WHERE agent_id IN ("
                    "SELECT agent_id FROM da_agent_profile WHERE is_builtin = 1 AND agent_id <> %s"
                    ")",
                    (DEFAULT_AGENT_ID, snapshot_json, DEFAULT_AGENT_ID),
                )
                cur.execute(
                    "DELETE FROM da_agent_profile WHERE is_builtin = 1 AND agent_id <> %s",
                    (DEFAULT_AGENT_ID,),
                )
            conn.commit()
        finally:
            conn.close()


_agent_profile_store = AgentProfileStore()


def get_agent_profile_store() -> AgentProfileStore:
    return _agent_profile_store


def bootstrap_default_agent_profile() -> dict[str, Any]:
    store = get_agent_profile_store()
    store.init_schema()
    # The bundled profile is a versioned platform contract, not editable user
    # data. Reconcile it on startup while leaving custom profiles untouched.
    default_profile = store.save_profile(default_agent_payload())
    store.remove_noncanonical_builtin_profiles(default_profile)
    store.backfill_default_bindings(default_profile)
    return default_profile


def list_agent_profiles() -> list[dict[str, Any]]:
    bootstrap_default_agent_profile()
    return get_agent_profile_store().list_profiles()


def get_agent_profile(agent_id: str) -> dict[str, Any] | None:
    bootstrap_default_agent_profile()
    return get_agent_profile_store().get_profile(str(agent_id or "").strip())


def create_agent_profile(payload: dict[str, Any], *, available_skill_folders: set[str] | None = None) -> dict[str, Any]:
    skill_folders = available_skill_folders
    if skill_folders is None:
        skill_folders = set(_dedupe_strings((payload or {}).get("skill_folders")))
    normalized = normalize_agent_profile_payload(
        payload,
        available_skill_folders=skill_folders,
        available_mcp_server_ids=available_mcp_server_ids(),
    )
    normalized["agent_id"] = _new_agent_id()
    normalized["is_default"] = False
    return get_agent_profile_store().save_profile(normalized)


def update_agent_profile(
    agent_id: str,
    payload: dict[str, Any],
    *,
    available_skill_folders: set[str] | None = None,
) -> dict[str, Any]:
    existing = get_agent_profile(agent_id)
    if not existing:
        raise ValueError("agent not found")
    skill_folders = available_skill_folders
    if skill_folders is None:
        skill_folders = set(_dedupe_strings((payload or {}).get("skill_folders") or existing.get("skill_folders")))
    normalized = normalize_agent_profile_payload(
        payload,
        existing=existing,
        available_skill_folders=skill_folders,
        available_mcp_server_ids=available_mcp_server_ids(),
    )
    normalized["agent_id"] = existing["agent_id"]
    normalized["is_default"] = bool(existing.get("is_default"))
    normalized["is_builtin"] = bool(existing.get("is_builtin"))
    return get_agent_profile_store().save_profile(normalized)


def delete_agent_profile(agent_id: str) -> bool:
    return get_agent_profile_store().delete_profile(str(agent_id or "").strip())


def agent_capabilities(skill_documents: list[dict[str, Any]]) -> dict[str, Any]:
    folders: dict[str, dict[str, Any]] = {}
    for document in skill_documents:
        folder = str(document.get("folder") or "").strip()
        if not folder:
            relative = str(document.get("relative_path") or "").strip("/")
            folder = relative.split("/", 1)[0] if "/" in relative else ""
        if not folder:
            continue
        item = folders.setdefault(
            folder,
            {
                "folder": folder,
                "source": str(document.get("source") or "bundled"),
                "enabled": bool(document.get("enabled")),
            },
        )
        item["enabled"] = bool(item.get("enabled")) or bool(document.get("enabled"))
    return {
        "tools": list(SAFE_AGENT_TOOLS),
        "mcp_servers": available_mcp_servers(),
        "skills": sorted(folders.values(), key=lambda item: item["folder"]),
    }


def skill_folders_from_documents(skill_documents: list[dict[str, Any]]) -> set[str]:
    folders: set[str] = set()
    for item in agent_capabilities(skill_documents).get("skills") or []:
        folder = str(item.get("folder") or "").strip()
        if folder:
            folders.add(folder)
    return folders


def list_data_scope_options() -> list[dict[str, Any]]:
    # OntoFoundry does not read another platform's metadata database. Keep the
    # extension endpoint stable; future data-source plugins can supply options.
    return []
