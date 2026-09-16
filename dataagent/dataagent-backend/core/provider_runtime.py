from __future__ import annotations

from urllib.parse import urlparse, urlunparse


ANTHROPIC_MESSAGES_FORMAT = "/v1/messages"
OPENAI_COMPLETIONS_FORMAT = "/v1/chat/completions"
SUPPORTED_API_FORMATS = frozenset({ANTHROPIC_MESSAGES_FORMAT, OPENAI_COMPLETIONS_FORMAT})


def normalize_api_format(raw: str | None) -> str:
    """Validate the wire protocol a provider speaks.

    Routing used to key off ``provider_id`` — a vendor identity — and guessed it
    from substrings of the base URL (``openrouter.ai``, ``.fcapp.run``). Two
    problems: a self-hosted gateway on any other domain fell through to a default,
    and vendor identity does not determine the protocol anyway. The request shape
    does, so that is what routing keys off now. An unknown value raises instead of
    defaulting, because silently picking a protocol produces a failure at the API
    boundary that looks like a credential problem.
    """
    value = str(raw or ANTHROPIC_MESSAGES_FORMAT).strip().lower()
    if value not in SUPPORTED_API_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_API_FORMATS))
        raise ValueError(f"api_format must be one of: {supported}")
    return value


def build_provider_api_url(base_url: str, api_format: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("base_url is required")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute http(s) URL")

    fmt = normalize_api_format(api_format)
    if base.endswith(fmt):
        return base
    if base.endswith("/v1"):
        suffix = "/messages" if fmt == ANTHROPIC_MESSAGES_FORMAT else "/chat/completions"
        return base + suffix
    return base + fmt


def provider_client_base_url(base_url: str, api_format: str) -> str:
    """Return the base URL expected by the selected SDK client.

    Anthropic clients append ``/v1/messages`` themselves, while OpenAI clients
    append ``/chat/completions`` to a base that normally ends in ``/v1``.
    Deriving both from api_format keeps provider ids out of protocol routing.
    """
    endpoint = build_provider_api_url(base_url, api_format)
    fmt = normalize_api_format(api_format)
    suffix = ANTHROPIC_MESSAGES_FORMAT if fmt == ANTHROPIC_MESSAGES_FORMAT else "/chat/completions"
    return endpoint[: -len(suffix)].rstrip("/")


def safe_base_url_for_log(raw_url: str | None) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
        if parsed.scheme and parsed.netloc:
            host = parsed.hostname or ""
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            netloc = host
            if parsed.port is not None:
                netloc = f"{netloc}:{parsed.port}"
            return urlunparse((parsed.scheme, netloc, parsed.path or "", "", "", ""))
    except Exception:
        pass
    return text.split("?", 1)[0].split("#", 1)[0][:200]


def build_provider_env(api_format: str, *, api_key: str, auth_token: str, base_url: str) -> dict[str, str]:
    """Environment for the runtime subprocess, keyed by protocol.

    Every key is written on both branches, including the empty ones: the child
    inherits the parent environment, so omitting a key leaves whatever the
    previous run set. A stale ``ANTHROPIC_BASE_URL`` pointing at the last
    provider is worse than an empty one.
    """
    fmt = normalize_api_format(api_format)
    token = str(api_key or auth_token).strip()
    client_base_url = provider_client_base_url(base_url, fmt)
    if fmt == OPENAI_COMPLETIONS_FORMAT:
        return {
            "ANTHROPIC_AUTH_TOKEN": "",
            "ANTHROPIC_API_KEY": "",
            "ANTHROPIC_BASE_URL": "",
            "OPENAI_API_KEY": token,
            "OPENAI_BASE_URL": client_base_url,
        }
    return {
        "ANTHROPIC_AUTH_TOKEN": "",
        "ANTHROPIC_API_KEY": token,
        "ANTHROPIC_BASE_URL": client_base_url,
        "OPENAI_API_KEY": "",
        "OPENAI_BASE_URL": "",
    }
