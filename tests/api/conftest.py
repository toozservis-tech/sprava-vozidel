"""
Pytest konfigurace pro API testy
"""
import os
import pytest
import requests
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.api.integration_accounts import (
    CI_DEFAULT_PASSWORD,
    TEST_USER_EMAIL_DEFAULT,
    ensure_fixed_test_user,
)

# Testovací konfigurace
TEST_API_URL = os.getenv("TEST_API_URL", "http://127.0.0.1:8000")
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_vehicles.db")
TEST_ENV = "test"

TEST_USER_EMAIL = os.getenv("TEST_USER_EMAIL", TEST_USER_EMAIL_DEFAULT)
TEST_USER_PASSWORD = os.getenv("TEST_USER_PASSWORD", CI_DEFAULT_PASSWORD)


@pytest.fixture(scope="session")
def api_url():
    """Base URL pro API"""
    return TEST_API_URL


@pytest.fixture(scope="session")
def test_db_url():
    """Testovací databáze URL"""
    return TEST_DB_URL


@pytest.fixture(scope="session")
def auth_token(api_url):
    """
    Získat auth token pro testy.
    Používá fixed E2E účet; nevytváří náhodné účty při každém běhu.
    """
    try:
        ensure_fixed_test_user()
    except Exception:
        pass

    try:
        response = requests.post(
            f"{api_url}/user/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            },
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
    except Exception:
        pass
    
    return None


@pytest.fixture(scope="function")
def authenticated_headers(auth_token):
    """Headers s autentizací"""
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return {}


@pytest.fixture(scope="function")
def cleanup_test_data(api_url, authenticated_headers):
    """
    Cleanup fixture - smaže testovací data po testu
    """
    yield
    
    # Cleanup: smazat testovací vozidla
    try:
        response = requests.get(
            f"{api_url}/api/v1/vehicles",
            headers=authenticated_headers,
            timeout=5
        )
        if response.status_code == 200:
            vehicles = response.json()
            for vehicle in vehicles:
                nickname = str(vehicle.get("nickname") or "").lower()
                plate = str(vehicle.get("plate") or "").upper()
                brand = str(vehicle.get("brand") or "").lower()
                model = str(vehicle.get("model") or "").lower()
                is_test_vehicle = (
                    "test" in nickname
                    or plate.startswith("TEST")
                    or "test" in brand
                    or "test" in model
                )
                if is_test_vehicle:
                    requests.delete(
                        f"{api_url}/api/v1/vehicles/{vehicle['id']}",
                        headers=authenticated_headers,
                        timeout=5
                    )
    except Exception:
        pass
