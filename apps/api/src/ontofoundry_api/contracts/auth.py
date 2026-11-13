"""Public platform login request and response contracts."""

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class OAuthOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class AuthOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_login: bool
    oauth: OAuthOption | None


class LocalLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str = Field(repr=False)


def auth_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "ontofoundry.auth.v1.schema.json",
        **TypeAdapter(AuthOptions | LocalLoginRequest).json_schema(),
    }
