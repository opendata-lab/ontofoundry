import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ONTOFOUNDRY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = (
        "postgresql+psycopg://ontofoundry:ontofoundry@127.0.0.1:5432/ontofoundry"
    )
    data_dir: Path = Path("./.data/files")
    web_dist: Path | None = None
    # Test-only escape hatch. Deployed schemas are owned by the unified Alembic chain.
    auto_create_schema: bool = False
    seed_demo: bool = True
    auth_mode: Literal["dev", "login"] = "dev"
    auth_config: Path | None = None
    session_secret: str = "development-only-session-secret-change-me"
    session_cookie_name: str = "ontofoundry_session"
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    # Complete agent execution lives in an external OpenDataWorks DataAgent.
    dataagent_base_url: str = ""
    dataagent_api_prefix: str = "/api/v1/nl2sql"
    dataagent_website_id: str = "ontofoundry"
    dataagent_access_key: str = ""
    dataagent_agent_id: str = "agent_ontofoundry"
    dataagent_request_timeout_seconds: int = Field(default=30, gt=0)
    dataagent_execution_mode: Literal["interactive", "background", "auto"] = "auto"
    modeling_result_contract: Literal["proposals"] = "proposals"
    # Base URL the DataAgent uses to reach this API's MCP endpoint. Empty means
    # "the URL the browser used", which is right when both share a network.
    public_base_url: str = ""
    # A fixed read-only bearer token for the ontology MCP, pasted into the DataAgent
    # MCP header. The public default works out of the box; deployments should set
    # their own value. An explicit empty value disables external MCP access.
    mcp_token: str = "ontofoundry-mcp-default-token"
    metric_query_timeout_seconds: int = Field(default=15, ge=1, le=300)
    max_file_mb: int = 256

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        def checked_dotenv():
            values = dotenv_settings()
            # DotEnvSettingsSource omits empty extras. Keep removed keys so the
            # migration validator can reject them even when their value is empty.
            for name in dotenv_settings.env_vars:
                if name.upper().startswith("ONTOFOUNDRY_OAUTH_"):
                    values[name] = ""
            return values

        return init_settings, env_settings, checked_dotenv, file_secret_settings

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_oauth_settings(cls, values):
        # BaseSettings includes dotenv extras here, even for removed fields.
        supplied = values if isinstance(values, Mapping) else {}
        legacy = sorted({
            key for key in (*os.environ, *supplied)
            if key.upper().startswith("ONTOFOUNDRY_OAUTH_")
            or key.lower().startswith("oauth_")
        })
        if legacy or supplied.get("auth_mode") == "oauth" or os.getenv("ONTOFOUNDRY_AUTH_MODE") == "oauth":
            names = ", ".join(legacy) if legacy else "ONTOFOUNDRY_AUTH_MODE=oauth"
            raise ValueError(
                f"旧 OAuth 配置已移除（{names}）；请迁移到 ONTOFOUNDRY_AUTH_MODE=login，"
                "通过 ONTOFOUNDRY_AUTH_CONFIG 指定 Python 配置文件，"
                "使用 OAUTH_PROVIDERS 和 OAUTH_USER_INFO"
            )
        return values

    @model_validator(mode="after")
    def reject_insecure_production_settings(self) -> "Settings":
        if self.mcp_token and len(self.mcp_token) < 24:
            raise ValueError("ONTOFOUNDRY_MCP_TOKEN must be at least 24 characters")
        if self.environment == "production":
            if self.auth_mode != "login":
                raise ValueError("production requires ONTOFOUNDRY_AUTH_MODE=login")
            if len(self.session_secret) < 32 or self.session_secret.startswith(
                "development-only"
            ):
                raise ValueError("production session secret must be at least 32 characters")
            if not self.cookie_secure or self.seed_demo:
                raise ValueError("production requires secure cookies and seed_demo=false")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
