"""P2 export additions are reversible; native JSON and identities are stable."""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import canonical_json, compile_ossie, validate_ossie
from ontofoundry_api.ossie.extensions import (
    ExtensionConflict,
    extension_collisions,
    reverse_export_edits,
)
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.ossie.validator import validate_schema

FIXTURES = Path(__file__).parent / 'fixtures' / 'ossie_real'


def export(payload):
    return compile_ossie(OntologyDraft.model_validate(payload), ontology_name='workspace', ontology_description='workspace')


def identities(payload):
    result = {key: [item['id'] for item in payload[key]] for key in (
        'object_types', 'value_types', 'properties', 'link_types', 'rules', 'semantic_models',
        'datasets', 'dataset_fields', 'dataset_relationships', 'metrics', 'concept_mappings', 'mapping_nodes')}
    result['roles'] = [role['id'] for key in ('properties', 'link_types') for item in payload[key] for role in item['roles']]
    return result


@pytest.mark.parametrize('stem', ['account-model-v2', 'architecture-governance'])
def test_real_registry_cross_workspace_reimport_and_zero_native_differences(stem):
    source = json.loads((FIXTURES / f'{stem}.ossie.json').read_text(encoding='utf-8'))
    first, _ = import_ossie(source, workspace_id=uuid4(), mode='replace')
    emitted = export(first)
    assert emitted['ai_context']['synonyms'] == source['ai_context']['synonyms']
    assert emitted['name'] == source['name'] and emitted['description'] == source['description']
    assert emitted['ai_context']['ontofoundry']['version'] == '4'
    assert validate_ossie(emitted)['publishable']
    assert reverse_export_edits(emitted) == source
    assert validate_schema(emitted) == []
    second, _ = import_ossie(emitted, workspace_id=uuid4(), mode='replace')
    assert identities(second) == identities(first)  # registry, not destination uuid5
    assert canonical_json(export(second)) == canonical_json(emitted)
    extension = emitted['ai_context']['ontofoundry']
    assert extension.get('ids', {}) == {}  # all identities are derivable
    assert len(json.dumps(extension, ensure_ascii=False, indent=2).encode('utf-8')) <= 2048
    same_space, _ = import_ossie(emitted, workspace_id=first['workspace_id'], mode='replace')
    assert identities(same_space) == identities(first)
    for relation, restored in zip(OntologyDraft.model_validate(first).link_types, OntologyDraft.model_validate(second).link_types, strict=True):
        assert relation.owner_role_id == restored.owner_role_id
    assert source == reverse_export_edits(export(first))


CONTEXTS = [None, '', '原始 instruction\n不改写', {'synonyms': ['b', 'b', 'a'], 'other': {'tags': [None, 'x']}},
            {'ontofoundry': 'opaque source'}, {'ontofoundry': ['old', None]},
            {'ontofoundry': {'version': 'other-vendor', 'ids': {'x': 'opaque'}, 'concept_context': {'x': [None]}, 'export_edits': ['source audit'], 'custom': {'null': None}}},
            {'ontofoundry': {'version': '3', 'display_names': {'Thing': '事物'}, 'export_edits': [], 'custom': [1, 1]}}]


@pytest.mark.parametrize('context', CONTEXTS)
def test_source_context_collision_string_or_missing_is_reversible(context):
    source = {'version': '0.2.0.dev0', 'name': '', 'ontology': [{'concept': 'Thing', 'type': 'EntityType'}]}
    if context is not None:
        source['ai_context'] = deepcopy(context)
    unchanged = deepcopy(source)
    first, _ = import_ossie(source, workspace_id=uuid4(), mode='replace')
    assert first['ai_context'] == source.get('ai_context')
    emitted = export(first)
    assert reverse_export_edits(emitted) == source
    assert source == unchanged
    assert validate_schema(emitted) == []
    second, _ = import_ossie(emitted, workspace_id=uuid4(), mode='replace')
    assert export(second) == emitted
    if isinstance(context, dict) and context.get('ontofoundry'):
        assert extension_collisions(emitted)
    if isinstance(context, dict) and isinstance(context.get('ontofoundry'), dict):
        assert emitted['ai_context']['ontofoundry']['custom'] == context['ontofoundry']['custom']


def test_reverse_reports_changed_owned_key_and_preserves_input():
    source = {'version': '0.2.0.dev0', 'name': 'model', 'ontology': [{'concept': 'Thing', 'type': 'EntityType'}]}
    first, _ = import_ossie(source, workspace_id=uuid4(), mode='replace')
    emitted = export(first)
    emitted['ai_context']['ontofoundry']['version'] = 'external edit'
    unchanged = deepcopy(emitted)
    with pytest.raises(ExtensionConflict, match='EXTENSION_REVERSE_CONFLICT'):
        reverse_export_edits(emitted)
    assert emitted == unchanged


def test_native_names_with_pointer_characters_and_concept_context_ids_restore():
    source = {'version': '0.2.0.dev0', 'name': 'model', 'ontology': [{'concept': 'A~/B', 'type': 'EntityType'}]}
    first, _ = import_ossie(source, workspace_id=uuid4(), mode='replace')
    concept_id = first['object_types'][0]['id']
    first['extension_v4']['concept_context'][concept_id] = {'synonyms': ['事物', '事物'], 'instructions': '平台说明'}
    emitted = export(first)
    assert emitted['ai_context']['ontofoundry'].get('ids', {}) == {}
    second, _ = import_ossie(emitted, workspace_id=uuid4(), mode='replace')
    assert second['extension_v4']['concept_context'] == first['extension_v4']['concept_context']
    assert export(second) == emitted
    assert reverse_export_edits(emitted) == source


def test_opaque_source_audit_is_not_interpreted_as_platform_edits():
    source = {'version': '0.2.0.dev0', 'name': 'model', 'ontology': [{'concept': 'Thing', 'type': 'EntityType'}],
              'ai_context': {'ontofoundry': {'version': 'foreign', 'export_edits': ['opaque', None]}}}
    assert validate_ossie(source)['publishable']
    assert extension_collisions(source) == []
    assert reverse_export_edits(source) == source
    payload, _ = import_ossie(source, workspace_id=uuid4(), mode='replace')
    assert reverse_export_edits(export(payload)) == source


def test_platform_action_rule_ids_restore_but_new_extension_carries_no_evidence():
    from test_t1_v2_model import action_draft

    from ontofoundry_api.domain.snapshot import as_v3_dict
    payload = as_v3_dict(action_draft().model_dump(mode='json'))
    evidence = {'kind': 'manual', 'id': str(uuid4()), 'note': '不导出的人工证据', 'created_by': 'actor', 'created_at': '2026-10-09T00:00:00Z'}
    payload['actions'][0]['evidence'] = [evidence]
    rule = next(rule for rule in payload['rules'] if rule['owner_kind'] == 'action')
    rule['evidence'] = [evidence]
    emitted = export(payload)
    extension = emitted['ai_context']['ontofoundry']
    assert all('evidence' not in action for action in extension['actions'])
    assert all('evidence' not in metadata for metadata in extension['rule_metadata'].values())
    assert rule['id'] in extension['rule_metadata']
    assert extension['actions'][0]['id'] == payload['actions'][0]['id']
    assert rule['id'] not in extension.get('ids', {}).values()  # already in the action payload
    restored, _ = import_ossie(emitted, workspace_id=uuid4(), mode='replace')
    assert [item['id'] for item in restored['actions']] == [item['id'] for item in payload['actions']]
    assert rule['id'] in {item['id'] for item in restored['rules']}
    assert export(restored) == emitted
