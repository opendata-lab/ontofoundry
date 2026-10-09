"""Published MCP aliases retain document, concept and semantic-node scopes."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_t7_mcp_elements import call

from ontofoundry_api.db_models import OntologyVersionRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.workspaces import publish_draft

FIXTURES = Path(__file__).parent / 'fixtures' / 'REDACTED_PRIVATE_PATH'
USER = '00000000-0000-0000-0000-000000000001'


@pytest.fixture(params=['client', 'pg_client'])
def synonym_client(request):
    return request.getfixturevalue(request.param)


def publish(client, stem, mutate=None):
    source = json.loads((FIXTURES / f'{stem}.ossie.json').read_text(encoding='utf-8'))
    draft, _ = import_ossie(source, workspace_id=DEMO_WORKSPACE_ID, mode='replace')
    if mutate:
        mutate(draft)
    with client.app.state.session_factory() as db:
        version = publish_draft(db, workspace_id=str(DEMO_WORKSPACE_ID), draft=OntologyDraft.model_validate(draft),
                                user_id=USER, message='P2 aliases')
    return source, draft, version.id


def candidate(result, element_id):
    return next(item for item in result['items'] if item['id'] == element_id)


def test_all_eight_real_document_synonyms_are_searchable_with_document_scope(synonym_client):
    client = synonym_client
    source, draft, version_id = publish(client, 'REDACTED')
    doc_id = 'document:' + str(DEMO_WORKSPACE_ID)
    assert len(source['ai_context']['synonyms']) == 8
    for alias in source['ai_context']['synonyms']:
        result = call(client, 'search_ontology_types', query=alias)
        document = candidate(result, doc_id)
        assert document['kind'] == 'document' and document['synonyms'] == source['ai_context']['synonyms']
        assert {'source': 'document.ai_context.synonyms', 'value': alias, 'scope_id': doc_id, 'standard': True} in document['matches']
        assert all(not item['synonyms'] for item in result['items'] if item['kind'] in ('object_type', 'value_type'))
    assert call(client, 'get_ontology_type', type_id=doc_id)['item']['synonyms'] == source['ai_context']['synonyms']
    assert call(client, 'list_ontology_elements', kind='document')['items'][0]['ai_context'] == source['ai_context']
    with client.app.state.session_factory() as db:
        assert db.get(OntologyVersionRecord, version_id).snapshot_json == draft  # pure reads


def test_real_metric_and_field_synonyms_return_complete_nodes_and_all_ambiguous_candidates(synonym_client):
    client = synonym_client
    _, draft, _ = publish(client, 'REDACTED')
    metric = next(item for item in draft['metrics'] if item['name'] == 'REDACTED')
    result = call(client, 'search_ontology_types', query='REDACTED')
    found = candidate(result, metric['id'])
    assert found['kind'] == 'metric' and found['expression'] == metric['expression']
    assert found['matches'] == [{'source': 'metric.ai_context.synonyms', 'value': 'REDACTED', 'scope_id': metric['id'], 'standard': True}]
    assert call(client, 'get_ontology_type', type_id=metric['id'])['item']['synonyms'] == metric['ai_context']['synonyms']
    listing = call(client, 'list_ontology_elements', kind='metric', limit=200)
    assert len(listing['items']) == 27 and candidate(listing, metric['id'])['ai_context'] == metric['ai_context']
    field = next(item for item in draft['dataset_fields'] if item['name'] == 'REDACTED')
    result = call(client, 'search_ontology_types', query='REDACTED')
    found = candidate(result, field['id'])
    assert found['dataset_id'] == field['dataset_id'] and found['ai_context'] == field['ai_context']
    assert any(match['source'] == 'field.ai_context.synonyms' and match['value'] == 'REDACTED' for match in found['matches'])
    ambiguous = call(client, 'search_ontology_types', query='REDACTED')
    fields = [item for item in ambiguous['items'] if item['kind'] == 'dataset_field']
    assert ambiguous['ambiguous'] and len(fields) >= 2 and len({item['dataset_id'] for item in fields}) >= 2
    fetched = call(client, 'get_ontology_elements', element_ids=[field['id'], metric['id']])
    assert fetched['missing'] == [] and {item['kind'] for item in fetched['items']} == {'dataset_field', 'metric'}
    assert all(item['element']['synonyms'] for item in fetched['items'])
    by_name = call(client, 'get_ontology_type', type_id='REDACTED')
    assert by_name['ambiguous'] and by_name['item'] is None and len(by_name['candidates']) >= 2


def test_concept_aliases_and_dataset_context_do_not_leak_across_scopes(synonym_client):
    client = synonym_client
    def mutate(draft):
        a, b = draft['object_types'][:2]
        draft['extension_v4']['concept_context'] = {
            a['id']: {'synonyms': ['共享别名', '购买者'], 'instructions': '非标准概念口径'},
            b['id']: {'synonyms': ['共享别名'], 'instructions': None},
            draft['value_types'][0]['id']: {'synonyms': ['值概念别名'], 'instructions': None},
        } if draft['value_types'] else {
            a['id']: {'synonyms': ['共享别名', '购买者'], 'instructions': '非标准概念口径'},
            b['id']: {'synonyms': ['共享别名'], 'instructions': None},
        }
        dataset = draft['datasets'][0]
        dataset['ai_context'] = {'synonyms': ['数据集别名', '数据集别名'], 'instructions': '原生数据集口径'}
        dataset['native_presence'].append('ai_context')
    _, draft, _ = publish(client, 'REDACTED', mutate)
    a, b = draft['object_types'][:2]
    result = call(client, 'search_ontology_types', query='共享别名')
    assert result['ambiguous'] and {item['id'] for item in result['items']} == {a['id'], b['id']}
    found = candidate(result, a['id'])
    assert found['concept_context']['instructions'] == '非标准概念口径' and not found['context_standard']
    assert found['matches'][0] == {'source': 'concept_context.synonyms', 'value': '共享别名', 'scope_id': a['id'], 'standard': False}
    listing = call(client, 'list_ontology_elements', kind='object_type', limit=200)
    assert candidate(listing, a['id'])['concept_context'] == draft['extension_v4']['concept_context'][a['id']]
    fetched = call(client, 'get_ontology_elements', element_ids=[a['id']])['items'][0]['element']
    assert fetched['synonyms'] == ['共享别名', '购买者']
    dataset = draft['datasets'][0]
    result = call(client, 'search_ontology_types', query='数据集别名')
    assert [item['id'] for item in result['items']] == [dataset['id']]
    assert len(result['items'][0]['matches']) == 2  # ordered repeated native aliases remain
    assert result['items'][0]['matches'][0]['source'] == 'dataset.ai_context.synonyms'
    assert candidate(call(client, 'list_ontology_elements', kind='dataset', limit=200), dataset['id'])['synonyms'] == ['数据集别名', '数据集别名']


def test_context_search_and_get_respect_existing_semantic_metadata_scopes(synonym_client):
    client = synonym_client
    source, _, _ = publish(client, 'REDACTED')
    root = '/api/v1/workspaces/' + str(DEMO_WORKSPACE_ID)
    token = client.post(root + '/service-tokens', json={'name': 'ontology-reader', 'scopes': ['ontology:read']}).json()['token']
    headers = {'Authorization': 'Bearer ' + token}
    manifest = call(client, 'get_ontology_manifest', headers=headers)
    assert 'metric' not in manifest['counts'] and manifest['counts']['document'] == 1
    result = call(client, 'search_ontology_types', headers=headers, query='REDACTED')
    assert all(item['kind'] != 'metric' for item in result['items'])
    result = call(client, 'search_ontology_types', headers=headers, query=source['ai_context']['synonyms'][0])
    assert any(item['kind'] == 'document' for item in result['items'])
    doc_id = 'document:' + str(DEMO_WORKSPACE_ID)
    assert call(client, 'get_ontology_type', headers=headers, type_id=doc_id)['item']['kind'] == 'document'


def test_value_concept_synonyms_are_searchable_without_changing_native_fields(synonym_client):
    client = synonym_client
    from test_p2_concept_context import CONTEXT, seed
    original, _ = seed(client)
    value_id = original['value_types'][0]['id']
    draft = deepcopy(original)
    draft['extension_v4']['concept_context'][value_id] = CONTEXT
    with client.app.state.session_factory() as db:
        publish_draft(db, workspace_id=str(DEMO_WORKSPACE_ID), draft=OntologyDraft.model_validate(draft), user_id=USER, message='value aliases')
    found = candidate(call(client, 'search_ontology_types', query='购买者'), value_id)
    assert found['kind'] == 'value_type' and found['extends'] == original['value_types'][0]['extends']
    assert call(client, 'list_ontology_elements', kind='value_type')['items'][0]['concept_context'] == CONTEXT
    assert call(client, 'get_ontology_type', type_id=value_id)['item']['synonyms'] == CONTEXT['synonyms']
