"""User-owned, non-expiring personal access tokens. Persist only SHA-256 digests."""

import hashlib
import secrets
from uuid import uuid4

from sqlalchemy import select

from ontofoundry_api.db_models import PersonalAccessTokenRecord, utc_now
from ontofoundry_api.services.errors import InvalidCredentialsError, NotFoundError


def metadata(item):
    return {
        key: getattr(item, key)
        for key in ("id", "name", "permissions", "created_at", "updated_at", "last_used_at")
    }


def create(db, user_id, payload):
    token = "ofpat." + secrets.token_urlsafe(32)
    item = PersonalAccessTokenRecord(
        id=str(uuid4()),
        user_id=user_id,
        name=payload.name,
        permissions=payload.permissions,
        token_sha256=hashlib.sha256(token.encode()).hexdigest(),
    )
    db.add(item)
    db.commit()
    return {
        **{key: getattr(item, key) for key in ("id", "name", "permissions", "created_at")},
        "token": token,
    }


def list_tokens(db, user_id):
    rows = db.scalars(
        select(PersonalAccessTokenRecord)
        .where(
            PersonalAccessTokenRecord.user_id == user_id,
            PersonalAccessTokenRecord.revoked_at.is_(None),
        )
        .order_by(
            PersonalAccessTokenRecord.created_at.desc(), PersonalAccessTokenRecord.id.desc()
        )
    )
    return [metadata(item) for item in rows]


def owned(db, user_id, token_id, *, active=True):
    item = db.scalar(
        select(PersonalAccessTokenRecord)
        .where(
            PersonalAccessTokenRecord.id == token_id,
            PersonalAccessTokenRecord.user_id == user_id,
        )
        .with_for_update()
    )
    if item is None or (active and item.revoked_at is not None):
        raise NotFoundError("个人令牌不存在", code="TOKEN_NOT_FOUND")
    return item


def patch(db, user_id, token_id, payload):
    item = owned(db, user_id, token_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.updated_at = utc_now()
    db.commit()
    return metadata(item)


def revoke(db, user_id, token_id):
    item = owned(db, user_id, token_id, active=False)
    if item.revoked_at is None:
        item.revoked_at = utc_now()
        item.updated_at = item.revoked_at
        db.commit()


def validate(db, token):
    item = None
    if token.startswith("ofpat."):
        item = db.scalar(select(PersonalAccessTokenRecord).where(
            PersonalAccessTokenRecord.token_sha256 == hashlib.sha256(token.encode()).hexdigest(),
            PersonalAccessTokenRecord.revoked_at.is_(None),
        ))
    if item is None:
        raise InvalidCredentialsError("个人令牌无效或已撤销", code="INVALID_PERSONAL_TOKEN")
    return item
