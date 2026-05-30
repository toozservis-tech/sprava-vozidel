from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import Customer, ServiceInvoice, ServiceInvoiceLine, Vehicle, VehicleDocument
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
from .invoice_models import InvoiceDocumentPayload, InvoiceLinePayload
from .renderers.invoice import render_invoice_document_pdf


def _invoice_document_status(invoice_status: str) -> str:
    mapping = {"draft": "draft", "issued": "completed", "cancelled": "cancelled"}
    return mapping.get(str(invoice_status or "").lower(), "draft")


def _status_label(invoice_status: str) -> str:
    mapping = {"draft": "Koncept", "issued": "Vystaveno", "cancelled": "Zrušeno"}
    return mapping.get(str(invoice_status or "").lower(), str(invoice_status or "—"))


def _customer_address(customer: Optional[Customer]) -> str:
    if not customer:
        return ""
    parts = []
    street = " ".join(p for p in [getattr(customer, "street", None), getattr(customer, "street_number", None)] if p)
    if street:
        parts.append(street)
    city_line = " ".join(p for p in [getattr(customer, "zip", None), getattr(customer, "city", None)] if p)
    if city_line:
        parts.append(city_line)
    return ", ".join(parts)


def _service_address(service: Customer, extra: dict) -> str:
    parts = []
    street = str(extra.get("supplier_street") or "").strip() or _customer_address(service)
    if street:
        parts.append(street)
    city = str(extra.get("supplier_city") or getattr(service, "city", None) or "").strip()
    zip_code = str(extra.get("supplier_zip") or getattr(service, "zip", None) or "").strip()
    city_line = " ".join(p for p in [zip_code, city] if p)
    if city_line:
        parts.append(city_line)
    return ", ".join(parts)


def _parse_extra(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        import json
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _build_payment_qr(*, account: str, amount: float, currency: str, vs: str, message: str) -> str:
    acc = str(account or "").strip().replace(" ", "")
    if not acc:
        return ""
    cur = "CZK" if str(currency or "CZK").upper() in {"CZK", "KČ", "KC"} else str(currency or "CZK").upper()
    try:
        amount_str = f"{float(amount):.2f}"
    except (TypeError, ValueError):
        amount_str = "0.00"
    parts = [f"SPD*1.0*ACC:{acc}*AM:{amount_str}*CC:{cur}"]
    if vs:
        parts.append(f"X-VS:{vs}")
    if message:
        parts.append(f"MSG:{message[:60]}")
    return "*".join(parts)


def build_invoice_document_payload(
    db: Session,
    *,
    invoice: ServiceInvoice,
    lines: list[ServiceInvoiceLine],
    service_customer: Customer,
    verification_token: Optional[str] = None,
    verification_code: Optional[str] = None,
) -> InvoiceDocumentPayload:
    customer = db.query(Customer).filter(Customer.id == int(invoice.customer_id)).first()
    vehicle = (
        db.query(Vehicle).filter(Vehicle.id == int(invoice.vehicle_id)).first()
        if invoice.vehicle_id
        else None
    )
    extra = _parse_extra(invoice.extra_json)
    inv_status = str(invoice.status or "draft")
    doc_status = _invoice_document_status(inv_status)

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

    vs = str(extra.get("variable_symbol") or invoice.invoice_number or invoice.id or "").strip()
    bank_account = str(extra.get("bank_account") or extra.get("supplier_bank_account") or "").strip() or None
    payment_qr = ""
    if inv_status == "issued" and bank_account:
        payment_qr = _build_payment_qr(
            account=bank_account,
            amount=float(invoice.total or 0),
            currency=str(invoice.currency or "CZK"),
            vs=vs,
            message=f"Faktura {invoice.invoice_number or invoice.id}",
        )

    verify_url = build_public_verify_url(verification_token) if verification_token else None

    return InvoiceDocumentPayload(
        invoice_id=int(invoice.id),
        invoice_number=invoice.invoice_number,
        document_status=doc_status,
        status_label=_status_label(inv_status),
        is_draft=inv_status == "draft",
        issued_at_label=invoice.issued_at.strftime("%d.%m.%Y %H:%M") if invoice.issued_at else "—",
        due_at_label=invoice.due_at.strftime("%d.%m.%Y %H:%M") if invoice.due_at else "—",
        variable_symbol=vs,
        payment_method=str(extra.get("payment_method") or "převod"),
        order_number=str(extra.get("order_number") or (f"WO-{invoice.work_order_id}" if invoice.work_order_id else "")),
        currency=str(invoice.currency or "CZK"),
        subtotal=float(invoice.subtotal or 0),
        tax_total=float(invoice.tax_total or 0),
        total=float(invoice.total or 0),
        notes=invoice.notes,
        service_name=str(service_customer.name or service_customer.email or "Servis"),
        service_ico=str(extra.get("supplier_ico") or getattr(service_customer, "ico", None) or "") or None,
        service_dic=str(extra.get("supplier_dic") or getattr(service_customer, "dic", None) or "") or None,
        service_address=_service_address(service_customer, extra),
        service_email=getattr(service_customer, "email", None),
        service_phone=getattr(service_customer, "phone", None) or getattr(service_customer, "phone_e164", None),
        bank_account=bank_account,
        customer_name=str((customer.name or customer.email) if customer else "—"),
        customer_address=_customer_address(customer),
        customer_ico=getattr(customer, "ico", None) if customer else None,
        customer_dic=getattr(customer, "dic", None) if customer else None,
        vehicle_label=vehicle_label,
        vehicle_plate=plate,
        vehicle_vin=vin,
        vehicle_odometer_km=int(odometer) if odometer is not None else None,
        work_order_id=int(invoice.work_order_id) if invoice.work_order_id else None,
        verify_url=verify_url,
        verification_code=verification_code,
        payment_qr_payload=payment_qr or None,
        lines=[
            InvoiceLinePayload(
                description=str(ln.description or "Položka"),
                quantity=float(ln.quantity or 0),
                unit=str(ln.unit or "ks"),
                unit_price=float(ln.unit_price or 0),
                tax_rate=float(ln.tax_rate or 0),
                line_total=float(ln.line_total or 0),
            )
            for ln in sorted(lines, key=lambda x: (x.sort_order, x.id))
        ],
    )


def find_invoice_vehicle_document(db: Session, *, invoice_id: int) -> Optional[VehicleDocument]:
    return (
        db.query(VehicleDocument)
        .filter(
            VehicleDocument.source_type == "service_invoice",
            VehicleDocument.source_id == int(invoice_id),
            VehicleDocument.document_type == "invoice",
        )
        .order_by(VehicleDocument.id.desc())
        .first()
    )


def sync_invoice_vehicle_document(
    db: Session,
    *,
    invoice: ServiceInvoice,
    service_customer: Customer,
    lines: list[ServiceInvoiceLine],
    actor: Customer,
) -> Optional[VehicleDocument]:
    if invoice.vehicle_id is None:
        return None

    vehicle = db.query(Vehicle).filter(Vehicle.id == int(invoice.vehicle_id)).first()
    if vehicle is None:
        return None

    existing = find_invoice_vehicle_document(db, invoice_id=int(invoice.id))
    token = existing.verification_token if existing and existing.verification_token else generate_verification_token()
    metadata_existing = parse_metadata(existing.metadata_json) if existing else {}
    verification_code = metadata_existing.get("verification_code") or build_verification_code(
        f"invoice:{invoice.id}:{token}"
    )

    payload = build_invoice_document_payload(
        db,
        invoice=invoice,
        lines=lines,
        service_customer=service_customer,
        verification_token=token,
        verification_code=verification_code,
    )
    pdf_bytes = render_invoice_document_pdf(payload)
    pdf_hash = sha256_bytes(pdf_bytes)

    doc_number = invoice.invoice_number or f"INV-DRAFT-{invoice.id}"
    filename = safe_filename(f"{doc_number}.pdf")
    storage_relative = f"tenants/{int(invoice.tenant_id)}/vehicles/{int(vehicle.id)}/invoice/{filename}"
    write_document_bytes(VEHICLE_DOCUMENTS_ROOT / storage_relative, pdf_bytes)

    from src.modules.vehicle_hub.ownership import get_primary_vehicle_owner
    owner = get_primary_vehicle_owner(db, vehicle)
    owner_id = int(owner.id) if owner else None

    doc_status = _invoice_document_status(str(invoice.status or "draft"))
    title = f"Faktura {doc_number}" if invoice.invoice_number else f"Faktura — koncept #{invoice.id}"
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
        "invoice_id": int(invoice.id),
        "work_order_id": int(invoice.work_order_id) if invoice.work_order_id else None,
    }

    if existing:
        existing.document_status = doc_status
        existing.title = title
        existing.document_number = invoice.invoice_number
        existing.storage_path = storage_relative
        existing.file_size = len(pdf_bytes)
        existing.updated_at = now
        existing.metadata_json = dump_metadata(metadata)
        if str(invoice.status) == "cancelled":
            existing.archived_at = existing.archived_at or now
        db.add(existing)
        db.flush()
        return existing

    row = VehicleDocument(
        tenant_id=int(invoice.tenant_id),
        vehicle_id=int(vehicle.id),
        document_type="invoice",
        document_status=doc_status,
        title=title,
        document_number=invoice.invoice_number,
        source_type="service_invoice",
        source_id=int(invoice.id),
        service_customer_id=int(invoice.service_id),
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


def get_invoice_document_card(db: Session, *, invoice_id: int) -> Optional[dict]:
    from .document_service import serialize_document_card

    doc = find_invoice_vehicle_document(db, invoice_id=int(invoice_id))
    if doc is None:
        return None
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(doc.vehicle_id)).first()
    return serialize_document_card(doc, vehicle=vehicle)
