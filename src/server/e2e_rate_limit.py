"""
E2E / Playwright rate-limit exemption (localhost + shared secret only).

Never weakens production login limits for arbitrary clients.
"""
from __future__ import annotations

from fastapi import Request

from src.core.config import E2E_RATE_LIMIT_BYPASS, E2E_RATE_LIMIT_BYPASS_SECRET
from src.server.security_tracking import extract_client_ip


def e2e_rate_limit_bypass_active(request: Request) -> bool:
    if not E2E_RATE_LIMIT_BYPASS:
        return False
    secret = (E2E_RATE_LIMIT_BYPASS_SECRET or "").strip()
    if not secret:
        return False
    client_ip = (extract_client_ip(request) or "").strip()
    if client_ip not in {"127.0.0.1", "::1"}:
        return False
    header = (request.headers.get("x-e2e-rate-limit-bypass") or "").strip()
    return header == secret
