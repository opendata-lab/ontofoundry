"""Hash workflow envelopes without applying core model array normalization."""

import hashlib

from ontofoundry_api.domain.canonical import jcs


def payload_sha256(value):
    return hashlib.sha256(("ontofoundry-imports-v1\n" + jcs(value)).encode()).hexdigest()
