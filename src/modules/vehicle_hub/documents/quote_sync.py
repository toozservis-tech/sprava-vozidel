from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import Customer, ServiceQuote, Vehicle, VehicleDocument
from src.modules.vehicle_hub.reports.vehicle_report_verification import build_public_verify_url, mask_vin

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
from .quote_models import QuoteDocumentPayload, QuoteLinePayload
from .renderers.quote import render_quote_document_pdf

DEFAULT_QUOTE_TAX_RATE = 21.0
DEFAULT_QUOTE_VALIDITY_DAYS = 30


def _quote_document_status(quote_status: str) -> str:
    mapping = {
        "draft": "draft",
        "sent": "pending",
        "approved": "approved",
        "rejected": "cancelled",
    }
    return mapping.get(str(quote_status or "").lower(), "draft")


def _quote_status_label(quote_status: str) -> str:
    mapping = {
        "draft": "Koncept",
        "sent": "Odesláno",
        "approved": "Schváleno",
        "rejected": "Zamítnuto",
    }
    return mapping.get(str(quote_status or "").lower(), str(quote_status or "—"))


def _service_address(service: Customer) -> str:
    return _customer_address(service)


def _quote_number(quote_id: int) -> str:
    return f"NAB-{int(quote_id):05d}"


def _parse_quote_items(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        import json
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _build_quote_lines(quote: ServiceQuote, items: list[dict]) -> list[QuoteLinePayload]:
    lines: list[QuoteLinePayload] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        quantity = float(item.get("quantity") or 0) or 1.0
        unit_price = float(item.get("unit_price") or 0)
        net_total = float(item.get("total_price") if item.get("total_price") is not None else quantity * unit_price)
        gross_total = round(net_total * (1 + DEFAULT_QUOTE_TAX_RATE / 100), 2)
        lines.append(
            QuoteLinePayload(
                description=str(item.get("name") or "Položka"),
                quantity=quantity,
                unit="ks",
                unit_price=unit_price,
                tax_rate=DEFAULT_QUOTE_TAX_RATE,
                line_total=gross_total,
            )
        )
    labor_hours = float(quote.labor_hours or 0)
    labor_rate = float(quote.labor_rate or 0)
    if labor_hours > 0 and labor_rate > 0 and not any("práce" in ln.description.lower() for ln in lines):
        net_labor = round(labor_hours * labor_rate, 2)
        lines.append(
            QuoteLinePayload(
                description="Práce",
                quantity=labor_hours,
                unit="h",
                unit_price=labor_rate,
                tax_rate=DEFAULT_QUOTE_TAX_RATE,
                line_total=round(net_labor * (1 + DEFAULT_QUOTE_TAX_RATE / 100), 2),
            )
        )
    return lines


def _quote_totals(lines: list[QuoteLinePayload], *, fallback_total: float) -> tuple[float, float, float]:
    if not lines:
        total = float(fallback_total or 0)
        subtotal = round(total / (1 + DEFAULT_QUOTE_TAX_RATE / 100), 2)
        tax_total = round(total - subtotal, 2)
        return subtotal, tax_total, total
    gross = round(sum(float(ln.line_total or 0) for ln in lines), 2)
    subtotal = round(sum(float(ln.line_total or 0) / (1 + float(ln.tax_rate or 0) / 100) for ln in lines), 2)
    tax_total = round(gross - subtotal, 2)
    return subtotal, tax_total, gross


def build_quote_document_payload(
    db: Session,
    *,
    quote: ServiceQuote,
    service_customer: Customer,
    verification_token: Optional[str] = None,
    verification_code: Optional[str] = None,
) -> QuoteDocumentPayload:
    customer = (
        db.query(Customer).filter(Customer.id == int(quote.customer_id)).first()
        if quote.customer_id
        else None
    )
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(quote.vehicle_id)).first()
    quote_status = str(quote.status or "draft")
    doc_status = _quote_document_status(quote_status)

    vehicle_label = "—"
    plate = None
    vin = None
    odometer = None
    if vehicle:
        vehicle_label = " ".join(
            p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None), getattr(vehicle, "nickname", None)] if p
        ).strip() or str(getattr(vehicle, "plate", None) or f"Vozidlo #{vehicle.id}")
        plate = getattr(vehicle, "plate", None)
        vin = getattr(vehicle, "vin", None)
        odometer = getattr(vehicle, "current_mileage_km", None)

    items = _parse_quote_items(quote.items_json)
    lines = _build_quote_lines(quote, items)
    subtotal, tax_total, total = _quote_totals(lines, fallback_total=float(quote.total_price or 0))

    created_at = quote.created_at or datetime.utcnow()
    valid_until = created_at + timedelta(days=DEFAULT_QUOTE_VALIDITY_DAYS)
    verify_url = build_public_verify_url(verification_token) if verification_token else None

    return QuoteDocumentPayload(
        quote_id=int(quote.id),
        quote_number=_quote_number(int(quote.id)),
        document_status=doc_status,
        status_label=_quote_status_label(quote_status),
        is_draft=quote_status == "draft",
        created_at_label=created_at.strftime("%d.%m.%Y %H:%M"),
        valid_until_label=valid_until.strftime("%d.%m.%Y"),
        validity_note=f"Nabídka je platná do {valid_until.strftime('%d.%m.%Y')} včetně, pokud není uvedeno jinak.",
        currency="CZK",
        subtotal=subtotal,
        tax_total=tax_total,
        total=total,
        service_name=str(service_customer.name or service_customer.email or "Servis"),
        service_ico=getattr(service_customer, "ico", None),
        service_dic=getattr(service_customer, "dic", None),
        service_address=_service_address(service_customer),
        service_email=getattr(service_customer, "email", None),
        service_phone=getattr(service_customer, "phone", None) or getattr(service_customer, "phone_e164", None),
        customer_name=str((customer.name or customer.email) if customer else "—"),
        customer_address=_customer_address(customer),
        customer_ico=getattr(customer, "ico", None) if customer else None,
        customer_dic=getattr(customer, "dic", None) if customer else None,
        vehicle_label=vehicle_label,
        vehicle_plate=plate,
        vehicle_vin=vin,
        vehicle_odometer_km=int(odometer) if odometer is not None else None,
        work_order_id=int(quote.work_order_id) if quote.work_order_id else None,
        verify_url=verify_url,
        verification_code=verification_code,
        lines=lines,
    )


def find_quote_vehicle_document(db: Session, *, quote_id: int) -> Optional[VehicleDocument]:
    return (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_quote",
            VehicleDocument.source_id == int(quote_id),
            VehicleDocument.document_type == "quote",
        )
        .order_by(VehicleDocument.id.desc())
        .first()
    )


def sync_quote_vehicle_document(
    db: Session,
    *,
    quote: ServiceQuote,
    service_customer: Customer,
    actor: Customer,
) -> Optional[VehicleDocument]:
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(quote.vehicle_id)).first()
    if vehicle is None:
        return None

    existing = find_quote_vehicle_document(db, quote_id=int(quote.id))
    token = existing.verification_token if existing and existing.verification_token else generate_verification_token()
    metadata_existing = parse_metadata(existing.metadata_json) if existing else {}
    verification_code = metadata_existing.get("verification_code") or build_verification_code(
        f"quote:{quote.id}:{token}"
    )

    payload = build_quote_document_payload(
        db,
        quote=quote,
        service_customer=service_customer,
        verification_token=token,
        verification_code=verification_code,
    )
    pdf_bytes = render_quote_document_pdf(payload)
    pdf_hash = sha256_bytes(pdf_bytes)

    doc_number = payload.quote_number
    filename = safe_filename(f"{doc_number}.pdf")
    storage_relative = f"tenants/{int(quote.tenant_id)}/vehicles/{int(vehicle.id)}/quote/{filename}"
    write_document_bytes(VEHICLE_DOCUMENTS_ROOT / storage_relative, pdf_bytes)

    from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner
    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    doc_status = _quote_document_status(str(quote.status or "draft"))
    title = f"Nabídka {doc_number}"
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
        "quote_id": int(quote.id),
        "work_order_id": int(quote.work_order_id) if quote.work_order_id else None,
    }

    if existing:
        existing.document_status = doc_status
        existing.title = title
        existing.document_number = doc_number
        existing.storage_path = storage_relative
        existing.file_size = len(pdf_bytes)
        existing.updated_at = now
        existing.metadata_json = dump_metadata(metadata)
        if str(quote.status) == "rejected":
            existing.archived_at = existing.archived_at or now
        db.add(existing)
        db.flush()
        return existing

    row = VehicleDocument(
        tenant_id=int(quote.tenant_id),
        vehicle_id=int(vehicle.id),
        document_type="quote",
        document_status=doc_status,
        title=title,
        document_number=doc_number,
        source_type="service_quote",
        source_id=int(quote.id),
        service_customer_id=int(quote.service_id),
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


def get_quote_document_card(db: Session, *, quote_id: int) -> Optional[dict]:
    from .document_service import serialize_document_card

    doc = find_quote_vehicle_document(db, quote_id=int(quote_id))
    if doc is None:
        return None
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(doc.vehicle_id)).first()
    return serialize_document_card(doc, vehicle=vehicle)
