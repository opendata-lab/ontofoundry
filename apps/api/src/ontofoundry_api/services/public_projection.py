"""Public read views, independent of the native snapshot/editing contract."""
from copy import deepcopy

# These fields describe storage/preservation, never business structure. Keep
# role order in the array itself; clients do not need persistence positions.
INTERNAL_FIELDS = frozenset({
    'native_presence', 'position', 'origin', 'map_presence',
    'concept_mappings_position', 'document_origin', 'core_presence',
    'extension_v4', 'client_ref',
})
# Open native/user JSON is data, not a serialized model. In particular a user
# may legitimately have a property named "origin" in instance values.
OPAQUE_FIELDS = frozenset({'ai_context', 'custom_extensions', 'values', 'value', 'data'})


def public_projection(value):
    """Copy a response recursively, including nested attributes and roles."""
    if isinstance(value, list):
        return [public_projection(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in INTERNAL_FIELDS:
                continue
            if key == 'ai_context' and isinstance(item, dict):
                # The platform registry/reversal journal is an export concern.
                # Public aliases/instructions are projected separately, while
                # native context and other vendor fields remain opaque data.
                result[key] = deepcopy({k: v for k, v in item.items() if k != 'ontofoundry'})
            else:
                result[key] = deepcopy(item) if key in OPAQUE_FIELDS else public_projection(item)
        return result
    return deepcopy(value)
