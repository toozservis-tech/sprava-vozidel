"""Společný rate-limit bucket pro /api/public/* (token guessing)."""
from __future__ import annotations

from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from src.core.security_middleware import RateLimitMiddleware, rate_limit_store


def test_public_api_paths_share_rate_limit_counter() -> None:
    rate_limit_store.clear()
    app = FastAPI()

    @app.get("/api/public/vehicle-history/{token}")
    def _pub(token: str):
        return JSONResponse({"ok": True})

    @app.get("/api/public/other/{slug}")
    def _other(slug: str):
        return JSONResponse({"ok": True})

    app.add_middleware(RateLimitMiddleware, calls=100, period=60, public_calls=5, public_period=60)
    client = TestClient(app)
    for i in range(5):
        r = client.get(f"/api/public/vehicle-history/tok-{i}")
        assert r.status_code == 200, i
    r6 = client.get("/api/public/vehicle-history/tok-6")
    assert r6.status_code == 429
    # Jiná cesta pod /api/public/ sdílí stejný bucket
    r7 = client.get("/api/public/other/xyz")
    assert r7.status_code == 429
