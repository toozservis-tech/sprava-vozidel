from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..document_layout import (
    COLOR_BORDER,
    COLOR_MUTED,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    FONT_BOLD,
    FONT_REGULAR,
    LOGO_PATH,
    build_document_styles,
    build_footer_paragraph,
    build_header_table,
    build_qr_block,
)
from ..intake_protocol_models import IntakeProtocolDocumentPayload


def _info_table(rows: list[tuple[str, str]], styles: dict) -> Table:
    data = [
        [Paragraph(f"<b>{label}</b>", styles["muted"]), Paragraph(str(value or "Neuvedeno"), styles["body"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[48 * mm, 130 * mm])
    table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_SURFACE),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    return table


def _party_table(payload: IntakeProtocolDocumentPayload, styles: dict) -> Table:
    service_lines = ["<b>Servis</b>", payload.service_name or "Neuvedeno"]
    if payload.service_address:
        service_lines.append(payload.service_address)
    if payload.service_ico:
        line = f"IČO: {payload.service_ico}"
        if payload.service_dic:
            line += f" · DIČ: {payload.service_dic}"
        service_lines.append(line)
    if payload.service_phone or payload.service_email:
        service_lines.append(" · ".join(p for p in [payload.service_phone, payload.service_email] if p))

    customer_lines = ["<b>Zákazník</b>", payload.customer_name or "Neuvedeno"]
    if payload.customer_contact and payload.customer_contact != payload.customer_name:
        customer_lines.append(payload.customer_contact)

    vehicle_lines = ["<b>Vozidlo</b>", payload.vehicle_label or "Neuvedeno"]
    if payload.vehicle_plate:
        vehicle_lines.append(f"SPZ: {payload.vehicle_plate}")
    if payload.vehicle_vin:
        vehicle_lines.append(f"VIN: {payload.vehicle_vin}")
    if payload.vehicle_odometer_km is not None:
        vehicle_lines.append(f"Stav km: {int(payload.vehicle_odometer_km):,}".replace(",", " "))
    if payload.fuel_level:
        vehicle_lines.append(f"Palivo: {payload.fuel_level}")

    table = Table(
        [
            [Paragraph("<br/>".join(service_lines), styles["body"]), Paragraph("<br/>".join(customer_lines), styles["body"])],
            [Paragraph("<br/>".join(vehicle_lines), styles["body"]), Paragraph("", styles["body"])],
        ],
        colWidths=[89 * mm, 89 * mm],
    )
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_SURFACE_ALT),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("SPAN", (0, 1), (1, 1)),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return table


def _checklist_table(payload: IntakeProtocolDocumentPayload, styles: dict) -> Table:
    header = ["Položka", "Stav"]
    data = [header]
    for item in payload.checklist_items:
        data.append([str(item.label), str(item.value or "Neuvedeno")])
    if len(data) == 1:
        data.append(["—", "Neuvedeno"])
    table = Table(data, colWidths=[100 * mm, 78 * mm], repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_SURFACE_ALT),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    return table


def _photo_slot_cell(slot, styles: dict) -> list:
    cell_parts: list = [Paragraph(f"<b>{slot.label}</b>", styles["body"])]
    status = str(slot.status or "Chybí")
    cell_parts.append(Paragraph(status, styles["muted"]))
    if slot.image_path:
        try:
            path = Path(slot.image_path)
            if path.exists():
                cell_parts.append(Spacer(1, 4))
                cell_parts.append(RLImage(str(path), width=38 * mm, height=28 * mm))
        except Exception:
            pass
    return cell_parts


def _photo_grid(payload: IntakeProtocolDocumentPayload, styles: dict) -> Table:
    slots = payload.photo_slots or []
    rows = []
    for index in range(0, len(slots), 2):
        left = slots[index]
        right = slots[index + 1] if index + 1 < len(slots) else None
        left_cell = _photo_slot_cell(left, styles)
        right_cell = _photo_slot_cell(right, styles) if right else [Paragraph("", styles["body"])]
        rows.append([
            left_cell if len(left_cell) == 1 else left_cell,
            right_cell if len(right_cell) == 1 else right_cell,
        ])
    if not rows:
        rows.append([
            [Paragraph("Fotodokumentace — neuvedena", styles["muted"])],
            [Paragraph("", styles["body"])],
        ])
    table = Table(rows, colWidths=[89 * mm, 89 * mm])
    table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return table


def _signature_table(payload: IntakeProtocolDocumentPayload, styles: dict) -> Table:
    table = Table(
        [[
            Paragraph(
                "<b>Podpis zákazníka</b><br/><br/><br/>_________________________<br/>"
                + payload.customer_signature_label,
                styles["body"],
            ),
            Paragraph(
                "<b>Podpis servisu</b><br/><br/><br/>_________________________<br/>"
                + payload.service_signature_label,
                styles["body"],
            ),
        ]],
        colWidths=[89 * mm, 89 * mm],
    )
    table.setStyle(
        TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ])
    )
    return table


def render_intake_protocol_pdf(payload: IntakeProtocolDocumentPayload) -> bytes:
    styles = build_document_styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=str(payload.document_number),
    )
    story: list = []

    if LOGO_PATH.exists():
        try:
            story.append(RLImage(str(LOGO_PATH), width=16 * mm, height=16 * mm))
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.append(
        build_header_table(
            service_name=payload.service_name,
            service_ico=payload.service_ico,
            document_type_label="Příjmový protokol",
            document_status=payload.document_status,
            document_number=payload.document_number,
            styles=styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph("PŘÍJMOVÝ PROTOKOL", styles["title"]))
    story.append(Paragraph("Doklad o stavu vozidla při převzetí do servisu", styles["subtitle"]))
    story.append(Spacer(1, 6))

    story.append(
        _info_table(
            [
                ("Číslo protokolu", payload.document_number),
                ("Stav dokumentu", payload.status_label),
                ("Datum a čas příjmu", payload.received_at_label),
                ("Vytvořeno", payload.created_at_label),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(_party_table(payload, styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Stav vozidla při příjmu", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(
        _info_table(
            [
                ("S čím auto přijelo", payload.arrival_condition),
                ("Požadavek zákazníka", payload.customer_request),
                ("Viditelná závada", payload.visible_defect),
                ("Poznámka technika", payload.technician_note),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph("Checklist stavu vozidla", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_checklist_table(payload, styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Fotodokumentace příjmu", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_photo_grid(payload, styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Podpisy", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_signature_table(payload, styles))
    story.append(Spacer(1, 10))

    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER, spaceBefore=4, spaceAfter=8))
    story.append(
        build_qr_block(
            verify_url=payload.verify_url,
            verification_code=payload.verification_code,
            styles=styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(
        build_footer_paragraph(
            footer_text="Doklad vystaven v systému Správa vozidel · Document Platform C1.4",
            styles=styles,
        )
    )

    doc.build(story)
    return buffer.getvalue()
