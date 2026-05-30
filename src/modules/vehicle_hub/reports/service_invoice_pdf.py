from __future__ import annotations

from typing import Iterable, Mapping

from ..documents.invoice_models import InvoiceDocumentPayload, InvoiceLinePayload
from ..documents.renderers.invoice import render_invoice_document_pdf


def _coerce_payload(payload: Mapping[str, object]) -> InvoiceDocumentPayload:
    lines_raw = payload.get("lines") or []
    lines: list[InvoiceLinePayload] = []
    if isinstance(lines_raw, Iterable):
        for raw in lines_raw:
            if not isinstance(raw, Mapping):
                continue
            lines.append(
                InvoiceLinePayload(
                    description=str(raw.get("description") or "Položka"),
                    quantity=float(raw.get("quantity") or 0),
                    unit=str(raw.get("unit") or "ks"),
                    unit_price=float(raw.get("unit_price") or 0),
                    tax_rate=float(raw.get("tax_rate") or 0),
                    line_total=float(raw.get("line_total") or 0),
                )
            )

    status = str(payload.get("status") or "draft")
    doc_status = {"draft": "draft", "issued": "completed", "cancelled": "cancelled"}.get(status, "draft")

    return InvoiceDocumentPayload(
        invoice_id=int(payload.get("id") or 0),
        invoice_number=str(payload.get("invoice_number")) if payload.get("invoice_number") else None,
        document_status=doc_status,
        status_label=str(payload.get("status_label") or status),
        is_draft=status == "draft",
        issued_at_label=str(payload.get("issued_at_label") or "—"),
        due_at_label=str(payload.get("due_at_label") or "—"),
        variable_symbol=str(payload.get("variable_symbol") or ""),
        payment_method=str(payload.get("payment_method") or "převod"),
        order_number=str(payload.get("order_number") or ""),
        currency=str(payload.get("currency") or "CZK"),
        subtotal=float(payload.get("subtotal") or 0),
        tax_total=float(payload.get("tax_total") or 0),
        total=float(payload.get("total") or 0),
        notes=str(payload.get("notes")) if payload.get("notes") else None,
        service_name=str(payload.get("service_name") or "Servis"),
        service_ico=str(payload.get("service_ico")) if payload.get("service_ico") else None,
        service_dic=None,
        service_address="",
        service_email=None,
        service_phone=None,
        bank_account=None,
        customer_name=str(payload.get("customer_label") or "—"),
        customer_address="",
        customer_ico=None,
        customer_dic=None,
        vehicle_label=str(payload.get("vehicle_label") or "—"),
        vehicle_plate=None,
        vehicle_vin=None,
        vehicle_odometer_km=None,
        work_order_id=None,
        verify_url=str(payload.get("verify_url")) if payload.get("verify_url") else None,
        verification_code=str(payload.get("verification_code")) if payload.get("verification_code") else None,
        payment_qr_payload=str(payload.get("payment_qr_payload")) if payload.get("payment_qr_payload") else None,
        lines=lines,
    )


def render_service_invoice_pdf(payload: Mapping[str, object]) -> bytes:
    """Kompatibilní wrapper — používá platform invoice renderer."""
    return render_invoice_document_pdf(_coerce_payload(payload))
