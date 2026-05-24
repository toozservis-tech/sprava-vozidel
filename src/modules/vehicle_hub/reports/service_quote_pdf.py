from __future__ import annotations

from io import BytesIO
from typing import Iterable, Mapping

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas


def render_service_quote_pdf(payload: Mapping[str, object]) -> bytes:
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    width, height = A4
    x = 18 * mm
    y = height - 20 * mm

    def line(text: str, *, size: int = 11, bold: bool = False, gap: float = 7) -> None:
        nonlocal y
        canvas.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        canvas.drawString(x, y, str(text or ""))
        y -= gap * mm

    canvas.setTitle(str(payload.get("quote_number") or f"quote-{payload.get('id') or 'service'}"))

    line(str(payload.get("service_name") or "Servis"), size=16, bold=True, gap=8)
    if payload.get("service_ico"):
        line(f"IČO: {payload.get('service_ico')}", size=10, gap=5)
    line("Cenová nabídka", size=14, bold=True, gap=8)
    line(f"Datum: {payload.get('created_at_label') or '-'}", size=10, gap=5)
    line(f"Vozidlo: {payload.get('vehicle_label') or '-'}", size=10, gap=5)
    if payload.get("vehicle_vin"):
        line(f"VIN: {payload.get('vehicle_vin')}", size=10, gap=5)
    line(f"Stav nabídky: {payload.get('status_label') or payload.get('status') or '-'}", size=10, gap=7)

    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(x, y, "Položky")
    y -= 7 * mm

    items = payload.get("items") or []
    if not isinstance(items, Iterable):
        items = []

    for raw_item in items:
        if not isinstance(raw_item, Mapping):
            continue
        name = str(raw_item.get("name") or "Položka")
        quantity = raw_item.get("quantity") or 0
        unit_price = raw_item.get("unit_price") or 0
        total_price = raw_item.get("total_price") or 0
        line(name, size=11, bold=True, gap=5)
        line(f"Množství: {quantity}   Cena/ks: {unit_price} Kč   Celkem: {total_price} Kč", size=10, gap=5)
        y -= 1.5 * mm
        if y < 35 * mm:
            canvas.showPage()
            y = height - 20 * mm

    labor_hours = payload.get("labor_hours")
    labor_rate = payload.get("labor_rate")
    if labor_hours or labor_rate:
        y -= 3 * mm
        line("Práce", size=11, bold=True, gap=5)
        line(f"Hodiny: {labor_hours or 0}   Sazba: {labor_rate or 0} Kč/h", size=10, gap=6)

    y -= 4 * mm
    line(f"Celková cena: {payload.get('total_price') or 0} Kč", size=13, bold=True, gap=8)
    line("Doklad je určen jako zákaznický výstup bez interních poznámek.", size=9, gap=5)

    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
