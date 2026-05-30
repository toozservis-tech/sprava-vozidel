from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..document_layout import (
    COLOR_BORDER,
    COLOR_DARK,
    COLOR_MUTED,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    FONT_BOLD,
    FONT_REGULAR,
    LOGO_PATH,
    build_document_styles,
    build_qr_block,
    status_label,
)
from ..invoice_models import InvoiceDocumentPayload


def _money(value: float, currency: str) -> str:
    cur = "Kč" if str(currency or "CZK").upper() == "CZK" else str(currency or "CZK")
    try:
        return f"{float(value):,.2f} {cur}".replace(",", " ")
    except (TypeError, ValueError):
        return f"{value} {cur}"


def _build_header(payload: InvoiceDocumentPayload, styles: dict[str, ParagraphStyle]) -> Table:
    badge_status = payload.document_status
    service_lines = [f"<b>{payload.service_name}</b>"]
    if payload.service_address:
        service_lines.append(payload.service_address)
    if payload.service_ico:
        ico_line = f"IČO: {payload.service_ico}"
        if payload.service_dic:
            ico_line += f" · DIČ: {payload.service_dic}"
        service_lines.append(ico_line)
    if payload.service_email or payload.service_phone:
        service_lines.append(" · ".join(p for p in [payload.service_email, payload.service_phone] if p))
    if payload.bank_account:
        service_lines.append(f"Účet: {payload.bank_account}")

    logo_cell = ""
    if LOGO_PATH.exists():
        try:
            logo_cell = RLImage(str(LOGO_PATH), width=18 * mm, height=18 * mm)
        except Exception:
            logo_cell = ""
    left_content = [[logo_cell, Paragraph("<br/>".join(service_lines), styles["body"])]]
    left = Table(left_content, colWidths=[20 * mm, 98 * mm])
    left.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

    meta = [
        f"<b>{status_label(badge_status)}</b>",
        payload.invoice_number or "(koncept — číslo po vystavení)",
    ]
    right = Paragraph("<br/>".join(meta), styles["badge"])
    table = Table([[left, right]], colWidths=[120 * mm, 58 * mm])
    table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (1, 0), (1, 0), COLOR_SURFACE),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return table


def _build_meta_table(payload: InvoiceDocumentPayload, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        ["Datum vystavení", payload.issued_at_label or "—"],
        ["Datum splatnosti", payload.due_at_label or "—"],
        ["Variabilní symbol", payload.variable_symbol or "—"],
        ["Forma úhrady", payload.payment_method or "—"],
    ]
    if payload.order_number:
        rows.append(["Objednávka / zakázka", payload.order_number])
    data = [[Paragraph(f"<b>{a}</b>", styles["muted"]), Paragraph(str(b), styles["body"])] for a, b in rows]
    table = Table(data, colWidths=[45 * mm, 133 * mm])
    table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_SURFACE),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    return table


def _build_party_table(payload: InvoiceDocumentPayload, styles: dict[str, ParagraphStyle]) -> Table:
    customer_lines = ["<b>Odběratel</b>", payload.customer_name or "—"]
    if payload.customer_address:
        customer_lines.append(payload.customer_address)
    if payload.customer_ico:
        line = f"IČO: {payload.customer_ico}"
        if payload.customer_dic:
            line += f" · DIČ: {payload.customer_dic}"
        customer_lines.append(line)

    vehicle_lines = ["<b>Vozidlo</b>", payload.vehicle_label or "—"]
    if payload.vehicle_plate:
        vehicle_lines.append(f"SPZ: {payload.vehicle_plate}")
    if payload.vehicle_vin:
        vehicle_lines.append(f"VIN: {payload.vehicle_vin}")
    if payload.vehicle_odometer_km is not None:
        vehicle_lines.append(f"Stav km: {int(payload.vehicle_odometer_km):,}".replace(",", " "))
    if payload.work_order_id:
        vehicle_lines.append(f"Zakázka: WO-{payload.work_order_id}")

    table = Table(
        [[Paragraph("<br/>".join(customer_lines), styles["body"]), Paragraph("<br/>".join(vehicle_lines), styles["body"])]],
        colWidths=[89 * mm, 89 * mm],
    )
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_SURFACE_ALT),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return table


def _build_lines_table(payload: InvoiceDocumentPayload, styles: dict[str, ParagraphStyle]) -> Table:
    header = ["Popis", "Množ.", "MJ", "Cena/j.", "DPH %", "Celkem"]
    data = [header]
    for line in payload.lines:
        data.append([
            str(line.description or "Položka"),
            f"{line.quantity:g}",
            str(line.unit or "ks"),
            _money(line.unit_price, payload.currency),
            f"{line.tax_rate:g}",
            _money(line.line_total, payload.currency),
        ])
    if len(data) == 1:
        data.append(["—", "—", "—", "—", "—", "—"])

    table = Table(data, colWidths=[68 * mm, 16 * mm, 12 * mm, 24 * mm, 16 * mm, 24 * mm], repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_SURFACE_ALT),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_DARK),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ])
    )
    return table


def _build_totals_table(payload: InvoiceDocumentPayload, styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        ["Mezisoučet bez DPH", _money(payload.subtotal, payload.currency)],
        ["DPH celkem", _money(payload.tax_total, payload.currency)],
        ["CELKEM K ÚHRADĚ", _money(payload.total, payload.currency)],
    ]
    data = [[Paragraph(r[0], styles["body"]), Paragraph(f"<b>{r[1]}</b>", styles["body"])] for r in rows]
    table = Table(data, colWidths=[120 * mm, 58 * mm])
    table.setStyle(
        TableStyle([
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("LINEABOVE", (0, 2), (-1, 2), 0.75, COLOR_BORDER),
            ("TOPPADDING", (0, 2), (-1, 2), 8),
        ])
    )
    return table


def render_invoice_document_pdf(payload: InvoiceDocumentPayload) -> bytes:
    styles = build_document_styles()
    buffer = BytesIO()
    title = payload.invoice_number or f"invoice-{payload.invoice_id}"
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=str(title),
    )
    story = []
    if payload.is_draft:
        story.append(Paragraph(
            "<b>KONCEPT — neplatný doklad</b>",
            ParagraphStyle("Draft", parent=styles["body"], textColor=colors.HexColor("#f59e0b")),
        ))
        story.append(Spacer(1, 4))

    story.append(_build_header(payload, styles))
    story.append(Spacer(1, 8))
    story.append(Paragraph("FAKTURA — daňový doklad", styles["title"]))
    story.append(Spacer(1, 6))
    story.append(_build_meta_table(payload, styles))
    story.append(Spacer(1, 8))
    story.append(_build_party_table(payload, styles))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Položky", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_build_lines_table(payload, styles))
    story.append(Spacer(1, 8))
    story.append(_build_totals_table(payload, styles))

    if payload.notes:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Poznámka", styles["section"]))
        story.append(Paragraph(str(payload.notes), styles["body"]))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER, spaceBefore=4, spaceAfter=8))
    story.append(build_qr_block(
        verify_url=payload.verify_url,
        verification_code=payload.verification_code,
        styles=styles,
    ))
    if payload.payment_qr_payload:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"<b>QR platba:</b> {payload.payment_qr_payload[:120]}…" if len(payload.payment_qr_payload or "") > 120 else f"<b>QR platba:</b> {payload.payment_qr_payload}",
            styles["muted"],
        ))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Doklad vystaven v systému Správa vozidel · Document Platform C1.1",
        styles["muted"],
    ))

    doc.build(story)
    content = buffer.getvalue()
    if len(content) < 4096:
        raise RuntimeError("Invoice PDF too small — render likely failed.")
    return content
