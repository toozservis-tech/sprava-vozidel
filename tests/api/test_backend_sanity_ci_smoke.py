"""Minimal CI smoke: backend imports and env defaults without production secrets."""
from __future__ import annotations

import os

import pytest


def test_ci_env_defaults_are_safe_for_sanity_gate() -> None:
    assert os.getenv("APP_ENV", "test") in {"test", "ci", "development"}
    assert os.getenv("ENVIRONMENT", "test") in {"test", "ci", "development"}
    assert "JWT_SECRET_KEY" in os.environ or os.getenv("APP_ENV", "test") == "test"


def test_backend_core_imports_without_production_secrets() -> None:
    pytest.importorskip("fastapi")
    from src.core import config
    from src.server import admin_api

    assert config.ENVIRONMENT in {"test", "ci", "development", "production"}
    assert admin_api.ARCHIVED_USERS_PURGE_CONFIRM_PHRASE == "VYMAZAT ARCHIV"
