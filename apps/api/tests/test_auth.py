import pytest
from fastapi import HTTPException

from ontofoundry_api.api.auth import build_state, parse_state, safe_return_to


def test_oauth_state_round_trip_and_nonce_binding():
    state = build_state(nonce="nonce-a", return_to="/workspaces/1", secret="secret")

    payload = parse_state(state=state, nonce="nonce-a", secret="secret")

    assert payload["return_to"] == "/workspaces/1"


def test_oauth_state_rejects_wrong_nonce():
    state = build_state(nonce="nonce-a", return_to="/", secret="secret")

    with pytest.raises(HTTPException, match="OAuth nonce"):
        parse_state(state=state, nonce="nonce-b", secret="secret")


def test_return_path_cannot_escape_the_site():
    assert safe_return_to("//malicious.example/path") == "/"
    assert safe_return_to("https://malicious.example") == "/"
    assert safe_return_to("/workspaces/1") == "/workspaces/1"
