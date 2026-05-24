"""
Cílená in-app oznámení (řádky v system_notifications s target_type=user).
Použití: zvonek v aplikaci, případně dashboard — bez nutnosti měnit API feed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME

from .models import Customer, ServiceInvoice, ServiceQuote, SystemNotification, Vehicle
from .schema_management import assert_module_ready
from .service_access import vehicle_label

# Zobrazení v administraci v přehledu oznámení („Odeslal“) — jednotný štítek pro automatické systémové záznamy.
APP_AUTOMATED_NOTIFICATION_SENDER = "SPRÁVA VOZIDEL"


def create_user_in_app_notification(
    db: Session,
    *,
    customer_id: int,
    title: str,
    message: str,
    severity: str = "info",
    expires_days: int = 90,
) -> None:
    """Přidá řádek do system_notifications; při chybě schématu tiše přeskočí."""
    try:
        assert_module_ready(
            db,
            "system_notifications",
            detail_prefix="Systémová oznámení nejsou připravená",
        )
        safe_title = (title or "").strip()[:240] or None
        safe_message = (message or "").strip()
        if not safe_message:
            return
        row = SystemNotification(
            target_type="user",
            target_value=str(int(customer_id)),
            title=safe_title,
            message=safe_message,
            severity=str(severity or "info")[:32],
            starts_at=None,
            expires_at=datetime.utcnow() + timedelta(days=max(1, int(expires_days))),
            is_active=True,
            created_by_customer_id=None,
            created_by_email=APP_AUTOMATED_NOTIFICATION_SENDER,
        )
        db.add(row)
    except Exception as exc:
        print(f"[IN_APP_NOTIFY] Nepodařilo se vytvořit oznámení pro user {customer_id}: {exc}")


def notify_owner_service_access_requested(
    db: Session,
    *,
    owner_customer_id: int,
    service: Customer,
    vehicle: Vehicle,
    request_message: Optional[str] = None,
) -> None:
    from .service_access import masked_plate, masked_vin

    service_disp = (service.name or service.email or "Servis").strip()
    vin_m = masked_vin(getattr(vehicle, "vin", None))
    plate_m = masked_plate(getattr(vehicle, "plate", None))
    vref = " ".join(x for x in [plate_m, vin_m] if x) or vehicle_label(vehicle)
    extra = ""
    if request_message and str(request_message).strip():
        extra = f"\n\nZpráva od servisu: {str(request_message).strip()[:500]}"
    create_user_in_app_notification(
        db,
        customer_id=int(owner_customer_id),
        title="Žádost servisu o přístup",
        message=(
            f"{service_disp} žádá o přístup k vozidlu ({vref}). "
            f"Schválení proveďte po přihlášení v aplikaci {APP_DISPLAY_NAME} v detailu vozidla (záložka Servis / žádosti o přístup)."
            f"{extra}"
        ),
        severity="info",
    )


def notify_service_owner_granted_direct_access(
    db: Session,
    *,
    service_customer_id: int,
    vehicle: Vehicle,
    owner: Customer,
) -> None:
    """Majitel udělil servisu přístup bez čekání na pending žádost."""
    vlabel = vehicle_label(vehicle)
    owner_disp = (owner.name or owner.email or "Majitel").strip()
    create_user_in_app_notification(
        db,
        customer_id=int(service_customer_id),
        title="Nový přístup k vozidlu",
        message=(
            f"{owner_disp} vám udělil přístup k vozidlu {vlabel}. "
            f"Najdete ho v servisním workspace mezi schválenými vozidly."
        ),
        severity="info",
    )


def notify_service_access_decided(
    db: Session,
    *,
    service_customer_id: int,
    vehicle: Vehicle,
    approved: bool,
    owner: Optional[Customer] = None,
) -> None:
    vlabel = vehicle_label(vehicle)
    owner_bit = ""
    if owner:
        owner_bit = (owner.name or owner.email or "Majitel").strip()
    if approved:
        title = "Přístup ke vozidlu schválen"
        msg = (
            f"Majitel{' (' + owner_bit + ')' if owner_bit else ''} schválil přístup k vozidlu {vlabel}. "
            f"Můžete pokračovat v servisním workspace."
        )
    else:
        title = "Žádost o přístup zamítnuta"
        msg = (
            f"Majitel{' (' + owner_bit + ')' if owner_bit else ''} zamítl žádost o přístup k vozidlu {vlabel}."
        )
    create_user_in_app_notification(
        db,
        customer_id=int(service_customer_id),
        title=title,
        message=msg,
        severity="warning" if not approved else "info",
    )


def notify_owner_service_quote_ready(
    db: Session,
    *,
    owner_customer_id: int,
    service: Customer,
    vehicle: Vehicle,
    quote: ServiceQuote,
    public_quote_url: Optional[str] = None,
) -> None:
    service_disp = (service.name or service.email or "Servis").strip()
    vlabel = vehicle_label(vehicle)
    total = float(getattr(quote, "total_price", None) or 0)
    amount = f"{total:,.2f} Kč".replace(",", " ").replace(".", ",")
    link_suffix = f"\n\nVeřejný odkaz pro schválení: {public_quote_url}" if public_quote_url else ""
    create_user_in_app_notification(
        db,
        customer_id=int(owner_customer_id),
        title="Nová cenová nabídka od servisu",
        message=(
            f"{service_disp} připravil cenovou nabídku pro vozidlo {vlabel} ve výši {amount}. "
            f"Nabídku můžete otevřít a schválit nebo odmítnout.{link_suffix}"
        ),
        severity="info",
    )


def notify_service_quote_decided(
    db: Session,
    *,
    service_customer_id: int,
    vehicle: Vehicle,
    quote: ServiceQuote,
    approved: bool,
    owner: Optional[Customer] = None,
) -> None:
    owner_disp = (owner.name or owner.email or "Klient").strip() if owner else "Klient"
    vlabel = vehicle_label(vehicle)
    total = float(getattr(quote, "total_price", None) or 0)
    amount = f"{total:,.2f} Kč".replace(",", " ").replace(".", ",")
    if approved:
        title = "Klient schválil cenovou nabídku"
        message = f"{owner_disp} schválil nabídku pro vozidlo {vlabel} ve výši {amount}."
        severity = "info"
    else:
        title = "Klient odmítl cenovou nabídku"
        message = f"{owner_disp} odmítl nabídku pro vozidlo {vlabel} ve výši {amount}."
        severity = "warning"
    create_user_in_app_notification(
        db,
        customer_id=int(service_customer_id),
        title=title,
        message=message,
        severity=severity,
    )


def notify_owner_service_invoice_issued(
    db: Session,
    *,
    owner_customer_id: int,
    service: Customer,
    vehicle: Optional[Vehicle],
    invoice: ServiceInvoice,
) -> None:
    service_disp = (service.name or service.email or "Servis").strip()
    vlabel = vehicle_label(vehicle) if vehicle is not None else "vozidlo bez přiřazení"
    total = float(getattr(invoice, "total", None) or 0)
    amount = f"{total:,.2f} {str(getattr(invoice, 'currency', None) or 'CZK')}".replace(",", " ").replace(".", ",")
    invoice_number = str(getattr(invoice, "invoice_number", None) or "bez čísla")
    create_user_in_app_notification(
        db,
        customer_id=int(owner_customer_id),
        title="Servis vystavil fakturu",
        message=(
            f"{service_disp} vystavil fakturu {invoice_number} k vozidlu {vlabel} "
            f"v celkové částce {amount}."
        ),
        severity="info",
    )
