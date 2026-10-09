"""Transient compatibility for existing DataMapping/data_join consumers in P1.

v3 remains the persisted truth. The P3 general semantic views are not enabled.
"""
import json
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid5

from ontofoundry_api.domain.models import LinkTypeDefinition, OntologyDraft
from ontofoundry_api.ossie.mappings import parse_joins, parse_mappings


def extension_data(text):
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def legacy_views(draft: OntologyDraft):
    if draft.schema_version == '2':
        return draft.mappings, draft.link_types
    from ontofoundry_api.ossie.native import compile_native
    document = compile_native(draft, '', '')
    for mapping, model in zip(document.get('ontology_mappings', []), sorted(draft.semantic_models, key=lambda m: (m.position is None, m.position or 0)), strict=True):
        for ext in model.custom_extensions:
            if ext.vendor_name == 'ONTOFOUNDRY':
                data = extension_data(ext.data)
                if isinstance(data, dict) and data.get('connection_alias'):
                    mapping['name'] = data['connection_alias']
    compat_objects = [o.model_copy(update={'technical_name': o.concept}) for o in draft.object_types]
    mappings = parse_mappings(document, compat_objects, draft.properties, str(draft.workspace_id), lambda *_: None)
    retired = {cm_id: old_id for old_id, cm_id in draft.extension_v4.legacy_mapping_ids.items()}
    for mapping in mappings:
        cm = next((c for c in draft.concept_mappings if c.concept_id.ref == mapping.type_id and c.id in retired
                   and any(m.id == c.semantic_model_id and (m.map_name == mapping.connection_alias or any(
                       ext.vendor_name == 'ONTOFOUNDRY' and extension_data(ext.data).get('connection_alias') == mapping.connection_alias
                       for ext in m.custom_extensions)) for m in draft.semantic_models)), None)
        if cm and cm.id in retired:
            mapping.id = retired[cm.id]
    links = [LinkTypeDefinition(
        id=link.id, name=link.name, technical_name=link.technical_name, description=link.description or '',
        source_type_id=link.source_type_id, target_type_id=link.target_type_id,
        multiplicity=link.legacy_multiplicity or ('one_to_one' if link.multiplicity == 'OneToOne' else 'many_to_one'),
        source_role_name=link.source_role_name, target_role_name=link.target_role_name,
        identifier=link.identifier, verbalizes=link.verbalizes, tags=link.tags, evidence=link.evidence,
    ) for link in draft.link_types if link.source_type_id is not None]
    # Model-wide join names are scoped when v2 owner-local names collide.
    # Restore them only in this transient view, never in the native document.
    for link in links:
        view = deepcopy(document)
        for mapping in view.get('ontology_mappings', []):
            legacy_id = uuid5(draft.workspace_id, f"v3:ontology_mappings/{mapping.get('name')}/relationships/{link.id}")
            scoped = {link.technical_name + '__' + link.id.hex, link.technical_name + '__' + legacy_id.hex}
            for relationship in mapping.get('semantic_model', {}).get('relationships', []):
                if relationship.get('name') in scoped:
                    relationship['name'] = link.technical_name
        parse_joins(view, compat_objects, [link], {m.type_id for m in mappings}, lambda *_: None)
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
    joins = {str(link.id): link.data_join.model_dump(mode='json') if link.data_join else None for link in links}
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
    """Keep the P1 mapping form contract while storing only frozen v3 nodes.

    This handles the existing simple legacy path; general native mapping editing
    and composite joins stay in P3. Unrelated semantic models remain unchanged.
    """
    from uuid import UUID, uuid5

    from ontofoundry_api.domain.models import DataMapping
    from ontofoundry_api.ossie.mappings import compile_mappings
    from ontofoundry_api.ossie.native import parse_native

    draft = OntologyDraft.model_validate(snapshot)
    _, binary = legacy_views(draft)
    for link in binary:
        if str(link.id) in joins:
            from ontofoundry_api.domain.models import DataJoin
            link.data_join = DataJoin.model_validate(joins[str(link.id)]) if joins[str(link.id)] else None
    legacy = SimpleNamespace(mappings=[DataMapping.model_validate(m) for m in mappings], link_types=binary,
                             effective_properties=draft.effective_properties)
    seen_types = set()
    for mapping in legacy.mappings:
        if mapping.type_id in seen_types or mapping.type_id not in draft.type_by_id():
            raise ValueError('每个已存在的业务对象只允许一个数据映射')
        seen_types.add(mapping.type_id)
        fields = {p.technical_name for p in draft.effective_properties(mapping.type_id)}
        if set(mapping.fields) - fields or '__key' in mapping.fields:
            raise ValueError('映射引用了未定义或保留的属性')
    for link in binary:
        if link.data_join and not {link.source_type_id, link.target_type_id} <= seen_types:
            raise ValueError('配置关系映射前，请先配置两端业务对象的数据映射')
    maps = compile_mappings(legacy, draft.object_types)
    for mapping in maps:
        seen = set()
        for relationship in mapping['semantic_model'].get('relationships', []):
            name = relationship['name']
            if name in seen:
                source, target = relationship['from'], relationship['to']
                link = next(link for link in binary if link.technical_name == name
                            and draft.type_by_id()[link.source_type_id].concept == source
                            and draft.type_by_id()[link.target_type_id].concept == target)
                relationship['name'] += '__' + link.id.hex
            seen.add(relationship['name'])
    mapped = {m.type_id: m for m in legacy.mappings}
    by_type = draft.type_by_id()
    for link in binary:
        if link.data_join is None or link.source_type_id not in mapped or link.target_type_id not in mapped:
            continue
        source, target = mapped[link.source_type_id], mapped[link.target_type_id]
        if source.connection_alias == target.connection_alias:
            continue
        src_name, dst_name = by_type[source.type_id].concept, by_type[target.type_id].concept
        maps.append({'name': 'legacy_join_' + link.id.hex, 'semantic_model': {
            'name': 'legacy_join_' + link.id.hex,
            'datasets': [{'name': name, 'source': (m.schema_name + '.' if m.schema_name else '') + m.table_name, 'fields': []}
                         for name, m in ((src_name, source), (dst_name, target))],
            'relationships': [{'name': link.technical_name, 'from': src_name, 'to': dst_name,
                               'from_columns': [link.data_join.source_column], 'to_columns': [link.data_join.target_column]}],
            'custom_extensions': [{'vendor_name': 'ONTOFOUNDRY', 'data': json.dumps({'legacy_connection_aliases': {
                src_name: source.connection_alias, dst_name: target.connection_alias}, 'read_only_reason': 'cross_connection'})}],
        }, 'concept_mappings': []})
    document = {'version': draft.ossie_version, 'name': 'legacy_mapping_edit', 'ontology': [
        {'concept': o.concept, 'type': 'EntityType'} for o in draft.object_types
    ] + [{'concept': v.concept, 'type': 'ValueType'} for v in draft.value_types], 'ontology_mappings': maps}
    parsed = parse_native(document, draft.workspace_id).model_dump(mode='json')
    # Namespace platform-created semantic identities independently of imported
    # positional paths; retaining a native model must never create ID collisions.
    models_by_id = {m['id']: m for m in parsed['semantic_models']}
    remap = {m['id']: str(uuid5(draft.workspace_id, 'v3:legacy-form:model:' + m['map_name'])) for m in models_by_id.values()}
    for collection in ('datasets', 'dataset_relationships', 'metrics'):
        for item in parsed[collection]:
            remap[item['id']] = str(uuid5(UUID(remap[item['semantic_model_id']]), collection + ':' + item['name']))
    for item in parsed['dataset_fields']:
        remap[item['id']] = str(uuid5(UUID(remap[item['dataset_id']]), 'field:' + item['name']))
    for item in parsed['concept_mappings']:
        remap[item['id']] = str(uuid5(UUID(remap[item['semantic_model_id']]), 'concept:' + item['concept_id']['ref']))
    nodes_by_id = {n['id']: n for n in parsed['mapping_nodes']}
    def node_id(key):
        if key in remap:
            return remap[key]
        node = nodes_by_id[key]
        parent = node_id(node['parent_id']) if node['parent_id'] else remap[node['concept_mapping_id']]
        remap[key] = str(uuid5(UUID(parent), 'node:' + node['slot'] + ':' + str(node['position'])))
        return remap[key]
    for key in nodes_by_id:
        node_id(key)
    for collection in ('semantic_models', 'datasets', 'dataset_fields', 'dataset_relationships', 'metrics', 'concept_mappings', 'mapping_nodes'):
        for item in parsed[collection]:
            for key in ('id', 'semantic_model_id', 'dataset_id', 'concept_mapping_id', 'parent_id'):
                if item.get(key) in remap:
                    item[key] = remap[item[key]]
    # The adapter owns models belonging to the legacy aliases being restated.
    aliases = {m.connection_alias for m in [*mappings_of(draft), *legacy.mappings]}
    replaced = {m.id for m in draft.semantic_models if any(
        ext.vendor_name == 'ONTOFOUNDRY' and isinstance(data := extension_data(ext.data), dict) and (data.get('connection_alias') in aliases or bool(aliases.intersection(data.get('legacy_connection_aliases', {}).values())))
        for ext in m.custom_extensions
    )}
    result = deepcopy(snapshot)
    dataset_ids = {d.id for d in draft.datasets if d.semantic_model_id in replaced}
    cm_ids = {c.id for c in draft.concept_mappings if c.semantic_model_id in replaced}
    for collection in ('semantic_models', 'datasets', 'dataset_fields', 'dataset_relationships', 'metrics', 'concept_mappings', 'mapping_nodes'):
        def keep(item, collection=collection):
            return (UUID(item['id']) not in replaced if collection == 'semantic_models'
                    else UUID(item['dataset_id']) not in dataset_ids if collection == 'dataset_fields'
                    else UUID(item['concept_mapping_id']) not in cm_ids if collection == 'mapping_nodes'
                    else UUID(item['semantic_model_id']) not in replaced)
        retained = [i for i in result[collection] if keep(i)]
        incoming = parsed[collection]
        if collection == 'semantic_models':
            for item, mapping in zip(incoming, maps, strict=True):
                if not mapping['name'].startswith('legacy_join_'):
                    item['custom_extensions'].append({'vendor_name': 'ONTOFOUNDRY', 'data': json.dumps({'connection_alias': mapping['name']}, ensure_ascii=False)})
                    if 'custom_extensions' not in item['native_presence']:
                        item['native_presence'].append('custom_extensions')
                item['position'] += max((i['position'] for i in retained if i.get('position') is not None), default=-1) + 1
        result[collection] = retained + incoming
    original_refs = {i.concept: str(i.id) for i in [*draft.object_types, *draft.value_types]}
    parsed_refs = {i['id']: original_refs[i['concept']] for c in ('object_types', 'value_types') for i in parsed[c]}
    for cm in result['concept_mappings']:
        cm['concept_id']['ref'] = parsed_refs.get(cm['concept_id']['ref'], cm['concept_id']['ref'])
    for node in result['mapping_nodes']:
        if node['concept']:
            node['concept']['ref'] = parsed_refs.get(node['concept']['ref'], node['concept']['ref'])
    for m in legacy.mappings:
        cm = next(c for c in parsed['concept_mappings'] if c['concept_id']['ref'] == str(m.type_id))
        result['extension_v4']['legacy_mapping_ids'][str(m.id)] = cm['id']
    return OntologyDraft.model_validate(result).model_dump(mode='json')


def proposal_snapshot(snapshot):
    """Native proposal targets plus the existing simple DataMapping contract."""
    if snapshot.get('schema_version') != '3':
        return snapshot
    result = deepcopy(snapshot)
    try:
        mappings, links = legacy_views(OntologyDraft.model_validate(snapshot))
        result['mappings'] = [m.model_dump(mode='json') for m in mappings]
        joins = {str(link.id): link.data_join.model_dump(mode='json') for link in links if link.data_join}
        for link in result['link_types']:
            if link['id'] in joins:
                link['data_join'] = joins[link['id']]
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
    return {'mappings': [m.model_dump(mode='json') for m in mappings],
            'joins': {str(link.id): link.data_join.model_dump(mode='json') if link.data_join else None for link in links}}


def apply_mapping_form(snapshot, mappings=None, joins=None):
    if mappings is None and joins is None:
        return snapshot
    original = legacy_mapping_form(snapshot)
    requested = {'mappings': original['mappings'] if mappings is None else mappings,
                 'joins': original['joins'] if joins is None else joins}
    if requested == original:
        return snapshot
    return apply_legacy_mappings(snapshot, requested['mappings'], requested['joins'])
