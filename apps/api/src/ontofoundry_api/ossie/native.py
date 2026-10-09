"""Ossie native nodes: one v3 truth with explicit presence and source positions."""
from copy import deepcopy
from uuid import UUID, uuid5

from ontofoundry_api.domain.models import OntologyDraft

BUILTINS = {'String', 'Integer', 'Decimal', 'Float', 'Boolean', 'Date', 'DateTime'}


def parse_native(document, workspace_id):
    workspace = UUID(str(workspace_id))
    ext = document.get('ai_context', {})
    ext = ext.get('ontofoundry', {}) if isinstance(ext, dict) else {}
    ext = ext if isinstance(ext, dict) else {}
    ids = ext.get('ids', {}) if ext.get('version') == '4' else {}
    labels = ext.get('display_names', {})
    tags = ext.get('tags', {})

    def identity(path):
        return str(ids.get(path) or uuid5(workspace, 'ossie:' + path))

    def meta(node, index):
        return dict(native_presence=sorted(node), position=index, origin='imported')

    result = dict(schema_version='3', hash_algorithm='ontofoundry-domain-v3', workspace_id=str(workspace),
                  document_origin='imported', native_presence=sorted(document),
                  ossie_version=document['version'], ontology_requires=deepcopy(document.get('requires', [])),
                  object_types=[], value_types=[], properties=[], link_types=[], rules=[],
                  semantic_models=[], datasets=[], dataset_fields=[], dataset_relationships=[], metrics=[],
                  concept_mappings=[], mapping_nodes=[])
    for field in ('name', 'description', 'ai_context'):
        if field in document:
            result[{'name': 'ossie_name', 'description': 'ossie_description'}.get(field, field)] = deepcopy(document[field])
    refs = {c['concept']: dict(kind='object_type' if c['type'] == 'EntityType' else 'value_type',
                             ref=identity('/ontology/' + c['concept'])) for c in document['ontology']}

    def ref(name):
        return deepcopy(refs.get(name) or dict(kind='any' if name == 'Any' else 'builtin', ref=name))

    def rules(node, item, path, kind):
        for key, rule_kind in (('requires', 'constraint'), ('derived_by', 'derivation')):
            item[key] = []
            for ri, expression in enumerate(node.get(key, [])):
                rid = identity(f'{path}/{key}/{ri}')
                legacy_path = path.removeprefix('/ontology/').replace('/relationships/', '.')
                kept = next((r for r in ext.get('rules', {}).get(legacy_path, []) if r.get('rule_kind') == rule_kind and r.get('expression') == expression), {})
                rid = str(kept.get('id') or rid)
                item[key].append(rid)
                result['rules'].append(dict(id=rid, owner_kind=kind, owner_id=item['id'], rule_kind=rule_kind,
                                            expression=expression, name=f'{item.get("name", "")}·{rule_kind}{ri + 1}',
                                            technical_name=f'{rule_kind}_{ri}', **meta({}, ri)))
                metadata = ext.get('rule_metadata', {}).get(rid, kept)
                for field in ('name', 'technical_name', 'description'):
                    if field in metadata:
                        result['rules'][-1][field] = metadata[field]

    for ci, node in enumerate(document['ontology']):
        name = node['concept']
        path = '/ontology/' + name
        kind = refs[name]['kind']
        item = dict(id=refs[name]['ref'], concept=name, name=labels.get(refs[name]['ref'], labels.get(name, name)),
                    technical_name=name, tags=tags.get(refs[name]['ref'], tags.get(name, [])), **meta(node, ci))
        for field in ('description', 'identify_by'):
            if field in node:
                item[field] = deepcopy(node[field])
        item['extends'] = [ref(p) for p in node.get('extends', [])]
        rules(node, item, path, kind)
        result['object_types' if kind == 'object_type' else 'value_types'].append(item)
        for li, relationship in enumerate(node.get('relationships', [])):
            lname = relationship['name']
            lpath = path + '/relationships/' + lname
            lid = identity(lpath)
            role_nodes = relationship.get('roles', [])
            is_prop = len(role_nodes) == 1 and ref(role_nodes[0]['concept'])['kind'] in ('value_type', 'builtin')
            lkind = 'property' if is_prop else 'link_type'
            link = dict(id=lid, name=labels.get(lid, labels.get(name + '.' + lname, lname)), technical_name=lname,
                        owner_ref=ref(name), identifier=lname in node.get('identify_by', []),
                        tags=tags.get(lid, tags.get(name + '.' + lname, [])), roles=[], **meta(relationship, li))
            for field in ('description', 'multiplicity', 'verbalizes'):
                if field in relationship:
                    link[field] = deepcopy(relationship[field])
            for ri, role in enumerate(role_nodes):
                link['roles'].append(dict(id=identity(f'{lpath}/roles/{ri}'), concept=ref(role['concept']),
                                          **({'name': role['name']} if 'name' in role else {}), **meta(role, ri)))
            if is_prop:
                from ontofoundry_api.ossie.importer import _resolve_value_kind
                values = {c['concept']: c for c in document['ontology'] if c['type'] == 'ValueType'}
                link['value_kind'] = _resolve_value_kind(role_nodes[0]['concept'], values)[0].value
                link['required'] = lid in ext.get('required_properties', []) or name + '.' + lname in ext.get('required_attributes', [])
            rules(relationship, link, lpath, lkind)
            result['properties' if is_prop else 'link_types'].append(link)

    def flatten(node, cm_id, path, slot, position, parent=None):
        nid = identity(path)
        item = dict(id=nid, concept_mapping_id=cm_id, parent_id=parent, slot=slot,
                    kind='link' if slot in ('link_mappings', 'children') else 'referent' if slot == 'referent_mappings' else 'object',
                    **meta(node, position))
        for field in ('relationship', 'expression'):
            if field in node:
                item[field] = node[field]
        if 'concept' in node:
            item['concept'] = ref(node['concept'])
        result['mapping_nodes'].append(item)
        for child_slot in ('object_mapping', 'children', 'referent_mappings'):
            children = [node[child_slot]] if child_slot == 'object_mapping' and child_slot in node else node.get(child_slot, [])
            for i, child in enumerate(children):
                flatten(child, cm_id, f'{path}/{child_slot}/{i}', child_slot, i, nid)

    for mi, mapping in enumerate(document.get('ontology_mappings', [])):
        path = f'/ontology_mappings/{mi}'
        mid = identity(path + '/semantic_model')
        model = mapping['semantic_model']
        result['semantic_models'].append(dict(id=mid, **{k: deepcopy(v) for k, v in model.items() if k not in ('datasets', 'relationships', 'metrics')},
                                             map_name=mapping.get('name'), map_description=mapping.get('description'),
                                             map_presence=sorted(mapping), **meta(model, mi)))
        for container, collection in (('datasets', 'datasets'), ('relationships', 'dataset_relationships'), ('metrics', 'metrics')):
            for i, node in enumerate(model.get(container, [])):
                npath = f'{path}/{container}/{i}'
                nid = identity(npath)
                result[collection].append(dict(id=nid, semantic_model_id=mid,
                                               **{k: deepcopy(v) for k, v in node.items() if k != 'fields'}, **meta(node, i)))
                if container == 'datasets':
                    for fi, field in enumerate(node.get('fields', [])):
                        result['dataset_fields'].append(dict(id=identity(f'{npath}/fields/{fi}'), dataset_id=nid, **deepcopy(field), **meta(field, fi)))
        for i, cm in enumerate(mapping.get('concept_mappings', [])):
            cpath = f'{path}/concept_mappings/{i}'
            cid = identity(cpath)
            result['concept_mappings'].append(dict(id=cid, semantic_model_id=mid, concept_id=ref(cm['concept']), **meta(cm, i)))
            for slot in ('object_mappings', 'link_mappings'):
                for ni, node in enumerate(cm.get(slot, [])):
                    flatten(node, cid, f'{cpath}/{slot}/{ni}', slot, ni)
    if ext.get('version') == '4':
        result['extension_v4'] = {'version': '4', 'legacy_mapping_ids': deepcopy(ext.get('legacy_mapping_ids', {}))}
        result['actions'] = deepcopy(ext.get('actions', []))
        for rid, metadata in ext.get('rule_metadata', {}).items():
            if metadata.get('owner_kind') == 'action':
                result['rules'].append(dict(id=rid, **deepcopy(metadata)))
    elif ext.get('actions'):
        from ontofoundry_api.ossie.importer import Report, _parse_actions
        report = Report()
        for collection in ('object_types', 'properties', 'link_types'):
            for item in result[collection]:
                if collection == 'object_types':
                    report.paths[item['id']] = item['concept']
                else:
                    owner = next(c['concept'] for group in ('object_types', 'value_types') for c in result[group] if c['id'] == item['owner_ref']['ref'])
                    report.paths[item['id']] = owner + '.' + item['technical_name']
        result['actions'], action_rules = _parse_actions(result, ext, report)
        result['rules'].extend(action_rules)
    return OntologyDraft.model_validate(result)


def compile_native(draft, ontology_name, ontology_description):
    concepts = {i.id: i for i in [*draft.object_types, *draft.value_types]}
    rules = {r.id: r for r in draft.rules}

    def ref(r):
        return concepts[r.ref].concept if r.kind in ('object_type', 'value_type') else r.ref

    def ordered(items):
        return sorted(items, key=lambda i: (i.position is None, i.position if i.position is not None else 0,
                                             i.technical_name if hasattr(i, 'technical_name') else str(i.id)))

    def native(item, fields):
        return {key: deepcopy(getattr(item, key)) for key in fields
                if key in item.native_presence or (item.origin == 'platform' and getattr(item, key) not in (None, [], ''))}

    def attach(item, node):
        for key in ('requires', 'derived_by'):
            entries = getattr(item, key)
            if key in item.native_presence or entries:
                node[key] = [rules[r].expression for r in entries]

    components = []
    for item in ordered(concepts.values()):
        node = dict(concept=item.concept, type='EntityType' if item in draft.object_types else 'ValueType')
        node.update(native(item, ('description', 'identify_by')))
        if 'extends' in item.native_presence or item.extends:
            node['extends'] = [ref(r) for r in item.extends]
        attach(item, node)
        relationships = []
        for link in ordered([rel for rel in [*draft.properties, *draft.link_types] if rel.owner_ref.ref == item.id]):
            rel = dict(name=link.technical_name or link.name)
            rel.update(native(link, ('description', 'multiplicity', 'verbalizes')))
            if 'roles' in link.native_presence or link.roles or link.origin == 'platform':
                rel['roles'] = [dict(concept=ref(r.concept), **native(r, ('name',))) for r in link.roles]
            if link.origin == 'platform':
                if 'verbalizes' not in link.native_presence and not link.verbalizes:
                    rel['verbalizes'] = ['{' + item.concept + '}' + link.name + ''.join('{' + r['concept'] + (':' + r['name'] if r.get('name') else '') + '}' for r in rel['roles'])]
                if 'multiplicity' not in link.native_presence and link.multiplicity is None and link in draft.properties:
                    identifiers = [p for p in draft.properties if p.owner_ref.ref == item.id and p.identifier]
                    rel['multiplicity'] = 'OneToOne' if link.identifier and len(identifiers) == 1 else 'ManyToOne'
            attach(link, rel)
            relationships.append(rel)
        if 'relationships' in item.native_presence or relationships:
            node['relationships'] = relationships
        components.append(node)
    document = dict(version=draft.ossie_version, ontology=components)
    for key, value in (('name', draft.ossie_name), ('description', draft.ossie_description), ('ai_context', draft.ai_context), ('requires', draft.ontology_requires)):
        if key in draft.native_presence or value not in (None, [], ''):
            document[key] = deepcopy(value)
    if draft.document_origin == 'migrated':
        document.setdefault('name', 'migrated_' + draft.workspace_id.hex)
    if draft.document_origin == 'platform':
        document.setdefault('name', ontology_name)
        document.setdefault('description', ontology_description)

    def semantic(item, fields):
        data = item.model_dump(mode='json', by_alias=True)
        return {f: data[f] for f in fields if f in item.native_presence or (item.origin == 'platform' and data.get(f) not in (None, [], ''))}

    nodes = draft.mapping_nodes
    def tree(item):
        node = semantic(item, ('relationship', 'expression'))
        if 'concept' in item.native_presence or item.concept:
            node['concept'] = ref(item.concept)
        for slot in ('object_mapping', 'children', 'referent_mappings'):
            children = ordered([n for n in nodes if n.parent_id == item.id and n.slot == slot])
            if slot in item.native_presence or children:
                node[slot] = tree(children[0]) if slot == 'object_mapping' else [tree(c) for c in children]
        return node
    maps = []
    for model in ordered(draft.semantic_models):
        sm = semantic(model, ('name', 'description', 'ai_context', 'custom_extensions'))
        for key, group, fields in (
            ('datasets', draft.datasets, ('name', 'source', 'description', 'ai_context', 'custom_extensions', 'primary_key', 'unique_keys')),
            ('relationships', draft.dataset_relationships, ('name', 'from', 'to', 'from_columns', 'to_columns', 'ai_context', 'custom_extensions')),
            ('metrics', draft.metrics, ('name', 'expression', 'description', 'datatype', 'ai_context', 'custom_extensions')),
        ):
            items = ordered([i for i in group if i.semantic_model_id == model.id])
            values = []
            for item in items:
                value = semantic(item, fields)
                if key == 'datasets':
                    fields_ = ordered([f for f in draft.dataset_fields if f.dataset_id == item.id])
                    if 'fields' in item.native_presence or fields_:
                        value['fields'] = [semantic(f, ('name', 'expression', 'description', 'datatype', 'dimension', 'label', 'ai_context', 'custom_extensions')) for f in fields_]
                values.append(value)
            if key in model.native_presence or items:
                sm[key] = values
        mapping = {'semantic_model': sm}
        for key in ('name', 'description'):
            if key in model.map_presence:
                mapping[key] = getattr(model, 'map_' + key)
        cms = ordered([c for c in draft.concept_mappings if c.semantic_model_id == model.id])
        if 'concept_mappings' in model.map_presence or cms:
            mapping['concept_mappings'] = []
            for cm in cms:
                value = {'concept': ref(cm.concept_id)}
                for slot in ('object_mappings', 'link_mappings'):
                    roots = ordered([n for n in nodes if n.concept_mapping_id == cm.id and n.parent_id is None and n.slot == slot])
                    if slot in cm.native_presence or roots:
                        value[slot] = [tree(n) for n in roots]
                mapping['concept_mappings'].append(value)
        maps.append(mapping)
    if 'ontology_mappings' in draft.native_presence or maps:
        document['ontology_mappings'] = maps
    prior_extension = draft.ai_context.get('ontofoundry') if isinstance(draft.ai_context, dict) else None
    source_labels = prior_extension.get('display_names', {}) if isinstance(prior_extension, dict) else {}
    source_tags = prior_extension.get('tags', {}) if isinstance(prior_extension, dict) else {}
    def source_path(item):
        return item.concept if hasattr(item, 'concept') else concepts[item.owner_ref.ref].concept + '.' + item.technical_name
    platform_metadata = any(i.origin == 'platform' or i.name != source_labels.get(str(i.id), source_labels.get(source_path(i), i.concept if hasattr(i, 'concept') else i.technical_name))
                            or i.tags != source_tags.get(str(i.id), source_tags.get(source_path(i), []))
                            for i in [*concepts.values(), *draft.properties, *draft.link_types])
    source_required = prior_extension.get('required_properties', []) if isinstance(prior_extension, dict) else []
    legacy_required = prior_extension.get('required_attributes', []) if isinstance(prior_extension, dict) else []
    platform_metadata = platform_metadata or bool(draft.extension_v4.legacy_mapping_ids) or any(
        p.required != (str(p.id) in source_required or source_path(p) in legacy_required) for p in draft.properties)
    if draft.document_origin != 'imported' or platform_metadata or (isinstance(prior_extension, dict) and prior_extension.get('version') == '4'):
        registry = {}
        for item in concepts.values():
            path = '/ontology/' + item.concept
            registry[path] = str(item.id)
            for field in ('requires', 'derived_by'):
                for index, rid in enumerate(getattr(item, field)):
                    registry[f'{path}/{field}/{index}'] = str(rid)
        for item in [*draft.properties, *draft.link_types]:
            path = '/ontology/' + concepts[item.owner_ref.ref].concept + '/relationships/' + item.technical_name
            registry[path] = str(item.id)
            registry[path + '/owner'] = str(item.owner_role_id)
            for index, role in enumerate(item.roles):
                registry[f'{path}/roles/{index}'] = str(role.id)
            for field in ('requires', 'derived_by'):
                for index, rid in enumerate(getattr(item, field)):
                    registry[f'{path}/{field}/{index}'] = str(rid)
        def register_tree(node, path):
            registry[path] = str(node.id)
            for slot in ('object_mapping', 'children', 'referent_mappings'):
                children = ordered([n for n in draft.mapping_nodes if n.parent_id == node.id and n.slot == slot])
                for index, child in enumerate(children):
                    register_tree(child, path + '/' + slot + ('' if slot == 'object_mapping' else '/' + str(index)))
        for mi, model in enumerate(ordered(draft.semantic_models)):
            path = f'/ontology_mappings/{mi}'
            registry[path + '/semantic_model'] = str(model.id)
            for container, group in (('datasets', draft.datasets), ('relationships', draft.dataset_relationships), ('metrics', draft.metrics)):
                for index, item in enumerate(ordered([i for i in group if i.semantic_model_id == model.id])):
                    ipath = f'{path}/{container}/{index}'
                    registry[ipath] = str(item.id)
                    if container == 'datasets':
                        for fi, field in enumerate(ordered([f for f in draft.dataset_fields if f.dataset_id == item.id])):
                            registry[f'{ipath}/fields/{fi}'] = str(field.id)
            for ci, cm in enumerate(ordered([c for c in draft.concept_mappings if c.semantic_model_id == model.id])):
                cpath = f'{path}/concept_mappings/{ci}'
                registry[cpath] = str(cm.id)
                for slot in ('object_mappings', 'link_mappings'):
                    roots = ordered([n for n in draft.mapping_nodes if n.concept_mapping_id == cm.id and n.parent_id is None and n.slot == slot])
                    for ni, root in enumerate(roots):
                        register_tree(root, f'{cpath}/{slot}/{ni}')
        extension = dict(version='4', ids=registry,
                         display_names={str(i.id): i.name for i in [*concepts.values(), *draft.properties, *draft.link_types]},
                         tags={str(i.id): i.tags for i in [*concepts.values(), *draft.properties, *draft.link_types] if i.tags},
                         required_properties=[str(i.id) for i in draft.properties if i.required],
                         rule_metadata={str(r.id): ({f: getattr(r, f) for f in ('name', 'technical_name', 'description')} if r.owner_kind != 'action' else {k: v for k, v in r.model_dump(mode='json').items() if k != 'id'}) for r in draft.rules},
                         actions=[a.model_dump(mode='json') for a in draft.actions],
                         legacy_mapping_ids={str(old): str(new) for old, new in draft.extension_v4.legacy_mapping_ids.items()})
        context = deepcopy(document.get('ai_context'))
        if not isinstance(context, dict):
            context = {'instructions': context} if isinstance(context, str) else {}
        prior = context.get('ontofoundry')
        if isinstance(prior, dict) and all(prior.get(k) == v for k, v in extension.items()):
            return document  # importing an export preserves the audit bytes
        combined = {**(prior if isinstance(prior, dict) else {}), **extension}
        context['ontofoundry'] = combined
        if 'ai_context' not in document or not isinstance(document.get('ai_context'), dict):
            edits = [dict(path='/ai_context', was_present='ai_context' in document,
                          original=deepcopy(document.get('ai_context')), written=deepcopy(context))]
        elif not isinstance(prior, dict):
            edits = [dict(path='/ai_context/ontofoundry', was_present='ontofoundry' in document['ai_context'],
                          original=deepcopy(prior), written=deepcopy(combined))]
        else:
            edits = [dict(path='/ai_context/ontofoundry/' + key, was_present=key in prior,
                          original=deepcopy(prior.get(key)), written=deepcopy(value))
                     for key, value in extension.items() if prior.get(key) != value or key not in prior]
        if isinstance(prior, dict) and 'export_edits' in prior:
            # The input audit is vendor input too; keep it in the reversible record.
            edits.append(dict(path='/ai_context/ontofoundry/export_edits', was_present=True,
                              original=deepcopy(prior['export_edits']), written=None))
        combined['export_edits'] = edits
        document['ai_context'] = context
    return document
