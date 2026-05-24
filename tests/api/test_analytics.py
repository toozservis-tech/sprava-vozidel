"""
Testy pro analytics API nad servisními záznamy.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
import requests


def _create_vehicle(api_url: str, headers: dict[str, str], nickname: str) -> int:
    response = requests.post(
        f"{api_url}/api/v1/vehicles",
        headers=headers,
        json={
            "nickname": nickname,
            "brand": "Test Brand",
            "model": "Test Model",
            "year": 2022,
            "plate": f"TEST{uuid4().hex[:4].upper()}",
            "stk_valid_until": (date.today() + timedelta(days=365)).isoformat(),
        },
        timeout=8,
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


def _create_service_record(
    api_url: str,
    headers: dict[str, str],
    *,
    vehicle_id: int,
    category: str,
    price: float,
    mileage: int,
    description: str,
) -> None:
    response = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/records",
        headers=headers,
        json={
            "performed_at": datetime.utcnow().replace(microsecond=0).isoformat(),
            "mileage": mileage,
            "description": description,
            "price": price,
            "note": "analytics test",
            "category": category,
            "next_service_due_date": None,
        },
        timeout=8,
    )
    assert response.status_code == 200, response.text


def _create_reminder(
    api_url: str,
    headers: dict[str, str],
    *,
    vehicle_id: int,
    text: str,
) -> None:
    response = requests.post(
        f"{api_url}/api/v1/reminders",
        headers=headers,
        json={
            "vehicle_id": vehicle_id,
            "type": "SERVIS",
            "text": text,
        },
        timeout=8,
    )
    assert response.status_code == 200, response.text


def test_analytics_summary_categories_and_monthly_costs(api_url, authenticated_headers, cleanup_test_data):
    if not authenticated_headers:
        pytest.skip("No auth token available")

    vehicle_id = _create_vehicle(api_url, authenticated_headers, "Test Analytics Vehicle")
    _create_service_record(
        api_url,
        authenticated_headers,
        vehicle_id=vehicle_id,
        category="OLEJ",
        price=1500.0,
        mileage=100000,
        description="Výměna oleje",
    )
    _create_service_record(
        api_url,
        authenticated_headers,
        vehicle_id=vehicle_id,
        category="BRZDY",
        price=3200.0,
        mileage=102000,
        description="Výměna destiček",
    )
    _create_service_record(
        api_url,
        authenticated_headers,
        vehicle_id=vehicle_id,
        category="OLEJ",
        price=900.0,
        mileage=103500,
        description="Doplnění oleje",
    )

    summary_response = requests.get(
        f"{api_url}/api/v1/analytics/summary",
        headers=authenticated_headers,
        params={"vehicle_id": vehicle_id},
        timeout=8,
    )
    assert summary_response.status_code == 200, summary_response.text
    summary_payload = summary_response.json()
    assert summary_payload["scope"] == "vehicle"
    assert int(summary_payload["vehicle_id"]) == vehicle_id
    assert int(summary_payload["total_records"]) == 3
    assert float(summary_payload["total_cost_czk"]) == 5600.0
    assert float(summary_payload["average_cost_czk"]) == 1866.67

    categories_response = requests.get(
        f"{api_url}/api/v1/analytics/categories",
        headers=authenticated_headers,
        params={"vehicle_id": vehicle_id},
        timeout=8,
    )
    assert categories_response.status_code == 200, categories_response.text
    categories_payload = categories_response.json()
    assert int(categories_payload["total_records"]) == 3
    categories = {row["category"]: row for row in categories_payload["categories"]}
    assert "OLEJ" in categories
    assert int(categories["OLEJ"]["records_count"]) == 2
    assert float(categories["OLEJ"]["total_cost_czk"]) == 2400.0
    assert "BRZDY" in categories
    assert int(categories["BRZDY"]["records_count"]) == 1
    assert float(categories["BRZDY"]["total_cost_czk"]) == 3200.0

    monthly_response = requests.get(
        f"{api_url}/api/v1/analytics/monthly-costs",
        headers=authenticated_headers,
        params={"vehicle_id": vehicle_id, "months": 6},
        timeout=8,
    )
    assert monthly_response.status_code == 200, monthly_response.text
    monthly_payload = monthly_response.json()
    assert int(monthly_payload["months"]) == 6
    assert len(monthly_payload["entries"]) == 6
    assert int(monthly_payload["total_records"]) == 3
    assert float(monthly_payload["total_cost_czk"]) == 5600.0


def test_dashboard_summary_returns_aggregated_view(api_url, authenticated_headers, cleanup_test_data):
    if not authenticated_headers:
        pytest.skip("No auth token available")

    vehicle_id = _create_vehicle(api_url, authenticated_headers, "Test Dashboard Vehicle")
    _create_service_record(
        api_url,
        authenticated_headers,
        vehicle_id=vehicle_id,
        category="OLEJ",
        price=2100.0,
        mileage=111000,
        description="Dashboard servis",
    )
    _create_reminder(
        api_url,
        authenticated_headers,
        vehicle_id=vehicle_id,
        text="Dashboard připomínka",
    )

    response = requests.get(
        f"{api_url}/api/v1/analytics/dashboard",
        headers=authenticated_headers,
        timeout=8,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert int(payload["vehicles_total"]) >= 1
    assert int(payload["active_reminders"]) >= 1
    assert "recent_activity" in payload
    assert "attention" in payload
    assert any(int(item["vehicle_id"]) == vehicle_id for item in payload["recent_activity"])


def test_reminder_settings_endpoint_available_after_dedup(api_url, authenticated_headers):
    if not authenticated_headers:
        pytest.skip("No auth token available")

    response = requests.get(
        f"{api_url}/api/v1/reminders/settings",
        headers=authenticated_headers,
        timeout=8,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "enabled" in payload
    assert "notification" in payload
