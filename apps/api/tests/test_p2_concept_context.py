"""Concept context is one platform truth; edits/proposals preserve native nodes."""
from copy import deepcopy
from uuid import uuid4

import pytest
from test_modeling import ROOT, create_session, save
from test_t4_proposal_decisions import seed_batch

from ontofoundry_api.domain.canonical import V3_HASH_ALGORITHM, element_sha256
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import compile_ossie
from ontofoundry_api.ossie.extensions import reverse_export_edits
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.element_diff import element_changes
from ontofoundry_api.services.merge import merge_snapshots
from ontofoundry_api.services.workspaces import publish_draft

USER = '00000000-0000-0000-0000-000000000001'
CONTEXT = {'synonyms': ['客户', '购买者', '客户'], 'instructions': '此处客户指签约买方。'}
SOURCE = {'version': '0.2.0.dev0', 'name': 'source', 'description': '原生说明',
          'ai_context': {'synonyms': ['模型别名'], 'vendor': {'null': None}}, 'ontology': [
              {'concept': 'Customer', 'type': 'EntityType'},
              {'concept': 'Money', 'type': 'ValueType', 'extends': ['Decimal']}]}


@pytest.fixture(params=['client', 'pg_client'])
def context_client(request):
    return request.getfixturevalue(request.param)


def seed(client):
    draft, _ = import_ossie(SOURCE, workspace_id=DEMO_WORKSPACE_ID, mode='replace')
    with client.app.state.session_factory() as db:
        version = publish_draft(db, workspace_id=str(DEMO_WORKSPACE_ID), draft=OntologyDraft.model_validate(draft),
                                user_id=USER, message='P2 context')
    return draft, version.id


def publish_session(client, session):
    path = ROOT + '/sessions/' + session['id']
    preview = client.post(path + '/preview', json={'revision': session['revision']})
    assert preview.status_code == 200, preview.text
    preview = preview.json()
    assert preview['validation']['publishable'] and not preview['validation']['errors'], preview['validation']
    response = client.post(path + '/publish', json={'expected_session_revision': session['revision'],
        'expected_current_version_id': preview['current_version_id'],
        'expected_merged_snapshot_sha256': preview['merged_snapshot_sha256']})
    assert response.status_code == 200, response.text
    return preview


@pytest.mark.parametrize('kind', ['object_type', 'value_type'])
def test_context_element_save_export_and_reimport(context_client, kind):
    client = context_client
    original, version_id = seed(client)
    collection = 'object_types' if kind == 'object_type' else 'value_types'
    concept_id = original[collection][0]['id']
    edited = deepcopy(original)
    edited['extension_v4']['concept_context'][concept_id] = CONTEXT
    response = client.post(ROOT + '/element-saves', json={'target_kind': kind, 'target_id': concept_id,
                           'expected_current_version_id': version_id, 'draft': edited})
    assert response.status_code == 200, response.text
    saved = response.json()['draft']
    assert saved['extension_v4']['concept_context'][concept_id] == CONTEXT
    assert saved[collection] == original[collection]
    changes = element_changes(original, saved)
    assert len(changes) == 1 and changes[0]['element_id'] == concept_id
    assert changes[0]['field_changes'] == [{'path': 'concept_context', 'before': None, 'after': CONTEXT}]
    emitted = compile_ossie(OntologyDraft.model_validate(saved), ontology_name='ignored', ontology_description='ignored')
    assert emitted['ai_context']['ontofoundry']['concept_context'][concept_id] == CONTEXT
    assert reverse_export_edits(emitted) == SOURCE
    imported, _ = import_ossie(emitted, workspace_id=uuid4(), mode='replace')
    assert imported['extension_v4']['concept_context'][concept_id] == CONTEXT


@pytest.mark.parametrize('kind', ['object_type', 'value_type'])
@pytest.mark.parametrize('operation', ['create', 'update'])
def test_context_proposal_accept_preview_publish(context_client, kind, operation):
    client = context_client
    original, _ = seed(client)
    session = create_session(client)
    collection = 'object_types' if kind == 'object_type' else 'value_types'
    if operation == 'update':
        before = deepcopy(session['draft'][collection][0])
        after = {k: v for k, v in before.items() if k != 'id'}
        after['concept_context'] = CONTEXT
        item = dict(operation=operation, target_kind=kind, target_id=before['id'], before=before, after=after,
                    expected_target_hash=element_sha256(before, hash_algorithm=V3_HASH_ALGORITHM, collection=collection))
    else:
        item = dict(operation=operation, target_kind=kind, client_ref='new_concept', target_id=None, before=None,
                    after={'concept': 'NewConcept', 'name': '新概念', 'technical_name': 'new_concept', 'concept_context': CONTEXT})
    if operation == 'create' and kind == 'value_type':
        item['after']['extends'] = [{'kind': 'builtin', 'ref': 'Decimal'}]
    batch = seed_batch(client, session, [item])
    proposal = batch['items'][0]
    response = client.post(ROOT + '/sessions/' + session['id'] + '/proposal-decisions', json={
        'idempotency_key': uuid4().hex, 'expected_session_revision': session['revision'],
        'decisions': [{'proposal_id': proposal['id'], 'decision': 'accept'}]})
    assert response.status_code == 200, response.text
    session = response.json()['session']
    concept_id = proposal['target_id']
    assert session['draft']['extension_v4']['concept_context'][concept_id] == CONTEXT
    concept = next(c for c in session['draft'][collection] if c['id'] == concept_id)
    assert 'concept_context' not in concept
    if operation == 'update':
        assert session['draft'][collection] == original[collection]
    preview = publish_session(client, session)
    assert preview['ossie']['ai_context']['ontofoundry']['concept_context'][concept_id] == CONTEXT


def test_context_save_scope_rejects_other_concepts_and_extension_registry(client):
    original, version = seed(client)
    entity_id, value_id = original['object_types'][0]['id'], original['value_types'][0]['id']
    edited = deepcopy(original)
    edited['extension_v4']['concept_context'][value_id] = CONTEXT
    body = dict(target_kind='object_type', target_id=entity_id, expected_current_version_id=version, draft=edited)
    response = client.post(ROOT + '/element-saves', json=body)
    assert response.status_code == 422 and response.json()['error']['code'] == 'ELEMENT_SCOPE_INVALID'
    body['draft'] = deepcopy(original)
    body['draft']['extension_v4']['ids']['/injected'] = entity_id
    response = client.post(ROOT + '/element-saves', json=body)
    assert response.status_code == 422 and response.json()['error']['code'] == 'ELEMENT_SCOPE_INVALID'


def test_context_proposal_is_stale_after_context_only_edit_and_can_be_rejected(client):
    seed(client)
    session = create_session(client)
    before = deepcopy(session['draft']['object_types'][0])
    item = dict(operation='update', target_kind='object_type', target_id=before['id'], before=before,
                after={**{k: v for k, v in before.items() if k != 'id'}, 'concept_context': CONTEXT}, expected_target_hash=element_sha256(before,
                    hash_algorithm=V3_HASH_ALGORITHM, collection='object_types'))
    batch = seed_batch(client, session, [item])
    draft = deepcopy(session['draft'])
    draft['extension_v4']['concept_context'][before['id']] = {'synonyms': ['人工修改'], 'instructions': None}
    response = save(client, session, draft)
    assert response.status_code == 200, response.text
    session = response.json()
    body = {'idempotency_key': uuid4().hex, 'expected_session_revision': session['revision'],
            'decisions': [{'proposal_id': batch['items'][0]['id'], 'decision': 'accept'}]}
    response = client.post(ROOT + '/sessions/' + session['id'] + '/proposal-decisions', json=body)
    assert response.status_code == 409 and response.json()['error']['code'] == 'PROPOSAL_STALE'
    body['idempotency_key'] = uuid4().hex
    body['decisions'][0]['decision'] = 'reject'
    assert client.post(ROOT + '/sessions/' + session['id'] + '/proposal-decisions', json=body).status_code == 200


def test_context_merges_by_concept_id_and_reports_alias_order_conflicts():
    base = {'extension_v4': {'concept_context': {'a': {'synonyms': ['x', 'y'], 'instructions': 'same'},
                                               'b': {'synonyms': ['b'], 'instructions': None}}}}
    left, right = deepcopy(base), deepcopy(base)
    left['extension_v4']['concept_context']['a']['instructions'] = 'new'
    right['extension_v4']['concept_context']['b']['synonyms'] = ['changed']
    merged, conflicts = merge_snapshots(base, left, right)
    assert not conflicts and merged['extension_v4']['concept_context']['a']['instructions'] == 'new'
    right['extension_v4']['concept_context']['a']['synonyms'] = ['y', 'x']
    left['extension_v4']['concept_context']['a']['synonyms'] = ['x', 'z']
    _, conflicts = merge_snapshots(base, left, right)
    assert [c['path'] for c in conflicts] == ['/extension_v4/concept_context/a/synonyms']


@pytest.mark.parametrize('operation', ['clear', 'delete'])
def test_context_clear_and_concept_delete_remove_only_selected_context(client, operation):
    original, _ = seed(client)
    session = create_session(client)
    draft = deepcopy(session['draft'])
    concept_id = original['object_types'][0]['id']
    value_id = original['value_types'][0]['id']
    draft['extension_v4']['concept_context'] = {concept_id: CONTEXT, value_id: CONTEXT}
    response = save(client, session, draft)
    assert response.status_code == 200, response.text
    session = response.json()
    before = deepcopy(session['draft']['object_types'][0])
    # MCP's read projection may carry this extension; native element hash remains frozen.
    displayed_before = {**before, 'concept_context': CONTEXT}
    after = {**{k: v for k, v in before.items() if k != 'id'}, 'concept_context': None}
    item = dict(operation='update' if operation == 'clear' else 'delete', target_kind='object_type',
                target_id=concept_id, before=displayed_before, after=after if operation == 'clear' else None,
                expected_target_hash=element_sha256(before, hash_algorithm=V3_HASH_ALGORITHM, collection='object_types'))
    proposal = seed_batch(client, session, [item])['items'][0]
    response = client.post(ROOT + '/sessions/' + session['id'] + '/proposal-decisions', json={
        'idempotency_key': uuid4().hex, 'expected_session_revision': session['revision'],
        'decisions': [{'proposal_id': proposal['id'], 'decision': 'accept'}]})
    assert response.status_code == 200, response.text
    assert response.json()['session']['draft']['extension_v4']['concept_context'] == {value_id: CONTEXT}


def test_context_proposal_cannot_author_manual_evidence(client):
    from ontofoundry_api.contracts.proposals import ProposalContractError
    seed(client)
    session = create_session(client)
    item = dict(operation='create', target_kind='object_type', client_ref='concept', target_id=None, before=None,
                after={'concept': 'Thing', 'name': '事物', 'technical_name': 'thing', 'concept_context': CONTEXT,
                       'evidence': [{'kind': 'manual', 'id': str(uuid4()), 'note': '虚构证据',
                                     'created_by': USER, 'created_at': '2026-10-09T00:00:00Z'}]})
    with pytest.raises(ProposalContractError) as error:
        seed_batch(client, session, [item])
    assert error.value.code == 'MANUAL_EVIDENCE_FORBIDDEN'


def test_merge_import_preserves_omitted_context_but_respects_explicit_v4_clear():
    base, _ = import_ossie(SOURCE, workspace_id=DEMO_WORKSPACE_ID, mode='replace')
    concept_id = base['object_types'][0]['id']
    base['extension_v4']['concept_context'][concept_id] = CONTEXT
    merged, _ = import_ossie(SOURCE, workspace_id=DEMO_WORKSPACE_ID, base=base)
    assert merged['extension_v4']['concept_context'][concept_id] == CONTEXT
    cleared = deepcopy(base)
    cleared['extension_v4']['concept_context'] = {}
    emitted = compile_ossie(OntologyDraft.model_validate(cleared), ontology_name='ignored', ontology_description='ignored')
    assert 'concept_context' not in emitted['ai_context']['ontofoundry']  # compact exports omit empty defaults
    # Omission preserves local context; a caller can still explicitly request
    # clearing through the established v4 input contract.
    emitted['ai_context']['ontofoundry']['concept_context'] = {}
    merged, _ = import_ossie(emitted, workspace_id=DEMO_WORKSPACE_ID, base=base)
    assert merged['extension_v4']['concept_context'] == {}
