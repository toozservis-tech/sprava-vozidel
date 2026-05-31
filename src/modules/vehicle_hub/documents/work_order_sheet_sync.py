from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import Customer, ServiceIntake, ServiceWorkOrder, Vehicle, VehicleDocument

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
from .renderers.work_order_sheet import render_work_order_sheet_pdf
from .work_order_sheet_models import WorkOrderSheetDocumentPayload, WorkOrderSheetItemPayload, WorkOrderSheetPhotoPayload

_MISSING = "Neuvedeno"
_FUEL_RE = re.compile(r"stav\s+paliva\s*:\s*(.+)", re.IGNORECASE)


def _label(value: object | None, *, default: str = _MISSING) -> str:
    text = str(value or "").strip()
    return text if text else default


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return _MISSING
    return value.strftime("%d.%m.%Y %H:%M")


def _work_order_document_status(status: str) -> str:
    mapping = {
        "awaiting_client_approval": "pending",
        "intake_pending": "pending",
        "approved": "pending",
        "in_progress": "pending",
        "issue": "pending",
        "completed": "completed",
    }
    return mapping.get(str(status or "").lower(), "draft")


def _work_order_sheet_number(work_order_id: int) -> str:
    return f"ZL-{int(work_order_id):05d}"


def _parse_fuel_level(intake: ServiceIntake | None) -> Optional[str]:
    if intake is None:
        return None
    note = str(intake.intake_note or "")
    for line in note.splitlines():
        match = _FUEL_RE.search(line.strip())
        if match:
            return match.group(1).strip()
        if "palivo" in line.lower() and ":" in line:
            return line.split(":", 1)[1].strip()
    raw = intake.fluids_ok
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                for key in ("fuel", "fuel_level", "palivo"):
                    if data.get(key):
                        return str(data[key]).strip()
        except json.JSONDecodeError:
            if str(raw).strip():
                return str(raw).strip()
    return None


def _build_item_payloads(items: dict[str, list[dict[str, object]]]) -> tuple[
    list[WorkOrderSheetItemPayload],
    list[WorkOrderSheetItemPayload],
    list[WorkOrderSheetItemPayload],
]:
    labor: list[WorkOrderSheetItemPayload] = []
    parts: list[WorkOrderSheetItemPayload] = []
    times: list[WorkOrderSheetItemPayload] = []
    for row in items.get("labor") or []:
        labor.append(
            WorkOrderSheetItemPayload(
                category="labor",
                name=_label(row.get("name")),
                quantity_label=str(row.get("quantity") or "—"),
                unit=_label(row.get("unit") or "h"),
                note=_label(row.get("note"), default="—") if row.get("note") else "—",
            )
        )
    for row in items.get("parts") or []:
        parts.append(
            WorkOrderSheetItemPayload(
                category="part",
                name=_label(row.get("name")),
                quantity_label=str(row.get("quantity") or "—"),
                unit=_label(row.get("unit") or "ks"),
                note=_label(row.get("note"), default="—") if row.get("note") else "—",
            )
        )
    for row in items.get("time") or []:
        qty = row.get("quantity")
        note = row.get("note")
        worked = row.get("worked_date")
        note_parts = [p for p in [note, f"Datum: {worked}" if worked else None] if p]
        times.append(
            WorkOrderSheetItemPayload(
                category="time",
                name=_label(row.get("name") or "Čas práce"),
                quantity_label=str(qty or "—"),
                unit=_label(row.get("unit") or "min"),
                note=" · ".join(note_parts) if note_parts else "—",
            )
        )
    return labor, parts, times


def build_work_order_sheet_document_payload(
    db: Session,
    *,
    order: ServiceWorkOrder,
    service_customer: Customer,
    verification_token: Optional[str] = None,
    verification_code: Optional[str] = None,
) -> WorkOrderSheetDocumentPayload:
    from src.modules.vehicle_hub.reports.vehicle_report_verification import build_public_verify_url
    from src.modules.vehicle_hub.routers_v1.service_dashboard import WORK_ORDER_STATUS_LABELS
    from src.modules.vehicle_hub.routers_v1.work_order_billing_api import _get_billing_contact_row, _serialize_billing_contact
    from src.modules.vehicle_hub.routers_v1.work_order_items_api import list_work_order_items_grouped
    from src.modules.vehicle_hub.routers_v1.work_order_photos_api import list_work_order_photos_for_order

    owner = (
        db.query(Customer).filter(Customer.id == int(order.owner_customer_id)).first()
        if order.owner_customer_id is not None
        else None
    )
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(order.vehicle_id)).first()
    technician = db.query(Customer).filter(Customer.id == int(order.technician_id)).first()
    intake = (
        db.query(ServiceIntake).filter(ServiceIntake.id == int(order.source_intake_id)).first()
        if order.source_intake_id
        else None
    )

    billing_row = _get_billing_contact_row(
        db,
        work_order_id=int(order.id),
        service_customer_id=int(service_customer.id),
    )
    billing = _serialize_billing_contact(billing_row) if billing_row else None

    items = list_work_order_items_grouped(db, work_order_id=int(order.id))
    labor_items, part_items, time_items = _build_item_payloads(items)

    photos = list_work_order_photos_for_order(
        db,
        work_order_id=int(order.id),
        service_customer_id=int(service_customer.id),
    )
    intake_photos = [
        WorkOrderSheetPhotoPayload(
            label=str(row.get("photo_type_label") or row.get("photo_type") or "Foto"),
            photo_type=str(row.get("photo_type") or "intake"),
        )
        for row in photos
        if str(row.get("photo_type") or "").lower() in {"intake", "damage"}
    ]

    vehicle_label = " / ".join(
        p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None), getattr(vehicle, "nickname", None)] if p
    ).strip() if vehicle else _MISSING
    if not vehicle_label or vehicle_label == _MISSING:
        vehicle_label = " / ".join(p for p in [getattr(vehicle, "vin", None), getattr(vehicle, "plate", None)] if p) if vehicle else _MISSING

    odometer = None
    if intake and intake.odometer_km is not None:
        odometer = int(intake.odometer_km)
    elif vehicle and getattr(vehicle, "current_mileage_km", None) is not None:
        odometer = int(vehicle.current_mileage_km)

    received_at = order.started_at or order.approved_at or (intake.check_in_at if intake else None) or order.created_at
    completed_at = order.completed_at

    customer_name = _MISSING
    customer_contact = _MISSING
    if owner:
        customer_name = _label(owner.name or owner.email)
        customer_contact = _label(" · ".join(p for p in [owner.email, owner.phone or getattr(owner, "phone_e164", None)] if p))
    elif billing:
        customer_name = _label(billing.get("display_name") or billing.get("company_name"))
        customer_contact = _label(" · ".join(p for p in [billing.get("email"), billing.get("phone")] if p))

    wo_status = str(order.status or "awaiting_client_approval")
    doc_status = _work_order_document_status(wo_status)
    verify_url = build_public_verify_url(verification_token) if verification_token else None

    signature_present = bool(intake and str(intake.signature or "").strip())
    customer_signature_label = "Elektronicky podepsáno" if signature_present else _MISSING
    service_signature_label = _label(
        technician.name if technician and technician.name else technician.email if technician else service_customer.name,
    )

    return WorkOrderSheetDocumentPayload(
        document_number=_work_order_sheet_number(int(order.id)),
        document_status=doc_status,
        status_label=WORK_ORDER_STATUS_LABELS.get(wo_status, wo_status),
        document_title=f"Zakázkový list { _work_order_sheet_number(int(order.id)) }",
        created_at_label=_format_dt(order.created_at),
        service_name=_label(service_customer.name or service_customer.email),
        service_ico=getattr(service_customer, "ico", None),
        service_dic=getattr(service_customer, "dic", None),
        service_address=_customer_address(service_customer),
        service_email=getattr(service_customer, "email", None),
        service_phone=getattr(service_customer, "phone", None) or getattr(service_customer, "phone_e164", None),
        customer_name=customer_name,
        customer_contact=customer_contact,
        billing_contact_name=_label(billing.get("display_name") if billing else None, default="—") if billing else None,
        billing_contact_phone=_label(billing.get("phone") if billing else None, default="—") if billing else None,
        billing_contact_email=_label(billing.get("email") if billing else None, default="—") if billing else None,
        vehicle_label=vehicle_label,
        vehicle_plate=getattr(vehicle, "plate", None) if vehicle else None,
        vehicle_vin=getattr(vehicle, "vin", None) if vehicle else None,
        vehicle_odometer_km=odometer,
        fuel_level=_parse_fuel_level(intake),
        intake_received_at_label=_format_dt(intake.check_in_at if intake else received_at),
        defect_description=_label(intake.damage_description if intake else order.description),
        customer_request=_label(intake.customer_request if intake else None),
        technical_note=_label(intake.diagnosis_summary or intake.internal_note if intake else None),
        intake_note=_label(intake.intake_note if intake else None),
        work_order_id=int(order.id),
        work_order_number=f"WO-{int(order.id)}",
        work_order_status=wo_status,
        work_order_status_label=WORK_ORDER_STATUS_LABELS.get(wo_status, wo_status),
        work_order_title=_label(order.title),
        work_order_description=_label(order.description),
        received_at_label=_format_dt(received_at),
        completed_at_label=_format_dt(completed_at),
        technician_name=_label(
            technician.name if technician and technician.name
            else technician.email if technician
            else f"Technik #{int(order.technician_id)}"
        ),
        labor_items=labor_items,
        part_items=part_items,
        time_items=time_items,
        intake_photos=intake_photos,
        intake_photo_count=len(intake_photos),
        customer_signature_present=signature_present,
        customer_signature_label=customer_signature_label,
        service_signature_label=service_signature_label,
        verify_url=verify_url,
        verification_code=verification_code,
    )


def find_work_order_sheet_vehicle_document(db: Session, *, work_order_id: int) -> Optional[VehicleDocument]:
    return (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_work_order",
            VehicleDocument.source_id == int(work_order_id),
            VehicleDocument.document_type == "work_order_sheet",
        )
        .order_by(VehicleDocument.id.desc())
        .first()
    )


def sync_work_order_vehicle_document(
    db: Session,
    *,
    order: ServiceWorkOrder,
    service_customer: Customer,
    actor: Customer,
) -> Optional[VehicleDocument]:
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(order.vehicle_id)).first()
    if vehicle is None:
        return None

    existing = find_work_order_sheet_vehicle_document(db, work_order_id=int(order.id))
    token = existing.verification_token if existing and existing.verification_token else generate_verification_token()
    metadata_existing = parse_metadata(existing.metadata_json) if existing else {}
    verification_code = metadata_existing.get("verification_code") or build_verification_code(
        f"work_order_sheet:{order.id}:{token}"
    )

    payload = build_work_order_sheet_document_payload(
        db,
        order=order,
        service_customer=service_customer,
        verification_token=token,
        verification_code=verification_code,
    )
    pdf_bytes = render_work_order_sheet_pdf(payload)
    pdf_hash = sha256_bytes(pdf_bytes)

    doc_number = payload.document_number
    filename = safe_filename(f"{doc_number}.pdf")
    storage_relative = f"tenants/{int(order.tenant_id)}/vehicles/{int(vehicle.id)}/work_order_sheet/{filename}"
    write_document_bytes(VEHICLE_DOCUMENTS_ROOT / storage_relative, pdf_bytes)

    from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner

    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    doc_status = _work_order_document_status(str(order.status or "awaiting_client_approval"))
    title = f"Zakázkový list {doc_number}"
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
        "work_order_id": int(order.id),
        "work_order_number": payload.work_order_number,
        "work_order_status": str(order.status or ""),
    }

    if existing:
        existing.document_status = doc_status
        existing.title = title
        existing.document_number = doc_number
        existing.storage_path = storage_relative
        existing.file_size = len(pdf_bytes)
        existing.updated_at = now
        existing.metadata_json = dump_metadata(metadata)
        if str(order.status) == "completed" and doc_status == "completed":
            existing.document_status = "completed"
        db.add(existing)
        db.flush()
        return existing

    row = VehicleDocument(
        tenant_id=int(order.tenant_id),
        vehicle_id=int(vehicle.id),
        document_type="work_order_sheet",
        document_status=doc_status,
        title=title,
        document_number=doc_number,
        source_type="service_work_order",
        source_id=int(order.id),
        service_customer_id=int(service_customer.id),
        owner_customer_id=owner_id,
        created_by_customer_id=int(actor.id),
        visibility_scope="service_private",
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


def get_work_order_sheet_document_card(db: Session, *, work_order_id: int) -> Optional[dict]:
    from .document_service import serialize_document_card

    doc = find_work_order_sheet_vehicle_document(db, work_order_id=int(work_order_id))
    if doc is None:
        return None
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(doc.vehicle_id)).first()
    card = serialize_document_card(doc, vehicle=vehicle)
    if card is not None:
        card["pdf_url"] = f"/api/service/work-orders/{int(work_order_id)}/sheet.pdf"
    return card
