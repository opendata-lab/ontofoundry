"""V3 authoring DTO, separate from the endpoint-oriented SQL join view."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoleJoin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_columns: list[str] = Field(min_length=1)
    role_columns: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def paired(self):
        if len(self.owner_columns) != len(self.role_columns):
            raise ValueError("所属概念与附加角色的连接列数量必须一致")
        if any(
            not c.strip() or len(c) > 240 for c in self.owner_columns + self.role_columns
        ):
            raise ValueError("连接列不能为空或超过 240 字符")
        return self


def role_join_input(value):
    if value is None:
        return None
    if "owner_columns" in value or "role_columns" in value:
        return RoleJoin.model_validate(value)
    # Legacy v3 spellings have OWNER as source, regardless of endpoint_direction.
    if set(value) == {"source_column", "target_column"}:
        return RoleJoin(
            owner_columns=[value["source_column"]], role_columns=[value["target_column"]]
        )
    if (
        set(value) <= {"source_column", "target_column", "source_columns", "target_columns"}
        and "source_columns" in value
        and "target_columns" in value
    ):
        return RoleJoin(
            owner_columns=value["source_columns"], role_columns=value["target_columns"]
        )
    raise ValueError(
        "连接须填写 owner_columns/role_columns，或旧 source_column/target_column"
    )


def authoring_join(views, link_id):
    from .semantic_views import join_columns

    join = views.join(link_id)
    if join is None:
        return None
    link = next(r for r in views.draft.link_types if str(r.id) == str(link_id))
    source, target = join_columns(join)
    owner, role = (
        (target, source) if link.endpoint_direction == "reverse" else (source, target)
    )
    return RoleJoin(owner_columns=list(owner), role_columns=list(role))
