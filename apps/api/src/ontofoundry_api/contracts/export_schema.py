"""Write the generated `ontofoundry.proposals/v1` JSON Schema next to this file.

    uv run python -m ontofoundry_api.contracts.export_schema

A test fails when the checked-in file and the models disagree.
"""

import json
from pathlib import Path

from ontofoundry_api.contracts.proposals import result_schema

TARGET = Path(__file__).with_name("ontofoundry.proposals.v1.schema.json")

if __name__ == "__main__":
    TARGET.write_text(
        json.dumps(result_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(TARGET)
