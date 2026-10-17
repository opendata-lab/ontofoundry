"""Check applicable declared source columns separately from final graph validity."""

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.errors import ServiceError


def validate_source_columns(draft):
    """Only known source/column pairs can be checked in an incomplete draft.

    Missing references and member/name constraints belong in validation reports;
    metadata not collected yet is not evidence of a missing physical column.
    No business connection or SQL is opened by this check.
    """
    datasets = {d["id"]: d for d in draft["datasets"]}
    objects = {o["id"]: o for o in draft["object_types"]}
    mappings = {m["type_id"]: m for m in draft["mappings"]}

    def columns(dataset_id, names):
        dataset = datasets.get(dataset_id)
        if dataset is None or not dataset.get("columns"):
            return
        known = {c["name"] for c in dataset["columns"]}
        if any(name not in known for name in names):
            raise ServiceError(
                "声明的来源列不存在", code="JOIN_COLUMN_NOT_FOUND", status_code=422
            )

    def join(value):
        if value and value["kind"] == "mapping_table":
            columns(value["dataset_id"], value["source_columns"] + value["target_columns"])

    for dataset in datasets.values():
        if dataset.get("snapshot_date_column"):
            columns(dataset["id"], [dataset["snapshot_date_column"]])
    for mapping in draft["mappings"]:
        sources, visited, current = {}, set(), mapping["type_id"]
        chain = []
        while current in objects and current not in visited:
            visited.add(current)
            if current in mappings:
                chain.append(mappings[current])
            current = objects[current].get("extends")
        for ancestor in reversed(chain):
            if ancestor["binding_mode"] == "independent":
                sources = {}
            sources.update({s["id"]: s for s in ancestor["sources"]})
        for source in mapping["sources"]:
            columns(source["dataset_id"], source["key_columns"])
        for field in mapping["fields"].values():
            if field["kind"] == "column" and field["source_id"] in sources:
                columns(sources[field["source_id"]]["dataset_id"], [field["column"]])
        for value in mapping.get("inherited_link_bindings", {}).values():
            join(value)
    for link in draft["link_types"]:
        join(link.get("data_join"))


def validate_join_columns(db, workspace_id, before, after, settings):
    validate_source_columns(after)
    try:
        validate_core_graph(CoreDraft.model_validate(after))
    except ValueError as exc:
        raise ServiceError(
            "定义引用校验失败：" + str(exc), code="VALIDATION_FAILED", status_code=422
        ) from exc
