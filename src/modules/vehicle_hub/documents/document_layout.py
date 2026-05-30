from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
LOGO_PATH = Path("/opt/toozhub2/app/web/assets/toozservis-logo-icon.png")
COLOR_DARK = colors.HexColor("#0f172a")
COLOR_MUTED = colors.HexColor("#64748b")
COLOR_BORDER = colors.HexColor("#dbe5f0")
COLOR_SURFACE = colors.HexColor("#f8fafc")
COLOR_SURFACE_ALT = colors.HexColor("#eef2ff")
COLOR_PRIMARY = colors.HexColor("#2563eb")
COLOR_SUCCESS = colors.HexColor("#059669")
COLOR_SUCCESS_SOFT = colors.HexColor("#ecfdf5")
COLOR_WARNING_SOFT = colors.HexColor("#fff7ed")
COLOR_WARNING = colors.HexColor("#f59e0b")

STATUS_COLORS = {
    "draft": (COLOR_WARNING_SOFT, COLOR_WARNING),
    "pending": (COLOR_WARNING_SOFT, COLOR_WARNING),
    "approved": (COLOR_SUCCESS_SOFT, COLOR_SUCCESS),
    "completed": (COLOR_SUCCESS_SOFT, COLOR_SUCCESS),
    "cancelled": (colors.HexColor("#fef2f2"), colors.HexColor("#dc2626")),
    "archived": (COLOR_SURFACE, COLOR_MUTED),
}


def register_document_fonts() -> None:
    registered = pdfmetrics.getRegisteredFontNames()
    if FONT_REGULAR in registered and FONT_BOLD in registered:
        return
    regular_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if not regular_path.exists() or not bold_path.exists():
        raise RuntimeError("DejaVuSans fonts required for document PDF platform.")
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular_path)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))


def build_document_styles() -> dict[str, ParagraphStyle]:
    register_document_fonts()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DocTitle",
            parent=base["Heading1"],
            fontName=FONT_BOLD,
            fontSize=18,
            textColor=COLOR_DARK,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName=FONT_REGULAR,
            fontSize=11,
            textColor=COLOR_MUTED,
        ),
        "section": ParagraphStyle(
            "DocSection",
            parent=base["Heading2"],
            fontName=FONT_BOLD,
            fontSize=12,
            textColor=COLOR_DARK,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "DocBody",
            parent=base["Normal"],
            fontName=FONT_REGULAR,
            fontSize=10.5,
            textColor=COLOR_DARK,
            leading=14,
        ),
        "muted": ParagraphStyle(
            "DocMuted",
            parent=base["Normal"],
            fontName=FONT_REGULAR,
            fontSize=9,
            textColor=COLOR_MUTED,
            leading=12,
        ),
        "badge": ParagraphStyle(
            "DocBadge",
            parent=base["Normal"],
            fontName=FONT_BOLD,
            fontSize=9,
            textColor=COLOR_DARK,
            alignment=TA_CENTER,
        ),
    }


def status_label(status: str) -> str:
    mapping = {
        "draft": "KONCEPT",
        "pending": "ČEKÁ",
        "approved": "SCHVÁLENO",
        "completed": "DOKONČENO",
        "cancelled": "ZRUŠENO",
        "archived": "ARCHIV",
    }
    return mapping.get(str(status or "").lower(), str(status or "—").upper())


def build_header_table(
    *,
    service_name: str,
    service_ico: str | None,
    document_type_label: str,
    document_status: str,
    document_number: str | None,
    styles: dict[str, ParagraphStyle],
) -> Table:
    badge_bg, badge_fg = STATUS_COLORS.get(document_status, (COLOR_SURFACE, COLOR_DARK))
    status_text = status_label(document_status)
    meta_lines = [
        f'<font color="{badge_fg.hexval()}"><b>{status_text}</b></font>',
    ]
    if document_number:
        meta_lines.append(document_number)
    service_lines = f"<b>{service_name}</b>"
    if service_ico:
        service_lines += f"<br/>IČO {service_ico}"

    left = Paragraph(
        f'{service_lines}<br/><font color="{COLOR_MUTED.hexval()}">{document_type_label}</font>',
        styles["body"],
    )
    right = Paragraph("<br/>".join(meta_lines), styles["badge"])
    table = Table([[left, right]], colWidths=[120 * mm, 58 * mm])
    table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (1, 0), (1, 0), badge_bg),
            ("BOX", (1, 0), (1, 0), 0.5, COLOR_BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return table


def build_vehicle_customer_table(
    *,
    vehicle_label: str,
    vehicle_plate: str | None,
    vehicle_vin_masked: str | None,
    customer_label: str | None,
    styles: dict[str, ParagraphStyle],
) -> Table:
    vehicle_lines = [f"<b>{vehicle_label}</b>"]
    if vehicle_plate:
        vehicle_lines.append(f"SPZ: {vehicle_plate}")
    if vehicle_vin_masked:
        vehicle_lines.append(f"VIN: {vehicle_vin_masked}")
    customer_lines = ["<b>Odběratel / zákazník</b>"]
    customer_lines.append(customer_label or "—")
    table = Table(
        [[Paragraph("<br/>".join(vehicle_lines), styles["body"]), Paragraph("<br/>".join(customer_lines), styles["body"])]],
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


def build_qr_block(
    *,
    verify_url: str | None,
    verification_code: str | None,
    styles: dict[str, ParagraphStyle],
) -> Table:
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    qr_text = verify_url or "https://hub.toozservis.cz/verify"
    qr = QrCodeWidget(qr_text)
    bounds = qr.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(28 * mm, 28 * mm, transform=[28 * mm / width, 0, 0, 28 * mm / height, 0, 0])
    drawing.add(qr)
    lines = ["<b>Ověření dokumentu</b>"]
    if verify_url:
        lines.append(verify_url)
    if verification_code:
        lines.append(f"Kód: {verification_code}")
    text = Paragraph("<br/>".join(lines), styles["muted"])
    table = Table([[drawing, text]], colWidths=[32 * mm, 146 * mm])
    table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_SURFACE),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    return table


def build_footer_paragraph(*, footer_text: str, styles: dict[str, ParagraphStyle]) -> Paragraph:
    return Paragraph(footer_text, ParagraphStyle(
        "DocFooter",
        parent=styles["muted"],
        alignment=TA_CENTER,
    ))
