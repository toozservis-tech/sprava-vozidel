#!/usr/bin/env python3
"""
Read-only diagnostika e-mail notifikací (žádný zápis do DB, žádná hesla na stdout).

Spuštění z kořene aplikace:
  python3 scripts/diagnose_email_notifications.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from sqlalchemy import desc  # noqa: E402

from src.core.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER  # noqa: E402
from src.modules.email_client.service import EmailService  # noqa: E402
from src.modules.vehicle_hub.database import SessionLocal  # noqa: E402
from src.modules.vehicle_hub.models import GlobalAuditLog, ServiceAccessRequest, ServiceCustomerLink  # noqa: E402

_AUDIT_ACTIONS = (
    "SERVICE_CUSTOMER_INVITE_EMAIL_SENT",
    "SERVICE_CUSTOMER_INVITE_EMAIL_FAILED",
    "SERVICE_CUSTOMER_LINK_CONFIRM_EMAIL_SENT",
    "SERVICE_CUSTOMER_LINK_CONFIRM_EMAIL_FAILED",
    "service_access_request_email_sent",
    "service_access_request_email_smtp_unavailable",
    "service_access_request_email_failed",
)


def _mask_email(addr: str | None) -> str | None:
    text = str(addr or "").strip()
    if not text or "@" not in text:
        return None
    local, domain = text.split("@", 1)
    if len(local) <= 2:
        lm = local[:1] + "***"
    else:
        lm = f"{local[:2]}***"
    return f"{lm}@{domain}"


def _smtp_missing_keys(svc: EmailService) -> list[str]:
    missing: list[str] = []
    if not (svc.host or "").strip():
        missing.append("SMTP_HOST")
    if not (svc.username or "").strip():
        missing.append("SMTP_USER")
    if not svc.password:
        missing.append("SMTP_PASSWORD")
    return missing


def main() -> int:
    svc = EmailService()
    configured = svc.is_configured()
    missing = _smtp_missing_keys(svc)
    print("=== SMTP (bez hodnot) ===")
    print(
        json.dumps(
            {
                "smtp_host_configured": bool((SMTP_HOST or "").strip()),
                "smtp_port_configured": bool(str(SMTP_PORT or "").strip()),
                "smtp_username_configured": bool((SMTP_USER or "").strip()),
                "smtp_password_configured": bool((SMTP_PASSWORD or "").strip()),
                "smtp_from_configured": bool((SMTP_FROM or "").strip()),
                "email_service_effective_configured": configured,
                "email_service_missing_keys": missing,
            },
            ensure_ascii=False,
        )
    )

    db = SessionLocal()
    try:
        print("\n=== Posledních 20 audit záznamů (vybrané akce, maskované e-maily v metadatech) ===")
        rows = (
            db.query(GlobalAuditLog)
            .filter(GlobalAuditLog.action.in_(_AUDIT_ACTIONS))
            .order_by(desc(GlobalAuditLog.id))
            .limit(20)
            .all()
        )
        out_rows = []
        email_like = re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            re.I,
        )

        def _redact_meta(meta: dict) -> dict:
            raw = json.dumps(meta, ensure_ascii=False, default=str)
            redacted = email_like.sub(lambda m: _mask_email(m.group(0)) or "***", raw)
            try:
                return json.loads(redacted)
            except json.JSONDecodeError:
                return {"_raw_redacted": redacted[:2000]}

        for row in rows:
            meta = {}
            if row.metadata_json:
                try:
                    meta = json.loads(row.metadata_json)
                except json.JSONDecodeError:
                    meta = {"_unparsed": True}
            out_rows.append(
                {
                    "id": row.id,
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                    "action": row.action,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "metadata": _redact_meta(meta if isinstance(meta, dict) else {}),
                }
            )
        print(json.dumps(out_rows, ensure_ascii=False, indent=2))

        print("\n=== Posledních 10 čekajících service_access_requests ===")
        sar = (
            db.query(ServiceAccessRequest)
            .filter(ServiceAccessRequest.status == "pending")
            .order_by(desc(ServiceAccessRequest.id))
            .limit(10)
            .all()
        )
        print(
            json.dumps(
                [
                    {
                        "id": r.id,
                        "vehicle_id": r.vehicle_id,
                        "service_customer_id": r.service_customer_id,
                        "owner_customer_id": r.owner_customer_id,
                        "requested_at": r.requested_at.isoformat() if r.requested_at else None,
                    }
                    for r in sar
                ],
                ensure_ascii=False,
                indent=2,
            )
        )

        print("\n=== Posledních 10 service_customer_links (invited / pending_customer_confirm) ===")
        links = (
            db.query(ServiceCustomerLink)
            .filter(ServiceCustomerLink.status.in_(["invited", "pending_customer_confirm"]))
            .order_by(desc(ServiceCustomerLink.id))
            .limit(10)
            .all()
        )
        print(
            json.dumps(
                [
                    {
                        "id": ln.id,
                        "status": ln.status,
                        "service_customer_id": ln.service_customer_id,
                        "customer_id": ln.customer_id,
                    }
                    for ln in links
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
