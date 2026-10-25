"""HTTP validators for authorized immutable representations."""

import hashlib
import json
import re

from fastapi import Response


def validator(identity) -> str:
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, default=str).encode()
    ).hexdigest()
    return f'W/"{digest}"'


def conditional(request, response, etag):
    headers = {
        "ETag": etag,
        "Cache-Control": "private, no-cache",
        "Vary": "Cookie, Authorization",
    }
    response.headers.update(headers)
    # ETag opaque values may contain commas. Only tokens outside quotes delimit lists.
    tokens = re.findall(r'(?:W/)?"[^"\r\n]*"|\*', request.headers.get("if-none-match", ""))
    if any(
        token == "*" or token.removeprefix("W/") == etag.removeprefix("W/")
        for token in tokens
    ):
        return Response(status_code=304, headers=headers)
    return None
