"""Put the skill scripts and the offline budget on sys.path for every test."""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
for path in (BASE / "scripts", BASE / "shared/scripts", BASE / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
