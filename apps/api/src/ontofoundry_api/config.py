from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ONTOFOUNDRY_",
        env_file=".env",
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
    auth_mode: Literal["dev", "oauth"] = "dev"
    session_secret: str = "development-only-session-secret-change-me"
    session_cookie_name: str = "ontofoundry_session"
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    oauth_provider: str = "internal"
    oauth_authorize_url: str = ""
    oauth_token_url: str = ""
    oauth_user_info_url: str = ""
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_redirect_uri: str = "http://localhost:8000/api/v1/auth/callback"
    # Complete agent execution lives in an external OpenDataWorks DataAgent.
    dataagent_base_url: str = ""
    dataagent_api_prefix: str = "/api/v1/nl2sql"
    dataagent_website_id: str = "ontofoundry"
    dataagent_access_key: str = ""
    dataagent_agent_id: str = "agent_ontofoundry"
    dataagent_request_timeout_seconds: int = Field(default=30, gt=0)
    dataagent_execution_mode: Literal["interactive", "background", "auto"] = "auto"
    connection_key: str = ""
    max_file_mb: int = 256

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @model_validator(mode="after")
    def reject_insecure_production_settings(self) -> "Settings":
        if self.environment == "production":
            if self.auth_mode != "oauth":
                raise ValueError("production requires ONTOFOUNDRY_AUTH_MODE=oauth")
            if len(self.session_secret) < 32 or self.session_secret.startswith(
                "development-only"
            ):
                raise ValueError("production session secret must be at least 32 characters")
            if not self.cookie_secure or self.seed_demo:
                raise ValueError("production requires secure cookies and seed_demo=false")
            required = {
                "oauth_authorize_url": self.oauth_authorize_url,
                "oauth_token_url": self.oauth_token_url,
                "oauth_user_info_url": self.oauth_user_info_url,
                "oauth_client_id": self.oauth_client_id,
                "oauth_client_secret": self.oauth_client_secret,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise ValueError("production OAuth settings missing: " + ", ".join(missing))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
