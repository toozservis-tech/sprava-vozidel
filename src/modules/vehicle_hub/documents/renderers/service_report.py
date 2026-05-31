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
from ..service_report_models import (
    ServiceReportDocumentPayload,
    ServiceReportPartPayload,
    ServiceReportWorkItemPayload,
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


def _party_table(payload: ServiceReportDocumentPayload, styles: dict) -> Table:
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

    vehicle_lines = ["<b>Vozidlo</b>", payload.vehicle_label or "Neuvedeno"]
    if payload.vehicle_plate:
        vehicle_lines.append(f"SPZ: {payload.vehicle_plate}")
    if payload.vehicle_vin:
        vehicle_lines.append(f"VIN: {payload.vehicle_vin}")
    if payload.vehicle_odometer_km is not None:
        vehicle_lines.append(f"Stav km: {int(payload.vehicle_odometer_km):,}".replace(",", " "))

    table = Table(
        [[
            Paragraph("<br/>".join(service_lines), styles["body"]),
            Paragraph("<br/>".join(vehicle_lines), styles["body"]),
        ]],
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


def _items_table(title: str, items: list[ServiceReportWorkItemPayload | ServiceReportPartPayload], styles: dict) -> Table | None:
    if not items:
        return None
    header = ["Položka", "Množství", "MJ", "Poznámka"]
    data = [header]
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


def _photo_grid(payload: ServiceReportDocumentPayload, styles: dict) -> Table:
    photos = payload.photos or []
    if not photos:
        rows = [[
            [Paragraph("Fotodokumentace po opravě — neuvedena", styles["muted"])],
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


def _signature_table(payload: ServiceReportDocumentPayload, styles: dict) -> Table:
    table = Table(
        [[
            Paragraph(
                "<b>Podpis servisu</b><br/><br/><br/>_________________________<br/>"
                + payload.service_signature_label,
                styles["body"],
            ),
            Paragraph(
                "<b>Ověření dokumentu</b><br/><br/>Technický report historie vozidla.<br/>"
                "Dokument neobsahuje obchodní ani fakturační údaje.",
                styles["muted"],
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


def render_service_report_pdf(payload: ServiceReportDocumentPayload) -> bytes:
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
            document_type_label="Servisní zpráva",
            document_status=payload.document_status,
            document_number=payload.document_number,
            styles=styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph("SERVISNÍ ZPRÁVA", styles["title"]))
    story.append(Paragraph("Technický report provedených prací a stavu vozidla po servisu", styles["subtitle"]))
    story.append(Spacer(1, 6))

    story.append(
        _info_table(
            [
                ("Číslo zprávy", payload.document_number),
                ("Stav dokumentu", payload.status_label),
                ("Datum provedení", payload.performed_at_label),
                ("Zakázka", payload.work_order_number),
                ("Název zásahu", payload.intervention_title),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(_party_table(payload, styles))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Popis závady / požadavek", styles["section"]))
    story.append(Paragraph(payload.defect_description, styles["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Provedené práce", styles["section"]))
    story.append(Paragraph(payload.performed_work_summary.replace("\n", "<br/>"), styles["body"]))
    story.append(Spacer(1, 6))

    labor_table = _items_table("Detail úkonů", payload.labor_items, styles)
    if labor_table is not None:
        story.append(labor_table)
        story.append(Spacer(1, 8))

    parts_table = _items_table("Vyměněné díly", payload.part_items, styles)
    if parts_table is not None:
        story.append(Paragraph("Vyměněné díly", styles["section"]))
        story.append(Spacer(1, 4))
        story.append(parts_table)
        story.append(Spacer(1, 8))
    elif payload.part_items:
        story.append(Paragraph("Vyměněné díly — neuvedeno", styles["muted"]))
        story.append(Spacer(1, 8))

    if payload.total_work_minutes is not None or payload.time_items:
        story.append(Paragraph("Čas práce", styles["section"]))
        if payload.total_work_minutes is not None:
            story.append(Paragraph(f"Celkový evidovaný čas: {payload.total_work_minutes} min", styles["body"]))
        for row in payload.time_items:
            detail = f" — {row.note}" if row.note else ""
            story.append(Paragraph(f"• {row.label}: {row.duration_label}{detail}", styles["body"]))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Doporučení", styles["section"]))
    story.append(Paragraph(payload.recommendations.replace("\n", "<br/>"), styles["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Fotodokumentace po opravě", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(_photo_grid(payload, styles))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Závěr technika", styles["section"]))
    story.append(Paragraph(payload.technician_conclusion.replace("\n", "<br/>"), styles["body"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Podpis servisu", styles["section"]))
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
            footer_text="Doklad vystaven v systému Správa vozidel · Document Platform C1.5",
            styles=styles,
        )
    )

    doc.build(story)
    return buffer.getvalue()
