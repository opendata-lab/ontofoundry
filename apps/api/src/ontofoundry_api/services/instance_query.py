"""Published core instance reads. MCP uses only the document path."""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ontofoundry_api.domain.graph import DraftIndex
from ontofoundry_api.domain.instance_display import document_display_text
from ontofoundry_api.domain.instance_validation import value_issues
from ontofoundry_api.domain.snapshot import read_snapshot
from ontofoundry_api.services.cursors import decode_cursor, encode_cursor
from ontofoundry_api.services.errors import NotFoundError, ServiceError
from ontofoundry_api.services.ontology_query import version_hashes


class ObjectSearch(BaseModel):
    type_id: UUID | None = None
    source: str = Field(default="document", pattern="^(document|database)$")
    q: str = Field(default="", max_length=240)
    cursor: str | None = Field(default=None, max_length=4000)
    limit: int = Field(default=20, ge=1, le=100)
    snapshot_date: str | None = None


def envelope(version):
    return {
        "workspace_id": version.workspace_id,
        "version_id": version.id,
        **version_hashes(version),
        "queried_at": datetime.now(UTC).isoformat(),
    }


def db_ref(type_id, key):
    from ontofoundry_api.services.instance_plan import key_values

    key_values(key)
    return "db." + base64.urlsafe_b64encode(
        json.dumps([str(type_id), key], ensure_ascii=False, separators=(",", ":")).encode()
    ).decode().rstrip("=")


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
                not isinstance(values, list)
                or len(values) != 2
                or not isinstance(values[1], list)
                or not 1 <= len(values[1]) <= 16
            ):
                raise ValueError()
            from ontofoundry_api.services.instance_plan import key_values

            key_values(values[1])
            return "database", str(UUID(values[0])), values[1]
    except (ValueError, TypeError, UnicodeError):
        pass
    raise ServiceError("实例引用无效", code="INVALID_OBJECT_REF", status_code=422)


def document_object(obj, draft):
    return {
        **obj.model_dump(mode="json"),
        "ref": "doc." + str(obj.id),
        "source": "document",
        "display_text": document_display_text(draft, obj),
    }


def database_object(type_id, row):
    ref = db_ref(row.get("__type_id", type_id), row["__key"])
    return {
        "id": ref,
        "ref": ref,
        "type_id": row.get("__type_id", str(type_id)),
        "key": row["__key"],
        "source": "database",
        "display_text": row["display_text"],
        "values": row["values"],
        "evidence": [],
    }


def mapping_for(draft, type_id):
    mapping = next((m for m in draft.mappings if m.type_id == UUID(str(type_id))), None)
    if mapping is None:
        raise ServiceError("对象没有本地绑定", code="MAPPING_REQUIRED", status_code=422)
    return mapping


def search_objects(db, version, options, settings, *, permission_fingerprint=""):
    draft = read_snapshot(version.snapshot_json, version.workspace_id)
    index = DraftIndex(draft)
    if options.type_id and options.type_id not in index.objects:
        raise NotFoundError("对象类型不存在")
    if options.source == "document" and options.snapshot_date:
        raise ServiceError(
            "文档事实不接受快照日期", code="VALIDATION_FAILED", status_code=422
        )
    context = [
        version.workspace_id,
        version.id,
        "rest_objects",
        str(options.type_id or ""),
        options.source,
        options.q,
        options.snapshot_date,
        permission_fingerprint,
    ]
    offset, _ = decode_cursor(settings, options.cursor, context)
    if options.source == "database":
        if not options.type_id:
            raise ServiceError(
                "数据库浏览必须指定对象类型", code="VALIDATION_FAILED", status_code=422
            )
        from ontofoundry_api.services.instance_plan import query_instances

        data = query_instances(
            db,
            version.workspace_id,
            draft,
            options.type_id,
            settings,
            q=options.q,
            offset=offset,
            limit=options.limit,
            snapshot_date=options.snapshot_date,
        )
        items = [database_object(options.type_id, r) for r in data["items"]]
        more, dates = data["has_more"], data["snapshot_dates"]
    else:
        rows = [
            o
            for o in draft.material_objects
            if (not options.type_id or index.is_a(o.type_id, options.type_id))
            and options.q.casefold()
            in (
                document_display_text(draft, o)
                + " "
                + " ".join(map(str, o.values.values()))
            ).casefold()
        ]
        rows.sort(key=lambda o: o.id.bytes)
        items = [document_object(o, draft) for o in rows[offset : offset + options.limit]]
        more, dates = len(rows) > offset + options.limit, []
    truncated = more and offset + options.limit > 10000
    return {
        **envelope(version),
        "items": items,
        "source": options.source,
        "data_mode": "live" if options.source == "database" else "snapshot",
        "snapshot_dates": dates,
        "next_cursor": encode_cursor(settings, context, offset + options.limit)
        if more and not truncated
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


def get_object(db, version, ref, settings, snapshot_date=None):
    source, identity, key = parse_ref(ref)
    draft = read_snapshot(version.snapshot_json, version.workspace_id)
    dates = []
    if source == "document":
        if snapshot_date:
            raise ServiceError(
                "文档事实不接受快照日期", code="VALIDATION_FAILED", status_code=422
            )
        fact = next((o for o in draft.material_objects if str(o.id) == identity), None)
        if fact is None:
            raise NotFoundError("该版本中没有此文档事实")
        item = document_object(fact, draft)
    else:
        from ontofoundry_api.services.instance_plan import query_instances

        data = query_instances(
            db,
            version.workspace_id,
            draft,
            identity,
            settings,
            key=key,
            limit=2,
            snapshot_date=snapshot_date,
        )
        if not data["items"]:
            raise NotFoundError("该实例不存在或源数据已删除")
        item, dates = database_object(identity, data["items"][0]), data["snapshot_dates"]
    return {
        **envelope(version),
        "item": item,
        "snapshot_dates": dates,
        "data_mode": "live" if source == "database" else "snapshot",
        "quality_issues": value_issues(draft, UUID(item["type_id"]), item["values"], ref),
    }


def object_neighborhood(db, version, ref, depth, settings, snapshot_date=None):
    source, identity, key = parse_ref(ref)
    draft = read_snapshot(version.snapshot_json, version.workspace_id)
    if source == "database":
        from types import SimpleNamespace

        from ontofoundry_api.services.instance_neighborhood import database_neighborhood

        result = database_neighborhood(
            db,
            version.workspace_id,
            draft,
            SimpleNamespace(
                type_id=identity, key=key, depth=depth, snapshot_date=snapshot_date
            ),
            settings,
        )
    else:
        center = get_object(db, version, ref, settings, snapshot_date)["item"]
        visible, frontier, edges, truncated = {identity}, {identity}, {}, False
        for _ in range(depth):
            following = set()
            for link in draft.material_links:
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
        result = {
            "center_id": center["id"],
            "objects": [
                document_object(o, draft)
                for o in draft.material_objects
                if str(o.id) in visible
            ],
            "links": list(edges.values()),
            "source": "document",
            "depth": depth,
            "warnings": [],
            "truncated": truncated,
            "snapshot_dates": [],
        }
    return {
        **envelope(version),
        **result,
        "data_mode": "live" if source == "database" else "snapshot",
        "quality_issues": [],
    }
