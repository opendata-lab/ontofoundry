from __future__ import annotations

from typing import Any

from ontofoundry_api.config import Settings
from ontofoundry_api.services.dataagent import (
    DataAgentClient,
    DataAgentError,
    require_dataagent_configuration,
)


def _check(name: str, ok: bool, message: str, hint: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "message": message, "hint": hint}


def _skipped(name: str, reason: str, hint: str) -> dict[str, Any]:
    return _check(name, False, f"未执行：{reason}", hint)


async def dataagent_health(settings: Settings, workspace_id: str) -> dict[str, Any]:
    try:
        require_dataagent_configuration(
            settings.dataagent_base_url, settings.dataagent_access_key
        )
    except DataAgentError as exc:
        checks = [
            _check("配置完整性", False, str(exc), exc.hint),
            _skipped("连通性", "配置不完整", exc.hint),
            _skipped("站点放行", "配置不完整", exc.hint),
            _skipped("Agent 存在性", "配置不完整", exc.hint),
        ]
        return {"ok": False, "checks": checks}

    checks = [_check("配置完整性", True, "服务端地址与接入密钥已配置")]
    client = DataAgentClient(
        settings.dataagent_base_url,
        prefix=settings.dataagent_api_prefix,
        website_id=settings.dataagent_website_id,
        access_key=settings.dataagent_access_key,
        session_ref=f"ontofoundry:{workspace_id}:diagnostics",
        timeout_seconds=settings.dataagent_request_timeout_seconds,
    )
    try:
        await client.agent_profile(settings.dataagent_agent_id)
    except DataAgentError as exc:
        if str(exc) == "无法连接 DataAgent":
            checks.extend(
                [
                    _check("连通性", False, str(exc), exc.hint),
                    _skipped("站点放行", "DataAgent 不可达", exc.hint),
                    _skipped("Agent 存在性", "DataAgent 不可达", exc.hint),
                ]
            )
        elif str(exc) in {
            "DataAgent 拒绝了本站点",
            "DataAgent 拒绝了服务端接入密钥",
        }:
            checks.extend(
                [
                    _check("连通性", True, "已连接 DataAgent"),
                    _check("站点放行", False, str(exc), exc.hint),
                    _skipped("Agent 存在性", "接入校验未通过", exc.hint),
                ]
            )
        elif str(exc) == "DataAgent 上找不到该 Agent":
            checks.extend(
                [
                    _check("连通性", True, "已连接 DataAgent"),
                    _check("站点放行", True, "站点与接入密钥校验通过"),
                    _check("Agent 存在性", False, str(exc), exc.hint),
                ]
            )
        else:
            checks.extend(
                [
                    _check("连通性", True, "已连接 DataAgent"),
                    _check("站点放行", False, str(exc), exc.hint),
                    _skipped("Agent 存在性", "DataAgent 请求失败", exc.hint),
                ]
            )
        return {"ok": False, "checks": checks}

    checks.extend(
        [
            _check("连通性", True, "已连接 DataAgent"),
            _check("站点放行", True, "站点与接入密钥校验通过"),
            _check(
                "Agent 存在性",
                True,
                f"agent_id={settings.dataagent_agent_id} 存在且可见",
            ),
        ]
    )
    return {"ok": True, "checks": checks}
