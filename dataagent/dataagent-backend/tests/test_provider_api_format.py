"""按协议而非厂商身份路由 provider。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.provider_runtime import (
    ANTHROPIC_MESSAGES_FORMAT,
    OPENAI_COMPLETIONS_FORMAT,
    build_provider_api_url,
    build_provider_env,
    normalize_api_format,
    provider_client_base_url,
)


def test_unknown_api_format_raises_instead_of_defaulting():
    """静默挑一个协议，失败会出现在 API 边界，看起来像凭证问题。"""
    with pytest.raises(ValueError, match="api_format must be one of"):
        normalize_api_format("/v1/responses")


def test_missing_api_format_defaults_to_anthropic():
    assert normalize_api_format(None) == ANTHROPIC_MESSAGES_FORMAT
    assert normalize_api_format("") == ANTHROPIC_MESSAGES_FORMAT


@pytest.mark.parametrize(
    "base_url,api_format,expected",
    [
        ("https://api.test", ANTHROPIC_MESSAGES_FORMAT, "https://api.test/v1/messages"),
        ("https://api.test/", ANTHROPIC_MESSAGES_FORMAT, "https://api.test/v1/messages"),
        # 已经以 /v1 结尾时只补动词段，不再叠一个 /v1
        ("https://api.test/v1", ANTHROPIC_MESSAGES_FORMAT, "https://api.test/v1/messages"),
        ("https://api.test/v1", OPENAI_COMPLETIONS_FORMAT, "https://api.test/v1/chat/completions"),
        # 已经是完整 endpoint 时保持幂等
        ("https://api.test/v1/messages", ANTHROPIC_MESSAGES_FORMAT, "https://api.test/v1/messages"),
    ],
)
def test_endpoint_construction(base_url, api_format, expected):
    assert build_provider_api_url(base_url, api_format) == expected


def test_relative_base_url_is_rejected():
    with pytest.raises(ValueError, match="absolute http"):
        build_provider_api_url("api.test/v1", ANTHROPIC_MESSAGES_FORMAT)


def test_client_base_url_strips_the_verb_each_sdk_appends_itself():
    assert provider_client_base_url("https://api.test", ANTHROPIC_MESSAGES_FORMAT) == "https://api.test"
    assert provider_client_base_url("https://api.test/v1", OPENAI_COMPLETIONS_FORMAT) == "https://api.test/v1"


def test_openai_format_populates_openai_env_only():
    env = build_provider_env(
        OPENAI_COMPLETIONS_FORMAT, api_key="sk-test", auth_token="", base_url="https://api.test/v1"
    )
    assert env["OPENAI_API_KEY"] == "sk-test"
    assert env["OPENAI_BASE_URL"] == "https://api.test/v1"
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["ANTHROPIC_BASE_URL"] == ""


def test_anthropic_format_populates_anthropic_env_only():
    env = build_provider_env(
        ANTHROPIC_MESSAGES_FORMAT, api_key="", auth_token="tok", base_url="https://api.test"
    )
    assert env["ANTHROPIC_API_KEY"] == "tok"
    assert env["ANTHROPIC_BASE_URL"] == "https://api.test"
    assert env["OPENAI_API_KEY"] == ""
    assert env["OPENAI_BASE_URL"] == ""


def test_both_formats_write_every_key():
    """子进程继承父环境，漏写的键会留着上一次运行的值。

    指向上一个 provider 的陈旧 ANTHROPIC_BASE_URL 比空值更糟：请求会带着新凭证
    打到旧网关。
    """
    anthropic = build_provider_env(
        ANTHROPIC_MESSAGES_FORMAT, api_key="k", auth_token="", base_url="https://a.test"
    )
    openai = build_provider_env(
        OPENAI_COMPLETIONS_FORMAT, api_key="k", auth_token="", base_url="https://b.test/v1"
    )
    assert set(anthropic) == set(openai)


def test_vendor_identity_does_not_leak_into_routing():
    """同一个 base_url 曾被子串匹配判成 anyrouter，现在只由 api_format 决定。"""
    for base in ("https://anyrouter.example/v1", "https://openrouter.ai/api/v1", "https://self.hosted/v1"):
        env = build_provider_env(OPENAI_COMPLETIONS_FORMAT, api_key="k", auth_token="", base_url=base)
        assert env["OPENAI_BASE_URL"] == base
        assert env["ANTHROPIC_BASE_URL"] == ""
