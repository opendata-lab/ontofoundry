"""M4: exceptional identity registration and clean public read contracts."""
from copy import deepcopy
from uuid import UUID, uuid4, uuid5

import pytest
from test_p2_extensions import export, identities
from test_p2_mcp_synonyms import publish
from test_t7_mcp_elements import call

from ontofoundry_api.db_models import OntologyVersionRecord
from ontofoundry_api.ossie.extensions import reverse_export_edits
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.public_projection import public_projection

FORBIDDEN = {'native_presence', 'position', 'origin', 'map_presence', 'client_ref',
             'extension_v4', 'concept_mappings_position', 'document_origin', 'core_presence'}

SOURCE = {'version': '0.2.0.dev0', 'name': 'model', 'ontology': [
    {'concept': 'Thing', 'type': 'EntityType', 'requires': ['true'], 'relationships': [
        {'name': 'related', 'roles': [{'concept': 'Other'}, {'concept': 'Third'}], 'verbalizes': []},
    ]},
    {'concept': 'Other', 'type': 'EntityType'},
    {'concept': 'Third', 'type': 'EntityType'},
]}


def clean(value):
    if isinstance(value, dict):
        assert not FORBIDDEN.intersection(value), value.keys()
        for key, item in value.items():
            if key not in ('ai_context', 'custom_extensions', 'values', 'value', 'data'):
                clean(item)
    elif isinstance(value, list):
        for item in value:
            clean(item)


def test_create_rename_move_reorder_register_only_exceptions_and_keep_all_identities():
    workspace = uuid4()
    draft, _ = import_ossie(SOURCE, workspace_id=workspace, mode='replace')
    draft['object_types'][0].update(concept='Renamed~/Thing', technical_name='Renamed~/Thing')
    created = str(uuid4())
    draft['object_types'].append(dict(id=created, concept='Created', technical_name='Created', name='Created'))
    relation = draft['link_types'][0]
    relation['owner_ref']['ref'] = draft['object_types'][1]['id']  # move into Other
    relation['roles'].reverse()
    for index, role in enumerate(relation['roles']):
        role['position'] = index
    # Nonstandard data must survive minimization, including rule name overrides.
    draft['object_types'][0]['name'] = '中文名'
    draft['rules'][0].update(name='业务约束', technical_name='business_constraint', description='平台说明')
    draft['extension_v4']['concept_context'][created] = {'synonyms': ['新建别名'], 'instructions': None}
    emitted = export(draft)
    extension = emitted['ai_context']['ontofoundry']
    registry = extension['ids']
    assert registry['/ontology/Created'] == created
    assert registry['/ontology/Renamed~0~1Thing'] == draft['object_types'][0]['id']
    assert '/ontology/Other' not in registry and '/ontology/Third' not in registry
    assert not any(path.endswith('/owner') for path in registry)
    assert all(UUID(value) != uuid5(workspace, 'ossie:' + path) for path, value in registry.items())
    assert extension['display_names'] == {draft['object_types'][0]['id']: '中文名'}
    assert 'tags' not in extension and 'actions' not in extension and 'required_properties' not in extension
    for destination in (workspace, uuid4()):
        restored, _ = import_ossie(emitted, workspace_id=destination, mode='replace')
        assert identities(restored) == identities(draft)
        assert restored['extension_v4']['concept_context'] == draft['extension_v4']['concept_context']
        assert restored['rules'][0]['name'] == '业务约束'
        assert export(restored) == emitted


def test_legacy_full_registry_is_readable_and_source_is_reversibly_preserved():
    fixed = str(uuid4())
    source = {'version': '0.2.0.dev0', 'name': 'model', 'ontology': [{'concept': 'Thing', 'type': 'EntityType'}],
              'ai_context': {'ontofoundry': {'version': '4', 'ids': {'/ontology/Thing': fixed},
                                            'display_names': {fixed: 'Thing'}, 'tags': {}}}}
    draft, _ = import_ossie(source, workspace_id=uuid4(), mode='replace')
    assert draft['object_types'][0]['id'] == fixed
    emitted = export(draft)
    assert reverse_export_edits(emitted) == source
    assert 'display_names' not in emitted['ai_context']['ontofoundry']
    assert 'tags' not in emitted['ai_context']['ontofoundry']
    restored, _ = import_ossie(emitted, workspace_id=uuid4(), mode='replace')
    assert restored['object_types'][0]['id'] == fixed
    assert export(restored) == emitted


def test_omitting_source_defaults_is_reversible_and_reintroduced_keys_conflict():
    from ontofoundry_api.ossie.extensions import ExtensionConflict
    source = {'version': '0.2.0.dev0', 'name': 'model', 'ontology': [{'concept': 'Thing', 'type': 'EntityType'}],
              'ai_context': {'ontofoundry': {'version': '4', 'ids': {}, 'tags': {}, 'actions': [],
                                            'concept_context': {}, 'export_edits': ['source audit'], 'vendor': [None, 1]}}}
    draft, _ = import_ossie(source, workspace_id=uuid4(), mode='replace')
    emitted = export(draft)
    extension = emitted['ai_context']['ontofoundry']
    assert not {'ids', 'tags', 'actions', 'concept_context'}.intersection(extension)
    assert extension['vendor'] == [None, 1]
    assert reverse_export_edits(emitted) == source
    extension['tags'] = None  # missing versus null matters in reversal as well
    with pytest.raises(ExtensionConflict, match='EXTENSION_REVERSE_CONFLICT'):
        reverse_export_edits(emitted)


def test_new_relationship_without_technical_name_registers_its_exported_path():
    workspace = uuid4()
    draft, _ = import_ossie(SOURCE, workspace_id=workspace, mode='replace')
    relation_id, role_id = str(uuid4()), str(uuid4())
    draft['link_types'].append(dict(id=relation_id, name='new_relationship',
                                    owner_ref={'kind': 'object_type', 'ref': draft['object_types'][0]['id']},
                                    roles=[{'id': role_id, 'concept': {'kind': 'object_type', 'ref': draft['object_types'][1]['id']}}]))
    emitted = export(draft)
    registry = emitted['ai_context']['ontofoundry']['ids']
    assert registry['/ontology/Thing/relationships/new_relationship'] == relation_id
    assert registry['/ontology/Thing/relationships/new_relationship/roles/0'] == role_id
    restored, _ = import_ossie(emitted, workspace_id=workspace, mode='replace')
    relation = next(item for item in restored['link_types'] if item['id'] == relation_id)
    assert relation['roles'][0]['id'] == role_id
    assert export(restored) == emitted


@pytest.mark.parametrize('backend', ['client', 'pg_client'])
def test_mcp_and_rest_project_nested_elements_and_leave_snapshot_intact(request, backend):
    client = request.getfixturevalue(backend)
    _, draft, version_id = publish(client, 'REDACTED')
    original = deepcopy(draft)
    result = call(client, 'search_ontology_types', query='REDACTED')
    clean(result)
    metric = next(item for item in result['items'] if item['name'] == 'REDACTED')
    assert metric['matches'][0]['source'] == 'metric.ai_context.synonyms'
    assert metric['expression'] == next(item['expression'] for item in draft['metrics'] if item['id'] == metric['id'])
    clean(call(client, 'get_ontology_type', type_id=metric['id']))
    clean(call(client, 'get_ontology_type', type_id='REDACTED'))  # ambiguity candidates
    clean(call(client, 'get_ontology_elements', element_ids=[metric['id'], draft['link_types'][0]['id']]))
    for kind in ('metric', 'object_type', 'value_type', 'property', 'link_type', 'dataset_field'):
        listing = call(client, 'list_ontology_elements', kind=kind, limit=200)
        clean(listing)
        assert all(item['kind'] == kind for item in listing['items'])
    link = draft['link_types'][0]
    found = call(client, 'get_ontology_type', type_id=link['id'])['item']
    assert [role['id'] for role in found['roles']] == [role['id'] for role in link['roles']]
    clean(call(client, 'get_ontology_graph'))
    root = '/api/v1/ontology/workspaces/' + str(DEMO_WORKSPACE_ID)
    for route in ('/types', '/types/' + link['id'], '/type-graph/neighborhood'):
        response = client.get(root + route)
        assert response.status_code == 200, response.text
        clean(response.json())
    response = client.get(root + '/types', params={'q': 'REDACTED', 'kind': 'metric'})
    assert response.status_code == 200
    clean(response.json())
    assert response.json()['items'][0]['id'] == metric['id']
    response = client.get(root + '/types/' + metric['id'])
    assert response.status_code == 200
    clean(response.json())
    assert response.json()['item']['synonyms'] == metric['synonyms']
    token = client.post('/api/v1/workspaces/' + str(DEMO_WORKSPACE_ID) + '/service-tokens',
                        json={'name': 'M4 ontology reader', 'scopes': ['ontology:read']}).json()['token']
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get(root + '/types', params={'q': 'REDACTED', 'kind': 'metric'}, headers=headers).json()['items'] == []
    assert client.get(root + '/types/' + metric['id'], headers=headers).status_code == 404
    with client.app.state.session_factory() as db:
        assert db.get(OntologyVersionRecord, version_id).snapshot_json == original


def test_projection_does_not_remove_user_fields_or_mutate_input():
    source = {'id': 'id', 'origin': 'imported', 'native_presence': [], 'position': 1,
              'roles': [{'id': 'role', 'origin': 'imported', 'position': 0}],
              'values': {'origin': '用户属性', 'position': 2},
              'ai_context': {'vendor': {'origin': '原文'}, 'ontofoundry': {'ids': {'path': 'internal'}}}}
    original = deepcopy(source)
    projected = public_projection(source)
    assert projected['roles'] == [{'id': 'role'}]
    assert projected['values'] == source['values']
    assert projected['ai_context'] == {'vendor': {'origin': '原文'}}
    projected['values']['origin'] = '修改投影'
    assert source == original
