"""Read-only scoped context; never turn document aliases into concept aliases."""
from copy import deepcopy

CONTEXT_COLLECTIONS = {'semantic_model': 'semantic_models', 'dataset': 'datasets',
                       'dataset_field': 'dataset_fields', 'metric': 'metrics'}


def synonyms(context) -> list[str]:
    values = context.get('synonyms', []) if isinstance(context, dict) else []
    return [value for value in values if isinstance(value, str)] if isinstance(values, list) else []


def _sources(values, source, scope_id, standard=True):
    return [dict(source=source, value=value, scope_id=scope_id, standard=standard) for value in values]


def concept_context(item: dict, snapshot: dict) -> dict:
    context = snapshot.get('extension_v4', {}).get('concept_context', {}).get(item['id'])
    values = synonyms(context)
    return {**deepcopy(item), 'concept_context': deepcopy(context), 'synonyms': values,
            'synonym_sources': _sources(values, 'concept_context.synonyms', item['id'], standard=False),
            'context_standard': False}


def semantic_context(item: dict, kind: str) -> dict:
    values = synonyms(item.get('ai_context'))
    scope = 'field' if kind == 'dataset_field' else kind
    return {**deepcopy(item), 'kind': kind, 'technical_name': item.get('name', ''), 'synonyms': values,
            'synonym_sources': _sources(values, scope + '.ai_context.synonyms', item['id']), 'context_standard': True}


def document_context(snapshot: dict) -> dict:
    values = synonyms(snapshot.get('ai_context'))
    document_id = 'document:' + snapshot['workspace_id']
    return dict(id=document_id, kind='document', name=snapshot.get('ossie_name') or '',
                technical_name=snapshot.get('ossie_name') or '', description=snapshot.get('ossie_description') or '',
                ai_context=deepcopy(snapshot.get('ai_context')), synonyms=values,
                synonym_sources=_sources(values, 'document.ai_context.synonyms', document_id), context_standard=True)


def context_elements(snapshot: dict) -> dict[str, list[dict]]:
    return {kind: [semantic_context(item, kind) for item in snapshot.get(collection, [])]
            for kind, collection in CONTEXT_COLLECTIONS.items()}


def matches(item: dict, query: str) -> list[dict]:
    result = [deepcopy(source) for source in item.get('synonym_sources', []) if query in source['value'].casefold()]
    for field in ('name', 'technical_name', 'description', 'tags', 'verbalizes', 'role_concepts'):
        value = item.get(field)
        if field == 'role_concepts':
            texts = [(role.get('name') or '') + ' ' + role['concept'] for role in value or []]
        else:
            texts = value if isinstance(value, list) else [value] if isinstance(value, str) else []
        result.extend(dict(source='element.' + field, value=text, scope_id=item['id'], standard=True)
                      for text in texts if isinstance(text, str) and query in text.casefold())
    return result
