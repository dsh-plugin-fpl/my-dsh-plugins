"""Shared file boundary exercised against all independently assembled products."""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "package",
    [
        "fpl_visual",
        "fpl_video",
        "fpl_presentation",
        "fpl_thought",
        "fpl_galgame",
        "fpl_annotation",
    ],
)
def test_product_file_boundary(package, tmp_path):
    prepare = importlib.import_module(package + ".embedded").prepare
    create_app = importlib.import_module(package + ".gateway").create_app
    root = tmp_path / package
    host = prepare(root, 19360)
    app = create_app(
        root,
        port=19360,
        run_worker=False,
        embedded_core=host,
        launch_secret="project-file-isolated-test",
    )
    with TestClient(
        app,
        base_url="http://127.0.0.1:19360",
        headers={"Origin": "http://127.0.0.1:19360"},
    ) as client:
        assert client.get("/v1/app/file-projects").status_code == 401
        assert (
            client.post(
                "/__desktop/session",
                headers={"x-fpl-launch": "project-file-isolated-test"},
            ).status_code
            == 200
        )
        for path in [
            "file-projects",
            "legacy-application-files",
            "legacy-file-receipts",
        ]:
            response = client.get("/v1/app/" + path)
            assert response.status_code == 200, response.text
            assert isinstance(response.json()["items"], list)
        response = client.get(
            "/v1/app/project-files?project_id=00000000-0000-0000-0000-000000000000"
        )
        assert response.status_code == 404, response.text
