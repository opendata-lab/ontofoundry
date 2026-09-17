from __future__ import annotations

import sys
import types
from pathlib import Path


from dataagent_backend.core.skill_admin_store import SkillAdminStore


def test_normalize_settings_payload_keeps_provider_settings_dict():
    store = SkillAdminStore()
    normalized = store._normalize_settings_payload(
        {
            "provider_id": "openrouter",
            "model": "anthropic/claude-sonnet-4.5",
            "provider_settings": {
                "openrouter": {
                    "provider_id": "openrouter",
                    "enabled_models": ["anthropic/claude-sonnet-4.5"],
                }
            },
        }
    )

    assert isinstance(normalized["provider_settings"], dict)
    assert normalized["provider_settings"]["openrouter"]["enabled_models"] == ["anthropic/claude-sonnet-4.5"]


def test_normalize_settings_payload_accepts_legacy_providers_list():
    store = SkillAdminStore()
    normalized = store._normalize_settings_payload(
        {
            "provider_id": "openrouter",
            "model": "anthropic/claude-sonnet-4.5",
            "providers": [
                {
                    "provider_id": "openrouter",
                    "enabled_models": ["anthropic/claude-sonnet-4.5"],
                }
            ],
        }
    )

    assert isinstance(normalized["provider_settings"], dict)
    assert normalized["provider_settings"]["openrouter"]["enabled_models"] == ["anthropic/claude-sonnet-4.5"]


def test_normalize_settings_payload_keeps_blank_provider_and_model():
    store = SkillAdminStore()
    normalized = store._normalize_settings_payload(
        {
            "provider_id": "",
            "model": "",
        }
    )

    assert normalized["provider_id"] == ""
    assert normalized["model"] == ""


def test_normalize_settings_row_keeps_provider_settings_dict():
    store = SkillAdminStore()
    normalized = store._normalize_settings_row(
        {
            "provider_id": "openrouter",
            "model_name": "anthropic/claude-sonnet-4.5",
            "anthropic_api_key": "",
            "anthropic_auth_token": "",
            "anthropic_base_url": "",
            "skills_output_dir": "../.claude/skills/md2ossie",
            "updated_at": None,
            "raw_json": "{\"provider_settings\":{\"openrouter\":{\"provider_id\":\"openrouter\",\"enabled_models\":[\"anthropic/claude-sonnet-4.5\"]}}}",
        }
    )

    assert isinstance(normalized["provider_settings"], dict)
    assert normalized["provider_settings"]["openrouter"]["provider_id"] == "openrouter"


def test_normalize_settings_row_accepts_legacy_providers_list():
    store = SkillAdminStore()
    normalized = store._normalize_settings_row(
        {
            "provider_id": "openrouter",
            "model_name": "anthropic/claude-sonnet-4.5",
            "anthropic_api_key": "",
            "anthropic_auth_token": "",
            "anthropic_base_url": "",
            "skills_output_dir": "../.claude/skills/md2ossie",
            "updated_at": None,
            "raw_json": "{\"providers\":[{\"provider_id\":\"openrouter\",\"enabled_models\":[\"anthropic/claude-sonnet-4.5\"]}]}",
        }
    )

    assert isinstance(normalized["provider_settings"], dict)
    assert normalized["provider_settings"]["openrouter"]["provider_id"] == "openrouter"


def test_normalize_settings_row_keeps_blank_provider_and_model():
    store = SkillAdminStore()
    normalized = store._normalize_settings_row(
        {
            "provider_id": "",
            "model_name": "",
            "anthropic_api_key": "",
            "anthropic_auth_token": "",
            "anthropic_base_url": "",
            "skills_output_dir": "../.claude/skills/md2ossie",
            "updated_at": None,
            "raw_json": None,
        }
    )

    assert normalized["provider_id"] == ""
    assert normalized["model"] == ""
