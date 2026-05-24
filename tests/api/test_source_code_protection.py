from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.security_middleware import SourceCodeProtectionMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SourceCodeProtectionMiddleware)

    @app.get("/{path:path}")
    def catch_all(path: str):
        return {"path": path}

    return TestClient(app)


def test_source_code_protection_blocks_direct_source_paths() -> None:
    client = _client()

    response = client.get("/src/core/config.py")

    assert response.status_code == 403
    assert response.headers.get("x-source-protection") == "blocked"


def test_source_code_protection_blocks_encoded_dotenv_probe() -> None:
    client = _client()

    response = client.get("/%2eenv")

    assert response.status_code == 403
    assert response.headers.get("x-source-protection") == "blocked"


def test_source_code_protection_blocks_file_browser_query_probe() -> None:
    client = _client()

    response = client.get("/files/view?path=src/core/security.py")

    assert response.status_code == 403
    assert response.headers.get("x-source-protection") == "blocked"


def test_source_code_protection_blocks_file_browser_dotenv_query_probe() -> None:
    client = _client()

    response = client.get("/files/view?path=.env")

    assert response.status_code == 403
    assert response.headers.get("x-source-protection") == "blocked"


def test_source_code_protection_allows_normal_web_assets() -> None:
    client = _client()

    response = client.get("/web/service-shell.js")

    assert response.status_code == 200
    assert response.json() == {"path": "web/service-shell.js"}
