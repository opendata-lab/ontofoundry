"""Permission-safe read projections; never feed these back into whole-draft saves."""

from copy import deepcopy


def public_projection(value):
    return deepcopy(value)


def authorized_snapshot(snapshot, *, mappings, instances):
    result = deepcopy(snapshot)
    if not mappings:
        result.update(datasets=[], mappings=[], metrics=[])
        for link in result["link_types"]:
            link.pop("data_join", None)
    if not instances:
        result.update(material_objects=[], material_links=[])
        for collection in ("object_types", "properties", "link_types", "rules", "metrics"):
            for item in result[collection]:
                item["evidence"] = []
    return result
