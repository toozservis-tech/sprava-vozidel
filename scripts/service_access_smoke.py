#!/usr/bin/env python3
"""
Release smoke test for the service access model.

Goal:
- confirm the deployed backend exposes the new service access routes
- fail hard on 404 for any of the new endpoints
- accept auth/validation/business responses (200/400/401/403/409/422)

Required environment variables unless *_TOKEN is provided:
- SERVICE_EMAIL
- SERVICE_PASSWORD
- USER_EMAIL
- USER_PASSWORD

Optional:
- BASE_URL=http://127.0.0.1:8000
- SERVICE_TOKEN=...
- USER_TOKEN=...
- SERVICE_2FA_CODE=...
- USER_2FA_CODE=...
- SMOKE_REPORT=logs/service_access_smoke_report.json
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "logs" / "service_access_smoke_report.json"

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = int(os.getenv("SMOKE_TIMEOUT", "20"))

EXPECTED_SERVICE_ACCESS_ROUTES = {
    ("POST", "/api/v1/services/vehicle-lookup"),
    ("POST", "/api/v1/services/access-requests"),
    ("GET", "/api/v1/services/access-requests"),
    ("PUT", "/api/v1/services/access-requests/{request_id}"),
    ("GET", "/api/v1/services/approved-vehicles"),
}


@dataclass
class StepResult:
    step: str
    ok: bool
    info: str = ""


class Recorder:
    def __init__(self) -> None:
        self.steps: list[StepResult] = []

    def add(self, step: str, ok: bool, info: str = "") -> None:
        self.steps.append(StepResult(step=step, ok=ok, info=info))
        state = "PASS" if ok else "FAIL"
        suffix = f" - {info}" if info else ""
        print(f"[{state}] {step}{suffix}")

    def all_ok(self) -> bool:
        return all(item.ok for item in self.steps)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def preview(value: Any, limit: int = 300) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
    return text[:limit]


def request_json(
    method: str,
    path: str,
    *,
    token: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(
        method=method,
        url=f"{BASE_URL}{path}",
        headers=headers,
        json=payload,
        timeout=TIMEOUT,
    )


def parse_body(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def login(
    *,
    email: str,
    password: str,
    expected_role: str,
    two_factor_code: Optional[str] = None,
) -> str:
    response = request_json(
        "POST",
        "/user/login",
        payload={
            "email": email,
            "password": password,
            "expected_role": expected_role,
        },
    )
    body = parse_body(response)
    if response.status_code != 200:
        raise RuntimeError(f"login failed: status={response.status_code} body={preview(body)}")
    if isinstance(body, dict) and body.get("access_token"):
        return str(body["access_token"])
    if isinstance(body, dict) and body.get("two_factor_required"):
        challenge_token = str(body.get("challenge_token") or "")
        if not challenge_token:
            raise RuntimeError("2FA login response missing challenge_token")
        if not two_factor_code:
            raise RuntimeError("2FA is required but *_2FA_CODE was not provided")
        verify_response = request_json(
            "POST",
            "/user/login/2fa",
            payload={
                "challenge_token": challenge_token,
                "code": two_factor_code,
            },
        )
        verify_body = parse_body(verify_response)
        if verify_response.status_code != 200:
            raise RuntimeError(
                f"2FA verify failed: status={verify_response.status_code} body={preview(verify_body)}"
            )
        if isinstance(verify_body, dict) and verify_body.get("access_token"):
            return str(verify_body["access_token"])
        raise RuntimeError(f"2FA verify returned no access token: {preview(verify_body)}")
    raise RuntimeError(f"login returned no access token: {preview(body)}")


def token_from_env_or_login(
    *,
    token_env: str,
    email_env: str,
    password_env: str,
    expected_role: str,
    two_factor_env: str,
) -> str:
    token = os.getenv(token_env, "").strip()
    if token:
        return token
    email = require_env(email_env)
    password = require_env(password_env)
    code = os.getenv(two_factor_env, "").strip() or None
    return login(email=email, password=password, expected_role=expected_role, two_factor_code=code)


def check_status(
    rec: Recorder,
    *,
    step: str,
    response: requests.Response,
    allowed_statuses: Iterable[int],
    fail_on_404: bool = True,
) -> Any:
    body = parse_body(response)
    allowed = set(allowed_statuses)
    status = response.status_code
    if fail_on_404 and status == 404:
        rec.add(step, False, f"status=404 body={preview(body)}")
        return body
    ok = status in allowed
    rec.add(step, ok, f"status={status} body={preview(body)}")
    return body


def route_inventory_check(rec: Recorder, token: str) -> None:
    response = request_json("GET", "/api/_debug/routes", token=token)
    body = parse_body(response)
    if response.status_code != 200:
        rec.add("route_inventory_debug_endpoint", False, f"status={response.status_code} body={preview(body)}")
        return

    routes = body.get("routes") if isinstance(body, dict) else None
    if not isinstance(routes, list):
        rec.add("route_inventory_debug_payload", False, f"unexpected-body={preview(body)}")
        return

    deployed = {
        (str(item.get("method") or "").upper(), str(item.get("path") or ""))
        for item in routes
        if isinstance(item, dict)
    }
    missing = sorted(EXPECTED_SERVICE_ACCESS_ROUTES - deployed)
    if missing:
        rec.add("route_inventory_service_access_routes", False, f"missing={missing}")
    else:
        rec.add("route_inventory_service_access_routes", True, "all expected routes are registered")


def main() -> int:
    rec = Recorder()
    report_path = Path(os.getenv("SMOKE_REPORT", str(DEFAULT_REPORT)))

    report: Dict[str, Any] = {
        "generated_at": now_iso(),
        "base_url": BASE_URL,
        "steps": [],
    }

    try:
        health = request_json("GET", "/health")
        check_status(rec, step="health", response=health, allowed_statuses={200}, fail_on_404=False)

        service_token = token_from_env_or_login(
            token_env="SERVICE_TOKEN",
            email_env="SERVICE_EMAIL",
            password_env="SERVICE_PASSWORD",
            expected_role="service",
            two_factor_env="SERVICE_2FA_CODE",
        )
        rec.add("service_auth", True, "service token acquired")

        user_token = token_from_env_or_login(
            token_env="USER_TOKEN",
            email_env="USER_EMAIL",
            password_env="USER_PASSWORD",
            expected_role="user",
            two_factor_env="USER_2FA_CODE",
        )
        rec.add("user_auth", True, "user token acquired")

        service_me = request_json("GET", "/user/me", token=service_token)
        check_status(rec, step="service_me", response=service_me, allowed_statuses={200}, fail_on_404=False)

        user_me = request_json("GET", "/user/me", token=user_token)
        check_status(rec, step="user_me", response=user_me, allowed_statuses={200}, fail_on_404=False)

        route_inventory_check(rec, user_token)

        # Unauthorized check
        unauthorized_lookup = request_json("POST", "/api/v1/services/vehicle-lookup", payload={})
        check_status(
            rec,
            step="unauthorized_lookup_route_presence",
            response=unauthorized_lookup,
            allowed_statuses={401, 403, 422},
        )

        # Authorized route presence checks.
        lookup = request_json(
            "POST",
            "/api/v1/services/vehicle-lookup",
            token=service_token,
            payload={},
        )
        check_status(
            rec,
            step="service_lookup_route",
            response=lookup,
            allowed_statuses={200, 400, 401, 403, 422},
        )

        access_request_create = request_json(
            "POST",
            "/api/v1/services/access-requests",
            token=service_token,
            payload={},
        )
        check_status(
            rec,
            step="service_access_request_create_route",
            response=access_request_create,
            allowed_statuses={200, 400, 401, 403, 409, 422},
        )

        user_requests = request_json(
            "GET",
            "/api/v1/services/access-requests",
            token=user_token,
        )
        check_status(
            rec,
            step="user_access_requests_route",
            response=user_requests,
            allowed_statuses={200, 401, 403},
        )

        decision = request_json(
            "PUT",
            "/api/v1/services/access-requests/not-an-int",
            token=user_token,
            payload={"decision": "approved"},
        )
        check_status(
            rec,
            step="user_access_request_decision_route",
            response=decision,
            allowed_statuses={401, 403, 422},
        )

        approved = request_json(
            "GET",
            "/api/v1/services/approved-vehicles",
            token=service_token,
        )
        check_status(
            rec,
            step="service_approved_vehicles_route",
            response=approved,
            allowed_statuses={200, 401, 403},
        )

    except Exception as exc:
        rec.add("smoke_runtime", False, repr(exc))

    report["steps"] = [asdict(step) for step in rec.steps]
    report["all_ok"] = rec.all_ok()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"REPORT={report_path}")
    print(f"ALL_OK={1 if rec.all_ok() else 0}")
    return 0 if rec.all_ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
