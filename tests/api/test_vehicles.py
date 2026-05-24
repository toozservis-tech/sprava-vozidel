"""
Testy pro vehicles API
"""
import pytest
import requests

VALID_STK_DATE = "2030-12-31"


def test_create_vehicle(api_url, authenticated_headers, cleanup_test_data):
    """Test vytvoření vozidla"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    vehicle_data = {
        "nickname": "Test Vehicle",
        "plate": "TEST123",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020,
        "stk_valid_until": VALID_STK_DATE,
    }
    
    response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == vehicle_data["nickname"]
    assert data["plate"] == vehicle_data["plate"]
    assert "id" in data
    
    return data["id"]


def test_get_vehicles(api_url, authenticated_headers):
    """Test získání seznamu vozidel"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    response = requests.get(
        f"{api_url}/api/v1/vehicles",
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_vehicle_detail(api_url, authenticated_headers, cleanup_test_data):
    """Test získání detailu vozidla"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    # Vytvořit vozidlo
    vehicle_data = {
        "nickname": "Test Vehicle Detail",
        "plate": "TEST456",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020,
        "stk_valid_until": VALID_STK_DATE,
    }
    
    create_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5
    )
    assert create_response.status_code == 200
    vehicle_id = create_response.json()["id"]
    
    # Získat detail
    response = requests.get(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == vehicle_id
    assert data["nickname"] == vehicle_data["nickname"]


def test_update_vehicle(api_url, authenticated_headers, cleanup_test_data):
    """Test aktualizace vozidla"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    # Vytvořit vozidlo
    vehicle_data = {
        "nickname": "Test Vehicle Update",
        "plate": "TEST789",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020,
        "stk_valid_until": VALID_STK_DATE,
    }
    
    create_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5
    )
    assert create_response.status_code == 200
    vehicle_id = create_response.json()["id"]
    
    # Aktualizovat
    update_data = {
        "nickname": "Updated Vehicle",
        "year": 2021
    }
    
    response = requests.put(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        json=update_data,
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == update_data["nickname"]
    assert data["year"] == update_data["year"]


def test_delete_vehicle(api_url, authenticated_headers):
    """Odebrání vozidla přes lifecycle (archivace); přímé DELETE je zablokované."""
    if not authenticated_headers:
        pytest.skip("No auth token available")

    vehicle_data = {
        "nickname": "Test Vehicle Delete",
        "plate": "TEST999",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020,
        "stk_valid_until": VALID_STK_DATE,
    }

    create_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5,
    )
    assert create_response.status_code == 200
    vehicle_id = create_response.json()["id"]

    blocked = requests.delete(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        headers=authenticated_headers,
        timeout=5,
    )
    assert blocked.status_code == 409

    init = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/remove/init",
        json={"reason_code": "ceased"},
        headers=authenticated_headers,
        timeout=15,
    )
    assert init.status_code == 200

    confirm = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/remove/confirm",
        json={
            "reason_code": "ceased",
            "followup_answer": {"note": "api test zánik"},
        },
        headers=authenticated_headers,
        timeout=60,
    )
    assert confirm.status_code == 200
    payload = confirm.json()
    assert payload.get("removed") is True
    assert payload.get("history_preserved") is True

    list_response = requests.get(
        f"{api_url}/api/v1/vehicles",
        headers=authenticated_headers,
        timeout=5,
    )
    assert list_response.status_code == 200
    vehicles = list_response.json()
    assert all(int(item["id"]) != vehicle_id for item in vehicles)
