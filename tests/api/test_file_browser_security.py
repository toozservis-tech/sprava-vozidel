"""
Security regression tests for file browser sensitive path blocking.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.server.file_browser import router as file_browser_router


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(file_browser_router)
    return TestClient(app)


def _assert_blocked(response, path: str, endpoint: str) -> None:
    assert response.status_code in {401, 403, 404}, (
        f"{endpoint} allowed sensitive path '{path}' "
        f"(status={response.status_code}, body={response.text})"
    )


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.backup",
        ".git/config",
        "node_modules",
        "__pycache__",
        "src/.git/config",
    ],
)
def test_file_browser_view_blocks_sensitive_paths(client: TestClient, path: str) -> None:
    response = client.get("/files/view", params={"path": path})
    _assert_blocked(response, path, "view")


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.backup",
        ".git/config",
        "node_modules",
        "__pycache__",
        "src/.git/config",
    ],
)
def test_file_browser_download_blocks_sensitive_paths(client: TestClient, path: str) -> None:
    response = client.get("/files/download", params={"path": path})
    _assert_blocked(response, path, "download")


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.backup",
        ".git",
        "node_modules",
        "__pycache__",
        "src/.git",
    ],
)
def test_file_browser_list_blocks_sensitive_paths(client: TestClient, path: str) -> None:
    response = client.get("/files/api/list", params={"path": path})
    _assert_blocked(response, path, "list")


def test_file_browser_encoded_hidden_path_is_blocked(client: TestClient) -> None:
    # Encoded ".env" path must not bypass filters.
    response = client.get("/files/view?path=%2eenv")
    _assert_blocked(response, "%2eenv", "view-encoded")
