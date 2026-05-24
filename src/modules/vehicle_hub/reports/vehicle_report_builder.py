from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import re
from typing import Any, Optional

from sqlalchemy import asc, nullslast
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR
from src.core.rbac import normalize_role
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceRecord,
    ServiceRecordAuditLog,
    Vehicle,
    VehicleInspectionHistory,
    VehiclePhotoAsset,
)
from src.modules.vehicle_hub.vehicle_photo_assets import resolve_storage_file
from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner
from src.modules.vehicle_hub.service_record_view import viewer_record_same_ownership_era

from .vehicle_report_mileage_timeline import build_vehicle_report_mileage_timeline
from .vehicle_report_models import (
    VehicleReportDocument,
    VehicleReportMode,
    VehicleReportOwner,
    VehicleReportServiceRecord,
    VehicleReportSummary,
    VehicleReportVehicle,
    VehicleServiceReportPayload,
)

FUEL_KEYWORDS = {
    "benzin": "Benzin",
    "petrol": "Benzin",
    "diesel": "Diesel",
    "nafta": "Diesel",
    "hybrid": "Hybrid",
    "phev": "Plug-in hybrid",
    "ev": "Elektro",
    "electric": "Elektro",
    "cng": "CNG",
    "lpg": "LPG",
}

TRANSMISSION_KEYWORDS = {
    "automat": "Automatická",
    "automatic": "Automatická",
    "dsg": "Automatická",
    "tiptronic": "Automatická",
    "manual": "Manuální",
    "manu": "Manuální",
}

CATEGORY_LABELS = {
    "OLEJ": "Výměna oleje",
    "FILTRY": "Filtry",
    "BRZDY": "Brzdy",
    "PNEU": "Pneumatiky",
    "STK": "STK / emise",
    "DIAGNOSTIKA": "Diagnostika",
    "KLIMATIZACE": "Klimatizace",
    "ELEKTRIKA": "Elektrika",
    "CHLADICI": "Chladicí soustava",
    "VYFUK": "Výfuk",
    "KAROSERIE": "Karoserie",
    "OSVETLENI": "Osvětlení",
    "OPRAVA": "Oprava",
    "JINE": "Jiný zásah",
}


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _isoformat(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _extract_engine_ccm(engine: Optional[str]) -> Optional[int]:
    if not engine:
        return None
    patterns = [
        r"(\d{3,4})\s*(?:ccm|cm3|cm\^3|cc)\b",
        r"\b(0\.\d|[1-9]\.\d)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, engine, re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1)
        if "." in raw:
            try:
                return int(float(raw) * 1000)
            except ValueError:
                return None
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _extract_power_kw(engine: Optional[str]) -> Optional[int]:
    if not engine:
        return None
    match = re.search(r"(\d{2,4})\s*kW\b", engine, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_keyword_value(engine: Optional[str], mapping: dict[str, str]) -> Optional[str]:
    haystack = str(engine or "").lower()
    for key, label in mapping.items():
        if key in haystack:
            return label
    return None


def _parse_attachments_payload(raw_value: Optional[str]) -> list[dict[str, Any]]:
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _record_users_by_id(db: Session, user_ids: set[int]) -> dict[int, Customer]:
    if not user_ids:
        return {}
    rows = db.query(Customer).filter(Customer.id.in_(sorted(user_ids))).all()
    return {int(row.id): row for row in rows if getattr(row, "id", None) is not None}


def _identity_label(
    user_id: Optional[int],
    *,
    users_by_id: dict[int, Customer],
    mode: VehicleReportMode,
    prefer_business_only: bool = False,
) -> Optional[str]:
    if not user_id:
        return None
    user = users_by_id.get(int(user_id))
    if not user:
        return f"Uživatel #{user_id}" if mode == VehicleReportMode.INTERNAL_AUDIT else None

    business_label = _first_non_empty(user.name, f"Uživatel #{user.id}")
    if prefer_business_only or mode != VehicleReportMode.INTERNAL_AUDIT:
        return business_label
    email = str(user.email or "").strip().lower()
    role = normalize_role(getattr(user, "role", None))
    if email:
        return f"{business_label} ({email}, role {role})"
    return f"{business_label} (role {role})"


def _build_owner_section(*, owner: Optional[Customer], mode: VehicleReportMode) -> Optional[VehicleReportOwner]:
    if owner is None or mode not in {VehicleReportMode.OWNER, VehicleReportMode.INTERNAL_AUDIT}:
        return None

    address_parts = [
        _first_non_empty(owner.street, None),
        _first_non_empty(owner.street_number, None),
        _first_non_empty(owner.zip, None),
        _first_non_empty(owner.city, None),
    ]
    address = ", ".join([part for part in address_parts if part])
    payload = VehicleReportOwner(
        label="Údaje vlastníka",
        name=_first_non_empty(owner.name, None),
        email=_first_non_empty(owner.email, None),
        phone=_first_non_empty(owner.phone, None),
        city=_first_non_empty(owner.city, None),
    )
    if mode == VehicleReportMode.INTERNAL_AUDIT:
        payload.ico = _first_non_empty(owner.ico, None)
        payload.dic = _first_non_empty(owner.dic, None)
        payload.address = address or None
    return payload


def _pick_record_source_type(record: ServiceRecord, attachments: list[dict[str, Any]]) -> str:
    for attachment in attachments:
        source_type = str(attachment.get("source_type") or "").strip().lower()
        if source_type:
            return source_type
    if record.created_by_ai:
        return "ai_import"
    return "manual"


def _attachment_summaries(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for attachment in attachments:
        summary = attachment.get("parsed_summary")
        if isinstance(summary, dict):
            summaries.append(summary)
    return summaries


def _extract_parts(attachments: list[dict[str, Any]]) -> list[str]:
    parts: list[str] = []
    for summary in _attachment_summaries(attachments):
        items = summary.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name or name in parts:
                continue
            parts.append(name)
            if len(parts) >= 8:
                return parts
    return parts


def _extract_record_totals(attachments: list[dict[str, Any]]) -> dict[str, Any]:
    for summary in _attachment_summaries(attachments):
        currency = str(summary.get("currency") or "CZK").upper()
        total = summary.get("total_with_vat")
        labor_total = summary.get("labor_total")
        materials_total = summary.get("materials_total")
        if total is None and labor_total is None and materials_total is None:
            continue
        return {
            "currency": currency,
            "total_with_vat": total,
            "labor_total": labor_total,
            "materials_total": materials_total,
        }
    return {}


def _pick_supplier_fields(
    *,
    record: ServiceRecord,
    attachments: list[dict[str, Any]],
    users_by_id: dict[int, Customer],
    mode: VehicleReportMode,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    supplier = None
    technician = None
    for summary in _attachment_summaries(attachments):
        supplier = supplier or _first_non_empty(summary.get("supplier_name"), summary.get("customer_name"))
        technician = technician or _first_non_empty(summary.get("technician_name"), summary.get("technician_initials"))

    creator = users_by_id.get(int(record.user_id)) if getattr(record, "user_id", None) else None
    if creator and normalize_role(getattr(creator, "role", None)) == "service":
        workshop = _first_non_empty(creator.name, f"Servis #{creator.id}")
        if mode == VehicleReportMode.INTERNAL_AUDIT and creator.email:
            workshop = f"{workshop} ({creator.email})"
        supplier = supplier or workshop
        return supplier, workshop, technician

    return supplier, supplier, technician


def _pick_record_title(record: ServiceRecord, attachments: list[dict[str, Any]]) -> str:
    for summary in _attachment_summaries(attachments):
        candidate = _first_non_empty(summary.get("service_summary"), summary.get("document_number"))
        if candidate:
            return candidate
    return _first_non_empty(record.description, CATEGORY_LABELS.get(str(record.category or "").upper()), f"Servisní záznam #{record.id}") or f"Servisní záznam #{record.id}"


def _verification_status(
    *,
    record: ServiceRecord,
    attachments: list[dict[str, Any]],
    audit_logs: list[ServiceRecordAuditLog],
) -> str:
    if bool(getattr(record, "is_deleted", False)):
        return "Archivováno"
    if any(summary.get("document_number") or summary.get("supplier_name") for summary in _attachment_summaries(attachments)):
        return "Ověřeno servisním dokladem"
    if audit_logs or record.snapshot_hash:
        return "Auditní stopa dostupná"
    if record.created_by_ai:
        return "Importováno AI"
    return "Ruční záznam"


def _record_audit_note(
    *,
    audit_logs: list[ServiceRecordAuditLog],
    mode: VehicleReportMode,
    users_by_id: dict[int, Customer],
) -> Optional[str]:
    if mode != VehicleReportMode.INTERNAL_AUDIT or not audit_logs:
        return None
    last_log = audit_logs[-1]
    actor = _identity_label(last_log.changed_by_user_id, users_by_id=users_by_id, mode=mode)
    pieces = [f"Poslední auditní změna: {_isoformat(last_log.created_at) or '-'}"]
    if actor:
        pieces.append(f"autor: {actor}")
    if last_log.action:
        pieces.append(f"akce: {last_log.action}")
    return " | ".join(pieces)


def _last_matching_record(records: list[VehicleReportServiceRecord], keywords: tuple[str, ...]) -> Optional[str]:
    for record in reversed(records):
        haystack = " ".join(
            [
                str(record.category or ""),
                str(record.title or ""),
                str(record.performed_work or ""),
                " ".join(record.parts),
            ]
        ).lower()
        if any(keyword in haystack for keyword in keywords):
            return record.date
    return None


def _summary_recommendations(records: list[ServiceRecord], rendered_records: list[VehicleReportServiceRecord]) -> list[str]:
    recommendations: list[str] = []
    today = date.today()
    due_records = [
        row for row in records
        if getattr(row, "next_service_due_date", None) is not None
    ]
    overdue = [row for row in due_records if row.next_service_due_date and row.next_service_due_date < today]
    upcoming = [
        row for row in due_records
        if row.next_service_due_date and today <= row.next_service_due_date <= (today + timedelta(days=45))
    ]
    if overdue:
        recommendations.append("Evidujeme alespoň jeden prošlý doporučený termín dalšího servisu.")
    elif upcoming:
        recommendations.append("Blíží se doporučený termín dalšího servisu podle evidovaných záznamů.")

    if not rendered_records:
        recommendations.append("V systému zatím nejsou evidovány žádné servisní záznamy.")
    elif not any(record.attachments_count for record in rendered_records):
        recommendations.append("Historie neobsahuje přiložené doklady; doporučeno doplnit faktury nebo zakázkové listy.")
    return recommendations


def _summary_quality_flags(rendered_records: list[VehicleReportServiceRecord]) -> list[str]:
    flags: list[str] = []
    if any(record.odometer_km is None for record in rendered_records):
        flags.append("Část historie nemá uvedený nájezd km.")
    if any(record.verification_status == "Ruční záznam" for record in rendered_records):
        flags.append("Část záznamů je vedena jako ruční zápis bez dokladu.")
    if any(not record.date for record in rendered_records):
        flags.append("Část záznamů nemá úplné datum provedení.")
    return flags


def _build_inspection_history_records(
    *,
    inspections: list[VehicleInspectionHistory],
    anomaly_notes_by_reference: dict[str, str],
) -> list[VehicleReportServiceRecord]:
    rendered: list[VehicleReportServiceRecord] = []
    for inspection in inspections:
        inspection_id = int(getattr(inspection, "id", 0) or 0)
        inspection_type = _first_non_empty(getattr(inspection, "inspection_type", None), "STK") or "STK"
        inspection_kind = _first_non_empty(getattr(inspection, "inspection_kind", None), None)
        source_name = _first_non_empty(getattr(inspection, "source", None), "kontrolatachometru.cz") or "kontrolatachometru.cz"
        protocol_number = _first_non_empty(getattr(inspection, "protocol_number", None), None)

        note_bits = [
            f"Zdroj: {source_name}",
            f"Typ: {inspection_type}",
        ]
        if inspection_kind:
            note_bits.append(f"Druh: {inspection_kind}")
        if protocol_number:
            note_bits.append(f"Protokol: {protocol_number}")
        note_bits.append("Importováno jako read-only STK historie")

        audit_note = anomaly_notes_by_reference.get(f"vehicle_inspection_history:{inspection_id}")
        rendered.append(
            VehicleReportServiceRecord(
                id=-(inspection_id or len(rendered) + 1),
                date=_isoformat(getattr(inspection, "inspection_date", None)),
                odometer_km=getattr(inspection, "odometer_km", None) or getattr(inspection, "mileage_km", None),
                category="STK / tachometr",
                title="Načteno z kontroly tachometru (MDČR)",
                performed_work=_first_non_empty(inspection_kind, inspection_type),
                parts=[],
                notes=" | ".join(bit for bit in note_bits if bit),
                attachments_count=0,
                supplier=source_name,
                workshop=source_name,
                technician=None,
                created_at=None,
                created_by=None,
                updated_at=_isoformat(getattr(inspection, "imported_at", None)),
                updated_by=None,
                source_type="stk_history",
                verification_status="Importovaná read-only STK historie",
                audit_note=audit_note,
                totals={},
            )
        )
    return rendered


def _primary_image_relative_path_for_report(*, db: Session, vehicle: Vehicle) -> Optional[str]:
    """Relativní klíč pod DATA_DIR/vehicle_photos pro PDF (existující soubor)."""
    photos_root = DATA_DIR / "vehicle_photos"
    aid = getattr(vehicle, "primary_photo_asset_id", None)
    if aid:
        row = (
            db.query(VehiclePhotoAsset)
            .filter(
                VehiclePhotoAsset.id == int(aid),
                VehiclePhotoAsset.vehicle_id == int(vehicle.id),
                VehiclePhotoAsset.deleted_at.is_(None),
            )
            .first()
        )
        if row and resolve_storage_file(photos_root, row.storage_key):
            return str(row.storage_key)
    raw = getattr(vehicle, "photo_path", None)
    if raw and str(raw).strip() and str(raw).strip() != "__primary_photo__":
        key = str(raw).strip()
        if resolve_storage_file(photos_root, key):
            return key
    return None


def _build_vehicle_section(vehicle: Vehicle, db: Session) -> VehicleReportVehicle:
    engine_text = _first_non_empty(vehicle.engine, vehicle.notes)
    return VehicleReportVehicle(
        internal_id=int(vehicle.id),
        nickname=_first_non_empty(vehicle.nickname, None),
        vin=_first_non_empty(vehicle.vin, None),
        spz=_first_non_empty(vehicle.plate, None),
        brand=_first_non_empty(vehicle.brand, None),
        model=_first_non_empty(vehicle.model, None),
        variant=_first_non_empty(vehicle.nickname, None),
        year=vehicle.year,
        first_registration_date=None,
        engine_ccm=_extract_engine_ccm(engine_text),
        power_kw=_extract_power_kw(engine_text),
        fuel_type=_extract_keyword_value(engine_text, FUEL_KEYWORDS),
        transmission=_extract_keyword_value(engine_text, TRANSMISSION_KEYWORDS),
        odometer_km=vehicle.current_mileage_km or vehicle.latest_stk_odometer_km or vehicle.last_stk_mileage_km,
        stk_valid_to=_isoformat(vehicle.stk_valid_until),
        primary_photo_path=_primary_image_relative_path_for_report(db=db, vehicle=vehicle),
    )


def build_vehicle_service_report_payload(
    *,
    db: Session,
    vehicle: Vehicle,
    current_user: Customer,
    mode: VehicleReportMode,
) -> VehicleServiceReportPayload:
    include_deleted = mode == VehicleReportMode.INTERNAL_AUDIT
    generated_at = _utc_now_iso()

    records_query = db.query(ServiceRecord).filter(ServiceRecord.vehicle_id == vehicle.id)
    if not include_deleted:
        records_query = records_query.filter(ServiceRecord.is_deleted.is_(False))
    records = (
        records_query
        .order_by(nullslast(asc(ServiceRecord.performed_at)), asc(ServiceRecord.id))
        .all()
    )

    record_ids = [int(row.id) for row in records if getattr(row, "id", None) is not None]
    audit_logs = (
        db.query(ServiceRecordAuditLog)
        .filter(ServiceRecordAuditLog.service_record_id.in_(record_ids))
        .order_by(asc(ServiceRecordAuditLog.created_at), asc(ServiceRecordAuditLog.id))
        .all()
        if record_ids else []
    )
    audit_logs_by_record: dict[int, list[ServiceRecordAuditLog]] = {}
    user_ids: set[int] = set()
    for row in records:
        if getattr(row, "user_id", None):
            user_ids.add(int(row.user_id))
    for log_row in audit_logs:
        audit_logs_by_record.setdefault(int(log_row.service_record_id), []).append(log_row)
        if getattr(log_row, "changed_by_user_id", None):
            user_ids.add(int(log_row.changed_by_user_id))
    if getattr(current_user, "id", None):
        user_ids.add(int(current_user.id))

    owner = get_primary_vehicle_owner(db, vehicle)
    if owner and getattr(owner, "id", None):
        user_ids.add(int(owner.id))
    users_by_id = _record_users_by_id(db, user_ids)

    rendered_records: list[VehicleReportServiceRecord] = []
    for row in records:
        attachments_full = _parse_attachments_payload(row.attachments)
        same_era = viewer_record_same_ownership_era(db, int(vehicle.id), current_user, row)
        attachments = attachments_full if same_era else []
        row_audit_logs = audit_logs_by_record.get(int(row.id), [])
        supplier, workshop, technician = _pick_supplier_fields(
            record=row,
            attachments=attachments,
            users_by_id=users_by_id,
            mode=mode,
        )
        if not same_era:
            supplier = workshop = technician = None
        created_at = None
        created_by = _identity_label(row.user_id, users_by_id=users_by_id, mode=mode) if mode == VehicleReportMode.INTERNAL_AUDIT else None
        updated_at = _isoformat(row_audit_logs[-1].created_at) if row_audit_logs else None
        updated_by = (
            _identity_label(row_audit_logs[-1].changed_by_user_id, users_by_id=users_by_id, mode=mode)
            if row_audit_logs else None
        )
        if row_audit_logs:
            create_logs = [item for item in row_audit_logs if str(item.action or "").lower() == "create"]
            if create_logs:
                created_at = _isoformat(create_logs[0].created_at)
                created_by = _identity_label(create_logs[0].changed_by_user_id, users_by_id=users_by_id, mode=mode)

        notes_render = _first_non_empty(row.note, None) if same_era else None
        verification_render = (
            _verification_status(record=row, attachments=attachments, audit_logs=row_audit_logs)
            if same_era
            else "Bez dokladů předchozího majitele (ochrana údajů)"
        )

        rendered_records.append(
            VehicleReportServiceRecord(
                id=int(row.id),
                date=_isoformat(row.performed_at),
                odometer_km=row.mileage,
                category=CATEGORY_LABELS.get(str(row.category or "").upper(), _first_non_empty(row.category, "Servisní zásah")),
                title=_pick_record_title(row, attachments),
                performed_work=_first_non_empty(row.description, None),
                parts=_extract_parts(attachments),
                notes=notes_render,
                attachments_count=len(attachments),
                supplier=supplier,
                workshop=workshop,
                technician=technician,
                created_at=created_at if mode == VehicleReportMode.INTERNAL_AUDIT else None,
                created_by=created_by if mode == VehicleReportMode.INTERNAL_AUDIT else None,
                updated_at=updated_at if mode in {VehicleReportMode.WORKSHOP, VehicleReportMode.INTERNAL_AUDIT} else None,
                updated_by=updated_by if mode == VehicleReportMode.INTERNAL_AUDIT else None,
                source_type=_pick_record_source_type(row, attachments) if mode in {VehicleReportMode.WORKSHOP, VehicleReportMode.INTERNAL_AUDIT} else None,
                verification_status=verification_render,
                audit_note=_record_audit_note(audit_logs=row_audit_logs, mode=mode, users_by_id=users_by_id),
                totals=_extract_record_totals(attachments),
            )
        )

    inspection_rows = (
        db.query(VehicleInspectionHistory)
        .filter(VehicleInspectionHistory.vehicle_id == vehicle.id)
        .order_by(
            nullslast(asc(VehicleInspectionHistory.inspection_date)),
            asc(VehicleInspectionHistory.imported_at),
            asc(VehicleInspectionHistory.id),
        )
        .all()
    )
    mileage_timeline = build_vehicle_report_mileage_timeline(
        service_records=rendered_records,
        inspections=inspection_rows,
    )
    anomaly_notes_by_reference = {
        str(point.reference): str(point.anomaly_note or "").strip()
        for point in mileage_timeline.points
        if str(point.reference or "").strip() and str(point.anomaly_note or "").strip()
    }
    inspection_history_records = _build_inspection_history_records(
        inspections=inspection_rows,
        anomaly_notes_by_reference=anomaly_notes_by_reference,
    )
    rendered_records = sorted(
        [*rendered_records, *inspection_history_records],
        key=lambda item: (
            _isoformat(item.date) or "9999-99-99",
            int(item.id),
        ),
    )

    last_record = rendered_records[-1] if rendered_records else None
    quality_flags = _summary_quality_flags(rendered_records)
    if mileage_timeline.anomalies_count:
        quality_flags.append(
            f"Km timeline obsahuje {mileage_timeline.anomalies_count} oznacenych anomalii nebo konfliktu."
        )
    if inspection_history_records:
        quality_flags.append(
            f"Do chronologie byly zahrnuty i importované STK/tachometr záznamy ({len(inspection_history_records)} položek)."
        )
    summary = VehicleReportSummary(
        records_count=len(rendered_records),
        last_service_date=last_record.date if last_record else None,
        last_service_km=last_record.odometer_km if last_record else None,
        last_oil_service_date=_last_matching_record(rendered_records, ("olej", "oil", "maziv")),
        last_brake_service_date=_last_matching_record(rendered_records, ("brzd", "kotou", "desti")),
        open_recommendations=_summary_recommendations(records, rendered_records),
        record_quality_flags=quality_flags,
    )

    owner_section = _build_owner_section(owner=owner, mode=mode)
    document = VehicleReportDocument(
        type="digital_service_vehicle_report",
        version="2.2",
        generated_at=generated_at,
        document_id="pending",
        verification_code="",
        fingerprint="",
        export_mode=mode.value,
        issued_by=None,
        public_token=None,
        verification_url=None,
        verification_enabled=False,
        revision=1,
        generated_by_user_id=getattr(current_user, "id", None) if mode == VehicleReportMode.INTERNAL_AUDIT else None,
        generated_by_role=normalize_role(getattr(current_user, "role", None)) if mode == VehicleReportMode.INTERNAL_AUDIT else None,
    )
    payload = VehicleServiceReportPayload(
        document=document,
        vehicle=_build_vehicle_section(vehicle, db),
        summary=summary,
        service_records=rendered_records,
        mileage_timeline=mileage_timeline,
        owner=owner_section,
    )
    return payload
