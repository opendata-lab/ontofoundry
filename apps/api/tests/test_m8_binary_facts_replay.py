"""Replay the unchanged real 26-item result through both persistent engines."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4, uuid5

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from ontofoundry_api.contracts.proposals import RunContext, item_fingerprint, parse_result
from ontofoundry_api.db_models import (
    MaterialRecord,
    ModelingSessionRecord,
    OntologyVersionRecord,
    ProposalItemRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.fact_views import binary_fact_view
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.services.element_diff import element_label
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposals import store_batch

FIXTURES = Path(__file__).parent / 'fixtures' / 'real_runs'
USER = '00000000-0000-0000-0000-000000000001'


@pytest.fixture(params=['client', 'pg_client'])
def replay_client(request):
    return request.getfixturevalue(request.param)


def seed_evidence(db, settings, workspace, raw):
    """Source files were not supplied: reconstruct only the supplied quote lines.

    Keep the original material IDs/hash metadata and exercise the real material
    lookup and line/quote validator. This is not a full source-file hash replay.
    """
    groups = {}
    for item in raw['items']:
        for evidence in [*item.get('evidence', []), *(item.get('after') or {}).get('evidence', [])]:
            if evidence.get('kind') == 'material':
                groups.setdefault(evidence['material_id'], []).append(evidence)
    directory = settings.data_dir / workspace
    directory.mkdir(parents=True, exist_ok=True)
    for material_id, evidences in groups.items():
        lines = [''] * max(e['locator']['line_end'] for e in evidences)
        # The multi-line instance quotes also contain their more specific citations.
        for evidence in sorted(evidences, key=lambda e: e['locator']['line_start'] - e['locator']['line_end']):
            start, end = evidence['locator']['line_start'], evidence['locator']['line_end']
            quote = evidence['quote']
            if ' '.join(quote.split()) in ' '.join(' '.join(lines[start - 1:end]).split()):
                continue
            for offset, line in enumerate(quote.splitlines()):
                assert start - 1 + offset < end
                old = lines[start - 1 + offset]
                assert not old or old == line
                lines[start - 1 + offset] = line
        text = '\n'.join(lines)
        sha = evidences[0]['material_sha256']
        (directory / (sha + '.md')).write_text(text, encoding='utf-8')
        db.add(MaterialRecord(id=material_id, workspace_id=workspace, name='replay-quotes.md',
                             sha256=sha, byte_size=len(text.encode())))


def seed_replay(client):
    raw_bytes = (FIXTURES / 'topdown-raw-result.json').read_bytes()
    raw = json.loads(raw_bytes)
    replay = json.loads((FIXTURES / 'topdown-replay.json').read_text(encoding='utf-8'))
    snapshot = replay['published_snapshot']
    assert snapshot_sha256(replay['session_draft']) == raw['source_draft_sha256']
    workspace = raw['workspace_id']
    with client.app.state.session_factory() as db:
        db.add(WorkspaceRecord(id=workspace, slug='real-topdown-replay', name='真实退货回放', created_by=USER))
        db.flush()
        db.add(WorkspaceMemberRecord(workspace_id=workspace, user_id=USER, role='owner'))
        db.add(OntologyVersionRecord(id=raw['base_version_id'], workspace_id=workspace, version_number=1,
               snapshot_json=snapshot, ossie_json=compile_ossie(OntologyDraft.model_validate(snapshot),
               ontology_name='coffee_sales', ontology_description=''), validation_json={},
               # The fixture is a read projection. Preserve the original stored-version hash from the header.
               sha256=raw['base_version_sha256'], published_by=USER))
        db.add(ModelingSessionRecord(id=raw['session_id'], workspace_id=workspace, created_by=USER,
               title='售后退货（备用）', base_version_id=raw['base_version_id'],
               base_version_sha256=raw['base_version_sha256'], revision=raw['source_session_revision'],
               draft_json=replay['session_draft'], draft_sha256=raw['source_draft_sha256']))
        db.flush()
        db.get(WorkspaceRecord, workspace).current_version_id = raw['base_version_id']
        seed_evidence(db, client.app.state.settings, workspace, raw)
        db.commit()
    context = RunContext(**{key: raw[key] for key in ('workspace_id', 'session_id', 'run_token', 'base_version_id',
                          'base_version_sha256', 'source_session_revision', 'source_draft_sha256')},
                         draft=replay['session_draft'])
    return raw_bytes, raw, replay, context


def endpoint_only(raw):
    result = deepcopy(raw)
    for item in result['items']:
        if item['target_kind'] == 'material_link':
            values = item['after'].pop('role_values')
            item['after']['source_id'], item['after']['target_id'] = values[0]['object_id'], values[1]['object_id']
    return result


def mcp(client, workspace, name, **arguments):
    response = client.post(f'/api/v1/ontology/workspaces/{workspace}/mcp', headers={
        'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/call', 'Mcp-Name': name,
        'Accept': 'application/json, text/event-stream'}, json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments, '_meta': {
            'io.modelcontextprotocol/protocolVersion': '2026-07-28',
            'io.modelcontextprotocol/clientCapabilities': {}}}})
    assert response.status_code == 200, response.text
    result = response.json()['result']
    assert not result.get('isError'), result
    return result['structuredContent']


@pytest.mark.parametrize('shape', ['role_values', 'endpoints', 'stored_role_values'])
def test_real_26_proposals_accept_preview_publish_export_and_mcp(replay_client, shape):
    client = replay_client
    raw_bytes, raw, replay, context = seed_replay(client)
    root = '/api/v1/workspaces/' + context.workspace_id
    with client.app.state.session_factory() as db:
        lookup = material_lookup(db, client.app.state.settings, context.workspace_id)
        original = parse_result(raw_bytes, context, material_lookup=lookup)
        parsed = parse_result(endpoint_only(raw), context, material_lookup=lookup) if shape == 'endpoints' else original
        assert original.result_sha256 == hashlib.sha256(raw_bytes).hexdigest()
        assert len(parsed.items) == 26
        assert [i.after for i in parsed.items] == [i.after for i in original.items]
        assert [i.fingerprint for i in parsed.items] == [i.fingerprint for i in original.items]
        assert [i.depends_on for i in parsed.items] == [i.depends_on for i in original.items]
        facts = [i for i in parsed.items if i.target_kind == 'material_link']
        assert len(facts) == 6 and all(i.after['source_id'] and i.after['target_id'] for i in facts)
        if shape == 'stored_role_values':
            old_items = {i['client_ref']: i for i in replay['batch']['items']}
            for fact in facts:
                old = old_items[fact.client_ref]['after']
                assert old['id'] == fact.target_id and old['role_values'] == fact.after['role_values']
                assert old.get('source_id') is None and old.get('target_id') is None
                fact.after = deepcopy(old)  # previously stored v3 pending proposal, no reparse/migration
                fact.fingerprint = item_fingerprint(fact.operation, fact.target_kind, fact.target_id, fact.after,
                                                    hash_algorithm='ontofoundry-domain-v3')
        store_batch(db, workspace_id=context.workspace_id, session_id=context.session_id, task_id='replay',
                    manifest={**{k: raw[k] for k in raw if k != 'items'}, 'pinned_draft': context.draft}, parsed=parsed)
        db.commit()
    detail = client.get(root + f'/sessions/{context.session_id}/proposal-batches/{parsed.id}').json()
    labels = [i['display_name'] for i in detail['items'] if i['target_kind'] == 'material_link']
    assert len(labels) == 6 and all('? ' not in name and name.startswith('RT-202601-') for name in labels)
    assert any('星海贸易' in label for label in labels) and any('订单编号 1' in label for label in labels)
    response = client.post(root + f'/sessions/{context.session_id}/proposal-decisions', json={
        'idempotency_key': uuid4().hex, 'expected_session_revision': context.source_session_revision,
        'decisions': [{'proposal_id': i.id, 'decision': 'accept'} for i in parsed.items]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result['results']) == 26 and all(i['status'] == 'accepted' for i in result['results'])
    session = result['session']
    preview = client.post(root + f'/sessions/{context.session_id}/preview', json={'revision': session['revision']})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body['validation']['publishable'] and not body['validation']['errors'], body['validation']
    response = client.post(root + f'/sessions/{context.session_id}/publish', json={
        'expected_session_revision': session['revision'], 'expected_current_version_id': body['current_version_id'],
        'expected_merged_snapshot_sha256': body['merged_snapshot_sha256']})
    assert response.status_code == 200, response.text
    version = response.json()['version']
    exported = client.get(f"/api/v1/ontology/workspaces/{context.workspace_id}/versions/{version['version_id']}/export").json()
    assert validate_ossie(exported)['publishable']
    return_type = next(t for t in session['draft']['object_types'] if t['concept'] == 'sales_return')
    objects = mcp(client, context.workspace_id, 'search_objects', type_id=return_type['id'], source='document')['items']
    assert {o['name'] for o in objects} == {'RT-202601-001', 'RT-202601-002', 'RT-202601-003'}
    for obj in objects:
        assert mcp(client, context.workspace_id, 'get_object', ref=obj['ref'])['item']['name'] == obj['name']
        neighbors = mcp(client, context.workspace_id, 'expand_object_graph', ref=obj['ref'], depth=1)
        assert len(neighbors['objects']) == 3 and len(neighbors['links']) == 2
        assert {o['type_id'] for o in neighbors['objects']} == {return_type['id'], 'ca686b85-6a46-597b-8592-7e56600f4018', '2cfd13ac-fe00-549b-a7bb-2d5817c7e298'}
        assert all(f['source_name'] == obj['name'] and f['target_name'] for f in neighbors['links'])
    with client.app.state.session_factory() as db:
        assert len(list(db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.session_id == context.session_id,
                    ProposalItemRecord.status == 'accepted')))) == 26
        assert db.get(OntologyVersionRecord, context.base_version_id).snapshot_json == replay['published_snapshot']
        assert db.get(OntologyVersionRecord, version['version_id']).snapshot_json['material_links'] == session['draft']['material_links']


def binary_definition(reverse=False):
    link_id, owner, extra = [str(uuid4()) for _ in range(3)]
    return dict(id=link_id, name='关联', technical_name='related',
                owner_ref=dict(kind='object_type', ref=owner),
                roles=[dict(id=extra, concept=dict(kind='object_type', ref=owner), name='other')],
                endpoint_direction='reverse' if reverse else 'forward'), str(uuid5(UUID(link_id), 'role:owner')), extra


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('shape', ['role_values', 'endpoints', 'both'])
def test_binary_projection_is_pure_idempotent_and_directional(reverse, shape):
    definition, owner, extra = binary_definition(reverse)
    a, b = [str(uuid4()) for _ in range(2)]
    source, target = (b, a) if reverse else (a, b)
    fact = dict(id=str(uuid4()), type_id=definition['id'])
    if shape != 'endpoints':
        # Deliberately reversed array order: roles IDs determine the endpoints.
        fact['role_values'] = [dict(role_id=extra, object_id=b), dict(role_id=owner, object_id=a)]
    if shape != 'role_values':
        fact.update(source_id=source, target_id=target)
    original = deepcopy(fact)
    normalized = binary_fact_view(definition, fact)
    assert fact == original
    assert normalized['source_id'] == source and normalized['target_id'] == target
    assert binary_fact_view(definition, normalized) == normalized
    assert len(normalized['role_values']) == 2
    if shape != 'endpoints':
        assert normalized['role_values'] == fact['role_values']
    elements = {definition['id']: ('link_type', definition), a: ('material_object', {'name': '退货单'}),
                b: ('material_object', {'name': '订单'})}
    assert element_label('material_link', fact, elements) == ('订单 → 退货单' if reverse else '退货单 → 订单')


def test_binary_conflicting_endpoints_and_duplicate_role_values_are_rejected():
    definition, owner, extra = binary_definition()
    fact = dict(source_id=str(uuid4()), target_id=str(uuid4()), role_values=[
                dict(role_id=owner, object_id=str(uuid4())), dict(role_id=extra, object_id=str(uuid4()))])
    with pytest.raises(ValueError, match='不一致'):
        binary_fact_view(definition, fact)
    fact['source_id'] = fact['target_id'] = None
    fact['role_values'][1]['role_id'] = owner
    with pytest.raises(ValueError, match='不能重复'):
        binary_fact_view(definition, fact)


def test_nary_cannot_gain_binary_endpoints_and_read_projection_keeps_raw_snapshot():
    from test_p0_v3_contract import instance_draft
    draft = instance_draft()
    definition = draft['link_types'][0]
    fact = draft['material_links'][0]
    assert binary_fact_view(definition, fact) == fact
    with pytest.raises(ValueError, match='不能提供二元端点'):
        binary_fact_view(definition, {**fact, 'source_id': str(uuid4())})
    # Full snapshot validation retains strict concept and cardinality checks.
    broken = deepcopy(draft)
    broken['material_links'][0]['role_values'].pop()
    with pytest.raises(ValidationError, match='全部角色'):
        OntologyDraft.model_validate(broken)
