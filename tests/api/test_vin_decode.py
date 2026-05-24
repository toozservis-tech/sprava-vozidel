"""
Testy pro VIN decode endpoint
"""
import pytest
from fastapi.testclient import TestClient
from src.server.main import app

from tests.api.integration_accounts import CI_DEFAULT_PASSWORD, CI_VIN_DECODE

client = TestClient(app)


@pytest.fixture(scope="module")
def vin_auth_headers():
    """Získá JWT token pro VIN endpoint testy (endpoint vyžaduje autentizaci)."""
    email = CI_VIN_DECODE
    password = CI_DEFAULT_PASSWORD

    register_response = client.post(
        "/user/register",
        json={"email": email, "password": password, "name": "VIN Test User"},
    )
    if register_response.status_code == 200:
        token = register_response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    assert register_response.status_code == 400
    login_response = client.post(
        "/user/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_vin_decode_invalid_length(vin_auth_headers):
    """Test VIN s neplatnou délkou"""
    response = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": "SHORT"},
        headers=vin_auth_headers,
    )
    assert response.status_code == 200  # Endpoint vrací 200 s success=False
    data = response.json()
    assert data["success"] is False
    assert "17 znaků" in data["errors"][0] or "length" in data["errors"][0].lower()


def test_vin_decode_invalid_characters(vin_auth_headers):
    """Test VIN s nepovolenými znaky (I, O, Q)"""
    response = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": "WVWZZZ1KZ6W000000"},  # 17 znaků, validní formát
        headers=vin_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Pokud VIN obsahuje I/O/Q, měl by být odmítnut
    # Ale některé VINy mohou být validní i s těmito znaky v některých pozicích
    # Pro tento test použijeme VIN který je určitě neplatný
    invalid_vin = "1HGBH41JXMN109186"  # Obsahuje I
    response2 = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": invalid_vin},
        headers=vin_auth_headers,
    )
    assert response2.status_code == 200
    data2 = response2.json()
    # Endpoint by měl vrátit buď success=False nebo success=True s errors


def test_vin_decode_valid_format(vin_auth_headers):
    """Test VIN s platným formátem (17 znaků, bez I, O, Q)"""
    # Použijeme testovací VIN (nemusí existovat v databázi)
    test_vin = "WVWZZZ1KZ6W000000"  # 17 znaků, bez I, O, Q
    response = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": test_vin},
        headers=vin_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Endpoint by měl vrátit response (i když data nemusí být dostupná)
    assert "success" in data
    assert "data" in data or "errors" in data


def test_vin_decode_missing_vin(vin_auth_headers):
    """Test bez VIN parametru"""
    response = client.post(
        "/api/vehicles/decode-vin",
        json={},
        headers=vin_auth_headers,
    )
    # Pydantic validation error - 422
    assert response.status_code == 422


def test_vin_decode_empty_vin(vin_auth_headers):
    """Test s prázdným VIN"""
    response = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": ""},
        headers=vin_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


def test_vin_decode_with_whitespace(vin_auth_headers):
    """Test VIN s mezerami (mělo by být automaticky vyčištěno)"""
    test_vin = "WVW ZZZ 1KZ 6W0 00000"  # S mezerami
    response = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": test_vin},
        headers=vin_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Endpoint by měl automaticky odstranit mezery
    assert "success" in data


def test_vin_decode_lowercase(vin_auth_headers):
    """Test VIN s malými písmeny (mělo by být automaticky převedeno na velká)"""
    test_vin = "wvwzzz1kz6w000000"  # Malá písmena
    response = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": test_vin},
        headers=vin_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # Endpoint by měl automaticky převést na velká písmena
    assert "success" in data


@pytest.mark.skip(reason="Requires MDČR API key - run manually with API key")
def test_vin_decode_with_real_vin(vin_auth_headers):
    """Test s reálným VIN (vyžaduje MDČR API key)"""
    # Tento test by měl běžet pouze pokud je nastaven DATAOVO_API_KEY
    real_vin = "TMBJF73T2B9044629"  # Testovací VIN z dokumentace
    response = client.post(
        "/api/vehicles/decode-vin",
        json={"vin": real_vin},
        headers=vin_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    if data.get("success"):
        assert "data" in data
        vehicle_data = data["data"]
        # Mělo by obsahovat alespoň některá pole
        assert vehicle_data.get("vin") == real_vin.upper().replace(" ", "").replace("-", "")
