"""Minimal FakturyWeb API client for service invoice export."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import urljoin

import requests


class FakturyWebError(RuntimeError):
    def __init__(self, message: str, *, status: Optional[int] = None, payload: Optional[Mapping[str, Any]] = None):
        super().__init__(message)
        self.status = status
        self.payload = dict(payload or {})


@dataclass(frozen=True)
class FakturyWebConfig:
    base_url: str
    email: str
    api_key: str
    api_test: bool = False
    supplier_id: Optional[str] = None
    timeout_seconds: float = 10.0

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.email and self.api_key)


class FakturyWebClient:
    """Wrapper around the GET+JSON API described in the FakturyWeb manual."""

    def __init__(self, config: FakturyWebConfig, *, session: Optional[requests.Session] = None):
        if not config.configured:
            raise FakturyWebError("FakturyWeb není nakonfigurovaný. Chybí e-mail nebo API klíč.")
        self.config = config
        self.session = session or requests.Session()

    def create_invoice(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        data = dict(payload)
        data.setdefault("key", self.config.api_key)
        data.setdefault("email", self.config.email)
        data.setdefault("apitest", 1 if self.config.api_test else 0)
        return self._api_json("api/nf", data)

    def invoice_status(self, code: str) -> dict[str, Any]:
        self._init_session()
        return self._api_json("api/status", self._base_payload(code=code))

    def invoice_pdf_info(self, code: str) -> dict[str, Any]:
        self._init_session()
        return self._api_json("api/zf", self._base_payload(code=code))

    def mark_invoice_paid(self, code: str, *, amount: Optional[float] = None, paid_at: Optional[str] = None) -> dict[str, Any]:
        data = self._base_payload(code=code)
        if amount is not None:
            data["amount"] = amount
        if paid_at:
            data["date"] = paid_at
        self._init_session()
        return self._api_json("api/uf", data)

    def _init_session(self) -> dict[str, Any]:
        return self._api_json("api/init", {"key": self.config.api_key, "email": self.config.email})

    def _base_payload(self, *, code: str) -> dict[str, Any]:
        return {"key": self.config.api_key, "email": self.config.email, "code": code}

    def _api_json(self, path: str, data: Mapping[str, Any]) -> dict[str, Any]:
        url = urljoin(self.config.base_url.rstrip("/") + "/", path.lstrip("/"))
        response = self.session.get(
            url,
            params={"data": json.dumps(data, ensure_ascii=False, separators=(",", ":"))},
            timeout=self.config.timeout_seconds,
            allow_redirects=True,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise FakturyWebError("FakturyWeb vrátil neplatnou JSON odpověď.") from exc
        status = int(payload.get("status", 0) or 0) if isinstance(payload, dict) else 0
        if status != 1:
            raise FakturyWebError(
                f"FakturyWeb vrátil chybu status={status}.",
                status=status,
                payload=payload if isinstance(payload, dict) else {},
            )
        return payload
