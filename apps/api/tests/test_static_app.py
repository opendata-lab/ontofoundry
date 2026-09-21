from fastapi.testclient import TestClient

from ontofoundry_api.config import Settings
from ontofoundry_api.main import create_app


def test_compiled_frontend_and_api_share_an_origin_without_masking_api_errors(
    tmp_path, monkeypatch
):
    async def no_op_dataagent_lifecycle() -> None:
        return None

    monkeypatch.setattr(
        "ontofoundry_api.main.start_dataagent", no_op_dataagent_lifecycle
    )
    monkeypatch.setattr(
        "ontofoundry_api.main.stop_dataagent", no_op_dataagent_lifecycle
    )
    dist = tmp_path / "web"
    dist.mkdir()
    (dist / "index.html").write_text("<html>OntoFoundry</html>")
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        data_dir=tmp_path / "files",
        web_dist=dist,
        auto_create_schema=True,
        seed_demo=False,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/workspaces/test/view").text == "<html>OntoFoundry</html>"
        assert client.get("/healthz").json()["status"] == "ok"
        assert client.get("/api/v1/unknown").status_code == 404
        assert client.get("/assets/missing.js").status_code == 404
