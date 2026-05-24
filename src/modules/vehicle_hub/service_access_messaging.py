"""
E-mail a audit kolem žádosti servisu o přístup (SMTP volitelné — nesmí shodit HTTP).
Testy mohou přepsat ``send_service_access_request_email``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME
from src.modules.email_client.service import EmailMessage, EmailService

from .audit_log import write_global_audit_log
from .models import Customer, Vehicle
from .service_access import masked_plate, vehicle_label

logger = logging.getLogger(__name__)

send_service_access_request_email: Callable[..., bool] | None = None


def _vehicle_label_for_access_email(vehicle: Vehicle) -> str:
    """
    Bezpečný popis vozidla pro e-mail majiteli: SPZ (maskovaná) + značka/model,
    případně zkrácený VIN (koncovka), bez dalších osobních údajů.
    """
    parts: list[str] = []
    pm = masked_plate(getattr(vehicle, "plate", None))
    if pm:
        parts.append(f"SPZ {pm}")
    bm = " ".join(
        p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if p
    ).strip()
    if bm:
        parts.append(bm)
    vin_raw = str(getattr(vehicle, "vin", None) or "").strip().upper()
    if vin_raw and len(vin_raw) >= 6 and not pm:
        parts.append(f"koncovka VIN …{vin_raw[-6:]}")
    if parts:
        return " – ".join(parts)
    return vehicle_label(vehicle)


def _sanitize_email_error(exc: BaseException, *, max_len: int = 300) -> str:
    text = str(exc).strip().replace("\n", " ")
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _default_send_owner_email(*, to_email: str, subject: str, plain_body: str) -> bool:
    svc = EmailService()
    if not svc.is_configured():
        raise ValueError("smtp_not_configured")
    msg = EmailMessage(to=[to_email], subject=subject, body=plain_body)
    return bool(svc.send_email(msg))


def try_email_owner_about_service_access_request(
    db: Session,
    *,
    owner: Customer,
    service: Customer,
    vehicle: Vehicle,
    request_id: int,
    tenant_id: Optional[int] = None,
) -> dict[str, Any]:
    to_email = str(getattr(owner, "email", None) or "").strip()
    if not to_email or "@" not in to_email:
        write_global_audit_log(
            db,
            entity_type="service_access_request",
            entity_id=int(request_id),
            action="service_access_request_email_skipped",
            actor_type="system",
            actor_user_id=None,
            tenant_id=tenant_id or getattr(owner, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={"reason": "owner_email_missing", "request_id": int(request_id)},
        )
        return {"attempted": False, "sent": False, "reason": "owner_email_missing", "error": None}

    service_disp = (service.name or service.email or "Servis").strip()
    vlabel = _vehicle_label_for_access_email(vehicle)
    subject = f"Servis žádá o přístup k vozidlu — {APP_DISPLAY_NAME}"
    body = (
        "Dobrý den,\n\n"
        f"servis {service_disp} žádá o přístup k vozidlu {vlabel} ve vaší aplikaci {APP_DISPLAY_NAME}.\n\n"
        "Žádost můžete schválit nebo odmítnout po přihlášení do aplikace.\n\n"
        "Bez vašeho schválení servis nezíská přístup k detailu vozidla.\n\n"
        "Pokud tuto žádost nečekáte, můžete ji v aplikaci odmítnout.\n\n"
        f"S pozdravem\n{APP_DISPLAY_NAME}\n"
    )

    sender = send_service_access_request_email or _default_send_owner_email
    try:
        ok = sender(to_email=to_email, subject=subject, plain_body=body)
    except ValueError as exc:
        if str(exc) == "smtp_not_configured":
            write_global_audit_log(
                db,
                entity_type="service_access_request",
                entity_id=int(request_id),
                action="service_access_request_email_smtp_unavailable",
                actor_type="system",
                actor_user_id=None,
                tenant_id=tenant_id or getattr(owner, "tenant_id", None),
                vehicle_id=int(vehicle.id),
                metadata={
                    "request_id": int(request_id),
                    "severity": "warning",
                    "service_id": int(service.id),
                },
            )
            logger.warning("[SERVICE_ACCESS_EMAIL] SMTP není nakonfigurováno — e-mail se neodeslal.")
            return {"attempted": True, "sent": False, "reason": "smtp_not_configured", "error": None}
        err_txt = _sanitize_email_error(exc)
        write_global_audit_log(
            db,
            entity_type="service_access_request",
            entity_id=int(request_id),
            action="service_access_request_email_failed",
            actor_type="system",
            actor_user_id=None,
            tenant_id=tenant_id or getattr(owner, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={
                "request_id": int(request_id),
                "error": err_txt,
                "severity": "warning",
            },
        )
        logger.warning("[SERVICE_ACCESS_EMAIL] Odeslání selhalo: %s", exc)
        return {"attempted": True, "sent": False, "reason": "send_failed", "error": err_txt}
    except Exception as exc:  # noqa: BLE001
        err_txt = _sanitize_email_error(exc)
        write_global_audit_log(
            db,
            entity_type="service_access_request",
            entity_id=int(request_id),
            action="service_access_request_email_failed",
            actor_type="system",
            actor_user_id=None,
            tenant_id=tenant_id or getattr(owner, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={
                "request_id": int(request_id),
                "error": err_txt,
                "severity": "warning",
            },
        )
        logger.warning("[SERVICE_ACCESS_EMAIL] Odeslání selhalo: %s", exc)
        return {"attempted": True, "sent": False, "reason": "send_failed", "error": err_txt}

    if ok is False:
        write_global_audit_log(
            db,
            entity_type="service_access_request",
            entity_id=int(request_id),
            action="service_access_request_email_failed",
            actor_type="system",
            actor_user_id=None,
            tenant_id=tenant_id or getattr(owner, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={
                "request_id": int(request_id),
                "severity": "warning",
                "service_id": int(service.id),
            },
        )
        logger.warning("[SERVICE_ACCESS_EMAIL] send_email vrátilo False — zpráva se nejspíš neodeslala.")
        return {"attempted": True, "sent": False, "reason": "send_failed", "error": None}

    write_global_audit_log(
        db,
        entity_type="service_access_request",
        entity_id=int(request_id),
        action="service_access_request_email_sent",
        actor_type="system",
        actor_user_id=None,
        tenant_id=tenant_id or getattr(owner, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        metadata={
            "request_id": int(request_id),
            "service_id": int(service.id),
            "vehicle_id": int(vehicle.id),
        },
    )
    return {"attempted": True, "sent": True, "reason": None, "error": None}
