"""Published MCP role DTOs, semantic incidence and document n-ary neighborhoods."""
from uuid import uuid4

import pytest
from test_modeling import ONTOLOGY, create_session, publish, save
from test_p1_roles import nary_items
from test_t4_proposal_decisions import decide, seed_batch
from test_t7_mcp_elements import call


@pytest.fixture
def nary_version(client):
    session = create_session(client)
    batch = seed_batch(client, session, nary_items())
    accepted = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert accepted.status_code == 200, accepted.text
    session = accepted.json()['session']
    result = publish(client, session)
    assert result.status_code == 200, result.text
    return session['draft']


def test_mcp_lists_gets_and_searches_complete_native_roles(client, nary_version):
    link = next(r for r in nary_version['link_types'] if r['technical_name'] == 'sale')
    listing = call(client, 'list_ontology_elements', kind='link_type', limit=200)
    found = next(r for r in listing['items'] if r['id'] == link['id'])
    single = call(client, 'get_ontology_elements', element_ids=[link['id']])['items'][0]['element']
    typed = call(client, 'get_ontology_type', type_id=link['id'])['item']
    for result in (found, single, typed):
        assert result['owner_ref'] == link['owner_ref'] and result['roles'] == link['roles']
        assert len(result['all_roles']) == 4 and result['all_roles'][0]['implicit_owner']
        assert [r['id'] for r in result['all_roles'][1:]] == [r['id'] for r in link['roles']]
    assert typed['source_type_id'] is None and typed['target_type_id'] is None
    values = call(client, 'list_ontology_elements', kind='value_type')
    assert any(v['concept'] == 'amount' for v in values['items'])
    searched = call(client, 'search_ontology_types', query='amount')
    assert link['id'] in {item['id'] for item in searched['items']}


def test_semantic_hyperedge_keeps_every_ordered_role_incidence(client, nary_version):
    link = next(r for r in nary_version['link_types'] if r['technical_name'] == 'sale')
    graph = call(client, 'get_ontology_graph', focus_id=link['id'], depth=1)
    center = next(n for n in graph['nodes'] if n['id'] == link['id'])
    assert center['kind'] == 'link_type' and center['roles'] == link['roles']
    roles = [e for e in graph['edges'] if e['kind'] == 'role']
    assert [e['role_id'] for e in roles] == [r['id'] for r in center['all_roles']]
    assert all(e['source'] == link['id'] for e in roles)
    assert len(roles) == 4 and len({e['id'] for e in roles}) == 4
    assert {e['target'] for e in roles} <= {n['id'] for n in graph['nodes']}


def test_expand_document_graph_uses_role_values_instead_of_binary_endpoints(client, nary_version):
    alice, bob = [o for o in nary_version['material_objects'] if o['name'] in ('Alice', 'Bob')]
    ref = 'doc.' + alice['id']
    graph = call(client, 'expand_object_graph', ref=ref, depth=1)
    assert {o['id'] for o in graph['objects']} == {alice['id'], bob['id']}
    fact = next(f for f in graph['links'] if f['id'] == nary_version['material_links'][-1]['id'])
    assert fact['role_values'] == nary_version['material_links'][-1]['role_values']
    assert len(fact['all_roles']) == 4 and len(fact['roles']) == 3
    assert fact['source_id'] is None and fact['target_id'] is None
    rest = client.get(ONTOLOGY + '/objects/' + ref + '/neighborhood').json()
    assert rest['links'] == graph['links']


def test_unary_graph_has_implicit_owner_role_only(client):
    session = create_session(client)
    link = {**session['draft']['link_types'][0], 'id': str(uuid4()), 'roles': [], 'technical_name': 'unary', 'name': '有效', 'verbalizes': [], 'requires': [], 'derived_by': [], 'position': None, 'origin': 'platform', 'native_presence': []}
    session['draft']['link_types'].append(link)
    session = save(client, session, session['draft']).json()
    response = publish(client, session)
    assert response.status_code == 200, response.text
    graph = call(client, 'get_ontology_graph', focus_id=link['id'], depth=1)
    assert len(graph['edges']) == 1 and graph['edges'][0]['kind'] == 'role'
