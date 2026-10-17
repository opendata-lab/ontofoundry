"""API setup for result regressions using the shared fictional design examples."""

from core1_fixtures import example_draft_json
from test_modeling import create_session, publish, save


def example_session(client, name, *, published=False):
    session = create_session(client)
    raw = example_draft_json(name)
    raw["workspace_id"] = session["workspace_id"]
    for elements in raw.values():
        if isinstance(elements, list):
            for element in elements:
                if "evidence" in element:
                    element["evidence"] = []
    response = save(client, session, raw)
    assert response.status_code == 200, response.text
    session = response.json()
    if published:
        response = publish(client, session)
        assert response.status_code == 200, response.text
        session = create_session(client)
    return session
