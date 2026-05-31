from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
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
    build_footer_paragraph,
    build_header_table,
    build_qr_block,
)
from ..handover_protocol_models import (
    HandoverProtocolDocumentPayload,
    HandoverProtocolItemPayload,
    HandoverProtocolPartPayload,
)


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


def _party_table(payload: HandoverProtocolDocumentPayload, styles: dict) -> Table:
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
    vehicle_lines.append(f"Stav při předání: {payload.vehicle_condition or 'Neuvedeno'}")

    table = Table(
        [[
            Paragraph("<br/>".join(service_lines), styles["body"]),
            Paragraph("<br/>".join(customer_lines), styles["body"]),
        ], [
            Paragraph("<br/>".join(vehicle_lines), styles["body"]),
            Paragraph("", styles["body"]),
        ]],
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


def _checklist_table(title: str, items: list[HandoverProtocolItemPayload], styles: dict) -> Table:
    data = [["Položka", "Stav / hodnota"]]
    for item in items:
        data.append([str(item.label or "—"), str(item.value or "Neuvedeno")])
    table = Table(data, colWidths=[78 * mm, 100 * mm], repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_SURFACE_ALT),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_DARK),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    return table


def _parts_table(items: list[HandoverProtocolPartPayload], styles: dict) -> Table | None:
    if not items:
        return None
    data = [["Díl", "Množství", "MJ", "Poznámka"]]
    for item in items:
        data.append([
            str(item.name or "—"),
            str(item.quantity_label or "—"),
            str(item.unit or "—"),
            str(item.note or "—"),
        ])
    table = Table(data, colWidths=[72 * mm, 22 * mm, 16 * mm, 68 * mm], repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_SURFACE_ALT),
            ("TEXTCOLOR", (0, 0), (-1, 0), COLOR_DARK),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, COLOR_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])
    )
    return table


def _photo_cell(photo, styles: dict) -> list:
    cell_parts: list = [Paragraph(f"<b>{photo.label}</b>", styles["body"])]
    if photo.image_path:
        try:
            path = Path(photo.image_path)
            if path.exists():
                cell_parts.append(Spacer(1, 4))
                cell_parts.append(RLImage(str(path), width=38 * mm, height=28 * mm))
            else:
                cell_parts.append(Paragraph("Snímek uložen v systému", styles["muted"]))
        except Exception:
            cell_parts.append(Paragraph("Snímek uložen v systému", styles["muted"]))
    else:
        cell_parts.append(Paragraph("Bez náhledu", styles["muted"]))
    return cell_parts


def _photo_grid(payload: HandoverProtocolDocumentPayload, styles: dict) -> Table:
    photos = payload.photos or []
    if not photos:
        rows = [[
            [Paragraph("Fotodokumentace při předání — neuvedena", styles["muted"])],
            [Paragraph("", styles["body"])],
        ]]
    else:
        rows = []
        for index in range(0, len(photos), 2):
            left = photos[index]
            right = photos[index + 1] if index + 1 < len(photos) else None
            left_cell = _photo_cell(left, styles)
            right_cell = _photo_cell(right, styles) if right else [Paragraph("", styles["body"])]
            rows.append([left_cell, right_cell])
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


def _signature_table(payload: HandoverProtocolDocumentPayload, styles: dict) -> Table:
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


def render_handover_protocol_pdf(payload: HandoverProtocolDocumentPayload) -> bytes:
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
            document_type_label="Předávací protokol",
            document_status=payload.document_status,
            document_number=payload.document_number,
            styles=styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph("PŘEDÁVACÍ PROTOKOL", styles["title"]))
    story.append(Paragraph("Důkazní dokument předání vozidla zákazníkovi po servisním zásahu", styles["subtitle"]))
    story.append(Spacer(1, 6))

    story.append(
        _info_table(
            [
                ("Číslo protokolu", payload.document_number),
                ("Stav dokumentu", payload.status_label),
                ("Datum a čas předání", payload.handover_at_label),
                ("Zakázka", payload.work_order_number),
                ("Název zakázky", payload.work_order_title),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(_party_table(payload, styles))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Provedené práce — souhrn", styles["section"]))
    story.append(Paragraph(payload.work_summary.replace("\n", "<br/>"), styles["body"]))
    story.append(Spacer(1, 8))

    parts_table = _parts_table(payload.part_items, styles)
    if parts_table is not None:
        story.append(Paragraph("Vyměněné díly", styles["section"]))
        story.append(Spacer(1, 4))
        story.append(parts_table)
        story.append(Spacer(1, 8))

    story.append(Paragraph("Doporučení / další servis", styles["section"]))
    story.append(Paragraph(payload.recommendations.replace("\n", "<br/>"), styles["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Předané dokumenty", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_checklist_table("Dokumenty", payload.handed_over_documents, styles))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Klíče a příslušenství", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_checklist_table("Příslušenství", payload.handed_over_accessories, styles))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Fotodokumentace při předání", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_photo_grid(payload, styles))
    story.append(Spacer(1, 8))

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
            footer_text="Doklad vystaven v systému Správa vozidel · Document Platform C1.6",
            styles=styles,
        )
    )

    doc.build(story)
    return buffer.getvalue()
