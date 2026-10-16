"""Generate or check the proposal and core JSON Schema artifacts."""

import argparse
import json
from pathlib import Path

from ontofoundry_api.contracts.export_core_schema import TARGET as CORE_TARGET
from ontofoundry_api.contracts.export_core_schema import schema_text
from ontofoundry_api.contracts.proposals import result_schema

TARGET = Path(__file__).with_name("ontofoundry.proposals.v1.schema.json")


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    export(check=parser.parse_args().check)
