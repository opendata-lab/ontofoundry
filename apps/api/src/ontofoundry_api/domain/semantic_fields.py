"""Fields for physical columns authored by platform forms or legacy migration.

Native Ossie import never calls this module. Existing fields are immutable.
"""

from sqlalchemy.engine.default import DefaultDialect

from .semantic_views import column_reference

quote = DefaultDialect().identifier_preparer.quote


def ensure_column_field(fields, dataset_name, column, append):
    def physical(field):
        expressions = [
            e["expression"]
            for e in field["expression"]["dialects"]
            if e["dialect"] == "ANSI_SQL"
        ]
        ref = column_reference(expressions[0]) if len(expressions) == 1 else None
        return ref[1] if ref and ref[0] in (None, dataset_name) else None

    names = {f["name"] for f in fields}
    # Prefer the physical name. Reuse an alias only when that name is occupied
    # by a different native expression; never change the existing expression.
    if column in names:
        if any(f["name"] == column and physical(f) == column for f in fields):
            return column
        for field in fields:
            if physical(field) == column:
                return field["name"]
    name, suffix = column, 0
    while name in names:
        suffix += 1
        name = column + "__join" + (str(suffix) if suffix > 1 else "")
    append(
        dict(
            name=name,
            expression=dict(dialects=[dict(dialect="ANSI_SQL", expression=quote(column))]),
        )
    )
    return name


def complete_generated_fields(document):
    """Resolve physical references in a newly compiled v2 document only."""
    datasets = {d["name"]: d for d in document["semantic_model"]["datasets"]}

    def ensure(dataset, column):
        fields = dataset.setdefault("fields", [])
        return ensure_column_field(fields, dataset["name"], column, fields.append)

    for dataset in datasets.values():
        dataset["primary_key"] = [
            ensure(dataset, c) for c in dataset.get("primary_key", [])
        ]
    for rel in document["semantic_model"].get("relationships", []):
        for endpoint, key in (("from", "from_columns"), ("to", "to_columns")):
            rel[key] = [ensure(datasets[rel[endpoint]], c) for c in rel[key]]

    def visit(node):
        if isinstance(node, dict):
            ref = column_reference(node.get("expression"))
            if ref and ref[0] in datasets:
                # The legacy compiler emitted physical SQL expressions. Only
                # resolve collisions with logical names; other expressions
                # keep their original text and do not add redundant fields.
                fields = datasets[ref[0]]["fields"]
                if any(f["name"] == ref[1] for f in fields):
                    name = ensure(datasets[ref[0]], ref[1])
                    node["expression"] = quote(ref[0]) + "." + quote(name)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(document["concept_mappings"])
