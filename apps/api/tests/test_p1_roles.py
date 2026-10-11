"""Native proposals, structural role merge and fact validation at runtime."""
from copy import deepcopy
from uuid import UUID, uuid5

import pytest
from pydantic import ValidationError
from test_modeling import create_session
from test_p0_v3_contract import instance_draft, uid
from test_t4_proposal_decisions import decide, seed_batch

from ontofoundry_api.contracts.proposals import ProposalContractError
from ontofoundry_api.domain.canonical import V3_HASH_ALGORITHM, element_sha256
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services.merge import merge_snapshots


def proposal(ref, kind, after):
    return dict(client_ref=ref, operation='create', target_kind=kind, target_id=None,
                expected_target_hash=None, before=None, after=after)


def nary_items():
    def cref(kind, ref):
        return dict(kind=kind, ref={'client_ref': ref})
    return [
        proposal('customer', 'object_type', dict(name='客户', technical_name='customer', concept='customer')),
        proposal('amount', 'value_type', dict(name='金额', technical_name='amount', concept='amount', extends=[dict(kind='builtin', ref='Decimal')])),
        proposal('sale', 'link_type', dict(name='销售', technical_name='sale', owner_ref=cref('object_type', 'customer'), roles=[
            dict(client_ref='buyer', name='buyer', concept=cref('object_type', 'customer')),
            dict(client_ref='price', concept=cref('value_type', 'amount')),
            dict(client_ref='any_party', concept=dict(kind='any', ref='Any')),
        ], verbalizes=['{customer} 销售给 {customer:buyer}，金额 {amount}'])),
        proposal('alice', 'material_object', dict(type_id={'client_ref': 'customer'}, name='Alice', values={})),
        proposal('bob', 'material_object', dict(type_id={'client_ref': 'customer'}, name='Bob', values={})),
        proposal('sale_fact', 'material_link', dict(type_id={'client_ref': 'sale'}, role_values=[
            dict(role_id={'client_ref': 'sale:owner'}, object_id={'client_ref': 'alice'}),
            dict(role_id={'client_ref': 'buyer'}, object_id={'client_ref': 'bob'}),
            dict(role_id={'client_ref': 'price'}, value=42.5),
            dict(role_id={'client_ref': 'any_party'}, object_id={'client_ref': 'bob'}),
        ])),
    ]


def test_nested_roles_and_fact_client_refs_are_resolved_and_accepted(client):
    session = create_session(client)
    batch = seed_batch(client, session, nary_items())
    response = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert response.status_code == 200, response.text
    draft = response.json()['session']['draft']
    link = next(link for link in draft['link_types'] if link['technical_name'] == 'sale')
    fact = draft['material_links'][-1]
    assert [r['name'] for r in link['roles']] == ['buyer', None, None]
    assert all(r['client_ref'] is None for r in link['roles'])
    assert fact['role_values'][0]['role_id'] == str(uuid5(UUID(link['id']), 'role:owner'))
    assert [v['role_id'] for v in fact['role_values'][1:]] == [r['id'] for r in link['roles']]
    assert fact['source_id'] is None and fact['target_id'] is None
    assert len(OntologyDraft.model_validate(draft).material_links[-1].role_values) == 4


def test_duplicate_nested_client_ref_is_rejected(client):
    items = nary_items()
    items[2]['after']['roles'][1]['client_ref'] = 'buyer'
    with pytest.raises(ProposalContractError, match='重复'):
        seed_batch(client, create_session(client), items)


def reordered(data, order):
    result = deepcopy(data)
    result['link_types'][0]['roles'] = [dict(data['link_types'][0]['roles'][i], position=p) for p, i in enumerate(order)]
    return result


def test_role_order_conflict_is_not_hidden_by_id_merge():
    base = instance_draft()
    latest, draft = reordered(base, [1, 0, 2]), reordered(base, [2, 1, 0])
    latest['link_types'][0]['roles'][1]['name'] = 'latest content'
    draft['link_types'][0]['roles'][0]['name'] = 'draft content'
    merged, conflicts = merge_snapshots(base, latest, draft)
    path = '/link_types/' + uid('link') + '/roles/order'
    assert [c['path'] for c in conflicts] == [path]
    assert [r['id'] for r in merged['link_types'][0]['roles']] == [r['id'] for r in draft['link_types'][0]['roles']]
    assert {r.get('name') for r in merged['link_types'][0]['roles']} >= {'latest content', 'draft content'}
    resolved, conflicts = merge_snapshots(base, latest, draft, {path: {'choice': 'latest'}})
    assert conflicts == []
    assert [r['id'] for r in resolved['link_types'][0]['roles']] == [r['id'] for r in latest['link_types'][0]['roles']]
    OntologyDraft.model_validate(resolved)
    assert element_sha256(base['link_types'][0], hash_algorithm=V3_HASH_ALGORITHM, collection='link_types') != element_sha256(draft['link_types'][0], hash_algorithm=V3_HASH_ALGORITHM, collection='link_types')


def test_role_content_and_unilateral_order_merge_independently():
    base = instance_draft()
    latest, draft = deepcopy(base), reordered(base, [2, 0, 1])
    latest['link_types'][0]['roles'][0]['name'] = 'content edit'
    merged, conflicts = merge_snapshots(base, latest, draft)
    assert conflicts == []
    assert merged['link_types'][0]['roles'][1]['name'] == 'content edit'
    OntologyDraft.model_validate(merged)


def test_one_to_one_checks_inverse_tuple_and_inherited_entities():
    data = instance_draft()
    data['object_types'].append(dict(id=uid('subtype'), concept='subtype', name='子类', technical_name='subtype', extends=[dict(kind='object_type', ref=uid('object'))]))
    data['material_objects'][0]['type_id'] = uid('subtype')
    OntologyDraft.model_validate(data)
    data['link_types'][0]['multiplicity'] = 'OneToOne'
    second = deepcopy(data['material_links'][0])
    second['id'] = uid('second_fact')
    second['role_values'][0]['value'] = 'Code2'
    data['material_links'].append(second)
    with pytest.raises(ValidationError, match='OneToOne'):
        OntologyDraft.model_validate(data)


def test_simple_mapping_proposal_still_stores_native_semantic_nodes(client):
    from ontofoundry_api.domain.runtime_views import mappings_of
    session = create_session(client)
    kind = session['draft']['object_types'][0]
    prop = next(p for p in session['draft']['properties'] if p['owner_ref']['ref'] == kind['id'])
    mapping = proposal('table_mapping', 'mapping', dict(type_id=kind['id'], connection_alias='erp', schema_name=None,
                      table_name='suppliers', key_column='id', fields={prop['technical_name']: 'id'}))
    batch = seed_batch(client, session, [mapping])
    response = decide(client, session, [(batch['items'][0]['id'], 'accept')])
    assert response.status_code == 200, response.text
    draft = response.json()['session']['draft']
    assert draft['mappings'] == [] and draft['concept_mappings']
    restored = next(m for m in mappings_of(OntologyDraft.model_validate(draft)) if str(m.type_id) == kind['id'])
    assert restored.table_name == 'suppliers' and restored.connection_alias == 'erp'
