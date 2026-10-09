"""Import reports count changes rather than the size of the incoming document."""
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import compile_ossie
from ontofoundry_api.ossie.importer import import_ossie

FIXTURES = Path(__file__).parent / 'fixtures' / 'ossie_real'


@pytest.mark.parametrize('stem', ['account-model-v2', 'architecture-governance'])
@pytest.mark.parametrize('mode', ['merge', 'replace'])
def test_export_reimport_reports_zero_actual_additions(stem, mode):
    original = json.loads((FIXTURES / f'{stem}.ossie.json').read_text())
    workspace = uuid4()
    base, first = import_ossie(original, workspace_id=workspace, mode='replace')
    exported = compile_ossie(OntologyDraft.model_validate(base), ontology_name='ignored', ontology_description='ignored')
    second, report = import_ossie(exported, workspace_id=workspace, base=base, mode=mode)
    assert first['counts']['mappings_added'] == len(base['concept_mappings'])
    assert report['counts']['mappings_added'] == report['counts']['mappings_updated'] == 0
    assert all(v == 0 for v in report['counts'].values()), report['counts']
    # The newly emitted ID envelope becomes native source context on reimport.
    assert second['ai_context'] == exported['ai_context']
    assert {k: v for k, v in second.items() if k != 'ai_context'} == {k: v for k, v in base.items() if k != 'ai_context'}


def test_partial_import_counts_only_one_new_concept_and_mapping_and_real_updates():
    original = json.loads((FIXTURES / 'architecture-governance.ossie.json').read_text())
    workspace = uuid4()
    base, _ = import_ossie(original, workspace_id=workspace, mode='replace')
    changed = deepcopy(original)
    changed['ontology'].append({'concept': 'NewEntity', 'type': 'EntityType'})
    changed['ontology'][0]['description'] = '新说明'
    changed['ontology_mappings'][0]['concept_mappings'].append({'concept': 'NewEntity', 'object_mappings': []})
    merged, report = import_ossie(changed, workspace_id=workspace, base=base)
    assert report['counts']['objects_added'] == report['counts']['mappings_added'] == 1
    assert report['counts']['objects_updated'] == 1
    assert report['counts']['values_added'] == report['counts']['attributes_added'] == report['counts']['links_added'] == 0
    assert len(merged['concept_mappings']) == len(base['concept_mappings']) + 1
