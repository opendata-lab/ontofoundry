"""Deployments run `alembic upgrade head`; two heads make it fail outright."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migrations_have_a_single_head():
    config = Config(str(Path(__file__).parents[1] / "src/ontofoundry_api/alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/ontofoundry_api/alembic")
    )
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1
