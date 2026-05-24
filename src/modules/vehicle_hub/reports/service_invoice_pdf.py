from __future__ import annotations

from io import BytesIO
from typing import Iterable, Mapping

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas


def render_service_invoice_pdf(payload: Mapping[str, object]) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    height = A4[1]
    x = 18 * mm
    y = height - 20 * mm

    def line(text: str, *, size: int = 11, bold: bool = False, gap: float = 7) -> None:
        nonlocal y
        canvas.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        canvas.drawString(x, y, str(text or ""))
        y -= gap * mm

    doc_label = str(payload.get("document_status_label") or "Faktura")
    canvas.setTitle(str(payload.get("invoice_number") or f"invoice-{payload.get('id') or 'draft'}"))

    line(str(payload.get("service_name") or "Servis"), size=16, bold=True, gap=8)
    if payload.get("service_ico"):
        line(f"IČO: {payload.get('service_ico')}", size=10, gap=5)
    line(f"{doc_label}", size=14, bold=True, gap=8)
    inv_no = payload.get("invoice_number")
    line(f"Číslo: {inv_no if inv_no else '(koncept — číslo po vystavení)'}", size=10, gap=5)
    line(f"Stav dokladu: {payload.get('status_label') or payload.get('status') or '-'}", size=10, gap=5)
    line(f"Datum vystavení: {payload.get('issued_at_label') or '-'}", size=10, gap=5)
    line(f"Splatnost: {payload.get('due_at_label') or '-'}", size=10, gap=5)
    if payload.get("variable_symbol"):
        line(f"Variabilní symbol: {payload.get('variable_symbol')}", size=10, gap=5)
    if payload.get("order_number"):
        line(f"Objednávka: {payload.get('order_number')}", size=10, gap=5)
    line(f"Platba: {payload.get('payment_method') or 'prevod'}", size=10, gap=5)
    line(f"Odběratel: {payload.get('customer_label') or '-'}", size=10, gap=5)
    if payload.get("vehicle_label"):
        line(f"Vozidlo: {payload.get('vehicle_label')}", size=10, gap=5)
    line(f"Měna: {payload.get('currency') or 'CZK'}", size=10, gap=7)

    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(x, y, "Položky")
    y -= 7 * mm

    items = payload.get("lines") or []
    if not isinstance(items, Iterable):
        items = []

    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            continue
        desc = str(raw_item.get("description") or "Položka")
        qty = raw_item.get("quantity") or 0
        unit = raw_item.get("unit") or "ks"
        unit_price = raw_item.get("unit_price") or 0
        tax_rate = raw_item.get("tax_rate") or 0
        line_total = raw_item.get("line_total") or 0
        line(desc, size=11, bold=True, gap=5)
        line(
            f"{qty} {unit} × {unit_price} Kč, DPH {tax_rate} % → řádek celkem: {line_total} Kč",
            size=10,
            gap=5,
        )
        y -= 1.5 * mm
        if y < 35 * mm:
            canvas.showPage()
            y = height - 20 * mm

    y -= 4 * mm
    line(f"Základ: {payload.get('subtotal') or 0} Kč", size=11, bold=False, gap=5)
    line(f"DPH celkem: {payload.get('tax_total') or 0} Kč", size=11, bold=False, gap=5)
    line(f"Celkem k úhradě: {payload.get('total') or 0} Kč", size=13, bold=True, gap=8)
    if payload.get("notes"):
        line("Poznámka:", size=10, bold=True, gap=5)
        line(str(payload.get("notes")), size=9, gap=4)
    line(
        "Interní doklad servisu — u konceptu jde o nečíslovaný náhled.",
        size=8,
        gap=5,
    )

    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
