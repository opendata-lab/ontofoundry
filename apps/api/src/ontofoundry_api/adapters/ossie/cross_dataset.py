"""Mechanically lift only metadata-proven many-to-one metric sources."""

from sqlglot import exp

from ontofoundry_api.domain.core import Dataset, DatasetColumn

from .ids import identifier_name
from .mappings import DatasetInfo


def lift_metric(importer, scope, ast, sources, path, metric_name):
    context = getattr(importer.t, "import_context", None)
    if not context:
        raise ValueError("缺少已登记主键、外键及连接证据")
    infos = {name: scope.datasets[name] for name in sources}
    connection_ids = {d.model.connection_id for d in infos.values()}
    if len(connection_ids) != 1 or None in connection_ids:
        raise ValueError("跨数据集连接未唯一绑定")
    if any(d.model.source_kind != "table" or d.model.snapshot_date_column for d in infos.values()):
        raise ValueError("复杂来源或快照期间无法证明等价")
    connection_id = next(iter(connection_ids))
    connection = next(c for c in context.connections if c["id"] == connection_id)
    metadata = {}
    for name, info in infos.items():
        schema = info.model.schema_name or connection["default_schema"]
        matches = [r for r in context.registered_tables if r["connection_id"] == connection_id and r["schema_name"] == schema and r["name"] == info.model.table_name]
        if len(matches) != 1:
            raise ValueError("参与表尚未登记")
        metadata[name] = matches[0]
    edges = []
    for left, right, lcols, rcols, _ in scope.relationships:
        lname, rname = left.raw["name"], right.raw["name"]
        if lname not in sources or rname not in sources:
            continue
        target = metadata[rname]
        if not target.get("primary_key") or set(target["primary_key"]) != set(rcols):
            continue
        columns = {c["name"]: c for c in metadata[lname]["columns"]}
        foreign = [
            f
            for f in metadata[lname].get("foreign_keys", [])
            if f.get("constrained_columns") == lcols
            and f.get("referred_columns") == rcols
            and f.get("referred_table") == right.model.table_name
            and (f.get("referred_schema") or metadata[lname]["schema_name"]) == metadata[rname]["schema_name"]
        ]
        if len(foreign) != 1 or any(columns.get(c, {}).get("nullable") is not False for c in lcols):
            continue
        edges.append((lname, rname, lcols, rcols))
    candidates = []
    for root in sorted(sources):
        reached, ordered = {root}, []
        while True:
            possible = [e for e in edges if e[0] in reached and e[1] not in reached]
            if not possible:
                break
            if len({e[1] for e in possible}) != len(possible):
                break
            for edge in possible:
                reached.add(edge[1])
                ordered.append(edge)
        if reached == sources and len(ordered) == len(sources) - 1:
            candidates.append((root, ordered))
    if len(candidates) != 1:
        raise ValueError("缺少唯一且完整的多对一连接路径或缺失匹配证据")
    root, ordered = candidates[0]
    aliases = {info.model.name: name for name, info in infos.items()}
    projections, output, used = {}, [], set()
    transformed = ast.copy()
    for col in transformed.find_all(exp.Column):
        original = aliases.get(col.table)
        if not original:
            raise ValueError("公式来源无法定位")
        key = (original, col.name)
        if key not in projections:
            alias = identifier_name(original + "_" + col.name, used)
            projections[key] = alias
            physical = next((c for c in metadata[original]["columns"] if c["name"] == col.name), None)
            if physical is None:
                raise ValueError("公式引用列未登记")
            output.append(DatasetColumn(name=alias, physical_type=physical.get("type"), comment=physical.get("comment") or ""))
        col.set("this", exp.to_identifier(projections[key], quoted=True))
    name = identifier_name(metric_name + "_source", {d.model.name.casefold() for d in scope.datasets.values()})
    for col in transformed.find_all(exp.Column):
        col.set("table", exp.to_identifier(name, quoted=True))
    def table(original):
        info = infos[original]
        return exp.Table(this=exp.to_identifier(info.model.table_name, quoted=True), db=exp.to_identifier(metadata[original]["schema_name"], quoted=True)).as_(info.model.name)
    query = exp.select(*[exp.column(column, table=infos[original].model.name, quoted=True).as_(alias, quoted=True) for (original, column), alias in projections.items()]).from_(table(root))
    for left, right, lcols, rcols in ordered:
        query = query.join(table(right), on=exp.and_(*[exp.column(a, table=infos[left].model.name, quoted=True).eq(exp.column(b, table=infos[right].model.name, quoted=True)) for a, b in zip(lcols, rcols, strict=True)]), join_type="INNER")
    from ontofoundry_api.services.dataset_sql import dialect_for
    model = Dataset(id=importer.t.id("metric-source:" + scope.key + ":" + metric_name), name=name, display_name="指标计算来源", source_kind="query", connection_id=connection_id, dialect=connection["kind"], query_sql=query.sql(dialect=dialect_for(connection["kind"])), columns=output, description="由已登记非空外键到完整主键机械转换，未改变原聚合算法")
    if not importer.t.accept("datasets", model, path, rule="RT-69"):
        raise ValueError("生成来源未通过核心校验")
    info = DatasetInfo({"name": name}, path, model, {}, [])
    scope.datasets[name] = info
    return transformed, model, {name}
