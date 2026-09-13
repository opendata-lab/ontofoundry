"""Published instance reads. REST and MCP share the same version and query limits."""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, Field

from ontofoundry_api.api.connections import PreviewRequest, query_mapping
from ontofoundry_api.api.instances import (
    NeighborhoodRequest,
    database_neighborhood,
    database_object,
)
from ontofoundry_api.domain.instance_validation import value_issues
from ontofoundry_api.domain.models import OntologyDraft


class ObjectSearch(BaseModel):
    type_id: UUID | None = None
    source: str = Field(default="document", pattern="^(document|database)$")
    q: str = Field(default="", max_length=240)
    cursor: str | None = Field(default=None, max_length=4000)
    limit: int = Field(default=20, ge=1, le=100)


def envelope(version):
    return {
        "workspace_id": version.workspace_id,
        "version_id": version.id,
        "version_sha256": version.sha256,
        "queried_at": datetime.now(UTC).isoformat(),
    }


def db_ref(type_id, key):
    payload = json.dumps([str(type_id), str(key)], ensure_ascii=False).encode()
    return "db." + base64.urlsafe_b64encode(payload).decode().rstrip("=")


def parse_ref(ref):
    try:
        if ref.startswith("doc."):
            return "document", str(UUID(ref[4:])), None
        if ref.startswith("db."):
            values = json.loads(
                base64.b64decode(
                    ref[3:] + "=" * (-len(ref[3:]) % 4), altchars=b"-_", validate=True
                )
            )
            if (
                isinstance(values, list)
                and len(values) == 2
                and isinstance(values[1], str)
                and len(values[1]) <= 2000
            ):
                return "database", str(UUID(values[0])), values[1]
    except (ValueError, TypeError, UnicodeError):
        pass
    raise HTTPException(422, {"code": "INVALID_OBJECT_REF", "message": "实例引用无效"})


def document_object(obj):
    return {
        **obj.model_dump(mode="json"),
        "ref": "doc." + str(obj.id),
        "source": "document",
    }


def mapping_for(draft, type_id):
    mapping = next((m for m in draft.mappings if str(m.type_id) == str(type_id)), None)
    if not mapping:
        raise HTTPException(
            422, {"code": "MAPPING_REQUIRED", "message": "该类型没有数据映射"}
        )
    return mapping


def search_objects(db, version, options: ObjectSearch, settings):
    draft = OntologyDraft.model_validate(version.snapshot_json)
    if options.type_id and options.type_id not in {t.id for t in draft.object_types}:
        raise HTTPException(404, "业务对象类型不存在")
    context = [
        version.workspace_id,
        version.id,
        str(options.type_id or ""),
        options.source,
        options.q,
    ]
    signer = URLSafeSerializer(settings.session_secret, salt="instance-cursor-v1")
    offset = 0
    if options.cursor:
        try:
            cursor = signer.loads(options.cursor)
            if (
                cursor["context"] != context
                or type(cursor["offset"]) is not int
                or not 0 <= cursor["offset"] <= 10000
            ):
                raise ValueError()
            offset = cursor["offset"]
        except (BadSignature, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(
                422, {"code": "INVALID_CURSOR", "message": "游标无效或与版本、筛选不一致"}
            ) from exc
    if options.source == "database":
        if not options.type_id:
            raise HTTPException(422, "数据库实例搜索需要指定业务对象类型")
        mapping = mapping_for(draft, options.type_id)
        data = query_mapping(
            db,
            version.workspace_id,
            PreviewRequest(
                mapping=mapping, q=options.q, offset=offset, limit=options.limit
            ),
            settings,
        )
        items = [
            {
                **database_object(options.type_id, row),
                "ref": db_ref(options.type_id, row["__key"]),
            }
            for row in data["items"]
        ]
        has_more = data["has_more"]
    else:
        rows = sorted(
            (
                obj
                for obj in draft.objects
                if (
                    not options.type_id or obj.type_id in draft.descendants(options.type_id)
                )
                and options.q.casefold()
                in (obj.name + " " + " ".join(map(str, obj.values.values()))).casefold()
            ),
            key=lambda obj: str(obj.id),
        )
        items = [document_object(obj) for obj in rows[offset : offset + options.limit]]
        has_more = offset + options.limit < len(rows)
    next_offset = offset + options.limit
    truncated = has_more and next_offset > 10000
    return {
        **envelope(version),
        "items": items,
        "source": options.source,
        "data_mode": "live" if options.source == "database" else "snapshot",
        "next_cursor": signer.dumps({"context": context, "offset": next_offset})
        if has_more and not truncated
        else None,
        "truncated": truncated,
        "quality_issues": [
            issue
            for item in items
            for issue in value_issues(
                draft, UUID(item["type_id"]), item["values"], item["ref"]
            )
        ],
    }


def get_object(db, version, ref, settings):
    source, identity, key = parse_ref(ref)
    draft = OntologyDraft.model_validate(version.snapshot_json)
    if source == "document":
        obj = next((obj for obj in draft.objects if str(obj.id) == identity), None)
        if not obj:
            raise HTTPException(404, "该版本中没有此文档实例")
        item = document_object(obj)
    else:
        mapping = mapping_for(draft, identity)
        rows = query_mapping(
            db,
            version.workspace_id,
            PreviewRequest(mapping=mapping, key=key, limit=2),
            settings,
        )["items"]
        if not rows:
            raise HTTPException(404, "实例不存在或源数据已删除")
        if len(rows) != 1 or rows[0]["__key"] is None:
            raise HTTPException(422, "实例标识不唯一或为空")
        item = {**database_object(identity, rows[0]), "ref": ref}
    return {
        **envelope(version),
        "item": item,
        "data_mode": "live" if source == "database" else "snapshot",
        "quality_issues": value_issues(draft, UUID(item["type_id"]), item["values"], ref),
    }


def object_neighborhood(db, version, ref, depth, settings):
    source, identity, key = parse_ref(ref)
    draft = OntologyDraft.model_validate(version.snapshot_json)
    if source == "database":
        result = database_neighborhood(
            db,
            version.workspace_id,
            draft,
            NeighborhoodRequest(type_id=identity, key=key, depth=depth),
            settings,
        )
        for obj in result["objects"]:
            obj["ref"] = db_ref(obj["type_id"], obj["key"])
    else:
        center = get_object(db, version, ref, settings)["item"]
        by_id = {str(obj.id): obj for obj in draft.objects}
        visible, frontier, edges, truncated = {identity}, {identity}, {}, False
        for _ in range(depth):
            following = set()
            for link in draft.links:
                ends = {str(link.source_id), str(link.target_id)}
                if not frontier.intersection(ends):
                    continue
                if len(visible | ends) > 100 or (
                    len(edges) >= 300 and str(link.id) not in edges
                ):
                    truncated = True
                    continue
                following.update(ends - visible)
                visible.update(ends)
                edges[str(link.id)] = link.model_dump(mode="json")
            frontier = following
            if not frontier or truncated:
                break
        result = {
            "center_id": center["id"],
            "objects": [document_object(by_id[oid]) for oid in sorted(visible)],
            "links": list(edges.values()),
            "warnings": [],
            "truncated": truncated,
            "source": source,
            "depth": depth,
        }
    return {
        **envelope(version),
        **result,
        "data_mode": "live" if source == "database" else "snapshot",
        "quality_issues": [
            issue
            for item in result["objects"]
            for issue in value_issues(
                draft, UUID(item["type_id"]), item["values"], item["ref"]
            )
        ],
    }
