from __future__ import annotations

from typing import Iterable, Mapping

from ..documents.quote_models import QuoteDocumentPayload, QuoteLinePayload
from ..documents.renderers.quote import render_quote_document_pdf


def _coerce_payload(payload: Mapping[str, object]) -> QuoteDocumentPayload:
    items_raw = payload.get("items") or payload.get("lines") or []
    lines: list[QuoteLinePayload] = []
    if isinstance(items_raw, Iterable):
        for raw in items_raw:
            if not isinstance(raw, Mapping):
                continue
            quantity = float(raw.get("quantity") or 0) or 1.0
            unit_price = float(raw.get("unit_price") or 0)
            total_price = float(raw.get("total_price") or raw.get("line_total") or quantity * unit_price)
            lines.append(
                QuoteLinePayload(
                    description=str(raw.get("name") or raw.get("description") or "Položka"),
                    quantity=quantity,
                    unit=str(raw.get("unit") or "ks"),
                    unit_price=unit_price,
                    tax_rate=float(raw.get("tax_rate") or 21),
                    line_total=total_price,
                )
            )

    status = str(payload.get("status") or "draft")
    doc_status = {"draft": "draft", "sent": "pending", "approved": "approved", "rejected": "cancelled"}.get(status, "draft")
    total = float(payload.get("total_price") or payload.get("total") or 0)
    subtotal = float(payload.get("subtotal") or round(total / 1.21, 2))
    tax_total = float(payload.get("tax_total") or round(total - subtotal, 2))

    return QuoteDocumentPayload(
        quote_id=int(payload.get("id") or payload.get("quote_id") or 0),
        quote_number=str(payload.get("quote_number") or f"NAB-{int(payload.get('id') or 0):05d}"),
        document_status=doc_status,
        status_label=str(payload.get("status_label") or status),
        is_draft=status == "draft",
        created_at_label=str(payload.get("created_at_label") or "—"),
        valid_until_label=str(payload.get("valid_until_label") or "—"),
        validity_note=str(payload.get("validity_note")) if payload.get("validity_note") else None,
        currency=str(payload.get("currency") or "CZK"),
        subtotal=subtotal,
        tax_total=tax_total,
        total=total,
        service_name=str(payload.get("service_name") or "Servis"),
        service_ico=str(payload.get("service_ico")) if payload.get("service_ico") else None,
        service_dic=None,
        service_address="",
        service_email=None,
        service_phone=None,
        customer_name=str(payload.get("customer_name") or payload.get("customer_label") or "—"),
        customer_address="",
        customer_ico=None,
        customer_dic=None,
        vehicle_label=str(payload.get("vehicle_label") or "—"),
        vehicle_plate=str(payload.get("vehicle_spz")) if payload.get("vehicle_spz") else None,
        vehicle_vin=str(payload.get("vehicle_vin")) if payload.get("vehicle_vin") else None,
        vehicle_odometer_km=None,
        work_order_id=int(payload.get("work_order_id")) if payload.get("work_order_id") else None,
        verify_url=str(payload.get("verify_url")) if payload.get("verify_url") else None,
        verification_code=str(payload.get("verification_code")) if payload.get("verification_code") else None,
        lines=lines,
    )


def render_service_quote_pdf(payload: Mapping[str, object]) -> bytes:
    """Kompatibilní wrapper — používá platform quote renderer."""
    return render_quote_document_pdf(_coerce_payload(payload))
