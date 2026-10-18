"""Signed cursors bind the resolved version, filters, projection and authorization."""

from itsdangerous import BadSignature, URLSafeSerializer

from ontofoundry_api.services.errors import ServiceError


def cursor_signer(settings):
    return URLSafeSerializer(settings.session_secret, salt="core-1-cursor")


def encode_cursor(settings, context, offset, section=None):
    return cursor_signer(settings).dumps(
        {"context": context, "offset": offset, "section": section}
    )


def decode_cursor(settings, cursor, context):
    if not cursor:
        return 0, None
    try:
        data = cursor_signer(settings).loads(cursor)
        if (
            data["context"] != context
            or type(data["offset"]) is not int
            or data["offset"] < 0
        ):
            raise ValueError()
        return data["offset"], data.get("section")
    except (BadSignature, ValueError, KeyError, TypeError) as exc:
        raise ServiceError(
            "游标无效或与当前版本、权限、筛选不一致", code="INVALID_CURSOR", status_code=422
        ) from exc
