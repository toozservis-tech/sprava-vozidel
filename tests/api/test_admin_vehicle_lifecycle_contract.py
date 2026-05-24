"""
HTTP kontrakty admin vehicle lifecycle + rozšíření bez privilegovaného účtu.

Plně integrační testy (revoke/resend s audit logem proti ostré DB) vyžadují účet s rolí
developer_admin / admin — v repozitáři není bezpečný pytest fixture (credentials).
Nastavte např. RUN_ADMIN_LIFECYCLE_E2E=1 + ADMIN_TEST_EMAIL + ADMIN_TEST_PASSWORD pokud je chcete doplnit lokálně.
"""
from __future__ import annotations

import os

import pytest
import requests

from tests.api.integration_accounts import CI_API_NONADMIN, ensure_user_token


@pytest.mark.parametrize(
    "path",
    (
        "/admin-api/vehicle-lifecycle",
        "/api/admin/vehicle-lifecycle",
    ),
)
def test_admin_vehicle_lifecycle_list_requires_authentication(api_url: str, path: str) -> None:
    r = requests.get(f"{api_url}{path}", timeout=8)
    assert r.status_code in (401, 403)
    assert "detail" in r.json()


@pytest.mark.parametrize(
    "path",
    (
        "/admin-api/vehicle-lifecycle",
        "/api/admin/vehicle-lifecycle",
    ),
)
def test_admin_vehicle_lifecycle_list_forbidden_for_regular_user(api_url: str, path: str) -> None:
    token, _ = ensure_user_token(api_url, CI_API_NONADMIN, name="Non-admin LC")
    r = requests.get(
        f"{api_url}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=8,
    )
    assert r.status_code == 403


def test_openapi_lists_transfer_claim_alias(api_url: str) -> None:
    r = requests.get(f"{api_url}/openapi.json", timeout=15)
    assert r.status_code == 200
    paths = r.json().get("paths") or {}
    assert "/api/v1/vehicles/transfer-claim" in paths
    assert "/api/v1/vehicles/claim-by-transfer" in paths


@pytest.mark.skip(
    reason=(
        "E2E admin lifecycle: nastavte RUN_ADMIN_LIFECYCLE_E2E=1 a ADMIN_TEST_EMAIL / ADMIN_TEST_PASSWORD "
        "pro účet s rolí developer_admin v cílové DB (fixture zde záměrně není)."
    ),
)
def test_placeholder_admin_e2e_requires_manual_credentials() -> None:
    assert os.getenv("RUN_ADMIN_LIFECYCLE_E2E") == "1"
