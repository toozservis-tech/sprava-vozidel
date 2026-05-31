from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.core.config import DATA_DIR
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceIntake,
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
from .intake_protocol_models import (
    IntakeProtocolChecklistItemPayload,
    IntakeProtocolDocumentPayload,
    IntakeProtocolPhotoSlotPayload,
)
from .invoice_sync import _customer_address
from .renderers.intake_protocol import render_intake_protocol_pdf
from .work_order_sheet_sync import _FUEL_RE, _format_dt, _label, _parse_fuel_level

_MISSING = "Neuvedeno"

_INTAKE_STATUS_LABELS = {
    "draft": "Koncept",
    "intake_started": "Příjem zahájen",
    "intake_completed": "Příjem dokončen",
    "cancelled": "Zrušeno",
}

_PHOTO_SLOT_DEFS: tuple[tuple[str, str], ...] = (
    ("front", "Předek"),
    ("rear", "Zadek"),
    ("left", "Levý bok"),
    ("right", "Pravý bok"),
    ("interior", "Interiér"),
    ("damage", "Poškození"),
)

_SLOT_FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "front": ("front", "pred", "před", "predni", "přední", "predek", "předek"),
    "rear": ("rear", "zad", "zadek", "zadni", "zadní"),
    "left": ("left", "lev", "levy", "levý", "bok_l"),
    "right": ("right", "prav", "pravy", "pravý", "bok_p"),
}

_CHECKLIST_LABELS: tuple[tuple[str, str], ...] = (
    ("keys", "Klíčky"),
    ("body", "Karoserie"),
    ("lights", "Světla"),
    ("tires", "Pneumatiky"),
    ("interior", "Interiér"),
    ("customer_notified", "Zákazník informován"),
)

_VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"


def _intake_protocol_number(intake_id: int) -> str:
    return f"PP-{int(intake_id):05d}"


def _intake_document_status(intake: ServiceIntake, *, work_order: Optional[ServiceWorkOrder] = None) -> str:
    status = str(intake.intake_status or "draft").lower()
    if status == "cancelled":
        return "cancelled"
    if status == "intake_completed":
        return "completed"
    if work_order and str(work_order.status or "").lower() == "completed":
        return "completed"
    if status in {"intake_started", "draft"}:
        return "pending"
    return "draft"


def _parse_structured_intake_note(intake: ServiceIntake) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    note = str(intake.intake_note or "")
    visible_defect = str(intake.damage_description or "").strip() or None
    fuel: Optional[str] = None
    agreement: Optional[str] = None
    tech_lines: list[str] = []
    for line in note.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("viditelná závada:"):
            if not visible_defect:
                visible_defect = stripped.split(":", 1)[1].strip() or None
            continue
        fuel_match = _FUEL_RE.search(stripped)
        if fuel_match:
            fuel = fuel_match.group(1).strip() or None
            continue
        if lower.startswith("stav paliva:"):
            fuel = stripped.split(":", 1)[1].strip() or None
            continue
        if lower.startswith("předběžná domluva:"):
            agreement = stripped.split(":", 1)[1].strip() or None
            continue
        tech_lines.append(stripped)
    technician_note = "\n".join(tech_lines).strip() or None
    return visible_defect, fuel, agreement, technician_note


def _arrival_condition(intake: ServiceIntake, work_order: Optional[ServiceWorkOrder]) -> str:
    if work_order and str(work_order.description or "").strip():
        first = str(work_order.description).split("\n", 1)[0].strip()
        if first:
            return first
    if str(intake.work_description or "").strip():
        return str(intake.work_description).strip()
    return _MISSING


def _build_checklist_items(intake: ServiceIntake) -> list[IntakeProtocolChecklistItemPayload]:
    parsed: dict[str, object] = {}
    raw = intake.fluids_ok
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                parsed = data
        except json.JSONDecodeError:
            parsed = {}

    items: list[IntakeProtocolChecklistItemPayload] = []
    for key, label in _CHECKLIST_LABELS:
        value = parsed.get(key)
        if value is True:
            text = "Ano"
        elif value is False:
            text = "Ne"
        elif value is not None and str(value).strip():
            text = str(value).strip()
        else:
            text = _MISSING
        items.append(IntakeProtocolChecklistItemPayload(label=label, value=text))
    return items


def _resolve_photo_path(row: VehiclePhotoAsset) -> Optional[str]:
    from src.modules.vehicle_hub.vehicle_photo_assets import resolve_storage_file

    key = getattr(row, "storage_key", None) or getattr(row, "stored_file_path", None)
    path = resolve_storage_file(_VEHICLE_PHOTOS_DIR, key)
    if path is not None:
        return str(path)
    return None


def _match_slot_from_filename(filename: str) -> Optional[str]:
    name = str(filename or "").lower()
    for slot_key, hints in _SLOT_FILENAME_HINTS.items():
        if any(h in name for h in hints):
            return slot_key
    return None


def _build_photo_slots(
    db: Session,
    *,
    intake: ServiceIntake,
    work_order: Optional[ServiceWorkOrder],
) -> list[IntakeProtocolPhotoSlotPayload]:
    assigned: dict[str, VehiclePhotoAsset] = {}
    intake_slots_remaining = ["front", "rear", "left", "right"]

    if work_order is not None:
        rows = (
            db.query(VehiclePhotoAsset)
            .filter(
                VehiclePhotoAsset.work_order_id == int(work_order.id),
                VehiclePhotoAsset.deleted_at.is_(None),
            )
            .order_by(VehiclePhotoAsset.id.asc())
            .all()
        )
        for row in rows:
            kind = str(row.photo_kind or "").lower()
            filename = str(row.original_filename or "")
            if kind == "damage" and "damage" not in assigned:
                assigned["damage"] = row
                continue
            if kind == "internal" and "interior" not in assigned:
                assigned["interior"] = row
                continue
            if kind == "intake":
                slot = _match_slot_from_filename(filename)
                if slot and slot not in assigned:
                    assigned[slot] = row
                elif intake_slots_remaining:
                    slot_key = intake_slots_remaining.pop(0)
                    if slot_key not in assigned:
                        assigned[slot_key] = row

    slots: list[IntakeProtocolPhotoSlotPayload] = []
    for slot_key, label in _PHOTO_SLOT_DEFS:
        row = assigned.get(slot_key)
        if row is None:
            slots.append(
                IntakeProtocolPhotoSlotPayload(
                    slot_key=slot_key,
                    label=label,
                    status="Chybí",
                    image_path=None,
                )
            )
            continue
        image_path = _resolve_photo_path(row)
        if image_path:
            slots.append(
                IntakeProtocolPhotoSlotPayload(
                    slot_key=slot_key,
                    label=label,
                    status="Fotografie evidována",
                    image_path=image_path,
                )
            )
        else:
            slots.append(
                IntakeProtocolPhotoSlotPayload(
                    slot_key=slot_key,
                    label=label,
                    status="Fotografie evidována",
                    image_path=None,
                )
            )
    return slots


def _find_linked_work_order(db: Session, *, intake_id: int) -> Optional[ServiceWorkOrder]:
    return (
        db.query(ServiceWorkOrder)
        .filter(ServiceWorkOrder.source_intake_id == int(intake_id))
        .order_by(ServiceWorkOrder.id.desc())
        .first()
    )


def build_intake_protocol_document_payload(
    db: Session,
    *,
    intake: ServiceIntake,
    service_customer: Customer,
    verification_token: Optional[str] = None,
    verification_code: Optional[str] = None,
) -> IntakeProtocolDocumentPayload:
    from src.modules.vehicle_hub.reports.vehicle_report_verification import build_public_verify_url
    from src.modules.vehicle_hub.routers_v1.work_order_billing_api import (
        _get_billing_contact_row,
        _serialize_billing_contact,
    )

    vehicle = (
        db.query(Vehicle).filter(Vehicle.id == int(intake.vehicle_id)).first()
        if intake.vehicle_id
        else None
    )
    owner = (
        db.query(Customer).filter(Customer.id == int(intake.customer_id)).first()
        if intake.customer_id
        else None
    )
    work_order = _find_linked_work_order(db, intake_id=int(intake.id))

    billing = None
    if work_order is not None:
        billing_row = _get_billing_contact_row(
            db,
            work_order_id=int(work_order.id),
            service_customer_id=int(service_customer.id),
        )
        if billing_row:
            billing = _serialize_billing_contact(billing_row)

    visible_defect, parsed_fuel, _agreement, technician_note = _parse_structured_intake_note(intake)
    fuel_level = parsed_fuel or _parse_fuel_level(intake)

    vehicle_label = _MISSING
    if vehicle:
        vehicle_label = " / ".join(
            p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None), getattr(vehicle, "nickname", None)] if p
        ).strip() or _MISSING
        if vehicle_label == _MISSING:
            vehicle_label = " / ".join(p for p in [getattr(vehicle, "vin", None), getattr(vehicle, "plate", None)] if p) or _MISSING

    customer_name = _MISSING
    customer_contact = _MISSING
    if billing:
        customer_name = _label(billing.get("display_name") or billing.get("company_name"))
        customer_contact = _label(" · ".join(p for p in [billing.get("email"), billing.get("phone")] if p))
    elif owner:
        customer_name = _label(owner.name or owner.email)
        customer_contact = _label(
            " · ".join(p for p in [owner.email, owner.phone or getattr(owner, "phone_e164", None)] if p)
        )

    intake_status = str(intake.intake_status or "draft")
    doc_status = _intake_document_status(intake, work_order=work_order)
    status_label = _INTAKE_STATUS_LABELS.get(intake_status, intake_status)
    verify_url = build_public_verify_url(verification_token) if verification_token else None

    signature_present = bool(str(intake.signature or "").strip())
    customer_signature_label = "Elektronicky podepsáno" if signature_present else _MISSING
    service_signature_label = _label(service_customer.name or service_customer.email)

    technician_note_safe = _label(
        technician_note or intake.visible_to_owner_note or intake.diagnosis_summary,
    )
    if intake.internal_note and technician_note_safe == _MISSING:
        technician_note_safe = _MISSING

    return IntakeProtocolDocumentPayload(
        document_number=_intake_protocol_number(int(intake.id)),
        document_status=doc_status,
        status_label=status_label,
        document_title=f"Příjmový protokol {_intake_protocol_number(int(intake.id))}",
        created_at_label=_format_dt(intake.created_at),
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
        vehicle_odometer_km=int(intake.odometer_km) if intake.odometer_km is not None else None,
        fuel_level=fuel_level,
        received_at_label=_format_dt(intake.check_in_at or intake.created_at),
        arrival_condition=_arrival_condition(intake, work_order),
        customer_request=_label(intake.customer_request),
        visible_defect=_label(visible_defect),
        technician_note=technician_note_safe,
        checklist_items=_build_checklist_items(intake),
        photo_slots=_build_photo_slots(db, intake=intake, work_order=work_order),
        customer_signature_present=signature_present,
        customer_signature_label=customer_signature_label,
        service_signature_label=service_signature_label,
        verify_url=verify_url,
        verification_code=verification_code,
    )


def find_intake_protocol_vehicle_document(db: Session, *, intake_id: int) -> Optional[VehicleDocument]:
    return (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_intake",
            VehicleDocument.source_id == int(intake_id),
            VehicleDocument.document_type == "intake_protocol",
        )
        .order_by(VehicleDocument.id.desc())
        .first()
    )


def sync_intake_protocol_vehicle_document(
    db: Session,
    *,
    intake: ServiceIntake,
    service_customer: Customer,
    actor: Customer,
) -> Optional[VehicleDocument]:
    if intake.vehicle_id is None:
        return None

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(intake.vehicle_id)).first()
    if vehicle is None:
        return None

    existing = find_intake_protocol_vehicle_document(db, intake_id=int(intake.id))
    token = existing.verification_token if existing and existing.verification_token else generate_verification_token()
    metadata_existing = parse_metadata(existing.metadata_json) if existing else {}
    verification_code = metadata_existing.get("verification_code") or build_verification_code(
        f"intake_protocol:{intake.id}:{token}"
    )

    payload = build_intake_protocol_document_payload(
        db,
        intake=intake,
        service_customer=service_customer,
        verification_token=token,
        verification_code=verification_code,
    )
    pdf_bytes = render_intake_protocol_pdf(payload)
    pdf_hash = sha256_bytes(pdf_bytes)

    doc_number = payload.document_number
    filename = safe_filename(f"{doc_number}.pdf")
    storage_relative = f"tenants/{int(intake.tenant_id)}/vehicles/{int(vehicle.id)}/intake_protocol/{filename}"
    write_document_bytes(VEHICLE_DOCUMENTS_ROOT / storage_relative, pdf_bytes)

    from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner

    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    doc_status = payload.document_status
    title = f"Příjmový protokol {doc_number}"
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
        "intake_id": int(intake.id),
        "intake_status": str(intake.intake_status or ""),
    }

    if existing:
        existing.document_status = doc_status
        existing.title = title
        existing.document_number = doc_number
        existing.storage_path = storage_relative
        existing.file_size = len(pdf_bytes)
        existing.updated_at = now
        existing.metadata_json = dump_metadata(metadata)
        db.add(existing)
        db.flush()
        return existing

    row = VehicleDocument(
        tenant_id=int(intake.tenant_id),
        vehicle_id=int(vehicle.id),
        document_type="intake_protocol",
        document_status=doc_status,
        title=title,
        document_number=doc_number,
        source_type="service_intake",
        source_id=int(intake.id),
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


def get_intake_protocol_document_card(db: Session, *, intake_id: int) -> Optional[dict]:
    from .document_service import serialize_document_card

    doc = find_intake_protocol_vehicle_document(db, intake_id=int(intake_id))
    if doc is None:
        return None
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(doc.vehicle_id)).first()
    card = serialize_document_card(doc, vehicle=vehicle)
    if card is not None:
        card["pdf_url"] = f"/api/service/intakes/{int(intake_id)}/protocol.pdf"
    return card
