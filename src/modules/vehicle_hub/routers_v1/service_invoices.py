"""
Servisní faktury (Fáze 1): draft / issued / cancelled, číslování při vystavení, PDF, audit.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core import config

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..fakturyweb_client import FakturyWebClient, FakturyWebConfig, FakturyWebError
from ..models import (
    Customer,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceInvoiceCounter,
    ServiceInvoiceLine,
    ServiceQuote,
    ServiceRecord,
    ServiceWorkOrder,
    Vehicle as VehicleModel,
)
from ..reports.service_invoice_pdf import render_service_invoice_pdf
from ..schema_management import assert_module_ready
from src.modules.licensing.service import assert_service_invoice_monthly_quota
from .auth import get_current_user

router = APIRouter(prefix="/api/service", tags=["service-invoices"])


def _require_service_invoice_role(current_user: Customer) -> None:
    role = str(getattr(current_user, "role", "") or "").lower()
    if role != "service":
        raise HTTPException(status_code=403, detail="Faktury může spravovat pouze servisní účet.")


def _ensure_service_invoices_schema(db: Session) -> None:
    assert_module_ready(db, "service_invoices", detail_prefix="Servisní faktury nejsou připraveny")
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní propojení není připravené")


def _ensure_invoice_customer(db: Session, *, current_user: Customer, customer_id: int) -> Customer:
    owner = db.query(Customer).filter(Customer.id == int(customer_id)).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Zákazník nebyl nalezen.")
    link = (
        db.query(ServiceCustomerLink.id)
        .filter(
            ServiceCustomerLink.service_customer_id == current_user.id,
            ServiceCustomerLink.customer_id == owner.id,
            ServiceCustomerLink.status == "active",
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="Servis nemá vazbu na tohoto zákazníka.")
    return owner


def _validate_service_invoice_links(
    db: Session,
    *,
    tenant_id: int,
    vehicle_id: Optional[int],
    service_record_id: Optional[int],
    work_order_id: Optional[int],
) -> None:
    if service_record_id is not None:
        rec = (
            db.query(ServiceRecord)
            .filter(
                ServiceRecord.id == int(service_record_id),
                ServiceRecord.tenant_id == int(tenant_id),
            )
            .first()
        )
        if not rec:
            raise HTTPException(status_code=404, detail="Servisní záznam nebyl nalezen.")
        if vehicle_id is not None and int(rec.vehicle_id) != int(vehicle_id):
            raise HTTPException(
                status_code=422,
                detail="service_record_id musí patřit ke stejnému vehicle_id jako faktura.",
            )
    if work_order_id is not None:
        wo = (
            db.query(ServiceWorkOrder)
            .filter(
                ServiceWorkOrder.id == int(work_order_id),
                ServiceWorkOrder.tenant_id == int(tenant_id),
            )
            .first()
        )
        if not wo:
            raise HTTPException(status_code=404, detail="Servisní zakázka nebyla nalezena.")
        if vehicle_id is not None and int(wo.vehicle_id) != int(vehicle_id):
            raise HTTPException(
                status_code=422,
                detail="work_order_id musí patřit ke stejnému vehicle_id jako faktura.",
            )


def _ensure_invoice_party(
    db: Session,
    *,
    current_user: Customer,
    customer_id: int,
    vehicle_id: Optional[int],
) -> tuple[Customer, Optional[VehicleModel]]:
    owner = _ensure_invoice_customer(db, current_user=current_user, customer_id=customer_id)
    if vehicle_id is None:
        return owner, None
    from .service_dashboard import _resolve_owner_and_vehicle

    o2, vehicle = _resolve_owner_and_vehicle(
        db,
        current_user=current_user,
        owner_id=int(owner.id),
        vehicle_id=int(vehicle_id),
    )
    return o2, vehicle


def _compute_line_amounts(*, quantity: float, unit_price: float, tax_rate: float) -> tuple[float, float, float]:
    net = round(float(quantity) * float(unit_price), 2)
    tax = round(net * (float(tax_rate) / 100.0), 2)
    gross = round(net + tax, 2)
    return net, tax, gross


def _build_lines_from_payload(
    db: Session,
    *,
    tenant_id: int,
    invoice_id: int,
    items: list["ServiceInvoiceLineIn"],
) -> tuple[list[ServiceInvoiceLine], float, float, float]:
    subtotal = 0.0
    tax_total = 0.0
    total = 0.0
    rows: list[ServiceInvoiceLine] = []
    for idx, item in enumerate(items):
        net, tax, gross = _compute_line_amounts(
            quantity=item.quantity,
            unit_price=item.unit_price,
            tax_rate=item.tax_rate,
        )
        subtotal += net
        tax_total += tax
        total += gross
        rows.append(
            ServiceInvoiceLine(
                tenant_id=int(tenant_id),
                invoice_id=int(invoice_id),
                description=str(item.description or "").strip() or "Položka",
                quantity=float(item.quantity),
                unit=str(item.unit or "ks").strip()[:32] or "ks",
                unit_price=float(item.unit_price),
                tax_rate=float(item.tax_rate),
                line_total=gross,
                sort_order=idx,
            )
        )
    subtotal = round(subtotal, 2)
    tax_total = round(tax_total, 2)
    total = round(total, 2)
    return rows, subtotal, tax_total, total


def _allocate_invoice_number(db: Session, *, tenant_id: int) -> str:
    row = db.query(ServiceInvoiceCounter).filter(ServiceInvoiceCounter.tenant_id == int(tenant_id)).first()
    if row is None:
        row = ServiceInvoiceCounter(tenant_id=int(tenant_id), next_seq=1)
        db.add(row)
        db.flush()
    seq = int(row.next_seq)
    row.next_seq = seq + 1
    db.flush()
    year = datetime.utcnow().year
    return f"FV-{year}-{seq:06d}"


def _get_invoice_for_service(
    db: Session,
    *,
    current_user: Customer,
    invoice_id: int,
) -> ServiceInvoice:
    inv = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.id == int(invoice_id),
            ServiceInvoice.service_id == int(current_user.id),
            ServiceInvoice.tenant_id == int(current_user.tenant_id),
        )
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nebyla nalezena.")
    return inv


def _serialize_line(line: ServiceInvoiceLine) -> dict[str, Any]:
    return {
        "id": int(line.id),
        "description": line.description,
        "quantity": line.quantity,
        "unit": line.unit,
        "unit_price": line.unit_price,
        "tax_rate": line.tax_rate,
        "line_total": line.line_total,
        "sort_order": line.sort_order,
    }


def _serialize_invoice(
    inv: ServiceInvoice,
    lines: list[ServiceInvoiceLine],
    *,
    include_lines: bool = True,
    customer_label: Optional[str] = None,
    vehicle_label: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": int(inv.id),
        "tenant_id": int(inv.tenant_id),
        "service_id": int(inv.service_id),
        "customer_id": int(inv.customer_id),
        "vehicle_id": int(inv.vehicle_id) if inv.vehicle_id is not None else None,
        "service_record_id": int(inv.service_record_id) if getattr(inv, "service_record_id", None) else None,
        "work_order_id": int(inv.work_order_id) if getattr(inv, "work_order_id", None) else None,
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "status_label": _status_label(str(inv.status or "")),
        "subtotal": inv.subtotal,
        "tax_total": inv.tax_total,
        "total": inv.total,
        "currency": inv.currency,
        "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        "due_at": inv.due_at.isoformat() if inv.due_at else None,
        "cancelled_at": inv.cancelled_at.isoformat() if inv.cancelled_at else None,
        "notes": inv.notes,
        "extra": _parse_invoice_extra(inv.extra_json),
        "fakturyweb": {
            "code": inv.fakturyweb_code,
            "number": inv.fakturyweb_number,
            "status": inv.fakturyweb_status,
            "pdf_url": inv.fakturyweb_pdf_url,
            "exported_at": inv.fakturyweb_exported_at.isoformat() if inv.fakturyweb_exported_at else None,
            "last_sync_at": inv.fakturyweb_last_sync_at.isoformat() if inv.fakturyweb_last_sync_at else None,
        },
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        "customer_label": customer_label,
        "vehicle_label": vehicle_label,
    }
    if include_lines:
        body["lines"] = [_serialize_line(ln) for ln in sorted(lines, key=lambda x: (x.sort_order, x.id))]
    return body


def _resolve_invoice_labels(db: Session, *, inv: ServiceInvoice) -> tuple[Optional[str], Optional[str]]:
    customer = db.query(Customer).filter(Customer.id == int(inv.customer_id)).first()
    vehicle = (
        db.query(VehicleModel).filter(VehicleModel.id == int(inv.vehicle_id)).first()
        if inv.vehicle_id is not None
        else None
    )
    customer_label = (customer.name or customer.email) if customer else None
    vehicle_label = None
    if vehicle:
        vehicle_label = " ".join(
            part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part
        ).strip() or getattr(vehicle, "nickname", None) or getattr(vehicle, "plate", None) or getattr(vehicle, "vin", None)
    return customer_label, vehicle_label


def _audit(
    db: Session,
    *,
    invoice: ServiceInvoice,
    action: str,
    actor: Customer,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    write_global_audit_log(
        db,
        entity_type="service_invoice",
        entity_id=int(invoice.id),
        action=action,
        actor_user_id=int(actor.id),
        actor_role=str(getattr(actor, "role", None) or ""),
        tenant_id=int(invoice.tenant_id),
        metadata=metadata or {},
    )


class ServiceInvoiceLineIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=512)
    quantity: float = Field(default=1, gt=0)
    unit: str = Field(default="ks", max_length=32)
    unit_price: float = Field(default=0, ge=0)
    tax_rate: float = Field(default=0, ge=0, le=100)


class ServiceInvoiceCreateRequest(BaseModel):
    customer_id: int = Field(gt=0)
    vehicle_id: Optional[int] = Field(default=None, gt=0)
    service_record_id: Optional[int] = Field(default=None, gt=0)
    work_order_id: Optional[int] = Field(default=None, gt=0)
    from_service_record: bool = Field(
        default=False,
        description="Pokud True, service_record_id je povinné (faktura vzniká ze servisního záznamu).",
    )
    non_vehicle_invoice: bool = Field(
        default=False,
        description="Ruční faktura bez vozidla; do extra_json se uloží manual_non_vehicle_invoice.",
    )
    currency: str = Field(default="CZK", max_length=8)
    due_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=8000)
    extra: dict[str, Any] = Field(default_factory=dict)
    lines: list[ServiceInvoiceLineIn] = Field(default_factory=list)


class ServiceInvoiceUpdateRequest(BaseModel):
    customer_id: Optional[int] = Field(default=None, gt=0)
    vehicle_id: Optional[int] = None
    service_record_id: Optional[int] = None
    work_order_id: Optional[int] = None
    currency: Optional[str] = Field(default=None, max_length=8)
    due_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=8000)
    extra: Optional[dict[str, Any]] = None
    lines: Optional[list[ServiceInvoiceLineIn]] = None


class InvoiceFromQuoteRequest(BaseModel):
    billing_customer_id: Optional[int] = Field(default=None, gt=0)
    tax_rate: float = Field(default=21, ge=0, le=100)
    currency: str = Field(default="CZK", max_length=8)
    notes: Optional[str] = Field(default=None, max_length=8000)


class FakturyWebExportRequest(BaseModel):
    force: bool = False
    apitest: Optional[bool] = None


def _status_label(status: str) -> str:
    return {"draft": "Koncept", "issued": "Vystaveno", "cancelled": "Zrušeno"}.get(
        str(status or "").lower(),
        str(status or ""),
    )


def _parse_invoice_extra(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean_invoice_extra(value: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed_scalars = {
        "invoice_type",
        "payment_method",
        "issue_date",
        "delivery_date",
        "variable_symbol",
        "constant_symbol",
        "specific_symbol",
        "order_number",
        "issued_by",
        "language",
        "style",
        "rounding",
        "qr",
        "already_paid",
        "internal_note",
        "customer_note",
        "supplier_name",
        "supplier_ico",
        "supplier_dic",
        "supplier_street",
        "supplier_city",
        "supplier_zip",
        "supplier_state",
        "supplier_email",
        "supplier_phone",
        "supplier_bankaccount",
        "supplier_bank",
        "supplier_iban",
        "supplier_swift",
        "customer_name",
        "customer_ico",
        "customer_dic",
        "customer_street",
        "customer_city",
        "customer_zip",
        "customer_state",
        "customer_email",
        "manual_non_vehicle_invoice",
    }
    cleaned: dict[str, Any] = {}
    for key in allowed_scalars:
        if key not in value:
            continue
        raw = value.get(key)
        if raw is None:
            continue
        if isinstance(raw, bool):
            cleaned[key] = raw
            continue
        if isinstance(raw, (int, float)):
            cleaned[key] = raw
            continue
        text = str(raw).strip()
        if text:
            cleaned[key] = text[:8000] if key in {"internal_note", "customer_note"} else text[:255]
    tags = value.get("tags")
    if isinstance(tags, list):
        cleaned["tags"] = [str(item).strip()[:80] for item in tags if str(item).strip()][:20]
    elif isinstance(tags, str):
        cleaned["tags"] = [item.strip()[:80] for item in tags.split(",") if item.strip()][:20]
    return cleaned


def _invoice_extra_json(value: Optional[dict[str, Any]]) -> Optional[str]:
    cleaned = _clean_invoice_extra(value)
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False, sort_keys=True)


def _invoice_type_code(value: Any) -> int:
    raw = str(value or "1").strip().lower()
    mapping = {
        "invoice": 1,
        "regular": 1,
        "faktura": 1,
        "advance": 2,
        "zalohova": 2,
        "credit_note": 3,
        "dobropis": 3,
        "debit_note": 4,
        "vrubopis": 4,
        "payment_receipt": 5,
        "receipt": 5,
    }
    if raw in mapping:
        return mapping[raw]
    try:
        numeric = int(raw)
    except Exception:
        return 1
    return numeric if numeric in {1, 2, 3, 4, 5} else 1


def _fakturyweb_date(value: Any, fallback: Optional[datetime] = None) -> Optional[str]:
    raw = str(value or "").strip()
    if raw:
        return raw[:10]
    return _date_only(fallback)


def _pdf_payload(
    db: Session,
    *,
    invoice: ServiceInvoice,
    lines: list[ServiceInvoiceLine],
    service_customer: Customer,
) -> dict[str, Any]:
    customer = db.query(Customer).filter(Customer.id == int(invoice.customer_id)).first()
    vehicle = (
        db.query(VehicleModel).filter(VehicleModel.id == int(invoice.vehicle_id)).first()
        if invoice.vehicle_id
        else None
    )
    vehicle_label = None
    if vehicle:
        vehicle_label = " ".join(
            p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if p
        ).strip() or getattr(vehicle, "nickname", None) or getattr(vehicle, "plate", None)

    doc_status = "KONCEPT — nečíslovaný náhled" if str(invoice.status) == "draft" else "Vystavený doklad"
    if str(invoice.status) == "cancelled":
        doc_status = "Zrušený doklad"

    extra = _parse_invoice_extra(invoice.extra_json)
    return {
        "id": int(invoice.id),
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "status_label": _status_label(str(invoice.status or "")),
        "document_status_label": doc_status,
        "service_name": service_customer.name or service_customer.email,
        "service_ico": getattr(service_customer, "ico", None),
        "issued_at_label": invoice.issued_at.strftime("%d.%m.%Y %H:%M") if invoice.issued_at else "-",
        "due_at_label": invoice.due_at.strftime("%d.%m.%Y %H:%M") if invoice.due_at else "-",
        "customer_label": (customer.name or customer.email) if customer else "-",
        "vehicle_label": vehicle_label,
        "payment_method": extra.get("payment_method") or "prevod",
        "variable_symbol": extra.get("variable_symbol") or "",
        "order_number": extra.get("order_number") or "",
        "currency": invoice.currency or "CZK",
        "subtotal": invoice.subtotal,
        "tax_total": invoice.tax_total,
        "total": invoice.total,
        "notes": invoice.notes,
        "lines": [_serialize_line(ln) for ln in sorted(lines, key=lambda x: (x.sort_order, x.id))],
    }


def _fakturyweb_config(*, api_test_override: Optional[bool] = None) -> FakturyWebConfig:
    return FakturyWebConfig(
        base_url=config.FAKTURYWEB_API_BASE_URL,
        email=config.FAKTURYWEB_EMAIL,
        api_key=config.FAKTURYWEB_API_KEY,
        api_test=config.FAKTURYWEB_API_TEST if api_test_override is None else bool(api_test_override),
        supplier_id=config.FAKTURYWEB_SUPPLIER_ID or None,
    )


def _fakturyweb_client(*, api_test_override: Optional[bool] = None) -> FakturyWebClient:
    return FakturyWebClient(_fakturyweb_config(api_test_override=api_test_override))


def _date_only(value: Optional[datetime]) -> Optional[str]:
    return value.strftime("%Y-%m-%d") if value else None


def _cz_currency(value: Optional[str]) -> str:
    raw = str(value or "CZK").strip()
    return "Kč" if raw.upper() == "CZK" else raw


def _customer_street(customer: Optional[Customer]) -> str:
    if not customer:
        return ""
    return " ".join(
        part for part in [getattr(customer, "street", None), getattr(customer, "street_number", None)] if part
    ).strip()


def _build_fakturyweb_payload(
    db: Session,
    *,
    invoice: ServiceInvoice,
    lines: list[ServiceInvoiceLine],
    service_customer: Customer,
    api_test_override: Optional[bool] = None,
) -> dict[str, Any]:
    customer = db.query(Customer).filter(Customer.id == int(invoice.customer_id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Zákazník faktury nebyl nalezen.")

    fw_config = _fakturyweb_config(api_test_override=api_test_override)
    extra = _parse_invoice_extra(invoice.extra_json)
    has_vat_lines = any(float(getattr(line, "tax_rate", 0) or 0) > 0 for line in lines)
    supplier: dict[str, Any]
    if fw_config.supplier_id:
        supplier = {"d_id": fw_config.supplier_id}
    else:
        supplier_name = str(extra.get("supplier_name") or service_customer.name or "").strip()
        if not supplier_name:
            raise HTTPException(
                status_code=422,
                detail="Servisní účet nemá vyplněný název dodavatele a FAKTURYWEB_SUPPLIER_ID není nastaven.",
            )
        supplier = {
            "d_name": supplier_name,
            "d_street": extra.get("supplier_street") or _customer_street(service_customer),
            "d_city": extra.get("supplier_city") or getattr(service_customer, "city", None) or "",
            "d_zip": extra.get("supplier_zip") or getattr(service_customer, "zip", None) or "",
            "d_state": extra.get("supplier_state") or "Česká republika",
            "d_ico": extra.get("supplier_ico") or getattr(service_customer, "ico", None) or "",
            "d_dic": extra.get("supplier_dic") or getattr(service_customer, "dic", None) or "",
            "d_vatpayer": 1 if (getattr(service_customer, "dic", None) or has_vat_lines) else 0,
            "d_viewpayer": 1,
            "d_email": extra.get("supplier_email") or getattr(service_customer, "email", None) or "",
            "d_phone": extra.get("supplier_phone") or getattr(service_customer, "phone", None) or "",
            "d_bankaccount": extra.get("supplier_bankaccount") or "",
            "d_bank": extra.get("supplier_bank") or "",
            "d_iban": extra.get("supplier_iban") or "",
            "d_swift": extra.get("supplier_swift") or "",
        }

    issue_date = _fakturyweb_date(extra.get("issue_date"), invoice.issued_at) or datetime.utcnow().strftime("%Y-%m-%d")
    delivery_date = _fakturyweb_date(extra.get("delivery_date"), invoice.issued_at) or issue_date
    due_date = _date_only(invoice.due_at)
    invoice_number = str(invoice.invoice_number or "").strip()
    fakturyweb_invoice: dict[str, Any] = {
        "f_vs": str(extra.get("variable_symbol") or "".join(ch for ch in invoice_number if ch.isdigit())[:10] or invoice.id),
        "f_date_issue": issue_date,
        "f_date_delivery": delivery_date,
        "f_ks": str(extra.get("constant_symbol") or ""),
        "f_ss": str(extra.get("specific_symbol") or ""),
        "f_issued_by": str(extra.get("issued_by") or ""),
        "f_payment": str(extra.get("payment_method") or "prevod"),
        "f_currency": _cz_currency(invoice.currency),
        "f_type": _invoice_type_code(extra.get("invoice_type")),
        "f_paid": extra.get("already_paid") or "",
        "f_rounding": int(extra.get("rounding") or 0),
        "f_style": str(extra.get("style") or "standard"),
        "f_language": str(extra.get("language") or "CS"),
        "f_qr": 1 if extra.get("qr", True) is not False else 0,
        "f_note": extra.get("customer_note") or invoice.notes or "",
        "f_internal_note": extra.get("internal_note") or f"TooZ Hub service_invoice_id={int(invoice.id)}",
        "f_order": str(extra.get("order_number") or ""),
        "f_tags": extra.get("tags") or [],
        "f_custom": str(invoice.id)[:50],
    }
    if due_date:
        fakturyweb_invoice["f_date_due"] = due_date
    if invoice_number.isdigit():
        fakturyweb_invoice["f_number"] = invoice_number

    return {
        "key": fw_config.api_key,
        "email": fw_config.email,
        "apitest": 1 if fw_config.api_test else 0,
        "d": supplier,
        "o": {
            "o_name": extra.get("customer_name") or customer.name or customer.email,
            "o_street": extra.get("customer_street") or _customer_street(customer),
            "o_city": extra.get("customer_city") or getattr(customer, "city", None) or "",
            "o_zip": extra.get("customer_zip") or getattr(customer, "zip", None) or "",
            "o_state": extra.get("customer_state") or "Česká republika",
            "o_ico": extra.get("customer_ico") or getattr(customer, "ico", None) or "",
            "o_dic": extra.get("customer_dic") or getattr(customer, "dic", None) or "",
            "o_email": extra.get("customer_email") or getattr(customer, "email", None) or "",
        },
        "f": fakturyweb_invoice,
        "p": [
            {
                "p_text": line.description,
                "p_quantity": line.quantity,
                "p_unit": line.unit,
                "p_price": line.unit_price,
                "p_vat": line.tax_rate,
                "p_custom": str(line.id)[:50],
            }
            for line in sorted(lines, key=lambda x: (x.sort_order, x.id))
        ],
    }


@router.get("/invoices")
def list_service_invoices(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    rows = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.service_id == int(current_user.id),
            ServiceInvoice.tenant_id == int(current_user.tenant_id),
        )
        .order_by(ServiceInvoice.created_at.desc(), ServiceInvoice.id.desc())
        .limit(250)
        .all()
    )
    items: list[dict[str, Any]] = []
    for inv in rows:
        customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
        items.append(
            _serialize_invoice(
                inv,
                [],
                include_lines=False,
                customer_label=customer_label,
                vehicle_label=vehicle_label,
            )
        )
    return {"items": items}


@router.post("/invoices", status_code=201)
def create_service_invoice(
    payload: ServiceInvoiceCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    if payload.non_vehicle_invoice:
        if payload.vehicle_id is not None:
            raise HTTPException(
                status_code=422,
                detail="U faktury bez vozidla ponechte vehicle_id prázdné.",
            )
        if payload.service_record_id or payload.work_order_id or payload.from_service_record:
            raise HTTPException(
                status_code=422,
                detail="Faktura bez vozidla nesmí nést vazbu na servisní záznam ani zakázku.",
            )
        _, vehicle = _ensure_invoice_party(
            db,
            current_user=current_user,
            customer_id=int(payload.customer_id),
            vehicle_id=None,
        )
        vehicle_id_val = None
        sr_id = None
        wo_id = None
    else:
        if not payload.vehicle_id:
            raise HTTPException(
                status_code=422,
                detail="vehicle_id je povinné pro běžnou servisní fakturu vázanou na vozidlo.",
            )
        if bool(payload.from_service_record) and not payload.service_record_id:
            raise HTTPException(
                status_code=422,
                detail="Faktura vznikající ze servisního záznamu musí mít vyplněné service_record_id.",
            )
        _, vehicle = _ensure_invoice_party(
            db,
            current_user=current_user,
            customer_id=int(payload.customer_id),
            vehicle_id=int(payload.vehicle_id),
        )
        vehicle_id_val = int(payload.vehicle_id)
        sr_id = int(payload.service_record_id) if payload.service_record_id else None
        wo_id = int(payload.work_order_id) if payload.work_order_id else None
        _validate_service_invoice_links(
            db,
            tenant_id=int(current_user.tenant_id),
            vehicle_id=vehicle_id_val,
            service_record_id=sr_id,
            work_order_id=wo_id,
        )

    extra_in = dict(payload.extra or {})
    if payload.non_vehicle_invoice:
        extra_in["manual_non_vehicle_invoice"] = True

    inv = ServiceInvoice(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        customer_id=int(payload.customer_id),
        vehicle_id=vehicle_id_val,
        service_record_id=sr_id,
        work_order_id=wo_id,
        status="draft",
        subtotal=0,
        tax_total=0,
        total=0,
        currency=str(payload.currency or "CZK").strip()[:8] or "CZK",
        due_at=payload.due_at,
        notes=(str(payload.notes).strip() if payload.notes else None),
        extra_json=_invoice_extra_json(extra_in),
    )
    db.add(inv)
    db.flush()

    line_rows, sub, tax, tot = _build_lines_from_payload(
        db,
        tenant_id=int(current_user.tenant_id),
        invoice_id=int(inv.id),
        items=payload.lines,
    )
    for lr in line_rows:
        db.add(lr)
    inv.subtotal = sub
    inv.tax_total = tax
    inv.total = tot
    db.flush()

    _audit(
        db,
        invoice=inv,
        action="invoice_created",
        actor=current_user,
        metadata={
            "customer_id": inv.customer_id,
            "vehicle_id": inv.vehicle_id,
            "vin": (str(getattr(vehicle, "vin", None) or "").strip().upper() or None),
            "non_vehicle": bool(payload.non_vehicle_invoice),
            "service_record_id": sr_id,
            "work_order_id": wo_id,
        },
    )
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.get("/invoices/{invoice_id}")
def get_service_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.put("/invoices/{invoice_id}")
def update_service_invoice(
    invoice_id: int,
    payload: ServiceInvoiceUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) != "draft":
        raise HTTPException(status_code=409, detail="Upravit lze pouze fakturu ve stavu koncept.")

    fields_set = set(getattr(payload, "model_fields_set", set()) or set())

    if "customer_id" in fields_set:
        if payload.customer_id is None:
            raise HTTPException(status_code=422, detail="customer_id je povinný.")
        cust_id = int(payload.customer_id)
    else:
        cust_id = int(inv.customer_id)

    if "vehicle_id" in fields_set:
        veh_id = payload.vehicle_id
    else:
        veh_id = int(inv.vehicle_id) if inv.vehicle_id is not None else None

    _ensure_invoice_party(db, current_user=current_user, customer_id=cust_id, vehicle_id=veh_id)

    if "customer_id" in fields_set:
        inv.customer_id = cust_id
    if "vehicle_id" in fields_set:
        inv.vehicle_id = int(payload.vehicle_id) if payload.vehicle_id else None
    if "service_record_id" in fields_set:
        inv.service_record_id = int(payload.service_record_id) if payload.service_record_id is not None else None
    if "work_order_id" in fields_set:
        inv.work_order_id = int(payload.work_order_id) if payload.work_order_id is not None else None
    if "currency" in fields_set and payload.currency is not None:
        inv.currency = str(payload.currency).strip()[:8] or "CZK"
    if "due_at" in fields_set:
        inv.due_at = payload.due_at
    if "notes" in fields_set:
        inv.notes = str(payload.notes).strip() if payload.notes else None
    if "extra" in fields_set:
        inv.extra_json = _invoice_extra_json(payload.extra)

    if "lines" in fields_set and payload.lines is not None:
        db.query(ServiceInvoiceLine).filter(ServiceInvoiceLine.invoice_id == int(inv.id)).delete(
            synchronize_session=False
        )
        line_rows, sub, tax, tot = _build_lines_from_payload(
            db,
            tenant_id=int(inv.tenant_id),
            invoice_id=int(inv.id),
            items=payload.lines,
        )
        for lr in line_rows:
            db.add(lr)
        inv.subtotal = sub
        inv.tax_total = tax
        inv.total = tot

    _validate_service_invoice_links(
        db,
        tenant_id=int(inv.tenant_id),
        vehicle_id=int(inv.vehicle_id) if inv.vehicle_id is not None else None,
        service_record_id=int(inv.service_record_id) if inv.service_record_id is not None else None,
        work_order_id=int(inv.work_order_id) if inv.work_order_id is not None else None,
    )

    db.flush()
    _audit(db, invoice=inv, action="invoice_updated", actor=current_user)
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.post("/invoices/{invoice_id}/issue")
def issue_service_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) != "draft":
        raise HTTPException(status_code=409, detail="Vystavit lze pouze koncept faktury.")

    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    if not lines:
        raise HTTPException(status_code=422, detail="Faktura musí obsahovat alespoň jednu položku.")

    assert_service_invoice_monthly_quota(db, service_customer_id=int(current_user.id))

    inv.invoice_number = _allocate_invoice_number(db, tenant_id=int(inv.tenant_id))
    inv.status = "issued"
    extra = _parse_invoice_extra(inv.extra_json)
    issue_date = _fakturyweb_date(extra.get("issue_date"))
    if issue_date:
        try:
            inv.issued_at = datetime.fromisoformat(issue_date)
        except Exception:
            inv.issued_at = datetime.utcnow()
    else:
        inv.issued_at = datetime.utcnow()
    db.flush()
    _audit(
        db,
        invoice=inv,
        action="invoice_issued",
        actor=current_user,
        metadata={
            "invoice_number": inv.invoice_number,
            "service_record_id": int(inv.service_record_id) if inv.service_record_id is not None else None,
        },
    )
    db.commit()
    db.refresh(inv)
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.get("/fakturyweb/status")
def get_fakturyweb_integration_status(
    current_user: Customer = Depends(get_current_user),
):
    _require_service_invoice_role(current_user)
    if not config.FAKTURYWEB_ENABLED:
        return {
            "enabled": False,
            "configured": False,
            "base_url": config.FAKTURYWEB_API_BASE_URL,
            "email": None,
            "api_test": config.FAKTURYWEB_API_TEST,
            "supplier_id_configured": bool(config.FAKTURYWEB_SUPPLIER_ID),
        }
    fw_config = _fakturyweb_config()
    return {
        "enabled": True,
        "configured": fw_config.configured,
        "base_url": fw_config.base_url,
        "email": fw_config.email if fw_config.email else None,
        "api_test": fw_config.api_test,
        "supplier_id_configured": bool(fw_config.supplier_id),
    }


@router.post("/invoices/{invoice_id}/fakturyweb/export")
def export_service_invoice_to_fakturyweb(
    invoice_id: int,
    payload: FakturyWebExportRequest | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    if not config.FAKTURYWEB_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Externí integrace FakturyWeb je vypnutá (FAKTURYWEB_ENABLED=false).",
        )

    payload = payload or FakturyWebExportRequest()
    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) != "issued":
        raise HTTPException(status_code=409, detail="Do FakturyWeb lze odeslat pouze vystavenou fakturu.")
    if inv.fakturyweb_code and not payload.force:
        raise HTTPException(status_code=409, detail="Faktura už je ve FakturyWeb exportovaná.")

    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    if not lines:
        raise HTTPException(status_code=422, detail="Faktura musí obsahovat alespoň jednu položku.")

    fw_payload = _build_fakturyweb_payload(
        db,
        invoice=inv,
        lines=lines,
        service_customer=current_user,
        api_test_override=payload.apitest,
    )
    try:
        result = _fakturyweb_client(api_test_override=payload.apitest).create_invoice(fw_payload)
    except FakturyWebError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FakturyWeb export selhal: {exc}") from exc

    inv.fakturyweb_code = str(result.get("code") or "").strip() or inv.fakturyweb_code
    inv.fakturyweb_number = str(result.get("number") or "").strip() or inv.fakturyweb_number
    inv.fakturyweb_status = "created"
    inv.fakturyweb_exported_at = datetime.utcnow()
    inv.fakturyweb_last_sync_at = inv.fakturyweb_exported_at
    db.flush()
    _audit(
        db,
        invoice=inv,
        action="invoice_fakturyweb_exported",
        actor=current_user,
        metadata={"fakturyweb_code": inv.fakturyweb_code, "fakturyweb_number": inv.fakturyweb_number},
    )
    db.commit()
    db.refresh(inv)
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.post("/invoices/{invoice_id}/fakturyweb/sync")
def sync_service_invoice_from_fakturyweb(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    if not config.FAKTURYWEB_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Externí integrace FakturyWeb je vypnutá (FAKTURYWEB_ENABLED=false).",
        )

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if not inv.fakturyweb_code:
        raise HTTPException(status_code=409, detail="Faktura zatím nemá FakturyWeb kód.")

    try:
        detail = _fakturyweb_client().invoice_status(str(inv.fakturyweb_code))
        pdf_info = _fakturyweb_client().invoice_pdf_info(str(inv.fakturyweb_code))
    except FakturyWebError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"FakturyWeb synchronizace selhala: {exc}") from exc

    inv.fakturyweb_status = str(detail.get("invoice_paid") or detail.get("invoice_status") or "synced")
    inv.fakturyweb_number = str(detail.get("invoice_number") or pdf_info.get("number") or inv.fakturyweb_number or "")
    inv.fakturyweb_pdf_url = str(pdf_info.get("url") or inv.fakturyweb_pdf_url or "")
    inv.fakturyweb_last_sync_at = datetime.utcnow()
    db.flush()
    _audit(
        db,
        invoice=inv,
        action="invoice_fakturyweb_synced",
        actor=current_user,
        metadata={"fakturyweb_status": inv.fakturyweb_status, "fakturyweb_number": inv.fakturyweb_number},
    )
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.post("/invoices/{invoice_id}/cancel")
def cancel_service_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) == "cancelled":
        raise HTTPException(status_code=409, detail="Faktura je již zrušena.")

    inv.status = "cancelled"
    inv.cancelled_at = datetime.utcnow()
    db.flush()
    _audit(db, invoice=inv, action="invoice_cancelled", actor=current_user)
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


def create_invoice_from_quote(
    quote_id: int,
    payload: InvoiceFromQuoteRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from . import service_dashboard as sd
    from .work_order_billing_api import (
        _invoice_for_work_order,
        _resolve_billing_customer_id,
        quote_items_to_invoice_lines,
    )

    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)
    sd._ensure_service_dashboard_schema(db)

    quote = sd._get_quote_or_404(db, current_user=current_user, quote_id=int(quote_id))
    if not quote.customer_id and quote.work_order_id:
        order = (
            db.query(ServiceWorkOrder)
            .filter(
                ServiceWorkOrder.id == int(quote.work_order_id),
                ServiceWorkOrder.service_customer_id == int(current_user.id),
            )
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Zakázka nabídky nebyla nalezena.")
        sd._assert_work_order_vehicle_access(db, current_user=current_user, order=order)
    elif not quote.customer_id:
        vehicle = db.query(VehicleModel).filter(VehicleModel.id == int(quote.vehicle_id)).first()
        if not vehicle or not sd._is_service_provisioned_unowned_for_service(
            db, current_user=current_user, vehicle=vehicle
        ):
            raise HTTPException(status_code=403, detail="Servis nemá oprávnění k nabídce.")

    work_order_id = int(quote.work_order_id) if quote.work_order_id else None
    if work_order_id:
        existing = _invoice_for_work_order(
            db,
            work_order_id=work_order_id,
            service_customer_id=int(current_user.id),
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "work_order_invoice_exists",
                    "message": "K této zakázce už existuje faktura.",
                    "invoice_id": int(existing.id),
                },
            )

    if quote.customer_id:
        customer_id = int(quote.customer_id)
        _ensure_invoice_customer(db, current_user=current_user, customer_id=customer_id)
    elif work_order_id:
        order = sd._get_work_order_or_404(db, current_user=current_user, work_order_id=work_order_id)
        customer_id = _resolve_billing_customer_id(
            db,
            current_user=current_user,
            order=order,
            billing_customer_id=payload.billing_customer_id,
        )
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "unowned_requires_billing_customer",
                "message": "Pro vystavení faktury k nepřiřazenému vozidlu doplňte fakturační kontakt zákazníka.",
            },
        )

    items = sd._parse_quote_items(getattr(quote, "items_json", None))
    if not items:
        raise HTTPException(status_code=422, detail="Nabídka nemá žádné položky pro fakturu.")
    line_payloads = quote_items_to_invoice_lines(items, default_tax_rate=float(payload.tax_rate))
    vehicle_id_val = int(quote.vehicle_id)
    sr_id = int(quote.service_record_id) if quote.service_record_id else None
    _validate_service_invoice_links(
        db,
        tenant_id=int(current_user.tenant_id),
        vehicle_id=vehicle_id_val,
        service_record_id=sr_id,
        work_order_id=work_order_id,
    )

    inv = ServiceInvoice(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        customer_id=int(customer_id),
        vehicle_id=vehicle_id_val,
        service_record_id=sr_id,
        work_order_id=work_order_id,
        status="draft",
        subtotal=0,
        tax_total=0,
        total=0,
        currency=str(payload.currency or "CZK").strip()[:8] or "CZK",
        notes=(str(payload.notes).strip() if payload.notes else None),
        extra_json=_invoice_extra_json({"source_quote_id": int(quote.id), "work_order_billing": True}),
    )
    db.add(inv)
    db.flush()

    line_rows, sub, tax, tot = _build_lines_from_payload(
        db,
        tenant_id=int(current_user.tenant_id),
        invoice_id=int(inv.id),
        items=line_payloads,
    )
    for lr in line_rows:
        db.add(lr)
    inv.subtotal = sub
    inv.tax_total = tax
    inv.total = tot
    db.flush()

    _audit(
        db,
        invoice=inv,
        action="invoice_created",
        actor=current_user,
        metadata={
            "quote_id": int(quote.id),
            "work_order_id": work_order_id,
            "vehicle_id": vehicle_id_val,
            "customer_id": int(customer_id),
            "source": "quote",
        },
    )
    write_global_audit_log(
        db,
        entity_type="service_invoice",
        entity_id=int(inv.id),
        action="invoice_created_from_quote",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(inv.tenant_id),
        vehicle_id=vehicle_id_val,
        metadata={"quote_id": int(quote.id), "work_order_id": work_order_id, "total": float(inv.total or 0)},
    )
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.post("/invoices/from-quote/{quote_id}", status_code=201)
def create_service_invoice_from_quote(
    quote_id: int,
    payload: InvoiceFromQuoteRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_invoice_from_quote(quote_id, payload, current_user=current_user, db=db)


@router.get("/invoices/{invoice_id}/pdf")
def get_service_invoice_pdf(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    pdf_bytes = render_internal_service_invoice_pdf(db, invoice=inv)
    _audit(
        db,
        invoice=inv,
        action="invoice_pdf_exported",
        actor=current_user,
        metadata={
            "invoice_number": inv.invoice_number,
            "status": inv.status,
            "service_record_id": getattr(inv, "service_record_id", None),
        },
    )
    db.commit()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="service-invoice-{int(inv.id)}.pdf"'},
    )


def render_internal_service_invoice_pdf(db: Session, *, invoice: ServiceInvoice) -> bytes:
    """PDF bytes pro interní fakturu (issuer podle invoice.service_id), bez zápisu auditu."""
    issuer = db.query(Customer).filter(Customer.id == int(invoice.service_id)).first()
    if not issuer:
        raise HTTPException(status_code=404, detail="Vystavitel faktury nebyl nalezen.")
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(invoice.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    return render_service_invoice_pdf(_pdf_payload(db, invoice=invoice, lines=lines, service_customer=issuer))
