from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
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
    build_footer_paragraph,
    build_header_table,
    build_qr_block,
    status_label,
)
from ..work_order_sheet_models import WorkOrderSheetDocumentPayload, WorkOrderSheetItemPayload


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


def _party_table(payload: WorkOrderSheetDocumentPayload, styles: dict) -> Table:
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
    if payload.billing_contact_name:
        customer_lines.append(f"Fakturační kontakt: {payload.billing_contact_name}")
        if payload.billing_contact_phone:
            customer_lines.append(payload.billing_contact_phone)
        if payload.billing_contact_email:
            customer_lines.append(payload.billing_contact_email)

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


def _items_table(title: str, items: list[WorkOrderSheetItemPayload], styles: dict) -> Table | None:
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


def _signature_table(payload: WorkOrderSheetDocumentPayload, styles: dict) -> Table:
    customer_sig = payload.customer_signature_label
    service_sig = payload.service_signature_label
    table = Table(
        [
            [
                Paragraph("<b>Podpis zákazníka</b><br/><br/><br/>_________________________<br/>" + customer_sig, styles["body"]),
                Paragraph("<b>Podpis servisu</b><br/><br/><br/>_________________________<br/>" + service_sig, styles["body"]),
            ],
        ],
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


def render_work_order_sheet_pdf(payload: WorkOrderSheetDocumentPayload) -> bytes:
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
            document_type_label="Zakázkový list",
            document_status=payload.document_status,
            document_number=payload.document_number,
            styles=styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph("ZAKÁZKOVÝ LIST", styles["title"]))
    story.append(Paragraph("Technicko-provozní servisní formulář vozidla", styles["subtitle"]))
    story.append(Spacer(1, 6))

    story.append(
        _info_table(
            [
                ("Číslo zakázky", payload.work_order_number),
                ("Stav zakázky", payload.work_order_status_label),
                ("Název / titulek", payload.work_order_title),
                ("Datum příjmu", payload.received_at_label),
                ("Datum dokončení", payload.completed_at_label),
                ("Technik", payload.technician_name),
                ("Vytvořeno", payload.created_at_label),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(_party_table(payload, styles))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Příjem vozidla", styles["section"]))
    story.append(Spacer(1, 4))
    story.append(
        _info_table(
            [
                ("Datum příjmu", payload.intake_received_at_label),
                ("Popis závady / stav při příjmu", payload.defect_description),
                ("Požadavek zákazníka", payload.customer_request),
                ("Technická poznámka", payload.technical_note),
                ("Poznámka k příjmu", payload.intake_note),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8))

    if payload.work_order_description and payload.work_order_description != "Neuvedeno":
        story.append(Paragraph("Popis zakázky", styles["section"]))
        story.append(Paragraph(payload.work_order_description, styles["body"]))
        story.append(Spacer(1, 8))

    for section_title, items in (
        ("Práce", payload.labor_items),
        ("Díly", payload.part_items),
        ("Čas práce", payload.time_items),
    ):
        table = _items_table(section_title, items, styles)
        if table is not None:
            story.append(Paragraph(section_title, styles["section"]))
            story.append(Spacer(1, 4))
            story.append(table)
            story.append(Spacer(1, 8))

    if payload.intake_photo_count > 0:
        story.append(Paragraph("Fotodokumentace příjmu", styles["section"]))
        photo_lines = [f"Počet snímků: {payload.intake_photo_count}"]
        for photo in payload.intake_photos[:6]:
            photo_lines.append(f"• {photo.label} ({photo.photo_type})")
        if payload.intake_photo_count > len(payload.intake_photos):
            photo_lines.append("• Další snímky jsou uloženy v servisním systému.")
        story.append(Paragraph("<br/>".join(photo_lines), styles["body"]))
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
            footer_text="Doklad vystaven v systému Správa vozidel · Document Platform C1.3",
            styles=styles,
        )
    )

    doc.build(story)
    return buffer.getvalue()
