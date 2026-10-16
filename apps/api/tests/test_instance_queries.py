"""Core direct and mapping-table adjacency, including reverse/self links."""

from types import SimpleNamespace

import pytest
from core1_query_fixtures import source_database

from ontofoundry_api.services.instance_neighborhood import database_neighborhood
from ontofoundry_api.services.instance_plan import query_instances


@pytest.mark.parametrize(
    "example",
    [
        "01-basic-sales",
        "02-many-to-many",
        "04-composite-key",
        "05-self-and-parallel-links",
        "11-multi-source-and-unique-link",
    ],
)
def test_neighborhood_uses_declared_join_columns(tmp_path, monkeypatch, example):
    draft, engine = source_database(tmp_path, monkeypatch, example)
    try:
        mapping = draft.mappings[0]
        rows = query_instances(None, str(draft.workspace_id), draft, mapping.type_id, None)[
            "items"
        ]
        if rows:
            result = database_neighborhood(
                None,
                str(draft.workspace_id),
                draft,
                SimpleNamespace(
                    type_id=mapping.type_id,
                    key=rows[0]["__key"],
                    depth=2,
                    snapshot_date=None,
                ),
                None,
            )
            assert result["objects"]
            assert len(result["objects"]) <= 100 and len(result["links"]) <= 300
            assert not result["warnings"], result["warnings"]
    finally:
        engine.dispose()
