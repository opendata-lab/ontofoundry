"""Derive extraction contracts from the platform schema, without importing apps."""

import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PLATFORM = BASE.parents[1] / "apps/api/src/ontofoundry_api"
FUNCTIONS_FILE = BASE / "shared/scripts/platform_functions.json"
SOURCE = BASE.parents[1] / "apps/api/src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json"
TARGETS = {
    "ontology-discovery": {"object_type", "property", "value_type", "link_type", "dataset", "mapping", "metric", "rule"},
    "entity-extraction": {"material_object", "material_link"},
}


def references(value):
    if isinstance(value, dict):
        ref = value.get("$ref")
        if ref:
            if not ref.startswith("#/$defs/"):
                raise ValueError(f"Unsupported schema reference: {ref}")
            yield ref.removeprefix("#/$defs/")
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def project_schema(source, targets):
    """Restrict item discriminants and retain precisely their reachable definitions."""
    schema = deepcopy(source)
    definitions = schema.pop("$defs")
    item = definitions["item"]
    known = set(item["properties"]["target_kind"]["enum"])
    if not targets <= known:
        raise ValueError(f"Unknown target kinds: {targets - known}")
    item["properties"]["target_kind"]["enum"] = [kind for kind in item["properties"]["target_kind"]["enum"] if kind in targets]
    item["oneOf"] = [branch for branch in item["oneOf"] if branch["properties"]["target_kind"]["const"] in targets]
    kept, pending = {}, set(references(schema))
    while pending:
        name = min(pending)
        pending.remove(name)
        if name in kept:
            continue
        kept[name] = definitions[name]
        pending.update(set(references(kept[name])) - kept.keys())
    schema["$defs"] = dict(sorted(kept.items()))
    return schema


def platform_constant(path, name):
    """A literal set assigned in a platform module, read without importing it."""
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            value = node.value
            if isinstance(value, ast.Call):  # frozenset({...})
                value = value.args[0]
            return set(ast.literal_eval(value))
    raise ValueError(f"{name} not found in {path}")


def call_node(sqlglot, name, dialect):
    """The node a call to name parses into, trying common arities; None if it never parses."""
    for args in ("x", "x, x", "x, x, x", ""):
        try:
            return sqlglot.parse_one(f"SELECT {name}({args}) FROM t", read=dialect).expressions[0]
        except Exception:  # noqa: S112 - sqlglot raises several unrelated types per arity
            continue
    return None


def function_lists(platform=PLATFORM):
    """Function names the platform rejects, so check_part can say so before submitting.

    Rules, derivations and field expressions allow SCALAR_FUNCTIONS by name
    (domain/expressions.py, default dialect). Query SQL allows sqlglot node classes
    in QUERY_NODES (services/dataset_sql.py, connection dialect); a name is listed
    only when MySQL and PostgreSQL both reject it, so no dialect gets a false error.
    """
    import sqlglot
    from sqlglot import exp
    from sqlglot.dialects.dialect import Dialect

    scalar = platform_constant(platform / "domain/expressions.py", "SCALAR_FUNCTIONS")
    query_nodes = platform_constant(platform / "services/dataset_sql.py", "QUERY_NODES")
    names = sorted({n for d in ("", "mysql", "postgres") for n in Dialect.get_or_raise(d).parser_class.FUNCTIONS if n.isidentifier()})

    def scalar_rejects(node):
        if node is None or not isinstance(node, exp.Func) or isinstance(node, (exp.Binary, exp.Unary)):
            return False
        return (node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name()) not in scalar

    def query_rejects(node):
        return node is not None and any(type(n).__name__ not in query_nodes for n in node.walk())

    return {
        "expression": [n for n in names if scalar_rejects(call_node(sqlglot, n, ""))],
        "query_sql": [n for n in names if all(query_rejects(call_node(sqlglot, n, d)) for d in ("mysql", "postgres"))],
    }


def generate(source=SOURCE, output_dir=BASE / "skills", platform=PLATFORM, functions_file=FUNCTIONS_FILE):
    source_schema = json.loads(Path(source).read_bytes())
    lists = function_lists(platform)
    Path(functions_file).write_text(json.dumps({"generated_by": "generate_output_schemas.py; do not edit", **lists}, indent=0) + "\n")
    # Standalone packages use the exact same readable lines as stored receipts.
    formatter = BASE.parents[1] / "apps/api/src/ontofoundry_api/domain/table_reading.py"
    (BASE / "shared/scripts/table_format.py").write_text("# Generated by generate_output_schemas.py; do not edit.\n" + formatter.read_text())
    for name, targets in TARGETS.items():
        destination = Path(output_dir) / name / "output-schema.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(project_schema(source_schema, targets), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description="从平台提案契约生成两个抽取技能的输出 Schema")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output-dir", type=Path, default=BASE / "skills")
    args = parser.parse_args()
    generate(args.source, args.output_dir)


if __name__ == "__main__":
    main()
