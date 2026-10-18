"""Generate or check core, proposal and interface read JSON Schema artifacts."""

import argparse
import json
from pathlib import Path

from ontofoundry_api.contracts.export_core_schema import TARGET as CORE_TARGET
from ontofoundry_api.contracts.export_core_schema import schema_text
from ontofoundry_api.contracts.exports import exports_schema
from ontofoundry_api.contracts.imports import imports_schema
from ontofoundry_api.contracts.proposals import result_schema
from ontofoundry_api.contracts.read_models import read_models_schema

TARGET = Path(__file__).with_name("ontofoundry.proposals.v1.schema.json")
READ_TARGET = Path(__file__).with_name("ontofoundry.api-read.v1.schema.json")


def export(*, check=False):
    payload = (
        json.dumps(result_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if check:
        if not TARGET.exists() or TARGET.read_text() != payload:
            raise SystemExit("提案 schema 与模型不一致，请重新生成")
    else:
        TARGET.write_text(payload)
    if check:
        if CORE_TARGET.read_text() != schema_text():
            raise SystemExit("core schema 与模型不一致")
    else:
        CORE_TARGET.write_text(schema_text())
    export_target = Path(__file__).with_name("ontofoundry.exports.v1.schema.json")
    export_payload = (
        json.dumps(exports_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if check:
        if not export_target.exists() or export_target.read_text() != export_payload:
            raise SystemExit("导出接口 schema 与模型不一致，请重新生成")
    else:
        export_target.write_text(export_payload)
    import_target = Path(__file__).with_name("ontofoundry.imports.v1.schema.json")
    import_payload = (
        json.dumps(imports_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if check:
        if not import_target.exists() or import_target.read_text() != import_payload:
            raise SystemExit("导入接口 schema 与模型不一致，请重新生成")
    else:
        import_target.write_text(import_payload)
    read_payload = (
        json.dumps(read_models_schema(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    if check:
        if not READ_TARGET.exists() or READ_TARGET.read_text() != read_payload:
            raise SystemExit("接口读模型 schema 与模型不一致，请重新生成")
    else:
        READ_TARGET.write_text(read_payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    export(check=parser.parse_args().check)
