"""A material written in a transaction that rolls back leaves no file behind."""

from uuid import uuid4

from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.material_store import (
    discard_new_files,
    keep_new_files,
    store_text_material,
)


def path_of(client, material_sha):
    return client.app.state.settings.data_dir.resolve() / str(DEMO_WORKSPACE_ID) / (material_sha + ".md")


def test_rolled_back_material_file_is_discarded(client):
    settings = client.app.state.settings
    with client.app.state.session_factory() as db:
        material = store_text_material(db, settings, str(DEMO_WORKSPACE_ID), "表结构收据 · 虚构", f"虚构内容 {uuid4()}\n", origin="table_receipt")
        path = path_of(client, material.sha256)
        assert path.exists()  # evidence checks in the same request read it
        db.rollback()
        discard_new_files(db)
    assert not path.exists()


def test_committed_material_file_is_kept(client):
    settings = client.app.state.settings
    with client.app.state.session_factory() as db:
        material = store_text_material(db, settings, str(DEMO_WORKSPACE_ID), "虚构材料", f"虚构内容 {uuid4()}\n")
        db.commit()
        keep_new_files(db)
        path = path_of(client, material.sha256)
        # A later rollback in the same session does not touch it.
        db.rollback()
        discard_new_files(db)
    assert path.exists()
