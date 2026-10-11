"""Public authoring projections; native semantic nodes remain the sole truth."""
from copy import deepcopy
from types import SimpleNamespace

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.role_join import authoring_join, role_join_input
from ontofoundry_api.domain.semantic_views import SemanticViews


def legacy_views(draft: OntologyDraft):
    """Authoring/query DTOs derived directly from the native semantic tree."""
    from ontofoundry_api.domain.semantic_views import SemanticViews
    from ontofoundry_api.domain.snapshot import read_snapshot
    if draft.schema_version != '3':
        draft = read_snapshot(draft.model_dump(mode='json'), draft.workspace_id, target_version='3')
    views = SemanticViews(draft)
    mappings = [a.mapping for t in draft.object_types if (a := views.analyze(t.id)).mapping]
    links = [SimpleNamespace(**{
        **link.model_dump(mode='json'), 'id': link.id, 'name': link.name,
        'source_type_id': link.source_type_id, 'target_type_id': link.target_type_id,
        'data_join': views.join(link.id),
    }) for link in draft.link_types if link.source_type_id is not None]
    return mappings, links


def mappings_of(draft):
    return legacy_views(draft)[0]


def binary_links_of(draft):
    return legacy_views(draft)[1]


def query_compat(snapshot):
    """Query/UI endpoint fields supplement full native relationship roles."""
    if snapshot.get('schema_version') != '3':
        return deepcopy(snapshot)
    draft = OntologyDraft.model_validate(snapshot)
    result = deepcopy(snapshot)
    mappings, links = legacy_views(draft)
    views = SemanticViews(draft)
    joins = {str(link.id): join.model_dump(mode='json') if (join := authoring_join(views, link.id)) else None for link in links}
    for raw, item in zip(result['object_types'], draft.object_types, strict=True):
        raw['extends'] = [str(r.ref) for r in item.extends if r.kind == 'object_type']
        raw['description'] = raw['description'] or ''
    for raw, item in zip(result['properties'], draft.properties, strict=True):
        raw['owner_type_id'] = str(item.owner_ref.ref)
        raw['target_role_name'] = item.roles[0].name
        role = item.roles[0].concept
        raw['value_concept'] = next((v.concept for v in draft.value_types if v.id == role.ref), role.ref if role.kind == 'builtin' else None)
        raw['multiplicity'] = 'one_to_one' if item.multiplicity == 'OneToOne' else 'many_to_one' if item.multiplicity else None
        raw['description'] = raw['description'] or ''
    concepts = {i.id: i for i in [*draft.object_types, *draft.value_types]}
    for raw, item in zip(result['link_types'], draft.link_types, strict=True):
        raw.update(source_type_id=str(item.source_type_id) if item.source_type_id else None,
                   target_type_id=str(item.target_type_id) if item.target_type_id else None,
                   source_role_name=item.source_role_name, target_role_name=item.target_role_name,
                   data_join=joins.get(str(item.id)), description=item.description or '',
                   multiplicity=item.legacy_multiplicity or ('one_to_one' if item.multiplicity == 'OneToOne' else 'many_to_one' if item.multiplicity else None),
                   readonly=item.source_type_id is None,
                   owner_role_id=str(item.owner_role_id), all_roles=all_roles_of(raw))
        raw['role_concepts'] = [{'id': str(item.owner_role_id), 'name': item.owner_role_name, 'concept': concepts[item.owner_ref.ref].concept, 'kind': item.owner_ref.kind}]
        raw['role_concepts'] += [{'id': str(r.id), 'name': r.name, 'concept': concepts[r.concept.ref].concept if r.concept.kind in ('object_type', 'value_type') else r.concept.ref, 'kind': r.concept.kind} for r in item.roles]
    result['mappings'] = [m.model_dump(mode='json') for m in mappings]
    return result


def apply_legacy_mappings(snapshot, mappings, joins):
    """The existing form/proposal DTO is an input, never persisted truth."""
    from ontofoundry_api.domain.semantic_edit import apply_semantic_form
    return apply_semantic_form(snapshot, mappings, joins)


def proposal_snapshot(snapshot):
    """Native proposal targets plus the existing simple DataMapping contract."""
    if snapshot.get('schema_version') != '3':
        return snapshot
    result = deepcopy(snapshot)
    try:
        mappings, _ = legacy_views(OntologyDraft.model_validate(snapshot))
        result['mappings'] = [m.model_dump(mode='json') for m in mappings]
    except ValueError:
        return snapshot
    return result


def all_roles_of(link):
    """Complete role DTO: implicit owner first, native extra roles unchanged."""
    from uuid import UUID, uuid5
    owner_id = str(uuid5(UUID(link['id']), 'role:owner'))
    return [{'id': owner_id, 'name': link.get('owner_role_name'), 'concept': deepcopy(link['owner_ref']), 'implicit_owner': True},
            *deepcopy(link['roles'])]


def legacy_mapping_form(snapshot):
    draft = OntologyDraft.model_validate(snapshot)
    mappings, links = legacy_views(draft)
    from ontofoundry_api.domain.snapshot import read_snapshot
    if draft.schema_version != '3':
        draft = read_snapshot(snapshot, target_version='3')
    views = SemanticViews(draft)
    return {'mappings': [m.model_dump(mode='json') for m in mappings],
            'joins': {str(link.id): join.model_dump(mode='json') if (join := authoring_join(views, link.id)) else None for link in links},
            'mapping_status': mapping_status(draft)}


def apply_mapping_form(snapshot, mappings=None, joins=None):
    if mappings is None and joins is None:
        return snapshot
    original = legacy_mapping_form(snapshot)
    requested = {'mappings': original['mappings'] if mappings is None else mappings,
                 'joins': original['joins'] if joins is None else {key: parsed.model_dump(mode='json') if (parsed := role_join_input(value)) else None for key, value in joins.items()}}
    if requested == {key: original[key] for key in requested}:
        return snapshot
    return apply_legacy_mappings(snapshot, requested['mappings'], requested['joins'])


def mapping_status(draft):
    from ontofoundry_api.domain.semantic_views import SemanticViews
    views = SemanticViews(draft)
    return {str(t.id): views.analyze(t.id).public(t.id) for t in draft.object_types}
