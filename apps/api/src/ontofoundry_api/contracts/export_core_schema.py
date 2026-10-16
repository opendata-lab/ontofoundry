"""Generate the core-1 Draft 2020-12 schema, or check for drift without writes."""

import argparse
import json
from pathlib import Path

from ontofoundry_api.domain.core import CoreDraft

TARGET = Path(__file__).with_name("ontofoundry.core-1.schema.json")


def core_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **CoreDraft.model_json_schema(mode="validation"),
    }


def schema_text() -> str:
    return json.dumps(core_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = schema_text()
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            parser.exit(1, "core-1 schema 已漂移，请重新生成\n")
        print("core-1 schema 与模型一致")
    else:
        TARGET.write_text(content, encoding="utf-8")
        print(TARGET)


if __name__ == "__main__":
    main()
