"""Generate or check core, proposal and interface read JSON Schema artifacts."""

import argparse
import json
from pathlib import Path

from ontofoundry_api.contracts.connections import ConnectionInUseResponse
from ontofoundry_api.contracts.proposal_checks import ProposalCheckResponse
from ontofoundry_api.contracts.export_core_schema import TARGET as CORE_TARGET
from ontofoundry_api.contracts.export_core_schema import schema_text
from ontofoundry_api.contracts.exports import exports_schema
from ontofoundry_api.contracts.imports import imports_schema
from ontofoundry_api.contracts.instances import instances_schema
from ontofoundry_api.contracts.materials import MaterialOverview
from ontofoundry_api.contracts.proposals import result_schema
from ontofoundry_api.contracts.read_models import read_models_schema

TARGET = Path(__file__).with_name("ontofoundry.proposals.v1.schema.json")
READ_TARGET = Path(__file__).with_name("ontofoundry.api-read.v1.schema.json")
MATERIAL_TARGET = Path(__file__).with_name("ontofoundry.materials.v1.schema.json")


def export(*, check=False):
    instance_target = Path(__file__).with_name("ontofoundry.instances.v1.schema.json")
    instance_payload = json.dumps(instances_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if check:
        if not instance_target.exists() or instance_target.read_text() != instance_payload:
            raise SystemExit("实例 schema 与模型不一致，请重新生成")
    else:
        instance_target.write_text(instance_payload)
    connection_target = Path(__file__).with_name("ontofoundry.connections.v1.schema.json")
    connection_payload = json.dumps(
        ConnectionInUseResponse.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if check:
        if not connection_target.exists() or connection_target.read_text() != connection_payload:
            raise SystemExit("连接接口 schema 与模型不一致，请重新生成")
    else:
        connection_target.write_text(connection_payload)
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
    for model, name in ((ProposalCheckResponse, "proposal-check"),):
        target = Path(__file__).with_name(f"ontofoundry.{name}.v1.schema.json")
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **model.model_json_schema()}
        payload = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
        if check:
            if not target.exists() or target.read_text() != payload:
                raise SystemExit(f"{name} schema 与模型不一致，请重新生成")
        else:
            target.write_text(payload)
    material_schema = MaterialOverview.model_json_schema(mode="serialization")
    material_schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    material_schema["$id"] = MATERIAL_TARGET.name
    material_payload = json.dumps(
        material_schema, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if check:
        if not MATERIAL_TARGET.exists() or MATERIAL_TARGET.read_text() != material_payload:
            raise SystemExit("材料接口 schema 与模型不一致，请重新生成")
    else:
        MATERIAL_TARGET.write_text(material_payload)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    export(check=parser.parse_args().check)
