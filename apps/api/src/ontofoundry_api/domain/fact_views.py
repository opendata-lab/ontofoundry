"""Pure binary compatibility projection; role values remain the native facts."""
from copy import deepcopy
from uuid import UUID, uuid5


def binary_fact_view(definition: dict, fact: dict) -> dict:
    """Complete either binary representation and reject contradictory inputs.

    The role IDs, not the role_values array order, identify the owner and extra
    role. Unary, n-ary and value-ended relations have no binary endpoint view.
    """
    result = deepcopy(fact)
    roles = definition.get('roles')
    if roles is None:  # unchanged legacy v2 view
        return result
    binary = (len(roles) == 1 and definition.get('owner_ref', {}).get('kind') == 'object_type'
              and roles[0]['concept']['kind'] == 'object_type')
    source, target = result.get('source_id'), result.get('target_id')
    if not binary:
        if source is not None or target is not None:
            raise ValueError('一元或多元关系不能提供二元端点')
        return result
    owner_role = str(uuid5(UUID(str(definition['id'])), 'role:owner'))
    extra_role = str(roles[0]['id'])
    values = result.get('role_values') or []
    reverse = definition.get('endpoint_direction') == 'reverse'
    if not values:
        if source is None or target is None:
            raise ValueError('实例角色值必须覆盖全部角色且不能重复')
        owner, extra = (target, source) if reverse else (source, target)
        values = [{'role_id': owner_role, 'object_id': str(owner), 'value': None},
                  {'role_id': extra_role, 'object_id': str(extra), 'value': None}]
        result['role_values'] = values
    by_role = {str(v['role_id']): v for v in values}
    if len(values) != 2 or set(by_role) != {owner_role, extra_role}:
        raise ValueError('实例角色值必须覆盖全部角色且不能重复')
    owner, extra = by_role[owner_role].get('object_id'), by_role[extra_role].get('object_id')
    if owner is None or extra is None:
        raise ValueError('实体角色必须指定有效 object_id')
    expected_source, expected_target = (extra, owner) if reverse else (owner, extra)
    if (source is not None and str(source) != str(expected_source)
            or target is not None and str(target) != str(expected_target)):
        raise ValueError('实例二元端点与角色值不一致')
    result['source_id'], result['target_id'] = str(expected_source), str(expected_target)
    return result
