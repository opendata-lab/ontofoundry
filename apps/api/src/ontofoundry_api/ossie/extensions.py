"""Reversible platform additions; source/vendor JSON stays independent in the draft."""
from copy import deepcopy


class ExtensionConflict(ValueError):
    pass


def pointer_part(value: str) -> str:
    return value.replace('~', '~0').replace('/', '~1')


def extension_of(document: dict) -> dict:
    context = document.get('ai_context')
    value = context.get('ontofoundry') if isinstance(context, dict) else None
    return value if isinstance(value, dict) else {}


def write_extension(document: dict, payload: dict, *, remove_keys=()) -> dict:
    """Overlay owned keys, retaining every overwritten value and unknown vendor key."""
    result = deepcopy(document)
    source = result.get('ai_context')
    context = deepcopy(source) if isinstance(source, dict) else {'instructions': source} if isinstance(source, str) else {}
    prior = context.get('ontofoundry')
    removed = set(remove_keys).intersection(prior) if isinstance(prior, dict) else set()
    if isinstance(prior, dict) and not removed and all(key in prior and prior[key] == value for key, value in payload.items()):
        return result  # Re-imported exports retain their existing audit byte for byte.
    combined = {**(deepcopy(prior) if isinstance(prior, dict) else {}), **deepcopy(payload)}
    for key in removed:
        combined.pop(key)
    context['ontofoundry'] = combined
    if not isinstance(source, dict):
        edits = [dict(path='/ai_context', was_present='ai_context' in result,
                      original=deepcopy(source), written=deepcopy(context))]
    elif not isinstance(prior, dict):
        edits = [dict(path='/ai_context/ontofoundry', was_present='ontofoundry' in source,
                      original=deepcopy(prior), written=deepcopy(combined))]
    elif removed:
        # Journal the container when removing a default key. This records
        # actual absence (rather than treating a missing key as JSON null),
        # retains any source audit, and detects externally reintroduced keys.
        combined.pop('export_edits', None)
        edits = [dict(path='/ai_context/ontofoundry', was_present=True,
                      original=deepcopy(prior), written=deepcopy(combined))]
    else:
        edits = [dict(path='/ai_context/ontofoundry/' + pointer_part(key), was_present=key in prior,
                      original=deepcopy(prior.get(key)), written=deepcopy(value))
                 for key, value in payload.items() if key not in prior or prior[key] != value]
    if isinstance(prior, dict) and not removed:
        # Audit itself is not self-referential: reversal temporarily removes this
        # export's audit, compares written values, then restores the source audit.
        edits.insert(0, dict(path='/ai_context/ontofoundry/export_edits', was_present='export_edits' in prior,
                             original=deepcopy(prior.get('export_edits')), written=None))
    combined['export_edits'] = edits
    result['ai_context'] = context
    return result


def _export_edits(extension: dict) -> list[dict]:
    edits = extension.get('export_edits', [])
    required = {'path', 'was_present', 'original', 'written'}
    if not isinstance(edits, list) or any(
        not isinstance(edit, dict) or not required <= edit.keys()
        or not isinstance(edit['path'], str)
        or not (edit['path'] == '/ai_context' or edit['path'].startswith('/ai_context/ontofoundry'))
        or not isinstance(edit['was_present'], bool) for edit in edits
    ):
        return []  # An opaque source/vendor audit is not ours to reverse or interpret.
    return edits


def reverse_export_edits(document: dict) -> dict:
    """Undo only this export's additions; never silently discard an external edit."""
    result = deepcopy(document)
    extension = extension_of(result)
    edits = deepcopy(_export_edits(extension))
    if not edits:
        return result
    extension.pop('export_edits')
    for edit in reversed(edits):
        parts = [part.replace('~1', '/').replace('~0', '~') for part in edit['path'].split('/')[1:]]
        parent = result
        for part in parts[:-1]:
            if not isinstance(parent, dict) or part not in parent:
                raise ExtensionConflict('EXTENSION_REVERSE_CONFLICT: ' + edit['path'])
            parent = parent[part]
        key = parts[-1]
        if not isinstance(parent, dict) or parent.get(key) != edit['written']:
            raise ExtensionConflict('EXTENSION_REVERSE_CONFLICT: ' + edit['path'])
        if edit['was_present']:
            parent[key] = deepcopy(edit['original'])
        else:
            parent.pop(key, None)
    return result


def extension_collisions(document: dict) -> list[str]:
    """Only overwrites of source values count as collisions, not newly added keys."""
    return [edit['path'] for edit in _export_edits(extension_of(document))
            if edit['was_present'] and edit['original'] != edit['written']
            and edit['path'] != '/ai_context/ontofoundry/export_edits']
