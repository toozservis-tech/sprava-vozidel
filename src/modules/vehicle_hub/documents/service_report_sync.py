from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.core.config import DATA_DIR
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceIntake,
    ServiceRecord,
    ServiceWorkOrder,
    Vehicle,
    VehicleDocument,
    VehiclePhotoAsset,
)

from .document_storage import (
    VEHICLE_DOCUMENTS_ROOT,
    dump_metadata,
    generate_verification_token,
    parse_metadata,
    safe_filename,
    sha256_bytes,
    write_document_bytes,
)
from .document_verify import build_verification_code, mask_plate
from .invoice_sync import _customer_address
from .renderers.service_report import render_service_report_pdf
from .service_report_models import (
    ServiceReportDocumentPayload,
    ServiceReportPartPayload,
    ServiceReportPhotoPayload,
    ServiceReportTimePayload,
    ServiceReportWorkItemPayload,
)
from .work_order_sheet_sync import _format_dt, _label

_MISSING = "Neuvedeno"
_VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"
_POST_REPAIR_PHOTO_TYPES = frozenset({"completion", "work_progress"})
_OWNER_SAFE_PHOTO_VISIBILITY = frozenset({"owner_visible", "safe_after_claim"})

_RECORD_STATUS_LABELS = {
    "draft": "Koncept",
    "submitted": "Odesláno",
    "published": "Dokončeno",
    "cancelled": "Zrušeno",
}


def _service_report_number(service_record_id: int) -> str:
    return f"SZ-{int(service_record_id):05d}"


def _record_document_status(record: ServiceRecord) -> str:
    status = str(record.record_status or "draft").lower()
    if status == "published":
        return "completed"
    if status == "cancelled":
        return "cancelled"
    if status == "submitted":
        return "pending"
    return "draft"


def _document_visibility_from_record(record: ServiceRecord) -> str:
    scope = str(record.visibility_scope or "").lower()
    if scope in {"owner_visible", "owner_visible_no_prices"}:
        return "owner_visible"
    if scope in {"safe_after_claim", "safe_history_after_claim"}:
        return "safe_after_claim"
    return "service_private"


def _owner_safe_mode_for_visibility(visibility_scope: str) -> bool:
    return str(visibility_scope or "") in {"owner_visible", "safe_after_claim"}


def _resolve_photo_path(row: VehiclePhotoAsset) -> Optional[str]:
    from src.modules.vehicle_hub.vehicle_photo_assets import resolve_storage_file

    key = getattr(row, "storage_key", None) or getattr(row, "stored_file_path", None)
    path = resolve_storage_file(_VEHICLE_PHOTOS_DIR, key)
    if path is not None:
        return str(path)
    return None


def _build_photo_payloads(
    db: Session,
    *,
    work_order_id: Optional[int],
    owner_safe: bool,
) -> list[ServiceReportPhotoPayload]:
    if work_order_id is None:
        return []
    rows = (
        db.query(VehiclePhotoAsset)
        .filter(
            VehiclePhotoAsset.work_order_id == int(work_order_id),
            VehiclePhotoAsset.deleted_at.is_(None),
        )
        .order_by(VehiclePhotoAsset.id.asc())
        .all()
    )
    from src.modules.vehicle_hub.routers_v1.work_order_photos_api import WORK_ORDER_PHOTO_TYPE_LABELS

    photos: list[ServiceReportPhotoPayload] = []
    for row in rows:
        kind = str(row.photo_kind or "").lower()
        if kind not in _POST_REPAIR_PHOTO_TYPES:
            continue
        scope = str(row.visibility_scope or "")
        if owner_safe and scope not in _OWNER_SAFE_PHOTO_VISIBILITY:
            continue
        label = WORK_ORDER_PHOTO_TYPE_LABELS.get(kind, kind) or "Foto"
        photos.append(
            ServiceReportPhotoPayload(
                label=label,
                photo_type=kind,
                image_path=_resolve_photo_path(row),
            )
        )
    return photos


def _owner_safe_parts_from_record(record: ServiceRecord) -> list[dict[str, object]]:
    from src.modules.vehicle_hub.routers_v1.work_order_items_api import owner_safe_parts_from_record_attachments

    return owner_safe_parts_from_record_attachments(record.attachments)


def _build_labor_items(items: dict[str, list[dict[str, object]]]) -> list[ServiceReportWorkItemPayload]:
    labor: list[ServiceReportWorkItemPayload] = []
    for row in items.get("labor") or []:
        labor.append(
            ServiceReportWorkItemPayload(
                name=_label(row.get("name")),
                quantity_label=str(row.get("quantity") or "—"),
                unit=_label(row.get("unit") or "h"),
                note=_label(row.get("note"), default="—") if row.get("note") else None,
            )
        )
    return labor


def _build_part_items(
    *,
    grouped_items: dict[str, list[dict[str, object]]],
    owner_safe_parts: list[dict[str, object]],
) -> list[ServiceReportPartPayload]:
    parts: list[ServiceReportPartPayload] = []
    if owner_safe_parts:
        for row in owner_safe_parts:
            parts.append(
                ServiceReportPartPayload(
                    name=_label(row.get("name")),
                    quantity_label=str(row.get("quantity") or "—"),
                    unit=_label(row.get("unit") or "ks"),
                    note=_label(row.get("note"), default="—") if row.get("note") else None,
                )
            )
        return parts
    for row in grouped_items.get("parts") or []:
        parts.append(
            ServiceReportPartPayload(
                name=_label(row.get("name")),
                quantity_label=str(row.get("quantity") or "—"),
                unit=_label(row.get("unit") or "ks"),
                note=_label(row.get("note"), default="—") if row.get("note") else None,
            )
        )
    return parts


def _build_time_items(
    *,
    grouped_items: dict[str, list[dict[str, object]]],
    labor_seconds: Optional[int],
) -> tuple[list[ServiceReportTimePayload], Optional[int]]:
    times: list[ServiceReportTimePayload] = []
    total_minutes: Optional[int] = None
    if labor_seconds is not None and int(labor_seconds) > 0:
        total_minutes = int(int(labor_seconds) / 60)
    for row in grouped_items.get("time") or []:
        qty = row.get("quantity")
        note = row.get("note")
        worked = row.get("worked_date")
        note_parts = [p for p in [note, f"Datum: {worked}" if worked else None] if p]
        times.append(
            ServiceReportTimePayload(
                label=_label(row.get("name") or "Čas práce"),
                duration_label=f"{qty} {row.get('unit') or 'min'}" if qty is not None else _MISSING,
                note=" · ".join(note_parts) if note_parts else None,
            )
        )
        if total_minutes is None and qty is not None:
            try:
                total_minutes = int(float(qty))
            except (TypeError, ValueError):
                pass
    return times, total_minutes


def _build_recommendations(record: ServiceRecord) -> str:
    parts: list[str] = []
    if str(record.recommended_next_service_text or "").strip():
        parts.append(str(record.recommended_next_service_text).strip())
    if record.recommended_next_service_date is not None:
        parts.append(f"Doporučený termín: {record.recommended_next_service_date.strftime('%d.%m.%Y')}")
    if record.recommended_next_service_km is not None:
        parts.append(f"Doporučený stav km: {int(record.recommended_next_service_km):,}".replace(",", " "))
    return "\n".join(parts).strip() or _MISSING


def _defect_description(
    *,
    work_order: Optional[ServiceWorkOrder],
    intake: Optional[ServiceIntake],
) -> str:
    if intake and str(intake.damage_description or "").strip():
        return str(intake.damage_description).strip()
    if work_order and str(work_order.description or "").strip():
        return str(work_order.description).split("\n", 1)[0].strip()
    return _MISSING


def build_service_report_document_payload(
    db: Session,
    *,
    record: ServiceRecord,
    service_customer: Customer,
    verification_token: Optional[str] = None,
    verification_code: Optional[str] = None,
    owner_safe_mode: bool = False,
) -> ServiceReportDocumentPayload:
    from src.modules.vehicle_hub.reports.vehicle_report_verification import build_public_verify_url
    from src.modules.vehicle_hub.routers_v1.work_order_items_api import list_work_order_items_grouped

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(record.vehicle_id)).first()
    work_order = (
        db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(record.work_order_id)).first()
        if record.work_order_id
        else None
    )
    intake = None
    if work_order and work_order.source_intake_id:
        intake = db.query(ServiceIntake).filter(ServiceIntake.id == int(work_order.source_intake_id)).first()

    technician = None
    if work_order and work_order.technician_id:
        technician = db.query(Customer).filter(Customer.id == int(work_order.technician_id)).first()

    grouped_items: dict[str, list[dict[str, object]]] = {"labor": [], "parts": [], "time": []}
    if work_order is not None:
        grouped_items = list_work_order_items_grouped(db, work_order_id=int(work_order.id))

    owner_safe_parts = _owner_safe_parts_from_record(record)
    labor_items = _build_labor_items(grouped_items)
    part_items = _build_part_items(grouped_items=grouped_items, owner_safe_parts=owner_safe_parts)
    time_items, total_minutes = _build_time_items(
        grouped_items=grouped_items,
        labor_seconds=record.labor_seconds,
    )

    performed_work = str(record.notes_customer_visible or "").strip()
    if not performed_work and labor_items:
        lines = [f"• {item.name}" for item in labor_items]
        performed_work = "\n".join(lines)
    if not performed_work:
        performed_work = _MISSING

    vehicle_label = _MISSING
    if vehicle:
        vehicle_label = " / ".join(
            p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None), getattr(vehicle, "nickname", None)] if p
        ).strip() or _MISSING
        if vehicle_label == _MISSING:
            vehicle_label = " / ".join(p for p in [getattr(vehicle, "vin", None), getattr(vehicle, "plate", None)] if p) or _MISSING

    odometer = int(record.mileage) if record.mileage is not None else None
    if odometer is None and vehicle and getattr(vehicle, "current_mileage_km", None) is not None:
        odometer = int(vehicle.current_mileage_km)

    intervention_title = _label(work_order.title if work_order else record.category)
    defect = _defect_description(work_order=work_order, intake=intake)
    recommendations = _build_recommendations(record)

    record_status = str(record.record_status or "draft")
    doc_status = _record_document_status(record)
    status_label = _RECORD_STATUS_LABELS.get(record_status, record_status)
    verify_url = build_public_verify_url(verification_token) if verification_token else None

    technician_name = _label(
        technician.name if technician and technician.name
        else technician.email if technician
        else service_customer.name or service_customer.email,
    )
    conclusion = recommendations if recommendations != _MISSING else "Servisní úkon byl dokončen dle servisní zakázky."

    photos = _build_photo_payloads(
        db,
        work_order_id=int(record.work_order_id) if record.work_order_id else None,
        owner_safe=owner_safe_mode,
    )

    wo_number = f"WO-{int(work_order.id)}" if work_order else _MISSING

    return ServiceReportDocumentPayload(
        document_number=_service_report_number(int(record.id)),
        document_status=doc_status,
        status_label=status_label,
        document_title=f"Servisní zpráva {_service_report_number(int(record.id))}",
        created_at_label=_format_dt(record.performed_at or datetime.utcnow()),
        performed_at_label=_format_dt(record.performed_at),
        service_name=_label(service_customer.name or service_customer.email),
        service_ico=getattr(service_customer, "ico", None),
        service_dic=getattr(service_customer, "dic", None),
        service_address=_customer_address(service_customer),
        service_email=getattr(service_customer, "email", None),
        service_phone=getattr(service_customer, "phone", None) or getattr(service_customer, "phone_e164", None),
        vehicle_label=vehicle_label,
        vehicle_plate=getattr(vehicle, "plate", None) if vehicle else None,
        vehicle_vin=getattr(vehicle, "vin", None) if vehicle else None,
        vehicle_odometer_km=odometer,
        work_order_id=int(work_order.id) if work_order else None,
        work_order_number=wo_number,
        work_order_title=_label(work_order.title if work_order else None),
        intervention_title=intervention_title,
        defect_description=defect,
        service_record_id=int(record.id),
        record_status_label=status_label,
        performed_work_summary=performed_work,
        recommendations=recommendations,
        technician_conclusion=conclusion,
        labor_items=labor_items,
        part_items=part_items,
        time_items=time_items,
        total_work_minutes=total_minutes,
        photos=photos,
        photo_count=len(photos),
        service_signature_label=technician_name,
        verify_url=verify_url,
        verification_code=verification_code,
    )


def find_service_report_vehicle_document(db: Session, *, service_record_id: int) -> Optional[VehicleDocument]:
    return (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_record",
            VehicleDocument.source_id == int(service_record_id),
            VehicleDocument.document_type == "service_report",
        )
        .order_by(VehicleDocument.id.desc())
        .first()
    )


def sync_service_report_vehicle_document(
    db: Session,
    *,
    record: ServiceRecord,
    service_customer: Customer,
    actor: Customer,
) -> Optional[VehicleDocument]:
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(record.vehicle_id)).first()
    if vehicle is None:
        return None

    visibility_scope = _document_visibility_from_record(record)
    owner_safe_mode = _owner_safe_mode_for_visibility(visibility_scope)

    existing = find_service_report_vehicle_document(db, service_record_id=int(record.id))
    token = existing.verification_token if existing and existing.verification_token else generate_verification_token()
    metadata_existing = parse_metadata(existing.metadata_json) if existing else {}
    verification_code = metadata_existing.get("verification_code") or build_verification_code(
        f"service_report:{record.id}:{token}"
    )

    payload = build_service_report_document_payload(
        db,
        record=record,
        service_customer=service_customer,
        verification_token=token,
        verification_code=verification_code,
        owner_safe_mode=owner_safe_mode,
    )
    pdf_bytes = render_service_report_pdf(payload)
    pdf_hash = sha256_bytes(pdf_bytes)

    doc_number = payload.document_number
    filename = safe_filename(f"{doc_number}.pdf")
    storage_relative = f"tenants/{int(record.tenant_id)}/vehicles/{int(vehicle.id)}/service_report/{filename}"
    write_document_bytes(VEHICLE_DOCUMENTS_ROOT / storage_relative, pdf_bytes)

    from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner

    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    doc_status = payload.document_status
    title = f"Servisní zpráva {doc_number}"
    service_name = str(service_customer.name or service_customer.email or "Servis")
    now = datetime.utcnow()

    metadata = {
        "hash_sha256": pdf_hash,
        "verification_code": verification_code,
        "vehicle_brand": getattr(vehicle, "brand", None),
        "vehicle_model": getattr(vehicle, "model", None),
        "vehicle_plate_masked": mask_plate(getattr(vehicle, "plate", None)),
        "vehicle_label": payload.vehicle_label,
        "service_display": service_name,
        "service_record_id": int(record.id),
        "work_order_id": int(record.work_order_id) if record.work_order_id else None,
        "record_status": str(record.record_status or ""),
    }

    if existing:
        existing.document_status = doc_status
        existing.title = title
        existing.document_number = doc_number
        existing.storage_path = storage_relative
        existing.file_size = len(pdf_bytes)
        existing.visibility_scope = visibility_scope
        existing.updated_at = now
        existing.metadata_json = dump_metadata(metadata)
        db.add(existing)
        db.flush()
        return existing

    row = VehicleDocument(
        tenant_id=int(record.tenant_id),
        vehicle_id=int(vehicle.id),
        document_type="service_report",
        document_status=doc_status,
        title=title,
        document_number=doc_number,
        source_type="service_record",
        source_id=int(record.id),
        service_customer_id=int(service_customer.id),
        owner_customer_id=owner_id,
        created_by_customer_id=int(actor.id),
        visibility_scope=visibility_scope,
        verification_token=token,
        storage_path=storage_relative,
        thumbnail_path=None,
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
        created_at=now,
        updated_at=now,
        metadata_json=dump_metadata(metadata),
    )
    db.add(row)
    db.flush()
    return row


def get_service_report_document_card(db: Session, *, service_record_id: int) -> Optional[dict]:
    from .document_service import serialize_document_card

    doc = find_service_report_vehicle_document(db, service_record_id=int(service_record_id))
    if doc is None:
        return None
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(doc.vehicle_id)).first()
    card = serialize_document_card(doc, vehicle=vehicle)
    if card is not None:
        card["pdf_url"] = f"/api/service/service-records/{int(service_record_id)}/report.pdf"
    return card
