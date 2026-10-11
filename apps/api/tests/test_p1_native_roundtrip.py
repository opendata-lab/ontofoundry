"""P1 native nodes: real relationship arrays and exact presence/order/text."""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from ontofoundry_api.db_models import OntologyVersionRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.extensions import reverse_export_edits
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.workspaces import publish_draft

FIXTURES = Path(__file__).parent / 'fixtures' / 'ossie_real'


@pytest.mark.parametrize(('stem', 'count'), [('account-model-v2', 6), ('architecture-governance', 8)])
def test_real_nary_import_persist_publish_export(client, stem, count):
    original = json.loads((FIXTURES / f'{stem}.ossie.json').read_text())
    payload, report = import_ossie(original, workspace_id=DEMO_WORKSPACE_ID, mode='replace', target_version='3')
    assert not report['skipped']
    draft = OntologyDraft.model_validate(payload)
    assert len([r for r in draft.link_types if len(r.roles) >= 2]) == count
    assert all(r.source_type_id is None and r.target_type_id is None for r in draft.link_types if len(r.roles) >= 2)
    with client.app.state.session_factory() as db:
        version = publish_draft(db, workspace_id=str(DEMO_WORKSPACE_ID), draft=draft,
                                user_id='00000000-0000-0000-0000-000000000001', message='P1 原生往返')
        stored = db.get(OntologyVersionRecord, version.id)
        assert stored.snapshot_json == payload
        exported = compile_ossie(OntologyDraft.model_validate(stored.snapshot_json), ontology_name='ignored', ontology_description='ignored')
        assert stored.ossie_json == exported
    nary_original = [(c['concept'], r) for c in original['ontology'] for r in c.get('relationships', []) if len(r.get('roles', [])) >= 2]
    nary_export = [(c['concept'], r) for c in exported['ontology'] for r in c.get('relationships', []) if len(r.get('roles', [])) >= 2]
    assert len(nary_export) == count
    assert nary_export == nary_original  # objects only ignore key order; all arrays exact
    assert reverse_export_edits(exported) == original
    assert validate_ossie(exported)['publishable']
    second, _ = import_ossie(exported, workspace_id=DEMO_WORKSPACE_ID, mode='replace', target_version='3')
    assert second['object_types'] == payload['object_types']
    assert second['mapping_nodes'] == payload['mapping_nodes']
    assert compile_ossie(OntologyDraft.model_validate(second), ontology_name='ignored', ontology_description='ignored') == exported


def document():
    return {'version': '0.2.0.dev0', 'name': '', 'description': '', 'requires': [], 'ontology': [
        {'concept': 'Number', 'type': 'ValueType', 'extends': ['Integer'], 'description': '', 'identify_by': [],
         'requires': ['  ' + 'x' * 600 + '  ', '  ' + 'x' * 600 + '  '], 'derived_by': [],
         'relationships': [{'name': 'positive', 'verbalizes': ['{Number} is positive']}]},
        {'concept': 'Thing', 'type': 'EntityType', 'extends': ['Any'], 'relationships': [
            {'name': 'flag', 'roles': [], 'verbalizes': []},
            {'name': 'facts', 'roles': [{'concept': 'Any', 'name': ''}, {'concept': 'Number'}, {'concept': 'Date', 'name': 'day'}],
             'description': '', 'verbalizes': ['{Thing} with {Any} at {Date:day} has {Number}'], 'requires': [], 'derived_by': []},
            {'name': 'amount', 'roles': [{'concept': 'Number'}], 'verbalizes': []},
        ]},
    ]}


def test_value_unary_any_builtin_presence_order_long_expressions():
    original = document()
    before = deepcopy(original)
    payload, _ = import_ossie(original, workspace_id=str(uuid4()), mode='replace', target_version='3')
    assert original == before
    draft = OntologyDraft.model_validate(payload)
    assert len(draft.value_types) == 1
    assert len(draft.rules) == 2 and draft.rules[0].id != draft.rules[1].id
    assert draft.value_types[0].requires == [r.id for r in draft.rules]
    result = compile_ossie(draft, ontology_name='ignored', ontology_description='ignored')
    assert reverse_export_edits(result) == original
    next(r for r in draft.link_types if r.technical_name == 'facts').description = 'changed'
    edited = compile_ossie(draft, ontology_name='ignored', ontology_description='ignored')
    expected = deepcopy(original)
    expected['ontology'][1]['relationships'][1]['description'] = 'changed'
    assert reverse_export_edits(edited) == expected


def test_value_only_document_and_missing_containers():
    original = {'version': '0.2.0.dev0', 'name': 'value_only', 'ontology': [{'concept': 'Score', 'type': 'ValueType', 'extends': ['Float']}]}
    payload, _ = import_ossie(original, workspace_id=str(uuid4()), mode='replace', target_version='3')
    assert reverse_export_edits(compile_ossie(OntologyDraft.model_validate(payload), ontology_name='ignored', ontology_description='ignored')) == original
