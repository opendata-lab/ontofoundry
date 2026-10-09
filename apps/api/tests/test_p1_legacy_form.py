"""P1 keeps the existing simple mapping form separate from persisted native JSON."""
import json
from copy import deepcopy
from uuid import uuid4

import pytest
from test_modeling import ROOT, create_session
from test_p1_native_roundtrip import FIXTURES
from test_p1_roles import nary_items, proposal
from test_t4_proposal_decisions import decide, seed_batch

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.runtime_views import apply_mapping_form, legacy_mapping_form
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID


@pytest.mark.parametrize('stem', ['REDACTED', 'REDACTED'])
def test_unchanged_form_never_rewrites_native_semantic_nodes(client, stem):
    original = json.loads((FIXTURES / f'{stem}.ossie.json').read_text())
    draft, _ = import_ossie(original, workspace_id=DEMO_WORKSPACE_ID, mode='replace')
    session = create_session(client)
    response = client.put(ROOT + f"/sessions/{session['id']}", json={'revision': session['revision'], 'draft': draft})
    assert response.status_code == 200, response.text
    session = response.json()
    form = session['legacy_mapping_form']
    saved = client.put(ROOT + f"/sessions/{session['id']}", json={
        'revision': session['revision'], 'draft': session['draft'], 'legacy_mappings': form['mappings'], 'legacy_joins': form['joins'],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()['draft'] == session['draft']
    assert compile_ossie(OntologyDraft.model_validate(saved.json()['draft']), ontology_name='ignored', ontology_description='ignored') == original


def test_platform_mapping_identity_survives_export_reimport_and_retains_unrelated_native_nodes():
    document = json.loads((FIXTURES / 'REDACTED').read_text())
    draft, _ = import_ossie(document, workspace_id=DEMO_WORKSPACE_ID, mode='replace')
    target = draft['object_types'][0]
    # B's complex source nodes are retained even when a new simple table path is added.
    old_models = deepcopy(draft['semantic_models'])
    old_nodes = deepcopy(draft['mapping_nodes'])
    mapping = dict(id=str(uuid4()), type_id=target['id'], connection_alias='platform_new', schema_name=None,
                   table_name='governance', key_column='id', fields={})
    existing = legacy_mapping_form(draft)
    updated = apply_mapping_form(draft, [mapping], {key: None for key in existing['joins']})
    assert updated['mappings'] == []
    assert all(model in updated['semantic_models'] for model in old_models)
    assert all(node in updated['mapping_nodes'] for node in old_nodes)
    exported = compile_ossie(OntologyDraft.model_validate(updated), ontology_name='ignored', ontology_description='ignored')
    reloaded, _ = import_ossie(exported, workspace_id=DEMO_WORKSPACE_ID, mode='replace')
    for collection in ('semantic_models', 'datasets', 'dataset_fields', 'concept_mappings', 'mapping_nodes'):
        assert {node['id'] for node in reloaded[collection]} == {node['id'] for node in updated[collection]}
    assert reloaded['extension_v4']['legacy_mapping_ids'] == updated['extension_v4']['legacy_mapping_ids']
    assert compile_ossie(OntologyDraft.model_validate(reloaded), ontology_name='ignored', ontology_description='ignored') == exported


def test_binary_element_mapping_save_uses_the_form_and_updates_session(client):
    session = create_session(client)
    target = session['draft']['object_types'][0]
    prop = next(p for p in session['draft']['properties'] if p['owner_ref']['ref'] == target['id'])
    mapping = dict(id=str(uuid4()), type_id=target['id'], connection_alias='erp', schema_name=None,
                   table_name='supplier', key_column='id', fields={prop['technical_name']: 'id'})
    body = dict(target_kind='object_type', target_id=target['id'], session_id=session['id'],
                expected_session_revision=session['revision'], expected_current_version_id=session['base_version_id'],
                draft=session['draft'], legacy_mappings=[mapping], legacy_joins={})
    saved = client.post(ROOT + '/element-saves', json=body)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert result['draft']['mappings'] == [] and result['draft']['concept_mappings']
    assert result['legacy_mapping_form']['mappings'][0] == mapping
    assert result['session']['legacy_mapping_form']['mappings'][0] == mapping
    assert result['session']['draft']['concept_mappings'] == result['draft']['concept_mappings']


def test_new_rule_proposal_attaches_to_ordered_native_owner(client):
    session = create_session(client)
    items = nary_items()[:3]
    items.append(proposal('sale_rule', 'rule', dict(owner_kind='link_type', owner_id={'client_ref': 'sale'}, rule_kind='constraint', expression='true')))
    batch = seed_batch(client, session, items)
    accepted = decide(client, session, [(item['id'], 'accept') for item in batch['items']])
    assert accepted.status_code == 200, accepted.text
    draft = accepted.json()['session']['draft']
    link = next(r for r in draft['link_types'] if r['technical_name'] == 'sale')
    assert link['requires'] == [draft['rules'][-1]['id']]
    document = compile_ossie(OntologyDraft.model_validate(draft), ontology_name='demo', ontology_description='demo')
    relation = next(r for c in document['ontology'] for r in c.get('relationships', []) if r['name'] == 'sale')
    assert relation['requires'] == ['true']


def test_new_platform_self_relation_requires_explicit_role_name(client):
    draft = create_session(client)['draft']
    target = draft['object_types'][0]['id']
    draft['link_types'].append(dict(id=str(uuid4()), name='关联', technical_name='self_related',
                                   owner_ref=dict(kind='object_type', ref=target), roles=[dict(id=str(uuid4()), concept=dict(kind='object_type', ref=target), position=0)],
                                   legacy_multiplicity='many_to_many'))
    exported = compile_ossie(OntologyDraft.model_validate(draft), ontology_name='demo', ontology_description='demo')
    relation = next(r for c in exported['ontology'] for r in c.get('relationships', []) if r['name'] == 'self_related')
    assert 'name' not in relation['roles'][0]
    assert 'multiplicity' not in relation
    assert not validate_ossie(exported)['publishable']
    assert any(i['code'] == 'AMBIGUOUS_ROLE_NAME' for i in validate_ossie(exported)['errors'])
