from __future__ import annotations

import json
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
from .handover_protocol_models import (
    HandoverProtocolDocumentPayload,
    HandoverProtocolItemPayload,
    HandoverProtocolPartPayload,
    HandoverProtocolPhotoPayload,
)
from .invoice_sync import _customer_address
from .renderers.handover_protocol import render_handover_protocol_pdf
from .work_order_sheet_sync import _format_dt, _label

_MISSING = "Neuvedeno"
_VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"
_HANDOVER_PHOTO_TYPES = frozenset({"completion", "work_progress"})
_OWNER_SAFE_PHOTO_VISIBILITY = frozenset({"owner_visible", "safe_after_claim"})

_WO_STATUS_LABELS = {
    "awaiting_client_approval": "Čeká na schválení",
    "intake_pending": "Nový příjem",
    "approved": "Schváleno",
    "in_progress": "Probíhá",
    "completed": "Dokončeno",
    "issue": "Problém",
}


def _handover_protocol_number(work_order_id: int) -> str:
    return f"PV-{int(work_order_id):05d}"


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


def _document_visibility_from_context(
    *,
    order: ServiceWorkOrder,
    record: Optional[ServiceRecord],
) -> str:
    if record is not None:
        scope = str(record.visibility_scope or "").lower()
        if scope in {"owner_visible", "owner_visible_no_prices"}:
            return "owner_visible"
        if scope in {"safe_after_claim", "safe_history_after_claim"}:
            return "safe_after_claim"
    if order.owner_customer_id is not None:
        return "owner_visible"
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
    work_order_id: int,
    owner_safe: bool,
) -> list[HandoverProtocolPhotoPayload]:
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

    photos: list[HandoverProtocolPhotoPayload] = []
    for row in rows:
        kind = str(row.photo_kind or "").lower()
        if kind not in _HANDOVER_PHOTO_TYPES:
            continue
        scope = str(row.visibility_scope or "")
        if owner_safe and scope not in _OWNER_SAFE_PHOTO_VISIBILITY:
            continue
        label = WORK_ORDER_PHOTO_TYPE_LABELS.get(kind, kind) or "Foto"
        photos.append(
            HandoverProtocolPhotoPayload(
                label=label,
                photo_type=kind,
                image_path=_resolve_photo_path(row),
            )
        )
    return photos


def _build_part_items(
    *,
    grouped_items: dict[str, list[dict[str, object]]],
    owner_safe_parts: list[dict[str, object]],
) -> list[HandoverProtocolPartPayload]:
    parts: list[HandoverProtocolPartPayload] = []
    source_rows = owner_safe_parts if owner_safe_parts else (grouped_items.get("parts") or [])
    for row in source_rows:
        parts.append(
            HandoverProtocolPartPayload(
                name=_label(row.get("name")),
                quantity_label=str(row.get("quantity") or "—"),
                unit=_label(row.get("unit") or "ks"),
                note=_label(row.get("note"), default="—") if row.get("note") else None,
            )
        )
    return parts


def _build_work_summary(
    *,
    record: Optional[ServiceRecord],
    grouped_items: dict[str, list[dict[str, object]]],
    order: ServiceWorkOrder,
) -> str:
    if record and str(record.notes_customer_visible or "").strip():
        return str(record.notes_customer_visible).strip()
    labor = grouped_items.get("labor") or []
    if labor:
        lines = []
        for row in labor:
            name = _label(row.get("name"))
            qty = row.get("quantity")
            unit = row.get("unit") or "h"
            suffix = f" ({qty:g} {unit})" if qty else ""
            lines.append(f"• {name}{suffix}")
        return "\n".join(lines)
    if str(order.description or "").strip():
        return str(order.description).strip()
    if str(order.title or "").strip():
        return str(order.title).strip()
    return _MISSING


def _build_recommendations(record: Optional[ServiceRecord]) -> str:
    if record is None:
        return _MISSING
    parts: list[str] = []
    if str(record.recommended_next_service_text or "").strip():
        parts.append(str(record.recommended_next_service_text).strip())
    if record.recommended_next_service_date is not None:
        parts.append(f"Doporučený termín: {record.recommended_next_service_date.strftime('%d.%m.%Y')}")
    if record.recommended_next_service_km is not None:
        parts.append(f"Doporučený stav km: {int(record.recommended_next_service_km):,}".replace(",", " "))
    return "\n".join(parts).strip() or _MISSING


def _vehicle_condition_at_handover(
    *,
    order: ServiceWorkOrder,
    intake: Optional[ServiceIntake],
) -> str:
    if str(order.description or "").strip():
        first = str(order.description).split("\n", 1)[0].strip()
        if first:
            return first
    if intake and str(intake.work_description or "").strip():
        return str(intake.work_description).strip()
    return "Vozidlo předáno po servisním zásahu"


def _build_handed_over_documents(
    db: Session,
    *,
    order: ServiceWorkOrder,
    record: Optional[ServiceRecord],
    owner_safe: bool,
) -> list[HandoverProtocolItemPayload]:
    items: list[HandoverProtocolItemPayload] = []
    from .work_order_sheet_sync import find_work_order_sheet_vehicle_document
    from .service_report_sync import find_service_report_vehicle_document

    sheet = find_work_order_sheet_vehicle_document(db, work_order_id=int(order.id))
    if sheet is not None:
        items.append(HandoverProtocolItemPayload(label="Zakázkový list", value=str(sheet.document_number or "Ano")))

    if order.source_intake_id:
        from .intake_protocol_sync import find_intake_protocol_vehicle_document

        intake_doc = find_intake_protocol_vehicle_document(db, intake_id=int(order.source_intake_id))
        if intake_doc is not None:
            items.append(HandoverProtocolItemPayload(label="Příjmový protokol", value=str(intake_doc.document_number or "Ano")))

    if record is not None:
        report = find_service_report_vehicle_document(db, service_record_id=int(record.id))
        if report is not None:
            items.append(HandoverProtocolItemPayload(label="Servisní zpráva", value=str(report.document_number or "Ano")))

    if not owner_safe:
        from src.modules.vehicle_hub.routers_v1.work_order_billing_api import _linked_invoice

        invoice = _linked_invoice(
            db,
            work_order_id=int(order.id),
            service_customer_id=int(order.service_customer_id),
        )
        if invoice is not None and getattr(invoice, "invoice_number", None):
            items.append(
                HandoverProtocolItemPayload(
                    label="Faktura / doklad",
                    value=str(invoice.invoice_number),
                )
            )

    if not items:
        items.append(HandoverProtocolItemPayload(label="Předané dokumenty", value=_MISSING))
    return items


def _build_handed_over_accessories(intake: Optional[ServiceIntake]) -> list[HandoverProtocolItemPayload]:
    items: list[HandoverProtocolItemPayload] = []
    parsed: dict[str, object] = {}
    if intake and intake.fluids_ok:
        try:
            data = json.loads(str(intake.fluids_ok))
            if isinstance(data, dict):
                parsed = data
        except json.JSONDecodeError:
            parsed = {}

    keys_value = parsed.get("keys")
    if keys_value is True:
        keys_text = "Ano"
    elif keys_value is False:
        keys_text = "Ne"
    elif keys_value is not None and str(keys_value).strip():
        keys_text = str(keys_value).strip()
    else:
        keys_text = _MISSING
    items.append(HandoverProtocolItemPayload(label="Klíče vozidla", value=keys_text))

    accessories = parsed.get("accessories") or parsed.get("prilslusenstvi")
    if accessories is not None and str(accessories).strip():
        items.append(HandoverProtocolItemPayload(label="Příslušenství", value=str(accessories).strip()))
    else:
        items.append(HandoverProtocolItemPayload(label="Příslušenství", value=_MISSING))

    return items


def _resolve_odometer_km(
    *,
    record: Optional[ServiceRecord],
    intake: Optional[ServiceIntake],
    vehicle: Optional[Vehicle],
) -> Optional[int]:
    if record and record.mileage is not None:
        return int(record.mileage)
    if intake and intake.odometer_km is not None:
        return int(intake.odometer_km)
    if vehicle and getattr(vehicle, "current_mileage_km", None) is not None:
        return int(vehicle.current_mileage_km)
    return None


def build_handover_protocol_document_payload(
    db: Session,
    *,
    order: ServiceWorkOrder,
    service_customer: Customer,
    verification_token: Optional[str] = None,
    verification_code: Optional[str] = None,
    owner_safe_mode: bool = False,
) -> HandoverProtocolDocumentPayload:
    from src.modules.vehicle_hub.reports.vehicle_report_verification import build_public_verify_url
    from src.modules.vehicle_hub.routers_v1.work_order_items_api import list_work_order_items_grouped

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(order.vehicle_id)).first()
    owner = (
        db.query(Customer).filter(Customer.id == int(order.owner_customer_id)).first()
        if order.owner_customer_id
        else None
    )
    technician = db.query(Customer).filter(Customer.id == int(order.technician_id)).first()
    intake = (
        db.query(ServiceIntake).filter(ServiceIntake.id == int(order.source_intake_id)).first()
        if order.source_intake_id
        else None
    )
    record = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.work_order_id == int(order.id),
            ServiceRecord.is_deleted.is_(False),
            ServiceRecord.service_id == int(service_customer.id),
        )
        .order_by(ServiceRecord.id.desc())
        .first()
    )

    billing = None
    if order.owner_customer_id is None:
        from src.modules.vehicle_hub.routers_v1.work_order_billing_api import (
            _get_billing_contact_row,
            _serialize_billing_contact,
        )

        billing_row = _get_billing_contact_row(
            db,
            work_order_id=int(order.id),
            service_customer_id=int(service_customer.id),
        )
        if billing_row:
            billing = _serialize_billing_contact(billing_row)

    grouped_items = list_work_order_items_grouped(db, work_order_id=int(order.id))
    owner_safe_parts: list[dict[str, object]] = []
    if record is not None:
        from src.modules.vehicle_hub.routers_v1.work_order_items_api import owner_safe_parts_from_record_attachments

        owner_safe_parts = owner_safe_parts_from_record_attachments(record.attachments)

    part_items = _build_part_items(grouped_items=grouped_items, owner_safe_parts=owner_safe_parts)
    work_summary = _build_work_summary(record=record, grouped_items=grouped_items, order=order)
    recommendations = _build_recommendations(record)
    vehicle_condition = _vehicle_condition_at_handover(order=order, intake=intake)
    photos = _build_photo_payloads(db, work_order_id=int(order.id), owner_safe=owner_safe_mode)
    handed_over_documents = _build_handed_over_documents(
        db,
        order=order,
        record=record,
        owner_safe=owner_safe_mode,
    )
    handed_over_accessories = _build_handed_over_accessories(intake)

    vehicle_label = _MISSING
    if vehicle:
        vehicle_label = " / ".join(
            p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None), getattr(vehicle, "nickname", None)] if p
        ).strip() or _MISSING
        if vehicle_label == _MISSING:
            vehicle_label = " / ".join(p for p in [getattr(vehicle, "vin", None), getattr(vehicle, "plate", None)] if p) or _MISSING

    customer_name = _MISSING
    customer_contact = _MISSING
    if owner:
        customer_name = _label(owner.name or owner.email)
        if not owner_safe_mode:
            customer_contact = _label(
                " · ".join(p for p in [owner.email, owner.phone or getattr(owner, "phone_e164", None)] if p)
            )
        else:
            customer_contact = _label(owner.name or owner.email)
    elif billing and not owner_safe_mode:
        customer_name = _label(billing.get("display_name") or billing.get("company_name"))
        customer_contact = _label(" · ".join(p for p in [billing.get("email"), billing.get("phone")] if p))
    elif billing:
        customer_name = _label(billing.get("display_name") or billing.get("company_name"))
        customer_contact = customer_name

    wo_status = str(order.status or "awaiting_client_approval")
    doc_status = _work_order_document_status(wo_status)
    status_label = _WO_STATUS_LABELS.get(wo_status, wo_status)
    handover_at = order.completed_at or datetime.utcnow()
    verify_url = build_public_verify_url(verification_token) if verification_token else None

    signature_present = bool(intake and str(intake.signature or "").strip())
    customer_signature_label = "Elektronicky podepsáno" if signature_present else _MISSING
    service_signature_label = _label(
        technician.name if technician and technician.name
        else technician.email if technician
        else service_customer.name or service_customer.email,
    )

    return HandoverProtocolDocumentPayload(
        document_number=_handover_protocol_number(int(order.id)),
        document_status=doc_status,
        status_label=status_label,
        document_title=f"Předávací protokol {_handover_protocol_number(int(order.id))}",
        created_at_label=_format_dt(order.created_at),
        handover_at_label=_format_dt(handover_at),
        service_name=_label(service_customer.name or service_customer.email),
        service_ico=getattr(service_customer, "ico", None),
        service_dic=getattr(service_customer, "dic", None),
        service_address=_customer_address(service_customer),
        service_email=getattr(service_customer, "email", None),
        service_phone=getattr(service_customer, "phone", None) or getattr(service_customer, "phone_e164", None),
        customer_name=customer_name,
        customer_contact=customer_contact,
        vehicle_label=vehicle_label,
        vehicle_plate=getattr(vehicle, "plate", None) if vehicle else None,
        vehicle_vin=getattr(vehicle, "vin", None) if vehicle else None,
        vehicle_odometer_km=_resolve_odometer_km(record=record, intake=intake, vehicle=vehicle),
        vehicle_condition=vehicle_condition,
        work_order_id=int(order.id),
        work_order_number=f"WO-{int(order.id)}",
        work_order_title=_label(order.title),
        work_summary=work_summary,
        part_items=part_items,
        recommendations=recommendations,
        handed_over_documents=handed_over_documents,
        handed_over_accessories=handed_over_accessories,
        photos=photos,
        photo_count=len(photos),
        customer_signature_label=customer_signature_label,
        service_signature_label=service_signature_label,
        verify_url=verify_url,
        verification_code=verification_code,
    )


def find_handover_protocol_vehicle_document(db: Session, *, work_order_id: int) -> Optional[VehicleDocument]:
    return (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_work_order",
            VehicleDocument.source_id == int(work_order_id),
            VehicleDocument.document_type == "handover_protocol",
        )
        .order_by(VehicleDocument.id.desc())
        .first()
    )


def sync_handover_protocol_vehicle_document(
    db: Session,
    *,
    order: ServiceWorkOrder,
    service_customer: Customer,
    actor: Customer,
) -> Optional[VehicleDocument]:
    if str(order.status or "").lower() != "completed":
        return None

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(order.vehicle_id)).first()
    if vehicle is None:
        return None

    record = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.work_order_id == int(order.id),
            ServiceRecord.is_deleted.is_(False),
            ServiceRecord.service_id == int(service_customer.id),
        )
        .order_by(ServiceRecord.id.desc())
        .first()
    )
    visibility_scope = _document_visibility_from_context(order=order, record=record)
    owner_safe_mode = _owner_safe_mode_for_visibility(visibility_scope)

    existing = find_handover_protocol_vehicle_document(db, work_order_id=int(order.id))
    token = existing.verification_token if existing and existing.verification_token else generate_verification_token()
    metadata_existing = parse_metadata(existing.metadata_json) if existing else {}
    verification_code = metadata_existing.get("verification_code") or build_verification_code(
        f"handover_protocol:{order.id}:{token}"
    )

    payload = build_handover_protocol_document_payload(
        db,
        order=order,
        service_customer=service_customer,
        verification_token=token,
        verification_code=verification_code,
        owner_safe_mode=owner_safe_mode,
    )
    pdf_bytes = render_handover_protocol_pdf(payload)
    pdf_hash = sha256_bytes(pdf_bytes)

    doc_number = payload.document_number
    filename = safe_filename(f"{doc_number}.pdf")
    storage_relative = f"tenants/{int(order.tenant_id)}/vehicles/{int(vehicle.id)}/handover_protocol/{filename}"
    write_document_bytes(VEHICLE_DOCUMENTS_ROOT / storage_relative, pdf_bytes)

    from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner

    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    doc_status = payload.document_status
    title = f"Předávací protokol {doc_number}"
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
        "handover_at": payload.handover_at_label,
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
        tenant_id=int(order.tenant_id),
        vehicle_id=int(vehicle.id),
        document_type="handover_protocol",
        document_status=doc_status,
        title=title,
        document_number=doc_number,
        source_type="service_work_order",
        source_id=int(order.id),
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


def get_handover_protocol_document_card(db: Session, *, work_order_id: int) -> Optional[dict]:
    from .document_service import serialize_document_card

    doc = find_handover_protocol_vehicle_document(db, work_order_id=int(work_order_id))
    if doc is None:
        return None
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(doc.vehicle_id)).first()
    card = serialize_document_card(doc, vehicle=vehicle)
    if card is not None:
        card["pdf_url"] = f"/api/service/work-orders/{int(work_order_id)}/handover.pdf"
    return card
