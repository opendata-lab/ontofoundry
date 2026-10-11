"""An optional Ossie role name never comes from a platform display label."""
from copy import deepcopy
from uuid import uuid4

import pytest
from test_modeling import ONTOLOGY, ROOT, create_session, publish
from test_t4_proposal_decisions import create, decide, seed_batch, update

from ontofoundry_api.domain.models import LinkTypeDefinition, OntologyDraft
from ontofoundry_api.domain.snapshot import as_v3_dict
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import build_demo_draft


@pytest.fixture(params=['client', 'pg_client'])
def role_client(request):
    return request.getfixturevalue(request.param)


def return_proposals(shape, named=False, wrong=False):
    items = [create(key, 'object_type', {'name': label, 'technical_name': key})
             for key, label in [('return_order', '退货单'), ('customer', '客户'), ('order', '订单')]]
    for concept, description in [('customer', '由客户发起'), ('order', '针对订单')]:
        placeholder = concept + (':initiator' if named and not wrong else '')
        after = dict(name=description, technical_name='for_' + concept,
                     verbalizes=['{return_order}退货单' + description + '{' + placeholder + '}'])
        if shape == 'endpoints':
            after.update(source_type_id={'client_ref': 'return_order'}, target_type_id={'client_ref': concept})
            if named:
                after['target_role_name'] = 'initiator'
        else:
            role = {'concept': {'kind': 'object_type', 'ref': {'client_ref': concept}}}
            if named:
                role['name'] = 'initiator'
            after.update(owner_ref={'kind': 'object_type', 'ref': {'client_ref': 'return_order'}}, roles=[role])
        items.append(dict(client_ref='for_' + concept, operation='create', target_kind='link_type',
                          before=None, after=after))
    return items


@pytest.mark.parametrize('shape', ['endpoints', 'native'])
@pytest.mark.parametrize('named', [False, True])
def test_binary_proposals_accept_preview_publish_export_optional_names(role_client, shape, named):
    client = role_client
    session = create_session(client)
    proposals = return_proposals(shape, named)
    original = deepcopy(proposals)
    batch = seed_batch(client, session, proposals)
    assert proposals == original  # projection does not rewrite the delivered input
    response = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert response.status_code == 200, response.text
    session = response.json()['session']
    links = [r for r in session['draft']['link_types'] if r['technical_name'] in ('for_customer', 'for_order')]
    assert len(links) == 2
    assert all(r['roles'][0]['name'] == ('initiator' if named else None) for r in links)
    preview = client.post(ROOT + f"/sessions/{session['id']}/preview", json={'revision': session['revision']})
    assert preview.status_code == 200, preview.text
    assert preview.json()['validation']['publishable'], preview.text
    response = publish(client, session)
    assert response.status_code == 200, response.text
    exported = client.get(ONTOLOGY + f"/versions/{response.json()['version']['version_id']}/export").json()
    owner = next(c for c in exported['ontology'] if c['concept'] == 'return_order')
    assert len(owner['relationships']) == 2
    for relationship in owner['relationships']:
        role = relationship['roles'][0]
        assert role == {'concept': relationship['name'].removeprefix('for_'), **({'name': 'initiator'} if named else {})}
        assert relationship['verbalizes'] == next(i['after']['verbalizes'] for i in original if i['after'].get('technical_name') == relationship['name'])
    # Chinese display names belong to the platform extension, never roles[].name.
    assert '客户' in exported['ai_context']['ontofoundry']['display_names'].values()
    reloaded, _ = import_ossie(exported, workspace_id=session['workspace_id'], mode='replace')
    assert all(r['roles'][0]['name'] == ('initiator' if named else None)
               for r in reloaded['link_types'] if r['technical_name'] in ('for_customer', 'for_order'))


@pytest.mark.parametrize('shape', ['endpoints', 'native'])
def test_explicit_role_name_still_requires_named_verbalization_placeholder(client, shape):
    session = create_session(client)
    batch = seed_batch(client, session, return_proposals(shape, named=True, wrong=True))
    response = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert response.status_code == 200, response.text
    session = response.json()['session']
    preview = client.post(ROOT + f"/sessions/{session['id']}/preview", json={'revision': session['revision']}).json()
    assert not preview['validation']['publishable']
    assert any(i['code'] == 'UNKNOWN_VERBALIZATION_ROLE' for i in preview['validation']['errors'])
    assert publish(client, session).status_code == 422


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('named', [False, True])
def test_v2_read_and_edit_projection_never_infers_self_role_names(reverse, named):
    legacy = build_demo_draft()
    owner = legacy.object_types[0]
    link = LinkTypeDefinition(id=uuid4(), name='关联显示名', technical_name='self_related',
                              source_type_id=owner.id, target_type_id=owner.id,
                              multiplicity='one_to_many' if reverse else 'many_to_many',
                              source_role_name='related' if reverse and named else None,
                              target_role_name='related' if not reverse and named else None,
                              verbalizes=['{' + owner.technical_name + '}关联{' + owner.technical_name + (':related' if named else '') + '}'])
    legacy.link_types.append(link)
    source = legacy.model_dump(mode='json')
    before = deepcopy(source)
    migrated = as_v3_dict(source)
    assert source == before
    native = next(r for r in migrated['link_types'] if r['id'] == str(link.id))
    assert native['roles'][0]['name'] == ('related' if named else None)
    assert ('name' in native['roles'][0]['native_presence']) == named
    exported = compile_ossie(OntologyDraft.model_validate(migrated), ontology_name='demo', ontology_description='demo')
    relationship = next(r for c in exported['ontology'] for r in c.get('relationships', []) if r['name'] == 'self_related')
    assert ('name' in relationship['roles'][0]) == named
    issues = validate_ossie(exported)['errors']
    assert any(i['code'] == 'AMBIGUOUS_ROLE_NAME' for i in issues) == (not named)


def test_binary_element_save_keeps_unnamed_role_and_concept_placeholder(client):
    session = create_session(client)
    batch = seed_batch(client, session, return_proposals('endpoints'))
    response = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert response.status_code == 200, response.text
    session = response.json()['session']
    assert publish(client, session).status_code == 200
    session = create_session(client)
    draft = deepcopy(session['draft'])
    link = next(r for r in draft['link_types'] if r['technical_name'] == 'for_customer')
    link['description'] = '元素编辑'
    saved = client.post(ROOT + '/element-saves', json=dict(
        target_kind='link_type', target_id=link['id'], draft=draft, session_id=session['id'],
        expected_session_revision=session['revision'], expected_current_version_id=session['base_version_id']))
    assert saved.status_code == 200, saved.text
    result = saved.json()
    current = next(r for r in result['session']['draft']['link_types'] if r['id'] == link['id'])
    assert current['roles'][0]['name'] is None
    exported = client.get(ONTOLOGY + f"/versions/{result['version']['version_id']}/export").json()
    relationship = next(r for c in exported['ontology'] for r in c.get('relationships', []) if r['name'] == 'for_customer')
    assert relationship['roles'] == [{'concept': 'customer'}]
    assert relationship['verbalizes'] == ['{return_order}退货单由客户发起{customer}']


def test_proposal_can_clear_explicit_role_name_without_exporting_null(client):
    session = create_session(client)
    batch = seed_batch(client, session, return_proposals('native', named=True))
    response = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert response.status_code == 200, response.text
    session = response.json()['session']
    link = next(r for r in session['draft']['link_types'] if r['technical_name'] == 'for_customer')
    roles = deepcopy(link['roles'])
    roles[0]['name'] = None
    item = update('link_type', link, roles=roles, verbalizes=['{return_order}退货单由客户发起{customer}'])
    batch = seed_batch(client, session, [item])
    response = decide(client, session, [(i['id'], 'accept') for i in batch['items']])
    assert response.status_code == 200, response.text
    session = response.json()['session']
    preview = client.post(ROOT + f"/sessions/{session['id']}/preview", json={'revision': session['revision']}).json()
    assert preview['validation']['publishable'], preview
    relationship = next(r for c in preview['ossie']['ontology'] for r in c.get('relationships', []) if r['name'] == 'for_customer')
    assert relationship['roles'] == [{'concept': 'customer'}]
    assert publish(client, session).status_code == 200
