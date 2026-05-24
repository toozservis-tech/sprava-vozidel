"""
Shared schemas and helper functions extracted from src.server.main.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unicodedata
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import func, or_

from src.core.branding import APP_DISPLAY_NAME, APP_EXPORT_DISPLAY_NAME
from src.core.datetime_cz import format_prague_generated_label
from src.modules.vehicle_hub.models import (
    BotCommand,
    Customer,
    CustomerCommand,
    AdminCustomerChangeEvent,
    CustomerDeletionLabel,
    CustomerSecuritySettings,
    EmailNotificationLog,
    GlobalAuditLog,
    Instance,
    License,
    LicenseAuditLog,
    PushSubscription,
    Reminder as ReminderModel,
    Reservation as ReservationModel,
    SecurityAccessLog,
    SecurityBlockedIp,
    ServiceCustomerInvite,
    ServiceCustomerLink,
    ServiceDocumentIngestion,
    ServiceIntake,
    ServiceRecord as ServiceRecordModel,
    ServiceRegistrationRequest,
    Tenant,
    VehicleOwnership,
    Vehicle as VehicleModel,
)
from src.modules.vehicle_hub.ownership import get_owned_vehicle_ids, get_owned_vehicle_rows
from src.modules.vehicle_hub.account_state import ensure_customer_account_state_schema


try:
    from VERSION import __version__, __version_name__, __build_date__, __update_info__

    APP_VERSION = __version__
    APP_VERSION_NAME = __version_name__
    BUILD_DATE = __build_date__
    UPDATE_INFO = __update_info__
except ImportError:
    APP_VERSION = "2.1.0"
    APP_VERSION_NAME = "Správa vozidel 2.1.0"
    BUILD_DATE = "2025-01-27"
    UPDATE_INFO = "Aktualizace s vizuálními úpravami a vylepšeními"


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: str = Field(min_length=2, max_length=200)
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: str = Field(min_length=8, max_length=24)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)


class ResendVerificationEmailRequest(BaseModel):
    email: EmailStr


class ServiceRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    ico: str = Field(min_length=8, max_length=16)
    service_name: str = Field(min_length=2, max_length=200)
    responsible_person: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=6, max_length=64)
    street: str = Field(min_length=2, max_length=200)
    street_number: Optional[str] = Field(default=None, max_length=64)
    city: str = Field(min_length=2, max_length=120)
    zip: str = Field(min_length=3, max_length=32)
    dic: Optional[str] = Field(default=None, max_length=64)
    registration_purpose: str = Field(min_length=10, max_length=2000)


class ServiceRegisterResponse(BaseModel):
    request_id: int
    status: str = "pending"
    message: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    expected_role: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[dict] = None
    two_factor_required: bool = False
    challenge_token: Optional[str] = None
    challenge_expires_in: Optional[int] = None
    password_change_required: bool = False


class ServiceInviteOnboardingRequest(BaseModel):
    token: str = Field(..., min_length=12, max_length=4096)
    password: str = Field(..., min_length=8, max_length=128)


class RegisterTokenResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[dict] = None
    verification_required: bool = False
    message: Optional[str] = None
    email_sent: bool = False
    registration_email_status: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    notify_email: bool = True
    notify_sms: bool = False
    notify_stk: bool = True
    notify_oil: bool = True
    notify_general: bool = True
    role: str = "user"
    created_at: Optional[datetime] = None
    account_status: Optional[str] = None
    email_verified_at: Optional[datetime] = None
    phone_e164: Optional[str] = None
    phone_verified_at: Optional[datetime] = None
    phone_verification_status: str = "unverified"

    class Config:
        from_attributes = True

    @model_validator(mode="after")
    def _derive_phone_verification_status(self) -> UserResponse:
        if self.phone_verified_at is not None:
            object.__setattr__(self, "phone_verification_status", "verified")
        elif self.phone_e164:
            object.__setattr__(self, "phone_verification_status", "unverified")
        else:
            object.__setattr__(self, "phone_verification_status", "invalid")
        return self


class UserUpdate(BaseModel):
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_stk: Optional[bool] = None
    notify_oil: Optional[bool] = None
    notify_general: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    confirmation_text: str = Field(min_length=3, max_length=64)
    export_downloaded: bool = False


class DeleteAccountResponse(BaseModel):
    deleted: bool
    message: str
    deleted_counts: dict


class SupportContactRequest(BaseModel):
    category: str = Field(default="obecné", max_length=64)
    subject: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=10, max_length=4000)
    phone: Optional[str] = Field(default=None, max_length=64)
    include_diagnostics: bool = True
    page_url: Optional[str] = Field(default=None, max_length=500)
    user_agent: Optional[str] = Field(default=None, max_length=600)


class TwoFactorLoginVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=6, max_length=12)


class SecuritySettingsResponse(BaseModel):
    two_factor_enabled: bool
    totp_configured: bool
    biometric_enabled: bool
    biometric_preferred: bool


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    digits: int
    period_seconds: int
    message: str


class TotpEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class TotpDisableRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=12)


class BiometricSecurityPreferenceRequest(BaseModel):
    enabled: bool
    preferred: Optional[bool] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_customer_by_email(db, email: str):
    ensure_customer_account_state_schema(db)
    normalized_email = normalize_email(email)
    return db.query(Customer).filter(func.lower(Customer.email) == normalized_email).first()


def get_active_ip_block(db, ip_address: Optional[str]) -> Optional[SecurityBlockedIp]:
    if not ip_address:
        return None

    now = datetime.utcnow()
    block = (
        db.query(SecurityBlockedIp)
        .filter(
            SecurityBlockedIp.ip_address == ip_address,
            SecurityBlockedIp.is_active.is_(True),
        )
        .order_by(SecurityBlockedIp.blocked_at.desc())
        .first()
    )
    if not block:
        return None

    if block.expires_at and block.expires_at <= now:
        block.is_active = False
        block.unblocked_at = now
        db.commit()
        return None

    return block


def normalize_ico(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits or None


ACCOUNT_DELETE_CONFIRM_TOKENS = {
    "SMAZAT UCET",
    "DELETE ACCOUNT",
}


def normalize_delete_confirmation(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = " ".join(normalized.strip().upper().split())
    return normalized


def safe_filename(value: str, fallback: str, max_length: int = 80) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = fallback
    normalized = unicodedata.normalize("NFKD", raw)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_", " "} else "_" for ch in normalized)
    normalized = "_".join(normalized.split())
    normalized = normalized.strip("._")[:max_length]
    return normalized or fallback


def serialize_export_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def model_to_export_dict(row) -> dict:
    payload: dict = {}
    for column in row.__table__.columns:
        payload[column.name] = serialize_export_value(getattr(row, column.name))
    return payload


def build_vehicle_export_pdf(
    output_path: Path,
    *,
    customer: Customer,
    vehicle: VehicleModel,
    records: list[ServiceRecordModel],
    reminders: list[ReminderModel],
    reservations: list[ReservationModel],
) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Export PDF není dostupný (chybí reportlab): {exc}",
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ExportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ExportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        textColor=colors.HexColor("#475569"),
        alignment=TA_CENTER,
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "ExportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#1e293b"),
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=6,
    )
    text_style = ParagraphStyle(
        "ExportText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
    )

    def _fmt_dt(value) -> str:
        if not value:
            return "-"
        if isinstance(value, datetime):
            return value.strftime("%d.%m.%Y %H:%M")
        if isinstance(value, date):
            return value.strftime("%d.%m.%Y")
        return str(value)

    vehicle_name = vehicle.nickname or f"{vehicle.brand or ''} {vehicle.model or ''}".strip() or f"Vozidlo #{vehicle.id}"
    owner_text = customer.name or customer.email

    story = [
        Paragraph(f"{APP_EXPORT_DISPLAY_NAME} • Export vozidla", title_style),
        Paragraph(
            f"Generováno {format_prague_generated_label()} pro účet {customer.email}",
            subtitle_style,
        ),
        Paragraph("1) Identifikace vozidla", section_style),
    ]

    vehicle_table_data = [
        ["Název", vehicle_name],
        ["SPZ", vehicle.plate or "-"],
        ["VIN", vehicle.vin or "-"],
        ["Značka / Model", f"{vehicle.brand or '-'} / {vehicle.model or '-'}"],
        ["Rok výroby", str(vehicle.year) if vehicle.year else "-"],
        ["Motor", vehicle.engine or "-"],
        ["Platnost STK", _fmt_dt(vehicle.stk_valid_until)],
        ["Pojištění", vehicle.insurance_provider or "-"],
        ["Platnost pojištění", _fmt_dt(vehicle.insurance_valid_until)],
        ["Vlastník účtu", owner_text or "-"],
        ["Poznámky", vehicle.notes or "-"],
    ]
    vehicle_table = Table(vehicle_table_data, colWidths=[52 * mm, 120 * mm])
    vehicle_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(vehicle_table)

    story.append(Paragraph("2) Servisní záznamy", section_style))
    if records:
        service_table_data = [["Datum", "Km", "Kategorie", "Popis", "Cena"]]
        for row in records:
            service_table_data.append(
                [
                    _fmt_dt(row.performed_at),
                    str(row.mileage) if row.mileage is not None else "-",
                    row.category or "-",
                    row.description or "-",
                    (f"{row.price:,.2f} CZK".replace(",", " ") if row.price is not None else "-"),
                ]
            )
        service_table = Table(service_table_data, colWidths=[28 * mm, 20 * mm, 26 * mm, 78 * mm, 26 * mm])
        service_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d9e6")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(service_table)
        for row in records:
            if row.note:
                story.append(Spacer(1, 2))
                story.append(Paragraph(f"Poznámka ({_fmt_dt(row.performed_at)}): {row.note}", text_style))
    else:
        story.append(Paragraph("U vozidla zatím nejsou evidovány žádné servisní záznamy.", text_style))

    story.append(Paragraph("3) Připomínky", section_style))
    if reminders:
        for reminder in reminders:
            reminder_text = (
                f"• [{reminder.type}] {reminder.text or '-'} "
                f"(termín: {_fmt_dt(reminder.due_date)}, metoda: {reminder.notification_method or 'globální'})"
            )
            story.append(Paragraph(reminder_text, text_style))
    else:
        story.append(Paragraph("K vozidlu nejsou přiřazeny žádné připomínky.", text_style))

    story.append(Paragraph("4) Rezervace", section_style))
    if reservations:
        for reservation in reservations:
            reservation_text = (
                f"• {reservation.service_type or 'Servis'} | "
                f"{_fmt_dt(reservation.start_datetime)} - {_fmt_dt(reservation.end_datetime)} | "
                f"stav: {reservation.status or '-'}"
            )
            story.append(Paragraph(reservation_text, text_style))
            if reservation.note:
                story.append(Paragraph(f"Poznámka: {reservation.note}", text_style))
    else:
        story.append(Paragraph("K vozidlu nejsou evidovány žádné rezervace.", text_style))

    doc.build(story)


def bulk_delete(query) -> int:
    return int(query.delete(synchronize_session=False) or 0)


def parse_email_targets(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    targets: list[str] = []
    for part in str(raw_value).split(","):
        email = normalize_email(part)
        if email and "@" in email:
            targets.append(email)
    return targets


def get_registration_alert_recipients(db) -> list[str]:
    recipients: set[str] = set()

    recipients.update(parse_email_targets(os.getenv("REGISTRATION_ALERT_EMAILS", "")))
    recipients.update(parse_email_targets(os.getenv("DEVELOPER_ALERT_EMAIL", "")))

    admin_emails = (
        db.query(Customer.email)
        .filter(Customer.role.in_(["developer_admin", "admin"]))
        .all()
    )
    for row in admin_emails:
        email = normalize_email(row[0] if row else "")
        if email:
            recipients.add(email)

    return sorted(recipients)


def send_registration_alert_email(
    db,
    *,
    registration_type: str,
    account_email: str,
    account_name: Optional[str] = None,
    account_ico: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    result = {
        "sent": False,
        "status": "skipped",
        "recipients": [],
        "error": None,
    }
    try:
        recipients = get_registration_alert_recipients(db)
        result["recipients"] = recipients
        if not recipients:
            result["status"] = "no_recipients"
            return result

        from src.modules.email_client.service import EmailMessage, EmailService
        from src.modules.email_client.templates import render_email_layout, render_panel

        email_service = EmailService()
        if not email_service.is_configured():
            result["status"] = "smtp_not_configured"
            return result

        stamp = format_prague_generated_label()
        safe_name = (account_name or "").strip() or "-"
        safe_ico = normalize_ico(account_ico) or "-"
        safe_type = "servis" if str(registration_type).lower() == "service" else "uživatel"
        meta = metadata or {}

        antifraud_rows: list[tuple[str, str]] = []
        if meta.get("email_status") is not None:
            antifraud_rows.append(("Stav e-mailu", str(meta["email_status"])))
        if meta.get("phone_status") is not None:
            antifraud_rows.append(("Stav telefonu", str(meta["phone_status"])))
        if meta.get("fraud_score") is not None:
            antifraud_rows.append(("Fraud score", str(meta["fraud_score"])))
        if meta.get("risk_flags") is not None:
            antifraud_rows.append(("Risk flags", str(meta["risk_flags"])))
        if meta.get("registration_ip") is not None:
            antifraud_rows.append(("Registr. IP", str(meta["registration_ip"])))
        if meta.get("registration_user_agent") is not None:
            antifraud_rows.append(("User-Agent", str(meta["registration_user_agent"])[:500]))
        if meta.get("tenant_id") is not None:
            antifraud_rows.append(("tenant_id", str(meta["tenant_id"])))
        if meta.get("customer_id") is not None:
            antifraud_rows.append(("customer_id", str(meta["customer_id"])))
        if meta.get("role") is not None:
            antifraud_rows.append(("role", str(meta["role"])))

        detail_lines = []
        for key, value in meta.items():
            if value is None:
                continue
            detail_lines.append(f"- {key}: {value}")
        detail_block = "\n".join(detail_lines) if detail_lines else "- bez doplňujících údajů"

        if str(registration_type).lower() == "service":
            subject = f"[{APP_DISPLAY_NAME}] Nová žádost o registraci servisu"
        else:
            subject = f"[{APP_DISPLAY_NAME}] Nová registrace ({safe_type})"

        is_service_registration = str(registration_type).lower() == "service"
        lead_line = (
            f"Byla přijata nová žádost o servisní účet v aplikaci {APP_DISPLAY_NAME}."
            if is_service_registration
            else f"Byla vytvořena nová registrace v aplikaci {APP_DISPLAY_NAME}."
        )
        body = f"""{lead_line}

Typ registrace: {safe_type}
Email účtu: {account_email}
Název/Jméno: {safe_name}
IČO: {safe_ico}
Čas: {stamp}

Detaily:
{detail_block}
"""

        html_body = render_email_layout(
            title="Nová žádost o registraci servisu" if is_service_registration else "Nová registrace",
            subtitle=(
                "Žádost čeká na schválení v administraci."
                if is_service_registration
                else "Interní oznámení o novém účtu v aplikaci."
            ),
            intro=(
                f"Byla přijata nová žádost o servisní účet v aplikaci {APP_DISPLAY_NAME}."
                if is_service_registration
                else f"Byla vytvořena nová registrace v aplikaci {APP_DISPLAY_NAME}."
            ),
            panels=[
                render_panel(
                    title="Souhrn registrace",
                    rows=[
                        ("Typ registrace", safe_type),
                        ("Email účtu", account_email),
                        ("Název/Jméno", safe_name),
                        ("IČO", safe_ico),
                        ("Čas", stamp),
                    ],
                    accent="#3b82f6",
                    tone="#eff6ff",
                ),
                *(
                    [
                        render_panel(
                            title="Antifraud / registrace",
                            rows=antifraud_rows,
                            accent="#f59e0b",
                            tone="#fffbeb",
                        )
                    ]
                    if antifraud_rows
                    else []
                ),
                render_panel(
                    title="Detaily",
                    message=detail_block,
                    accent="#64748b",
                    tone="#f8fafc",
                ),
            ],
            accent="#f59e0b",
            footer_note="Interní oznámení pro tým Správa vozidel.",
        )

        message = EmailMessage(
            to=recipients,
            subject=subject,
            body=body,
            html_body=html_body,
        )
        email_service.send_email(message)

        result["sent"] = True
        result["status"] = "sent"
        return result
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        print(f"[REGISTER] Developer alert email selhal: {exc}")
        return result


def export_current_customer_bundle(customer: Customer, *, email: str, db, app_version: str) -> tuple[Path, Path, str, int]:
    normalized_email = normalize_email(customer.email or email)
    vehicles = list(reversed(get_owned_vehicle_rows(db, customer, tenant_id=customer.tenant_id)))
    vehicle_ids = [v.id for v in vehicles]
    vehicle_record_condition = ServiceRecordModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ServiceRecordModel.id == -1)
    vehicle_reminder_condition = ReminderModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ReminderModel.id == -1)
    vehicle_reservation_condition = ReservationModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ReservationModel.id == -1)
    vehicle_intake_condition = ServiceIntake.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ServiceIntake.id == -1)
    vehicle_document_condition = ServiceDocumentIngestion.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ServiceDocumentIngestion.id == -1)
    vehicle_customer_command_condition = CustomerCommand.vehicle_id.in_(vehicle_ids) if vehicle_ids else (CustomerCommand.id == -1)

    service_records = db.query(ServiceRecordModel).filter(
        or_(
            ServiceRecordModel.user_id == customer.id,
            vehicle_record_condition,
        )
    ).order_by(ServiceRecordModel.performed_at.asc()).all()

    reminders = db.query(ReminderModel).filter(
        or_(
            ReminderModel.customer_id == customer.id,
            vehicle_reminder_condition,
        )
    ).order_by(ReminderModel.created_at.asc()).all()

    reservations = db.query(ReservationModel).filter(
        or_(
            ReservationModel.customer_id == customer.id,
            ReservationModel.service_id == customer.id,
            vehicle_reservation_condition,
        )
    ).order_by(ReservationModel.start_datetime.asc()).all()

    service_intakes = db.query(ServiceIntake).filter(
        or_(
            ServiceIntake.customer_id == customer.id,
            ServiceIntake.service_id == customer.id,
            vehicle_intake_condition,
        )
    ).order_by(ServiceIntake.created_at.asc()).all()

    service_links = db.query(ServiceCustomerLink).filter(
        or_(
            ServiceCustomerLink.service_customer_id == customer.id,
            ServiceCustomerLink.customer_id == customer.id,
        )
    ).order_by(ServiceCustomerLink.created_at.asc()).all()

    service_invites = db.query(ServiceCustomerInvite).filter(
        or_(
            ServiceCustomerInvite.service_customer_id == customer.id,
            ServiceCustomerInvite.linked_customer_id == customer.id,
            func.lower(ServiceCustomerInvite.invite_email) == normalized_email,
        )
    ).order_by(ServiceCustomerInvite.created_at.asc()).all()

    service_documents = db.query(ServiceDocumentIngestion).filter(
        or_(
            ServiceDocumentIngestion.customer_id == customer.id,
            ServiceDocumentIngestion.service_customer_id == customer.id,
            vehicle_document_condition,
        )
    ).order_by(ServiceDocumentIngestion.created_at.asc()).all()

    email_logs = db.query(EmailNotificationLog).filter(
        or_(
            EmailNotificationLog.customer_id == customer.id,
            func.lower(EmailNotificationLog.email) == normalized_email,
        )
    ).order_by(EmailNotificationLog.sent_at.asc()).all()

    push_subscriptions = db.query(PushSubscription).filter(
        PushSubscription.customer_id == customer.id
    ).order_by(PushSubscription.created_at.asc()).all()

    security_logs = db.query(SecurityAccessLog).filter(
        or_(
            SecurityAccessLog.customer_id == customer.id,
            func.lower(SecurityAccessLog.user_email) == normalized_email,
        )
    ).order_by(SecurityAccessLog.created_at.asc()).all()

    registration_requests = db.query(ServiceRegistrationRequest).filter(
        func.lower(ServiceRegistrationRequest.email) == normalized_email
    ).order_by(ServiceRegistrationRequest.created_at.asc()).all()

    bot_commands = db.query(BotCommand).filter(
        or_(
            BotCommand.user_id == customer.id,
            func.lower(BotCommand.user_email) == normalized_email,
        )
    ).order_by(BotCommand.created_at.asc()).all()

    customer_commands = db.query(CustomerCommand).filter(
        or_(
            func.lower(CustomerCommand.customer_email) == normalized_email,
            vehicle_customer_command_condition,
        )
    ).order_by(CustomerCommand.created_at.asc()).all()

    security_settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )

    export_payload = {
        "meta": {
            "generated_at_utc": datetime.utcnow().isoformat(),
            "app": APP_DISPLAY_NAME,
            "version": app_version,
            "customer_id": customer.id,
            "tenant_id": customer.tenant_id,
            "email": customer.email,
        },
        "account": model_to_export_dict(customer),
        "security_settings": model_to_export_dict(security_settings) if security_settings else None,
        "counts": {
            "vehicles": len(vehicles),
            "service_records": len(service_records),
            "reminders": len(reminders),
            "reservations": len(reservations),
            "service_intakes": len(service_intakes),
            "service_links": len(service_links),
            "service_invites": len(service_invites),
            "service_documents": len(service_documents),
            "email_logs": len(email_logs),
            "push_subscriptions": len(push_subscriptions),
            "security_logs": len(security_logs),
            "service_registration_requests": len(registration_requests),
            "bot_commands": len(bot_commands),
            "customer_commands": len(customer_commands),
        },
        "vehicles": [model_to_export_dict(v) for v in vehicles],
        "service_records": [model_to_export_dict(v) for v in service_records],
        "reminders": [model_to_export_dict(v) for v in reminders],
        "reservations": [model_to_export_dict(v) for v in reservations],
        "service_intakes": [model_to_export_dict(v) for v in service_intakes],
        "service_links": [model_to_export_dict(v) for v in service_links],
        "service_invites": [model_to_export_dict(v) for v in service_invites],
        "service_documents": [model_to_export_dict(v) for v in service_documents],
        "email_logs": [model_to_export_dict(v) for v in email_logs],
        "push_subscriptions": [model_to_export_dict(v) for v in push_subscriptions],
        "security_logs": [model_to_export_dict(v) for v in security_logs],
        "service_registration_requests": [model_to_export_dict(v) for v in registration_requests],
        "bot_commands": [model_to_export_dict(v) for v in bot_commands],
        "customer_commands": [model_to_export_dict(v) for v in customer_commands],
    }

    tmp_dir_path = Path(tempfile.mkdtemp(prefix="sprava_vozidel_export_"))
    data_dir = tmp_dir_path / "data"
    pdf_dir = tmp_dir_path / "vozidla_pdf"
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    export_json_path = data_dir / "kompletni_export.json"
    account_summary_path = data_dir / "ucet_prehled.json"
    readme_path = tmp_dir_path / "README.txt"

    export_json_path.write_text(
        json.dumps(export_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    account_summary = {
        "generated_at_utc": export_payload["meta"]["generated_at_utc"],
        "email": customer.email,
        "name": customer.name,
        "customer_id": customer.id,
        "tenant_id": customer.tenant_id,
        "counts": export_payload["counts"],
    }
    account_summary_path.write_text(
        json.dumps(account_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    readme_path.write_text(
        (
            f"{APP_EXPORT_DISPLAY_NAME} - Export dat\n"
            "\n"
            "Obsah archivu:\n"
            "- data/kompletni_export.json  (kompletní strojově čitelný export)\n"
            "- data/ucet_prehled.json      (stručný přehled účtu)\n"
            "- vozidla_pdf/*.pdf           (strukturovaný report pro každé vozidlo)\n"
            "\n"
            "Doporučení: Před smazáním účtu archiv bezpečně uložte.\n"
        ),
        encoding="utf-8",
    )

    reminders_by_vehicle: dict[int, list[ReminderModel]] = {}
    for reminder in reminders:
        if reminder.vehicle_id:
            reminders_by_vehicle.setdefault(int(reminder.vehicle_id), []).append(reminder)

    reservations_by_vehicle: dict[int, list[ReservationModel]] = {}
    for reservation in reservations:
        if reservation.vehicle_id:
            reservations_by_vehicle.setdefault(int(reservation.vehicle_id), []).append(reservation)

    records_by_vehicle: dict[int, list[ServiceRecordModel]] = {}
    for record in service_records:
        if record.vehicle_id:
            records_by_vehicle.setdefault(int(record.vehicle_id), []).append(record)

    for vehicle in vehicles:
        vehicle_identifier = vehicle.plate or vehicle.nickname or f"vozidlo_{vehicle.id}"
        safe_identifier = safe_filename(vehicle_identifier, fallback=f"vozidlo_{vehicle.id}")
        pdf_name = f"{vehicle.id:04d}_{safe_identifier}.pdf"
        pdf_path = pdf_dir / pdf_name
        build_vehicle_export_pdf(
            pdf_path,
            customer=customer,
            vehicle=vehicle,
            records=records_by_vehicle.get(vehicle.id, []),
            reminders=reminders_by_vehicle.get(vehicle.id, []),
            reservations=reservations_by_vehicle.get(vehicle.id, []),
        )

    export_file_name = f"sprava_vozidel_export_{customer.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = tmp_dir_path / export_file_name
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in sorted(tmp_dir_path.rglob("*")):
            if file_path == zip_path:
                continue
            if file_path.is_file():
                zip_file.write(file_path, arcname=str(file_path.relative_to(tmp_dir_path)))

    return tmp_dir_path, zip_path, export_file_name, len(vehicles)


def delete_customer_account(customer: Customer, *, email: str, db) -> dict:
    normalized_email = normalize_email(customer.email or email)
    vehicle_ids = sorted(get_owned_vehicle_ids(db, customer, tenant_id=customer.tenant_id))

    deleted_counts: dict[str, int] = {}
    tenant_id = customer.tenant_id
    no_vehicle_match_docs = ServiceDocumentIngestion.id == -1
    no_vehicle_match_intakes = ServiceIntake.id == -1
    no_vehicle_match_reservations = ReservationModel.id == -1
    no_vehicle_match_reminders = ReminderModel.id == -1
    no_vehicle_match_records = ServiceRecordModel.id == -1
    no_vehicle_match_commands = CustomerCommand.id == -1
    no_vehicle_match_vehicles = VehicleModel.id == -1

    vehicle_docs_condition = ServiceDocumentIngestion.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_docs
    vehicle_intakes_condition = ServiceIntake.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_intakes
    vehicle_reservation_condition = ReservationModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_reservations
    vehicle_reminder_condition = ReminderModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_reminders
    vehicle_record_condition = ServiceRecordModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_records
    vehicle_command_condition = CustomerCommand.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_commands
    vehicle_self_condition = VehicleModel.id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_vehicles

    db.query(ServiceRegistrationRequest).filter(
        ServiceRegistrationRequest.reviewed_by_customer_id == customer.id
    ).update({ServiceRegistrationRequest.reviewed_by_customer_id: None}, synchronize_session=False)
    db.query(ServiceRegistrationRequest).filter(
        ServiceRegistrationRequest.approved_customer_id == customer.id
    ).update({ServiceRegistrationRequest.approved_customer_id: None}, synchronize_session=False)
    if tenant_id:
        db.query(ServiceRegistrationRequest).filter(
            ServiceRegistrationRequest.approved_tenant_id == tenant_id
        ).update({ServiceRegistrationRequest.approved_tenant_id: None}, synchronize_session=False)

    db.query(VehicleOwnership).filter(VehicleOwnership.assigned_by_customer_id == customer.id).update(
        {VehicleOwnership.assigned_by_customer_id: None},
        synchronize_session=False,
    )
    db.query(GlobalAuditLog).filter(GlobalAuditLog.actor_user_id == customer.id).update(
        {GlobalAuditLog.actor_user_id: None},
        synchronize_session=False,
    )
    deleted_counts["license_audit_logs_user"] = bulk_delete(
        db.query(LicenseAuditLog).filter(LicenseAuditLog.user_id == customer.id)
    )

    deleted_counts["service_documents"] = bulk_delete(
        db.query(ServiceDocumentIngestion).filter(
            or_(
                ServiceDocumentIngestion.customer_id == customer.id,
                ServiceDocumentIngestion.service_customer_id == customer.id,
                vehicle_docs_condition,
            )
        )
    )
    deleted_counts["service_intakes"] = bulk_delete(
        db.query(ServiceIntake).filter(
            or_(
                ServiceIntake.customer_id == customer.id,
                ServiceIntake.service_id == customer.id,
                vehicle_intakes_condition,
            )
        )
    )
    deleted_counts["reservations"] = bulk_delete(
        db.query(ReservationModel).filter(
            or_(
                ReservationModel.customer_id == customer.id,
                ReservationModel.service_id == customer.id,
                vehicle_reservation_condition,
            )
        )
    )
    deleted_counts["reminders"] = bulk_delete(
        db.query(ReminderModel).filter(
            or_(
                ReminderModel.customer_id == customer.id,
                vehicle_reminder_condition,
            )
        )
    )
    deleted_counts["service_records"] = bulk_delete(
        db.query(ServiceRecordModel).filter(
            or_(
                ServiceRecordModel.user_id == customer.id,
                vehicle_record_condition,
            )
        )
    )
    deleted_counts["service_links"] = bulk_delete(
        db.query(ServiceCustomerLink).filter(
            or_(
                ServiceCustomerLink.service_customer_id == customer.id,
                ServiceCustomerLink.customer_id == customer.id,
            )
        )
    )
    deleted_counts["service_invites"] = bulk_delete(
        db.query(ServiceCustomerInvite).filter(
            or_(
                ServiceCustomerInvite.service_customer_id == customer.id,
                ServiceCustomerInvite.linked_customer_id == customer.id,
                func.lower(ServiceCustomerInvite.invite_email) == normalized_email,
            )
        )
    )
    deleted_counts["email_logs"] = bulk_delete(
        db.query(EmailNotificationLog).filter(
            or_(
                EmailNotificationLog.customer_id == customer.id,
                func.lower(EmailNotificationLog.email) == normalized_email,
            )
        )
    )
    deleted_counts["push_subscriptions"] = bulk_delete(
        db.query(PushSubscription).filter(PushSubscription.customer_id == customer.id)
    )
    deleted_counts["security_logs"] = bulk_delete(
        db.query(SecurityAccessLog).filter(
            or_(
                SecurityAccessLog.customer_id == customer.id,
                func.lower(SecurityAccessLog.user_email) == normalized_email,
            )
        )
    )
    deleted_counts["bot_commands"] = bulk_delete(
        db.query(BotCommand).filter(
            or_(
                BotCommand.user_id == customer.id,
                func.lower(BotCommand.user_email) == normalized_email,
            )
        )
    )
    deleted_counts["customer_commands"] = bulk_delete(
        db.query(CustomerCommand).filter(
            or_(
                func.lower(CustomerCommand.customer_email) == normalized_email,
                vehicle_command_condition,
            )
        )
    )
    deleted_counts["admin_customer_change_events"] = bulk_delete(
        db.query(AdminCustomerChangeEvent).filter(AdminCustomerChangeEvent.customer_id == customer.id)
    )
    deleted_counts["customer_deletion_labels"] = bulk_delete(
        db.query(CustomerDeletionLabel).filter(CustomerDeletionLabel.customer_id == customer.id)
    )
    deleted_counts["service_registration_requests"] = bulk_delete(
        db.query(ServiceRegistrationRequest).filter(
            func.lower(ServiceRegistrationRequest.email) == normalized_email
        )
    )
    deleted_counts["vehicle_ownerships"] = bulk_delete(
        db.query(VehicleOwnership).filter(
            VehicleOwnership.customer_id == customer.id
        )
    )
    deleted_counts["security_settings"] = bulk_delete(
        db.query(CustomerSecuritySettings).filter(CustomerSecuritySettings.customer_id == customer.id)
    )
    deleted_counts["vehicles"] = bulk_delete(
        db.query(VehicleModel).filter(vehicle_self_condition)
    )
    deleted_counts["customers"] = bulk_delete(
        db.query(Customer).filter(Customer.id == customer.id)
    )

    if tenant_id:
        remaining_customers = db.query(Customer.id).filter(Customer.tenant_id == tenant_id).count()
        if remaining_customers == 0:
            deleted_counts["tenant_service_documents"] = bulk_delete(
                db.query(ServiceDocumentIngestion).filter(ServiceDocumentIngestion.service_tenant_id == tenant_id)
            )
            deleted_counts["tenant_records"] = bulk_delete(
                db.query(ServiceRecordModel).filter(ServiceRecordModel.tenant_id == tenant_id)
            )
            deleted_counts["tenant_reminders"] = bulk_delete(
                db.query(ReminderModel).filter(ReminderModel.tenant_id == tenant_id)
            )
            deleted_counts["tenant_reservations"] = bulk_delete(
                db.query(ReservationModel).filter(ReservationModel.tenant_id == tenant_id)
            )
            deleted_counts["tenant_intakes"] = bulk_delete(
                db.query(ServiceIntake).filter(ServiceIntake.tenant_id == tenant_id)
            )
            deleted_counts["tenant_vehicles"] = bulk_delete(
                db.query(VehicleModel).filter(VehicleModel.tenant_id == tenant_id)
            )
            deleted_counts["tenant_vehicle_ownerships"] = bulk_delete(
                db.query(VehicleOwnership).filter(VehicleOwnership.tenant_id == tenant_id)
            )
            deleted_counts["tenant_push_subscriptions"] = bulk_delete(
                db.query(PushSubscription).filter(PushSubscription.tenant_id == tenant_id)
            )
            deleted_counts["tenant_email_logs"] = bulk_delete(
                db.query(EmailNotificationLog).filter(EmailNotificationLog.tenant_id == tenant_id)
            )
            deleted_counts["tenant_security_logs"] = bulk_delete(
                db.query(SecurityAccessLog).filter(SecurityAccessLog.tenant_id == tenant_id)
            )
            deleted_counts["tenant_bot_commands"] = bulk_delete(
                db.query(BotCommand).filter(BotCommand.tenant_id == tenant_id)
            )
            deleted_counts["tenant_customer_commands"] = bulk_delete(
                db.query(CustomerCommand).filter(CustomerCommand.tenant_id == tenant_id)
            )
            deleted_counts["tenant_instances"] = bulk_delete(
                db.query(Instance).filter(Instance.tenant_id == tenant_id)
            )
            deleted_counts["tenant_license"] = bulk_delete(
                db.query(License).filter(License.tenant_id == tenant_id)
            )
            deleted_counts["tenant_global_audit_log"] = bulk_delete(
                db.query(GlobalAuditLog).filter(GlobalAuditLog.tenant_id == tenant_id)
            )
            deleted_counts["tenants"] = bulk_delete(
                db.query(Tenant).filter(Tenant.id == tenant_id)
            )

    return deleted_counts


def cleanup_export_dir(tmp_dir_path: Path) -> None:
    shutil.rmtree(str(tmp_dir_path), True)
