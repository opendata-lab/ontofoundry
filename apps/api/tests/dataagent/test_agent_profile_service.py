from __future__ import annotations

import sys
from pathlib import Path

import pytest


from dataagent_backend.config import get_settings, update_settings
from dataagent_backend.core import agent_profile_service


def test_default_agent_payload_is_the_single_md2ossie_builtin_agent():
    payload = agent_profile_service.default_agent_payload()

    assert payload["agent_id"] == "agent_ontofoundry"
    assert payload["name"] == "OntoFoundry 建模助手"
    assert payload["description"] == "基于会话材料和当前草稿进行 Apache Ossie 本体建模与概念澄清。"
    assert payload["allowed_tools"] == ["Skill", "Bash", "Read", "LS", "Glob", "Grep"]
    assert payload["mcp_server_ids"] == []
    assert payload["skill_folders"] == ["md2ossie"]
    assert payload["is_default"] is True
    assert payload["is_builtin"] is True


def test_normalize_agent_profile_payload_accepts_scoped_runtime_config():
    payload = agent_profile_service.normalize_agent_profile_payload(
        {
            "name": "质量巡检助手",
            "description": "只处理数据质量规则和巡检结果分析。",
            "system_prompt": "你是数据质量巡检场景的智能体。",
            "permission_mode": "bypassPermissions",
            "allowed_tools": ["Read", "Skill", "Read", "Grep"],
            "mcp_server_ids": ["catalog"],
            "skill_folders": ["business-modeling"],
            "max_turns": 12,
            "env_vars": {"AGENT_SCENE": "quality"},
            "data_scope": {
                "allowed_scopes": [
                    {"cluster_id": 3, "source_type": "DORIS", "database": "ads_user"},
                    {"cluster_id": 3, "source_type": "DORIS", "database": "ads_user"},
                    {"cluster_id": None, "source_type": "MYSQL", "database": "crm"},
                ]
            },
        },
        available_skill_folders={"business-modeling"},
        available_mcp_server_ids={"catalog"},
    )

    assert payload["name"] == "质量巡检助手"
    assert "permission_mode" not in payload
    assert payload["allowed_tools"] == ["Read", "Skill", "Grep"]
    assert payload["mcp_server_ids"] == ["catalog"]
    assert payload["skill_folders"] == ["business-modeling"]
    assert payload["max_turns"] == 12
    assert payload["env_vars"] == {"AGENT_SCENE": "quality"}
    assert payload["data_scope"] == {
        "allowed_scopes": [
            {"cluster_id": 3, "source_type": "DORIS", "database": "ads_user"},
            {"cluster_id": None, "source_type": "MYSQL", "database": "crm"},
        ]
    }


def test_normalize_agent_profile_payload_defaults_empty_data_scope_to_deny_all():
    payload = agent_profile_service.normalize_agent_profile_payload(
        {"name": "无数据授权智能体"},
        available_skill_folders=set(),
        available_mcp_server_ids=set(),
    )

    assert payload["data_scope"] == {"allowed_scopes": []}


def test_normalize_agent_profile_payload_rejects_reserved_environment_keys():
    with pytest.raises(ValueError, match="reserved environment variable"):
        agent_profile_service.normalize_agent_profile_payload(
            {
                "name": "危险配置",
                "env_vars": {"DATAAGENT_TOKEN": "bad"},
            },
            available_skill_folders=set(),
            available_mcp_server_ids=set(),
        )


def test_normalize_agent_profile_payload_defaults_visibility_to_all():
    payload = agent_profile_service.normalize_agent_profile_payload(
        {"name": "默认可见性智能体"},
        available_skill_folders=set(),
        available_mcp_server_ids=set(),
    )

    assert payload["visibility"] == {"mode": "all", "allowed_users": [], "allowed_groups": []}


def test_normalize_agent_profile_payload_accepts_visibility_scope():
    payload = agent_profile_service.normalize_agent_profile_payload(
        {
            "name": "受限智能体",
            "visibility": {
                "mode": "selected",
                "allowed_users": ["SSO:42", "SSO:42", " local:alice "],
            },
        },
        available_skill_folders=set(),
        available_mcp_server_ids=set(),
    )

    assert payload["visibility"] == {
        "mode": "selected",
        "allowed_users": ["SSO:42", "local:alice"],
        "allowed_groups": [],
    }


def test_normalize_agent_profile_payload_preserves_existing_visibility_on_partial_update():
    existing = {
        "name": "受限智能体",
        "visibility": {"mode": "authenticated", "allowed_users": [], "allowed_groups": []},
    }
    payload = agent_profile_service.normalize_agent_profile_payload(
        {"description": "只改描述"},
        existing=existing,
        available_skill_folders=set(),
        available_mcp_server_ids=set(),
    )

    assert payload["visibility"]["mode"] == "authenticated"


def test_normalize_agent_profile_payload_rejects_invalid_visibility_mode():
    with pytest.raises(ValueError, match="invalid visibility mode"):
        agent_profile_service.normalize_agent_profile_payload(
            {"name": "非法可见性", "visibility": {"mode": "vip-only"}},
            available_skill_folders=set(),
            available_mcp_server_ids=set(),
        )


def test_build_agent_snapshot_excludes_visibility():
    snapshot = agent_profile_service.build_agent_snapshot(
        {
            "agent_id": "agent_scoped",
            "name": "受限智能体",
            "visibility": {"mode": "selected", "allowed_users": ["SSO:42"], "allowed_groups": []},
        }
    )

    # 快照供运行时消费，可见性只在实时 profile 上强制，避免话题携带过期副本。
    assert "visibility" not in snapshot


def test_build_agent_snapshot_keeps_runtime_fields_without_timestamps():
    snapshot = agent_profile_service.build_agent_snapshot(
        {
            "agent_id": "agent_quality",
            "name": "质量巡检助手",
            "description": "只处理数据质量规则和巡检结果分析。",
            "system_prompt": "你是数据质量巡检场景的智能体。",
            "permission_mode": "default",
            "allowed_tools": ["Skill", "Read"],
            "mcp_server_ids": ["catalog"],
            "skill_folders": ["business-modeling"],
            "max_turns": 8,
            "env_vars": {"AGENT_SCENE": "quality"},
            "data_scope": {
                "allowed_scopes": [
                    {"cluster_id": 3, "source_type": "DORIS", "database": "ads_user"},
                ]
            },
            "is_default": False,
            "is_builtin": False,
            "created_at": "2026-05-21T10:00:00",
            "updated_at": "2026-05-21T11:00:00",
        }
    )

    assert snapshot == {
        "agent_id": "agent_quality",
        "name": "质量巡检助手",
        "description": "只处理数据质量规则和巡检结果分析。",
        "system_prompt": "你是数据质量巡检场景的智能体。",
        "allowed_tools": ["Skill", "Read"],
        "mcp_server_ids": ["catalog"],
        "skill_folders": ["business-modeling"],
        "max_turns": 8,
        "env_vars": {"AGENT_SCENE": "quality"},
        "data_scope": {
            "allowed_scopes": [
                {"cluster_id": 3, "source_type": "DORIS", "database": "ads_user"},
            ]
        },
        "is_default": False,
        "is_builtin": False,
    }
