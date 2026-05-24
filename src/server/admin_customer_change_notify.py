"""
Záznam změn účtu z admin panelu a odeslání vybraného souhrnu na e-mail uživatele.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME
from src.modules.email_client.service import EmailService
from src.modules.email_client.templates import build_app_url, render_email_layout, render_summary_steps
from src.modules.vehicle_hub.models import AdminCustomerChangeEvent

TABLE_NAME = "admin_customer_change_events"


def admin_change_table_exists(db: Session) -> bool:
    return inspect(db.bind).has_table(TABLE_NAME)


def record_admin_customer_change(
    db: Session,
    *,
    customer_id: int,
    admin_email: str,
    change_key: str,
    summary_line: str,
    detail_text: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[int]:
    if not summary_line or not admin_change_table_exists(db):
        return None
    payload_json = None
    if payload:
        try:
            payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            payload_json = None
    row = AdminCustomerChangeEvent(
        customer_id=int(customer_id),
        admin_email=(admin_email or "").strip()[:255] or None,
        change_key=(change_key or "unknown")[:128],
        summary_line=str(summary_line)[:4000],
        detail_text=detail_text,
        payload_json=payload_json,
    )
    db.add(row)
    db.flush()
    return int(row.id)


def _norm_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _norm_ws(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    return str(raw).strip() or None


def record_user_profile_license_changes_from_admin(
    db: Session,
    *,
    customer_id: int,
    admin_email: str,
    before: dict[str, Any],
    after: dict[str, Any],
    license_before: tuple[Optional[str], Optional[str]],
    license_after: tuple[Optional[str], Optional[str]],
    password_updated: bool,
) -> None:
    if not admin_change_table_exists(db):
        return

    def changed(key: str) -> bool:
        return _norm_str(before.get(key)) != _norm_str(after.get(key))

    if changed("email"):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.email",
            summary_line="Změna e-mailu účtu",
            detail_text=f"Dříve: {_norm_str(before.get('email')) or '—'} → nyní: {_norm_str(after.get('email')) or '—'}",
        )
    if changed("name"):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.name",
            summary_line="Změna jména / názvu",
            detail_text=f"Dříve: {_norm_str(before.get('name')) or '—'} → nyní: {_norm_str(after.get('name')) or '—'}",
        )
    if changed("role"):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.role",
            summary_line="Změna role účtu",
            detail_text=f"Dříve: {_norm_str(before.get('role')) or '—'} → nyní: {_norm_str(after.get('role')) or '—'}",
        )
    if changed("ico") or changed("dic"):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.company_ids",
            summary_line="Úprava IČO / DIČ",
            detail_text=(
                f"IČO: {_norm_str(before.get('ico')) or '—'} → {_norm_str(after.get('ico')) or '—'}\n"
                f"DIČ: {_norm_str(before.get('dic')) or '—'} → {_norm_str(after.get('dic')) or '—'}"
            ),
        )
    if changed("phone"):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.phone",
            summary_line="Změna telefonu",
            detail_text=f"Dříve: {_norm_str(before.get('phone')) or '—'} → nyní: {_norm_str(after.get('phone')) or '—'}",
        )
    if changed("street") or changed("street_number") or changed("city") or changed("zip"):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.address",
            summary_line="Úprava adresy",
            detail_text=(
                f"Dříve: {_norm_str(before.get('street')) or ''} {_norm_str(before.get('street_number')) or ''}, "
                f"{_norm_str(before.get('city')) or ''} {_norm_str(before.get('zip')) or ''}\n"
                f"Nyní: {_norm_str(after.get('street')) or ''} {_norm_str(after.get('street_number')) or ''}, "
                f"{_norm_str(after.get('city')) or ''} {_norm_str(after.get('zip')) or ''}"
            ),
        )
    if _norm_ws(before.get("workspace_entitlements")) != _norm_ws(after.get("workspace_entitlements")):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.workspace_entitlements",
            summary_line="Úprava pracovních režimů (uživatel / servis)",
            detail_text=(
                f"Dříve: {_norm_ws(before.get('workspace_entitlements')) or 'výchozí'}\n"
                f"Nyní: {_norm_ws(after.get('workspace_entitlements')) or 'výchozí'}"
            ),
        )
    if _norm_ws(before.get("workspace_ui_default")) != _norm_ws(after.get("workspace_ui_default")):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.workspace_ui_default",
            summary_line="Změna výchozího rozhraní",
            detail_text=(
                f"Dříve: {_norm_ws(before.get('workspace_ui_default')) or '—'} → "
                f"nyní: {_norm_ws(after.get('workspace_ui_default')) or '—'}"
            ),
        )
    if password_updated:
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="profile.password",
            summary_line="Heslo bylo změněno administrátorem",
            detail_text="Nové heslo z bezpečnostních důvodů do e-mailu neuvádíme.",
        )

    lp0, ls0 = license_before
    lp1, ls1 = license_after
    if _norm_str(lp0) != _norm_str(lp1) or _norm_str(ls0) != _norm_str(ls1):
        record_admin_customer_change(
            db,
            customer_id=customer_id,
            admin_email=admin_email,
            change_key="license.tenant",
            summary_line="Úprava licence účtu",
            detail_text=(
                f"Plán: {_norm_str(lp0) or '—'} → {_norm_str(lp1) or '—'}\n"
                f"Stav: {_norm_str(ls0) or '—'} → {_norm_str(ls1) or '—'}"
            ),
            payload={"plan_before": lp0, "plan_after": lp1, "status_before": ls0, "status_after": ls1},
        )


def send_customer_change_notification_email(
    *,
    to_email: str,
    user_name: Optional[str],
    admin_email: str,
    lines: Iterable[str],
) -> None:
    svc = EmailService()
    if not svc.is_configured():
        raise ValueError("E-mail není nakonfigurován (SMTP).")

    name = (user_name or "").strip() or "uživateli"
    bullet_lines = [f"• {s}" for s in lines if s]
    body_plain = f"""Dobrý den {name},

v aplikaci {APP_DISPLAY_NAME} byly na vašem účtu provedeny následující úpravy administrátorem ({admin_email}):

{chr(10).join(bullet_lines)}

Další změny můžete vidět přímo v aplikaci.

S pozdravem,
{APP_DISPLAY_NAME}
"""
    line_list = [str(s).strip() for s in lines if str(s or "").strip()]
    summary_html = (
        render_summary_steps(title="Provedené úpravy", items=line_list, accent="#4f46e5")
        if line_list
        else ""
    )
    html_body = render_email_layout(
        title="Změny na vašem účtu",
        subtitle="Níže najdete přehled změn, které administrátor zařadil do této zprávy.",
        intro=f"Dobrý den {name},",
        paragraphs=[
            f"v aplikaci {APP_DISPLAY_NAME} byly na vašem účtu provedeny úpravy.",
            f"Kontakt administrátora: {admin_email}",
        ],
        panels=[summary_html] if summary_html else [],
        cta_label="Otevřít aplikaci",
        cta_url=build_app_url(),
        accent="#4f46e5",
    )
    svc.send_simple_email(
        to=to_email,
        subject=f"Změny na účtu – {APP_DISPLAY_NAME}",
        body=body_plain,
        html_body=html_body,
    )


def mark_events_notified(
    db: Session,
    *,
    rows: list[AdminCustomerChangeEvent],
    to_email: str,
) -> None:
    now = datetime.utcnow()
    to = (to_email or "").strip()[:255]
    for r in rows:
        r.notified_at = now
        r.notified_to_email = to or None
    db.add_all(rows)
