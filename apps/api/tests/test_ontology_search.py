"""Shared ontology retrieval contracts, relevance, expansion and authorization."""

import hashlib
import json
from dataclasses import replace

import pytest
from test_core1_mcp import call
from test_modeling import ONTOLOGY, create_session, publish, save
from test_read_contracts import validator

from ontofoundry_api.api.auth import Principal
from ontofoundry_api.contracts.read_models import OntologySearchRead, OntologySearchRequest
from ontofoundry_api.db_models import ServiceTokenRecord, ServiceTokenScopeRecord
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.services.cursors import cursor_signer
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.mcp_ontology import invoke
from ontofoundry_api.services.ontology_search import (
    KeywordRecall,
    RecallHit,
    normalize,
    normalized_positions,
    retrieve,
    search_ontology,
)
from ontofoundry_api.services.workspaces import DEV_USER_ID


def uid(n):
    return f"00000000-0000-4000-8000-{n:012d}"


@pytest.fixture
def draft():
    raw = {
        "workspace_id": str(DEMO_WORKSPACE_ID),
        "object_types": [
            {
                "id": uid(1),
                "name": "purchase_order",
                "display_name": "采购订单",
                "title_property_id": uid(11),
                "synonyms": ["进货单"],
            },
            {
                "id": uid(2),
                "name": "supplier",
                "display_name": "供应商",
                "title_property_id": uid(12),
            },
        ],
        "properties": [
            {
                "id": uid(11),
                "name": "order_no",
                "display_name": "单号",
                "owner_type_id": uid(1),
                "value_kind": "string",
                "identifier": True,
                "unique": True,
                "value_type_id": uid(61),
                "synonyms": ["单据号"],
            },
            {
                "id": uid(12),
                "name": "supplier_name",
                "display_name": "供方名称",
                "owner_type_id": uid(2),
                "value_kind": "string",
            },
        ],
        "link_types": [
            {
                "id": uid(21),
                "name": "belongs_to",
                "display_name": "归属供方",
                "source_type_id": uid(1),
                "target_type_id": uid(2),
                "source_role_name": "购货记录",
                "target_role_name": "供货方",
                "multiplicity": "many_to_one",
            }
        ],
        "datasets": [
            {
                "id": uid(31),
                "name": "purchase_records",
                "display_name": "采购明细集",
                "table_name": "fictional_purchase_records",
                "columns": [
                    {"name": "order_no", "physical_type": "varchar"},
                    {"name": "amount", "physical_type": "decimal"},
                    {"name": "ordered_at", "physical_type": "date"},
                ],
            }
        ],
        "mappings": [
            {
                "id": uid(41),
                "type_id": uid(1),
                "binding_mode": "independent",
                "sources": [
                    {"id": "main", "dataset_id": uid(31), "key_columns": ["order_no"]}
                ],
                "fields": {
                    "order_no": {
                        "kind": "column",
                        "source_id": "main",
                        "column": "order_no",
                    }
                },
            }
        ],
        "metrics": [
            {
                "id": uid(51),
                "kind": "simple",
                "name": "purchase_amount",
                "display_name": "采购金额",
                "dataset_id": uid(31),
                "aggregation": "sum",
                "measure": {"dataset_id": uid(31), "column": "amount"},
                "time_field": {"dataset_id": uid(31), "column": "ordered_at"},
                "synonyms": ["购货总额", "货款"],
            },
            {
                "id": uid(52),
                "kind": "simple",
                "name": "gross_total",
                "display_name": "含税采购金额",
                "dataset_id": uid(31),
                "aggregation": "count",
            },
            {
                "id": uid(53),
                "kind": "ratio",
                "name": "purchase_share",
                "display_name": "采购占比",
                "numerator_id": uid(51),
                "denominator_id": uid(52),
            },
            {
                "id": uid(54),
                "kind": "expression",
                "name": "settlement_pace",
                "display_name": "结算节奏",
                "description": "用于分析延迟到账以及估算结算天数。",
                "dataset_id": uid(31),
                "expression": "SUM(purchase_records.amount)",
            },
        ],
        "rules": [
            {
                "id": uid(71),
                "name": "order_required",
                "display_name": "订单完整性",
                "owner_kind": "object_type",
                "owner_id": uid(1),
                "rule_kind": "constraint",
                "expression": "purchase_order.order_no IS NOT NULL",
            }
        ],
        "value_types": [
            {
                "id": uid(61),
                "name": "order_code",
                "display_name": "订单编码值域",
                "value_kind": "string",
            }
        ],
    }
    raw["metrics"][0]["evidence"] = [
        {
            "kind": "manual",
            "id": uid(81),
            "note": "虚构的私密口径依据",
            "created_by": DEV_USER_ID,
            "created_at": "2026-10-21T00:00:00Z",
        }
    ]
    return CoreDraft.model_validate(raw)


def result(draft, query, **kwargs):
    items, retrieval, unmatched = retrieve(
        query, draft, mappings=kwargs.pop("mappings", True), **kwargs
    )
    return {"items": items, "retrieval": retrieval, "unmatched_terms": unmatched}


def by_id(response):
    return {item["id"]: item for item in response["items"]}


@pytest.mark.parametrize(
    ("query", "identity", "by", "unmatched"),
    [
        ("星河电子近三个月的采购金额", 51, "name_in_query", ["星河电子近三个月的"]),
        ("星河电子购货总额", 51, "name_in_query", ["星河电子"]),
        ("货款", 51, "name_in_query", []),
        ("采购", 51, "query_in_name", ["采购"]),
        ("purchase amount", 51, "name_in_query", []),
        ("ＰＵＲＣＨＡＳＥ　ＡＭＯＵＮＴ", 51, "name_in_query", []),
        ("amount", 51, "name_in_query", []),
        ("进货单", 1, "name_in_query", []),
        ("单据号", 11, "name_in_query", []),
        ("归属供方", 21, "name_in_query", []),
        ("订单完整性", 71, "name_in_query", []),
        ("订单编码值域", 61, "name_in_query", []),
        ("采购明细集", 31, "name_in_query", []),
        ("延迟到账", 54, "description", ["延迟到账"]),
        ("结算天数", 54, "description", ["结算天数"]),
        ("星河，采购金额；昨天", 51, "name_in_query", ["星河", "昨天"]),
        ("采购金额和采购金额", 51, "name_in_query", ["和"]),
        ("查询 采 购 金 额 吧", 51, "name_in_query", ["查询", "吧"]),
        ("purchase_amount！今年", 51, "name_in_query", ["今年"]),
        ("采购占比", 53, "name_in_query", []),
    ],
)
def test_keyword_cases(draft, query, identity, by, unmatched):
    response = result(draft, query, expand=False)
    assert by_id(response)[uid(identity)]["match"]["by"] == by
    assert response["retrieval"] == {"keyword": True, "vector": False}
    assert response["unmatched_terms"] == unmatched


def test_relevance_and_description_use_only_remaining_fragments(draft):
    response = result(draft, "采购金额，延迟到账", expand=False)
    assert [i["id"] for i in response["items"]] == [uid(51), uid(54)]
    assert response["items"][1]["match"] == {"by": "description", "text": "延迟到账"}
    assert response["unmatched_terms"] == ["延迟到账"]
    partial = result(draft, "采购金额", expand=False)
    assert [i["id"] for i in partial["items"]] == [uid(51), uid(52)]
    # A one-character fragment is never a description match.
    assert not result(draft, "迟", expand=False)["items"]
    assert not result(draft, "未定义的叫法", expand=False)["items"]


def test_same_rank_uses_longest_match_then_id(draft):
    query = "含税采购金额和采购金额"
    response = result(draft, query, expand=False)
    assert [i["id"] for i in response["items"]] == [uid(52), uid(51)]
    assert response["unmatched_terms"] == ["和"]
    assert [i["id"] for i in result(draft, "采购", expand=False)["items"]] == sorted(
        i["id"] for i in result(draft, "采购", expand=False)["items"]
    )


def test_normalization_preserves_raw_offsets_and_does_not_casefold(draft):
    raw = "甲，Ａ\u030a \ufb03，乙"
    normalized, positions = normalized_positions(raw)
    assert normalized == normalize(raw) == "甲,Åffi,乙"
    assert positions[2] == (2, 4)
    assert positions[3:6] == [(5, 6)] * 3
    assert normalize("ẞ ß") == "ẞß"
    draft.metrics[0].synonyms = ["Åffi"]
    assert result(draft, raw, expand=False)["unmatched_terms"] == ["甲", "乙"]


def test_expansion_is_one_hop_and_kinds_filter_is_after_expansion(draft):
    metric = result(draft, "货款")
    assert set(by_id(metric)) == {uid(51), uid(1)}
    assert by_id(metric)[uid(1)]["match"] == {
        "by": "expansion",
        "via": {"id": uid(51), "relation": "metric_dataset_bound_type"},
    }
    filtered = result(draft, "货款", kinds=["object_type"])
    assert [i["id"] for i in filtered["items"]] == [uid(1)]
    assert filtered["unmatched_terms"] == []
    assert not result(draft, "货款", kinds=["object_type"], expand=False)["items"]
    obj = result(draft, "进货单")
    assert set(by_id(obj)) == {uid(1), uid(11), uid(21)}
    assert by_id(obj)[uid(11)]["match"]["via"]["relation"] == "object_title_property"
    assert by_id(obj)[uid(21)]["match"]["via"]["relation"] == "object_link_type"
    prop = result(draft, "单据号")
    assert set(by_id(prop)) == {uid(11), uid(1)}
    assert by_id(prop)[uid(1)]["match"]["via"]["relation"] == "property_owner"
    link = result(draft, "归属供方")
    assert set(by_id(link)) == {uid(21), uid(1), uid(2)}
    assert by_id(link)[uid(1)]["match"]["via"]["relation"] == "link_source_type"
    assert by_id(link)[uid(2)]["match"]["via"]["relation"] == "link_target_type"
    ratio = result(draft, "采购占比", mappings=False)
    assert set(by_id(ratio)) == {uid(53), uid(51), uid(52)}
    assert by_id(ratio)[uid(51)]["match"]["via"]["relation"] == "metric_numerator"
    assert by_id(ratio)[uid(52)]["match"]["via"]["relation"] == "metric_denominator"


def test_direct_hits_win_over_expansion_and_summaries(draft):
    response = result(draft, "进货单 单据号 归属供方 采购占比")
    items = response["items"]
    expanded = [i for i, item in enumerate(items) if item["match"]["by"] == "expansion"]
    assert all(item["match"]["by"] != "expansion" for item in items[: expanded[0]])
    directory = by_id(response)
    assert directory[uid(11)]["match"]["by"] == "name_in_query"
    assert directory[uid(1)]["synonyms"] == ["进货单"]
    assert directory[uid(1)]["title_property_id"] == uid(11)
    prop = directory[uid(11)]
    assert prop["owner"] == {
        "id": uid(1),
        "name": "purchase_order",
        "display_name": "采购订单",
    }
    assert (prop["value_kind"], prop["identifier"], prop["value_type_id"]) == (
        "string",
        True,
        uid(61),
    )
    link = directory[uid(21)]
    assert link["source"]["id"] == uid(1) and link["target"]["id"] == uid(2)
    assert (link["source_role_name"], link["target_role_name"], link["multiplicity"]) == (
        "购货记录",
        "供货方",
        "many_to_one",
    )
    assert directory[uid(53)]["definition"] == {
        "kind": "ratio",
        "numerator_id": uid(51),
        "denominator_id": uid(52),
    }
    metric = directory[uid(51)]
    assert metric["definition"]["aggregation"] == "sum"
    assert metric["definition"]["measure"]["column"] == "amount"
    assert metric["definition"]["time_field"]["column"] == "ordered_at"
    assert metric["definition"]["filters"] == []
    assert metric["dataset"] == {"id": uid(31), "name": "purchase_records"}


@pytest.fixture
def published(client, draft):
    session = create_session(client)
    response = save(client, session, draft.model_dump(mode="json"))
    assert response.status_code == 200, response.text
    response = publish(client, response.json())
    assert response.status_code == 200, response.text
    return draft


def rest(client, options, headers=None):
    response = client.post(ONTOLOGY + "/search", json=options, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_rest_mcp_parity_and_pagination_contract(client, published):
    options = {"query": "采购金额", "limit": 1}
    first = rest(client, options)
    assert first == call(client, "search_ontology", options)["structuredContent"]
    assert set(first) == {
        "workspace_id",
        "version_id",
        "items",
        "total",
        "next_cursor",
        "retrieval",
        "unmatched_terms",
    }
    assert first["total"] == 3 and first["next_cursor"]
    assert first["workspace_id"] == str(DEMO_WORKSPACE_ID) and first["version_id"]
    validator("OntologySearchRead").validate(first)
    assert (
        OntologySearchRead.model_validate(first).model_dump(mode="json", exclude_unset=True)
        == first
    )
    decoded = cursor_signer(client.app.state.settings).loads(first["next_cursor"])
    assert decoded["section"]["retrieval"] == {"keyword": True, "vector": False}
    collected = first["items"][:]
    page = first
    while page["next_cursor"]:
        arguments = {**options, "cursor": page["next_cursor"]}
        page = rest(client, arguments)
        assert page == call(client, "search_ontology", arguments)["structuredContent"]
        assert page["unmatched_terms"] == first["unmatched_terms"]
        collected.extend(page["items"])
    assert [i["id"] for i in collected] == [uid(51), uid(52), uid(1)]
    for patch in (
        {"query": "供应商"},
        {"kinds": ["metric"]},
        {"expand": False},
        {"limit": 2},
    ):
        response = client.post(
            ONTOLOGY + "/search", json={**options, **patch, "cursor": first["next_cursor"]}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_CURSOR"
    assert (
        client.post(
            ONTOLOGY + "/search", json={**options, "cursor": "tampered"}
        ).status_code
        == 422
    )
    bad_section = cursor_signer(client.app.state.settings).dumps(
        {
            **decoded,
            "section": {
                "kind": "ontology_search",
                "retrieval": {"keyword": True, "vector": True},
            },
        }
    )
    assert (
        client.post(
            ONTOLOGY + "/search", json={**options, "cursor": bad_section}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"query": "甲" * 241},
        {"query": "", "limit": 0},
        {"query": "", "limit": 101},
        {"query": "", "kinds": ["relation_type"]},
        {"query": "", "version_id": uid(1)},
        {"query": "", "workspace_id": uid(1)},
    ],
)
def test_request_validation_shared_with_mcp(client, options):
    assert client.post(ONTOLOGY + "/search", json=options).status_code == 422
    assert call(client, "search_ontology", options)["isError"]


def token(client, scopes, n=91):
    secret = f"fictional-search-token-{n}"
    with client.app.state.session_factory() as db:
        db.add(
            ServiceTokenRecord(
                id=uid(n),
                workspace_id=str(DEMO_WORKSPACE_ID),
                created_by=DEV_USER_ID,
                name="虚构检索授权",
                token_hash=hashlib.sha256(secret.encode()).hexdigest(),
            )
        )
        db.flush()
        for scope in scopes:
            db.add(ServiceTokenScopeRecord(token_id=uid(n), scope=scope))
        db.commit()
    return {"Authorization": "Bearer " + secret}


def test_permissions_precede_recall_summaries_and_expansion(client, published):
    headers = token(client, [])
    low = rest(client, {"query": ""}, headers)
    assert "dataset" not in {i["kind"] for i in low["items"]}
    assert "fictional_purchase_records" not in json.dumps(low)
    for item in low["items"]:
        assert "dataset" not in item
        if item["kind"] == "metric":
            assert not (
                {"measure", "time_field", "filters", "expression"}
                & item["definition"].keys()
            )
    assert not rest(client, {"query": "货款", "kinds": ["object_type"]}, headers)["items"]
    assert not rest(client, {"query": "采购明细集"}, headers)["items"]
    high = rest(client, {"query": "货款", "limit": 1})
    assert high["next_cursor"]
    assert (
        client.post(
            ONTOLOGY + "/search",
            json={"query": "货款", "limit": 1, "cursor": high["next_cursor"]},
            headers=headers,
        ).status_code
        == 422
    )
    from test_modeling import mcp_request

    mcp = mcp_request(
        client,
        "tools/call",
        {"name": "search_ontology", "arguments": {"query": ""}},
        headers=headers,
    )
    assert mcp.json()["result"]["structuredContent"] == low
    mapping_headers = token(client, ["mappings:read"], n=92)
    mapped = rest(client, {"query": "货款"}, mapping_headers)
    assert by_id(mapped)[uid(51)]["dataset"]["id"] == uid(31)
    assert "evidence" not in json.dumps(mapped)
    assert "虚构的私密口径依据" not in json.dumps(mapped, ensure_ascii=False)
    # Service tokens are still bound to their own workspace by the auth dependency.
    assert (
        client.post(
            f"/api/v1/ontology/workspaces/{uid(999)}/search",
            json={"query": ""},
            headers=headers,
        ).status_code
        == 401
    )


def test_recall_sources_receive_only_visible_elements_and_can_be_added(draft):
    class ExtraRecall:
        name = "vector"

        def recall(self, query, elements):
            assert query == "货款"
            assert all(
                e.kind != "dataset" and "evidence" not in e.definition for e in elements
            )
            assert all("measure" not in e.definition for e in elements)
            return [
                RecallHit(uid(51), {"by": "vector", "text": "货款"}),
                RecallHit(uid(2), {"by": "vector", "text": "供货单位"}),
            ]

    items, retrieval, unmatched = retrieve(
        "货款", draft, mappings=False, sources=(KeywordRecall(), ExtraRecall())
    )
    assert retrieval == {"keyword": True, "vector": True}
    assert [i["id"] for i in items] == [uid(51), uid(2), uid(12), uid(21)]
    assert items[2]["match"] == {
        "by": "expansion",
        "via": {"id": uid(2), "relation": "object_title_property"},
    }
    assert items[0]["match"]["by"] == "name_in_query"
    assert unmatched == []


def test_new_head_invalidates_cursor_and_mcp_pinned_version_is_preserved(client, published):
    options = {"query": "货款", "limit": 1}
    old = rest(client, options)
    session = create_session(client)
    session["draft"]["metrics"][0]["synonyms"] = ["新口径别名"]
    session = save(client, session, session["draft"]).json()
    assert publish(client, session).status_code == 200
    assert (
        client.post(
            ONTOLOGY + "/search", json={**options, "cursor": old["next_cursor"]}
        ).status_code
        == 422
    )
    assert not rest(client, options)["items"]
    high = Principal(id=DEV_USER_ID, subject="fictional", display_name="虚构", email=None)
    with client.app.state.session_factory() as db:
        pinned = replace(high, pinned_version_id=old["version_id"])
        value = invoke(
            db,
            str(DEMO_WORKSPACE_ID),
            pinned,
            "search_ontology",
            options,
            client.app.state.settings,
        )
        assert value == old
        empty = invoke(
            db,
            str(DEMO_WORKSPACE_ID),
            replace(high, pinned_version_id=""),
            "search_ontology",
            {"query": "货款"},
            client.app.state.settings,
        )
        assert empty["version_id"] is None and empty["items"] == []
        with pytest.raises(ServiceError, match="固定发布版已不可用"):
            invoke(
                db,
                str(DEMO_WORKSPACE_ID),
                replace(high, pinned_version_id=uid(999)),
                "search_ontology",
                options,
                client.app.state.settings,
            )

        # A retrieval mode change cannot silently change a later page.
        class ExtraRecall:
            name = "vector"

            def recall(self, query, elements):
                return []

        second = search_ontology(
            db,
            str(DEMO_WORKSPACE_ID),
            pinned,
            OntologySearchRequest(**options, cursor=old["next_cursor"]),
            client.app.state.settings,
            pinned_version_id=pinned.pinned_version_id,
            sources=(KeywordRecall(), ExtraRecall()),
        )
        assert second["retrieval"] == old["retrieval"]
        assert second["items"][0]["id"] == uid(1)
        with pytest.raises(ServiceError, match="召回方式"):
            search_ontology(
                db,
                str(DEMO_WORKSPACE_ID),
                pinned,
                OntologySearchRequest(**options, cursor=old["next_cursor"]),
                client.app.state.settings,
                pinned_version_id=pinned.pinned_version_id,
                sources=(ExtraRecall(),),
            )
