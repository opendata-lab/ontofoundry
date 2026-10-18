"""Validate against the per-run schema and explicit create references."""
import argparse
import json
from pathlib import Path
from jsonschema import Draft202012Validator


def check_result(result, schema, context=None):
    errors = [f"{list(e.path)}: {e.message}" for e in Draft202012Validator(schema).iter_errors(result)]
    items = result.get("items", [])
    refs = [i.get("client_ref") for i in items if i.get("client_ref")]
    if len(refs)!=len(set(refs)):
        errors.append("client_ref 重复")
    creates = {i["client_ref"] for i in items if i.get("operation")=="create" and i.get("client_ref")}
    def walk(value):
        if isinstance(value,dict):
            if set(value)=={"client_ref"} and value["client_ref"] not in creates:
                errors.append("client_ref 引用未闭合："+str(value["client_ref"]))
            for key,entry in value.items():
                if key not in {"values","quote"}:
                    walk(entry)
        elif isinstance(value,list):
            for entry in value:
                walk(entry)
    for item in items:
        if item.get("operation")=="create" and not item.get("client_ref"):
            errors.append("create 缺少 client_ref")
        walk(item.get("after"))
        for ref in item.get("depends_on",[]):
            if ref not in refs:
                errors.append("depends_on 引用未闭合："+ref)
    if context:
        run=context.get("run",context)
        for key in ("run_token","base_version_id","source_session_revision"):
            if key in run and result.get(key)!=run[key]:
                errors.append("固定上下文不一致："+key)
    return errors


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--schema",required=True)
    parser.add_argument("--context")
    parser.add_argument("result")
    args=parser.parse_args()
    read=lambda path:json.loads(Path(path).read_text())
    errors=check_result(read(args.result),read(args.schema),read(args.context) if args.context else None)
    print("\n".join(errors) if errors else "提案格式及引用检查通过")
    return int(bool(errors))


if __name__=="__main__":
    raise SystemExit(main())
