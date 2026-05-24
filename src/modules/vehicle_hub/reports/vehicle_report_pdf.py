from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.core.config import DATA_DIR

from .vehicle_report_models import (
    VehicleReportMileagePoint,
    VehicleReportOwner,
    VehicleReportServiceRecord,
    VehicleServiceReportPayload,
)

FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
LOGO_PATH = Path("/opt/toozhub2/app/web/assets/toozservis-logo-icon.png")
COLOR_DARK = colors.HexColor("#0f172a")
COLOR_DARK_2 = colors.HexColor("#111827")
COLOR_SURFACE = colors.HexColor("#f8fafc")
COLOR_SURFACE_ALT = colors.HexColor("#eef2ff")
COLOR_BORDER = colors.HexColor("#dbe5f0")
COLOR_TEXT = colors.HexColor("#0f172a")
COLOR_MUTED = colors.HexColor("#64748b")
COLOR_BLUE = colors.HexColor("#2563eb")
COLOR_BLUE_SOFT = colors.HexColor("#dbeafe")
COLOR_PINK = colors.HexColor("#db2777")
COLOR_PINK_SOFT = colors.HexColor("#fce7f3")
COLOR_ORANGE_SOFT = colors.HexColor("#fff7ed")
COLOR_ORANGE_BORDER = colors.HexColor("#fdba74")
COLOR_ORANGE = colors.HexColor("#f59e0b")
COLOR_GREEN = colors.HexColor("#059669")
COLOR_GREEN_SOFT = colors.HexColor("#ecfdf5")
COLOR_RED = colors.HexColor("#dc2626")
COLOR_RED_SOFT = colors.HexColor("#fef2f2")
COLOR_LIGHT_GRAY = colors.HexColor("#f3f4f6")
COLOR_LINE = colors.HexColor("#e5e7eb")
VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"


def _register_fonts() -> None:
    registered = pdfmetrics.getRegisteredFontNames()
    if FONT_REGULAR in registered and FONT_BOLD in registered:
        return

    regular_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    bold_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if not regular_path.exists() or not bold_path.exists():
        raise RuntimeError("Na serveru chybí font DejaVuSans potřebný pro korektní českou diakritiku v PDF.")

    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular_path)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))


class _NumberedCanvasMixin:
    def __init__(self, *args, footer_text: str = "", version_text: str = "", **kwargs):
        from reportlab.pdfgen.canvas import Canvas

        self._states = []
        self._footer_text = footer_text
        self._version_text = version_text
        Canvas.__init__(self, *args, **kwargs)

    def showPage(self):
        self._states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._states)
        for state in self._states:
            self.__dict__.update(state)
            self._draw_footer(page_count)
            from reportlab.pdfgen.canvas import Canvas

            Canvas.showPage(self)
        from reportlab.pdfgen.canvas import Canvas

        Canvas.save(self)

    def _draw_footer(self, page_count: int):
        self.saveState()
        self.setFont(FONT_REGULAR, 8.2)
        self.setFillColor(colors.HexColor("#64748b"))
        self.drawString(16 * mm, 12 * mm, self._footer_text[:120])
        self.drawRightString(194 * mm, 12 * mm, f"Strana {self._pageNumber}/{page_count}")
        if self._version_text:
            self.drawString(16 * mm, 8 * mm, self._version_text[:120])
        self.restoreState()


def _canvas_factory(*, footer_text: str, version_text: str):
    from reportlab.pdfgen.canvas import Canvas

    class NumberedCanvas(_NumberedCanvasMixin, Canvas):
        def __init__(self, *args, **kwargs):
            kwargs["footer_text"] = footer_text
            kwargs["version_text"] = version_text
            super().__init__(*args, **kwargs)

    return NumberedCanvas


def _fmt_date(raw_value: Optional[str]) -> str:
    if not raw_value:
        return "Neuvedeno"
    text = str(raw_value)
    if "T" in text:
        date_part = text.split("T", 1)[0]
        parts = date_part.split("-")
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
    parts = text.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    return text


def _fmt_datetime(raw_value: Optional[str]) -> str:
    if not raw_value:
        return "Neuvedeno"
    text = str(raw_value).replace("Z", "")
    if "T" not in text:
        return _fmt_date(text)
    date_part, time_part = text.split("T", 1)
    time_part = time_part[:5]
    parts = date_part.split("-")
    if len(parts) == 3:
        return f"{parts[2]}.{parts[1]}.{parts[0]} {time_part}"
    return text


def _fmt_km(value: Optional[int]) -> str:
    if value is None:
        return "Neuvedeno"
    return f"{int(value):,}".replace(",", " ") + " km"


def _fmt_number(value: Optional[int]) -> str:
    if value is None:
        return "Neuvedeno"
    return f"{int(value):,}".replace(",", " ")


def _fmt_money_totals(totals: dict) -> str:
    if not totals:
        return "Neuvedeno"
    currency = str(totals.get("currency") or "CZK")
    total = totals.get("total_with_vat")
    if total is not None:
        try:
            return f"{float(total):,.2f} {currency}".replace(",", " ")
        except (TypeError, ValueError):
            return f"{total} {currency}"
    labor = totals.get("labor_total")
    materials = totals.get("materials_total")
    parts = []
    if labor is not None:
        parts.append(f"práce {labor} {currency}")
    if materials is not None:
        parts.append(f"materiál {materials} {currency}")
    return ", ".join(parts) if parts else "Neuvedeno"


def _paragraph(text: Optional[str], style: ParagraphStyle) -> Paragraph:
    safe = escape(str(text or "Neuvedeno")).replace("\n", "<br/>")
    return Paragraph(safe, style)


def _bullet_list(lines: Iterable[str], style: ParagraphStyle) -> Paragraph:
    safe_lines = [escape(str(line)) for line in lines if str(line or "").strip()]
    if not safe_lines:
        return Paragraph("Neuvedeno", style)
    html = "<br/>".join(f"• {line}" for line in safe_lines)
    return Paragraph(html, style)


def _kv_table(items: list[tuple[str, str]], *, styles: dict[str, ParagraphStyle], col_widths: Optional[list[float]] = None) -> Table:
    data = [
        [
            Paragraph(escape(label), styles["meta_label"]),
            Paragraph(escape(value), styles["meta_value"]),
        ]
        for label, value in items
    ]
    table = Table(data, colWidths=col_widths or [34 * mm, 56 * mm])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _build_qr(payload: VehicleServiceReportPayload) -> Drawing:
    qr_widget = QrCodeWidget(payload.document.verification_url or payload.verification_qr_payload or payload.document.verification_code)
    bounds = qr_widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    drawing = Drawing(14 * mm, 14 * mm, transform=[(14 * mm) / width, 0, 0, (14 * mm) / height, 0, 0])
    drawing.add(qr_widget)
    return drawing


def _build_qr_drawing_scaled(text: str, *, size_mm: float = 28) -> Drawing:
    raw = str(text or "").strip()
    if not raw:
        raw = " "
    qr_widget = QrCodeWidget(raw)
    bounds = qr_widget.getBounds()
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    s = float(size_mm)
    drawing = Drawing(s * mm, s * mm, transform=[(s * mm) / w, 0, 0, (s * mm) / h, 0, 0])
    drawing.add(qr_widget)
    return drawing


def _card(flowable, *, width: float, background=colors.white, border=COLOR_BORDER, padding: int = 10) -> Table:
    table = Table([[flowable]], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.8, border),
                ("LEFTPADDING", (0, 0), (-1, -1), padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), padding),
                ("TOPPADDING", (0, 0), (-1, -1), padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_verification_panel(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    items: list = [
        _paragraph("Ověření dokumentu", styles["verify_title"]),
        Spacer(1, 0.35 * mm),
        _paragraph(payload.document.verification_code or "Neuvedeno", styles["verify_code"]),
    ]
    if payload.document.verification_enabled and payload.document.verification_url:
        items.extend(
            [
                _paragraph("Naskenujte pro ověření pravosti", styles["verify_hint"]),
                Spacer(1, 0.55 * mm),
                _build_qr(payload),
                _paragraph("hub.toozservis.cz/verify", styles["verify_link"]),
            ]
        )
    else:
        items.append(_paragraph("Tato verze dokumentu nepodporuje veřejné QR ověření.", styles["verify_hint"]))
    return _card(
        _stack(21 * mm, *items),
        width=24 * mm,
        background=COLOR_SURFACE,
        border=COLOR_BORDER,
        padding=4,
    )


def _build_new_owner_handover_banner(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table | None:
    url = str(payload.new_owner_claim_qr_payload or "").strip()
    if not url:
        return None
    inner = _stack(
        176 * mm,
        _paragraph("Předání vozidla novému vlastníkovi", styles["section_kicker"]),
        _paragraph("QR pro připojení vozidla k účtu", styles["section_title_small"]),
        Spacer(1, 0.8 * mm),
        _paragraph(
            "Nový majitel naskenuje kód v aplikaci nebo otevře odkaz, ověří SPZ a VIN a přidá si vozidlo k účtu. Servisní historie zůstane zachovaná.",
            styles["body_small"],
        ),
        Spacer(1, 2 * mm),
        _build_qr_drawing_scaled(url, size_mm=32),
        Spacer(1, 1.2 * mm),
        _paragraph("Odkaz lze také přeposlat e‑mailem nebo SMS.", styles["verify_hint"]),
    )
    return _card(
        inner,
        width=180 * mm,
        background=COLOR_GREEN_SOFT,
        border=COLOR_GREEN,
        padding=18,
    )


def _stack(width: float, *items) -> Table:
    table = Table([[item] for item in items], colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _resolve_vehicle_photo_image(payload: VehicleServiceReportPayload) -> RLImage | None:
    raw_path = str(payload.vehicle.primary_photo_path or "").strip()
    if not raw_path:
        return None
    try:
        base = VEHICLE_PHOTOS_DIR.resolve()
        candidate = (VEHICLE_PHOTOS_DIR / raw_path).resolve()
        if not str(candidate).startswith(str(base)) or not candidate.is_file():
            return None
        with PILImage.open(candidate) as image:
            normalized = image.convert("RGB")
            target_width_px = 980
            target_height_px = 648
            outer_padding = 20
            inner_width = max(1, target_width_px - (outer_padding * 2))
            inner_height = max(1, target_height_px - (outer_padding * 2))

            working = normalized.copy()
            working.thumbnail((inner_width, inner_height), PILImage.Resampling.LANCZOS)

            canvas = PILImage.new("RGB", (target_width_px, target_height_px), "#ffffff")
            offset_x = (target_width_px - working.width) // 2
            offset_y = (target_height_px - working.height) // 2
            canvas.paste(working, (offset_x, offset_y))
            buffer = BytesIO()
            canvas.save(buffer, format="JPEG", quality=90, optimize=True)
        buffer.seek(0)
        return RLImage(buffer, width=56 * mm, height=37 * mm)
    except Exception:
        return None


def _resolve_export_mode_label(payload: VehicleServiceReportPayload) -> str:
    mode = str(payload.document.export_mode or "").strip().lower()
    mapping = {
        "public": "Veřejný sdílený výpis",
        "owner": "Výpis vlastníka",
        "workshop": "Servisní výpis",
        "internal_audit": "Interní auditní výpis",
    }
    return mapping.get(mode, mode or "Digitální výpis")


def _count_verified_records(payload: VehicleServiceReportPayload) -> int:
    return sum(
        1
        for record in payload.service_records
        if "ověř" in str(record.verification_status or "").lower()
    )


def _count_manual_records(payload: VehicleServiceReportPayload) -> int:
    return sum(
        1
        for record in payload.service_records
        if str(record.verification_status or "").strip().lower() == "ruční záznam"
    )


def _count_records_with_attachments(payload: VehicleServiceReportPayload) -> int:
    return sum(1 for record in payload.service_records if int(record.attachments_count or 0) > 0)


def _count_stk_import_records(payload: VehicleServiceReportPayload) -> int:
    return sum(1 for record in payload.service_records if str(record.source_type or "").strip().lower() == "stk_history")


def _metric_badge(label: str, value: str, note: str, styles: dict[str, ParagraphStyle]) -> Table:
    return _card(
        _stack(
            39 * mm,
            _paragraph(label, styles["metric_label"]),
            Spacer(1, 0.8 * mm),
            _paragraph(value, styles["metric_value"]),
            Spacer(1, 0.6 * mm),
            _paragraph(note, styles["metric_note"]),
        ),
        width=42 * mm,
        background=colors.white,
        border=COLOR_BORDER,
        padding=8,
    )


def _hero_chip(label: str, value: str, *, width: float, styles: dict[str, ParagraphStyle]) -> Table:
    return _card(
        _stack(
            width - (8 * mm),
            _paragraph(label, styles["hero_chip_label"]),
            Spacer(1, 0.4 * mm),
            _paragraph(value, styles["hero_chip_value"]),
        ),
        width=width,
        background=COLOR_SURFACE_ALT,
        border=COLOR_BORDER,
        padding=6,
    )


def _owner_field(label: str, value: str, *, width: float, styles: dict[str, ParagraphStyle]) -> Table:
    return _stack(
        width,
        _paragraph(label, styles["owner_label"]),
        Spacer(1, 0.35 * mm),
        _paragraph(value, styles["owner_value"]),
    )


def _history_stat_block(label: str, value: str, *, width: float, styles: dict[str, ParagraphStyle]):
    return _stack(
        width,
        _paragraph(label, styles["history_metric_label"]),
        Spacer(1, 0.45 * mm),
        _paragraph(value, styles["history_metric_value"]),
    )


def _load_chart_font(size: int, *, bold: bool = False):
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        return ImageFont.truetype(font_path, size=size)
    except Exception:
        return ImageFont.load_default()


def _point_color(point: VehicleReportMileagePoint) -> tuple[int, int, int]:
    if point.source_type == "stk_history":
        return (124, 58, 237)
    if point.source_type == "service_record":
        return (37, 99, 235)
    return (71, 85, 105)


def _anomaly_color(point: VehicleReportMileagePoint) -> tuple[int, int, int] | None:
    if "rollback" in point.anomaly_flags or "suspicious_jump" in point.anomaly_flags:
        return (220, 38, 38)
    if "duplicate" in point.anomaly_flags:
        return (217, 119, 6)
    return None


def _draw_centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, *, font, fill) -> None:
    left, top, right, bottom = box
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=4, align="center")
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = left + ((right - left - width) / 2)
    y = top + ((bottom - top - height) / 2)
    draw.multiline_text((x, y), text, font=font, fill=fill, spacing=4, align="center")


def _generate_mileage_chart_png(payload: VehicleServiceReportPayload) -> bytes | None:
    timeline = payload.mileage_timeline
    points = timeline.points
    if not points:
        return None

    width, height = 1160, 500
    image = PILImage.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)

    font_small = _load_chart_font(14)
    font_regular = _load_chart_font(17)
    font_bold = _load_chart_font(19, bold=True)

    margin_left = 108
    margin_right = 40
    margin_top = 40
    margin_bottom = 104
    plot_left = margin_left
    plot_top = margin_top
    plot_right = width - margin_right
    plot_bottom = height - margin_bottom
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    draw.rounded_rectangle((plot_left, plot_top, plot_right, plot_bottom), radius=18, outline="#dbe5f0", width=2, fill="#fbfdff")

    if len(points) == 1:
        single_point = points[0]
        draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill="#cbd5e1", width=2)
        draw.line((plot_left, plot_top, plot_left, plot_bottom), fill="#cbd5e1", width=2)
        center_x = plot_left + (plot_width // 2)
        center_y = plot_top + (plot_height // 2)
        draw.line((center_x, plot_bottom, center_x, center_y), fill="#bfdbfe", width=3)
        fill = _point_color(single_point)
        anomaly = _anomaly_color(single_point)
        if anomaly:
            draw.ellipse((center_x - 11, center_y - 11, center_x + 11, center_y + 11), outline=anomaly, width=4)
        draw.ellipse((center_x - 7, center_y - 7, center_x + 7, center_y + 7), fill=fill, outline="#ffffff", width=2)
        draw.text((plot_left, plot_bottom + 12), _fmt_date(single_point.date), font=font_small, fill="#475569")
        draw.text((plot_left, plot_top + 8), _fmt_km(single_point.mileage_km), font=font_regular, fill="#0f172a")
    else:
        raw_datetimes = [datetime.fromisoformat(point.date.replace("Z", "+00:00")) for point in points]
        base_dates = []
        for item in raw_datetimes:
            if item.tzinfo is not None:
                item = item.astimezone().replace(tzinfo=None)
            base_dates.append(item)
        min_dt = min(base_dates)
        max_dt = max(base_dates)
        if min_dt == max_dt:
            max_dt = min_dt + timedelta(hours=1)
        min_km = min(point.mileage_km for point in points)
        max_km = max(point.mileage_km for point in points)
        if min_km == max_km:
            min_km = max(0, min_km - 1000)
            max_km = max_km + 1000
        else:
            padding = max(int((max_km - min_km) * 0.08), 1500)
            min_km = max(0, min_km - padding)
            max_km = max_km + padding

        def x_for(dt_value: datetime) -> int:
            ratio = (dt_value - min_dt).total_seconds() / max((max_dt - min_dt).total_seconds(), 1)
            return int(plot_left + (ratio * plot_width))

        def y_for(km_value: int) -> int:
            ratio = (km_value - min_km) / max(max_km - min_km, 1)
            return int(plot_bottom - (ratio * plot_height))

        for tick_idx in range(5):
            tick_ratio = tick_idx / 4
            y = int(plot_bottom - (tick_ratio * plot_height))
            value = int(min_km + ((max_km - min_km) * tick_ratio))
            draw.line((plot_left, y, plot_right, y), fill="#e5e7eb", width=1)
            draw.text((18, y - 9), _fmt_km(value), font=font_small, fill="#64748b")

        for tick_idx in range(4):
            tick_ratio = tick_idx / 3
            dt_value = min_dt + ((max_dt - min_dt) * tick_ratio)
            x = int(plot_left + (tick_ratio * plot_width))
            draw.line((x, plot_top, x, plot_bottom), fill="#eef2f7", width=1)
            label = _fmt_date(dt_value.isoformat())
            bbox = draw.textbbox((0, 0), label, font=font_small)
            draw.text((x - ((bbox[2] - bbox[0]) / 2), plot_bottom + 12), label, font=font_small, fill="#64748b")

        draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill="#cbd5e1", width=2)
        draw.line((plot_left, plot_top, plot_left, plot_bottom), fill="#cbd5e1", width=2)

        line_points = [(x_for(dt_value), y_for(point.mileage_km)) for dt_value, point in zip(base_dates, points)]
        draw.line(line_points, fill="#1d4ed8", width=3)

        for (x, y), point in zip(line_points, points):
            fill = _point_color(point)
            anomaly = _anomaly_color(point)
            if anomaly:
                draw.ellipse((x - 11, y - 11, x + 11, y + 11), outline=anomaly, width=4)
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=fill, outline="#ffffff", width=2)

    draw.text((plot_left + (plot_width // 2) - 28, height - 42), "Datum", font=font_regular, fill="#334155")
    draw.text((18, 12), "Stav km", font=font_bold, fill="#334155")

    legend_y = height - 72
    legend_items = [
        ("Servisni zaznam", (37, 99, 235)),
        ("STK / tachometr", (124, 58, 237)),
        ("Anomalie", (220, 38, 38)),
    ]
    legend_x = plot_left
    for label, color in legend_items:
        draw.ellipse((legend_x, legend_y, legend_x + 16, legend_y + 16), fill=color, outline="#ffffff", width=1)
        draw.text((legend_x + 24, legend_y - 2), label, font=font_small, fill="#475569")
        legend_x += 190

    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _build_mileage_timeline_cards(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    timeline = payload.mileage_timeline
    badges = [
        _metric_badge("Prvni znamy stav", _fmt_km(timeline.first_known_mileage_km), _fmt_date(timeline.first_known_date), styles),
        _metric_badge("Posledni znamy stav", _fmt_km(timeline.last_known_mileage_km), _fmt_date(timeline.last_known_date), styles),
        _metric_badge("Pouzite body", str(len(timeline.points)), "casova osa", styles),
        _metric_badge("Anomalie", str(timeline.anomalies_count), "oznacene konflikty", styles),
    ]
    table = Table([badges], colWidths=[43.5 * mm, 43.5 * mm, 43.5 * mm, 43.5 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_mileage_timeline_anomaly_lines(payload: VehicleServiceReportPayload) -> list[str]:
    lines: list[str] = []
    for point in payload.mileage_timeline.points:
        if not point.anomaly_flags:
            continue
        flags = ", ".join(point.anomaly_flags)
        lines.append(
            f"{_fmt_date(point.date)} | {_fmt_km(point.mileage_km)} | {point.source_label} | {flags}"
        )
        if len(lines) >= 6:
            break
    return lines


def _build_mileage_timeline_section(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> list:
    timeline = payload.mileage_timeline
    story: list = [
        CondPageBreak(92 * mm),
        _paragraph("Kilometrova evidence", styles["section_kicker"]),
        _paragraph("Vyvoj stavu km", styles["section_title"]),
        _paragraph("Casova osa z evidovanych servisnich, rucnich a STK zaznamu", styles["body"]),
        Spacer(1, 1.6 * mm),
    ]

    if not timeline.points:
        story.append(
            _card(
                _paragraph(
                    "Pro graf vyvoje km zatim neni dostatek pouzitelnych bodu s datem a kilometrovym stavem.",
                    styles["empty_state"],
                ),
                width=180 * mm,
                background=COLOR_SURFACE,
                border=COLOR_BORDER,
                padding=16,
            )
        )
        story.append(Spacer(1, 2.6 * mm))
        return story

    story.append(_build_mileage_timeline_cards(payload, styles))
    story.append(Spacer(1, 1.8 * mm))

    chart_png = _generate_mileage_chart_png(payload)
    if chart_png:
        chart = RLImage(BytesIO(chart_png), width=180 * mm, height=77 * mm)
        story.append(_card(chart, width=180 * mm, background=colors.white, border=COLOR_BORDER, padding=6))
        story.append(Spacer(1, 1.6 * mm))

    anomaly_lines = _build_mileage_timeline_anomaly_lines(payload)
    if anomaly_lines:
        story.extend(
            [
                _card(
                    _stack(
                        176 * mm,
                        _paragraph("Označené anomálie", styles["section_kicker"]),
                        _bullet_list(anomaly_lines, styles["body_small"]),
                    ),
                    width=180 * mm,
                    background=COLOR_RED_SOFT,
                    border=COLOR_BORDER,
                    padding=10,
                ),
                Spacer(1, 1.2 * mm),
            ]
        )

    story.append(
        _card(
            _stack(
                176 * mm,
                _paragraph("Graf vychazi z dostupnych evidovanych hodnot km.", styles["body"]),
                _paragraph("Podezrele odchylky jsou v reportu oznaceny.", styles["body"]),
            ),
            width=180 * mm,
            background=COLOR_SURFACE_ALT,
            border=COLOR_BORDER,
            padding=10,
        )
    )
    story.append(Spacer(1, 2.4 * mm))
    return story


def _bucketize_records(payload: VehicleServiceReportPayload) -> list[tuple[str, int]]:
    counts = {
        "Havárie": 0,
        "Poruchy": 0,
        "Servis a údržba": 0,
        "Jiné": 0,
    }
    for record in payload.service_records:
        category = str(record.category or "").lower()
        title = str(record.title or "").lower()
        haystack = f"{category} {title}"
        if "hav" in haystack or "nehod" in haystack or "karoser" in haystack:
            counts["Havárie"] += 1
        elif any(token in haystack for token in ["poruch", "oprav", "brzd", "elektr", "výf", "vyf", "chladi"]):
            counts["Poruchy"] += 1
        elif any(token in haystack for token in ["servis", "údrž", "udrž", "olej", "filtr", "stk", "diagnost", "pneu", "klimat"]):
            counts["Servis a údržba"] += 1
        else:
            counts["Jiné"] += 1
    return list(counts.items())


def _group_records_by_year(records: list[VehicleReportServiceRecord]) -> list[tuple[str, list[VehicleReportServiceRecord]]]:
    grouped: dict[str, list[VehicleReportServiceRecord]] = defaultdict(list)
    for record in records:
        raw_date = str(record.date or "")
        year = "Neuvedeno"
        if len(raw_date) >= 4 and raw_date[:4].isdigit():
            year = raw_date[:4]
        grouped[year].append(record)
    sorted_years = sorted(grouped.keys(), reverse=True)
    return [(year, grouped[year]) for year in sorted_years]


def _build_header(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    logo = None
    if LOGO_PATH.exists():
        logo = RLImage(str(LOGO_PATH), width=12 * mm, height=12 * mm)
    left = _stack(
        39 * mm,
        Table(
            [[logo or Paragraph("Správa vozidel", styles["brand"]), Paragraph("SPRÁVA VOZIDEL", styles["brand_caps"])]],
            colWidths=[12 * mm, 27 * mm],
        ),
        _paragraph(
            "Digitální servisní kniha",
            styles["brand_meta"],
        ),
    )
    center = _stack(
        112 * mm,
        _paragraph("Digitální servisní výpis vozidla", styles["doc_title_center"]),
        _paragraph("Historie servisních úkonů", styles["doc_subtitle_center"]),
        Spacer(1, 0.55 * mm),
        _paragraph(
            f"Generováno {_fmt_datetime(payload.document.generated_at)} | ID {payload.document.document_id}",
            styles["doc_meta_center"],
        ),
        _paragraph(
            f"Vystavil {payload.document.issued_by or 'Správa vozidel'}",
            styles["doc_meta_center"],
        ),
    )
    right = _build_verification_panel(payload, styles)
    table = Table([[left, center, right]], colWidths=[41 * mm, 117 * mm, 22 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LINEBELOW", (0, 0), (-1, -1), 1, COLOR_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ]
        )
    )
    return table


def _build_hero(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    vehicle = payload.vehicle
    photo = _resolve_vehicle_photo_image(payload)
    display_name = f"{vehicle.brand or ''} {vehicle.model or ''}".strip() or vehicle.nickname or "Vozidlo"
    identity_label = vehicle.nickname or display_name
    left_brand = _card(
        _stack(
            48 * mm,
            _paragraph("Hlavní náhled", styles["section_kicker"]),
            Spacer(1, 1.1 * mm),
            *([photo] if photo else [_paragraph("Bez hlavní fotky", styles["empty_state"])]),
            Spacer(1, 2.1 * mm),
            _paragraph(display_name, styles["brand_showcase"]),
            Spacer(1, 0.8 * mm),
            _paragraph(vehicle.vin or "Neuvedeno", styles["brand_vin"]),
        ),
        width=56 * mm,
        background=colors.white,
        border=COLOR_LINE,
        padding=8,
    )
    identity_block = _stack(
        120 * mm,
        _paragraph("Referenční identita vozidla", styles["section_kicker"]),
        _paragraph(display_name, styles["hero_name"]),
        _paragraph(
            identity_label if identity_label != display_name else "Digitální servisní výpis referenčního klienta",
            styles["hero_subtitle"],
        ),
    )
    hero_chips = Table(
        [[
            _hero_chip("RZ", vehicle.spz or "Neuvedeno", width=26 * mm, styles=styles),
            _hero_chip("Stav km", _fmt_km(vehicle.odometer_km), width=48 * mm, styles=styles),
            _hero_chip("STK do", _fmt_date(vehicle.stk_valid_to), width=42 * mm, styles=styles),
        ]],
        colWidths=[28 * mm, 50 * mm, 44 * mm],
    )
    hero_chips.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    info_left = _kv_table(
        [
            ("Název", display_name),
            *((("Interní označení", identity_label),) if identity_label != display_name else ()),
            ("RZ", vehicle.spz or "Neuvedeno"),
            ("VIN", vehicle.vin or "Neuvedeno"),
            ("Typ vozidla", "Osobní automobil" if (vehicle.brand or vehicle.model) else "Neuvedeno"),
            ("1. registrace", "Neuvedeno"),
        ],
        styles=styles,
        col_widths=[22 * mm, 40 * mm],
    )
    info_right = _kv_table(
        [
            ("Režim", _resolve_export_mode_label(payload)),
            ("Druh pohonu", vehicle.fuel_type or "Neuvedeno"),
            ("Výkon motoru", f"{vehicle.power_kw} kW" if vehicle.power_kw else "Neuvedeno"),
            ("Objem motoru", f"{_fmt_number(vehicle.engine_ccm)} ccm" if vehicle.engine_ccm else "Neuvedeno"),
            ("Převodovka", vehicle.transmission or "Neuvedeno"),
            ("Stav km", _fmt_km(vehicle.odometer_km)),
            ("STK do", _fmt_date(vehicle.stk_valid_to)),
        ],
        styles=styles,
        col_widths=[24 * mm, 30 * mm],
    )
    info_grid = Table([[info_left, info_right]], colWidths=[60 * mm, 60 * mm])
    info_grid.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    right_panel = _card(
        _stack(
            118 * mm,
            identity_block,
            Spacer(1, 2 * mm),
            hero_chips,
            Spacer(1, 2.2 * mm),
            info_grid,
        ),
        width=122 * mm,
        background=colors.white,
        border=COLOR_LINE,
        padding=8,
    )
    table = Table([[left_brand, right_panel]], colWidths=[58 * mm, 122 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_summary_cards(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    badges = [
        _metric_badge(label, str(value), "počet záznamů", styles)
        for label, value in _bucketize_records(payload)
    ]
    table = Table([badges], colWidths=[43.5 * mm, 43.5 * mm, 43.5 * mm, 43.5 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_owner_block(owner: VehicleReportOwner, styles: dict[str, ParagraphStyle]) -> Table:
    items = [
        ("Jméno / subjekt", owner.name or "Neuvedeno"),
        ("E-mail", owner.email or "Neuvedeno"),
        ("Telefon", owner.phone or "Neuvedeno"),
        ("Město", owner.city or "Neuvedeno"),
    ]
    if owner.ico:
        items.append(("IČO", owner.ico))
    if owner.dic:
        items.append(("DIČ", owner.dic))
    if owner.address:
        items.append(("Adresa", owner.address))

    midpoint = (len(items) + 1) // 2
    left_items = items[:midpoint]
    right_items = items[midpoint:]
    left_column_items: list = []
    right_column_items: list = []
    for index, (label, value) in enumerate(left_items):
        left_column_items.append(_owner_field(label, value, width=78 * mm, styles=styles))
        if index != len(left_items) - 1:
            left_column_items.append(Spacer(1, 1.7 * mm))
    for index, (label, value) in enumerate(right_items):
        right_column_items.append(_owner_field(label, value, width=78 * mm, styles=styles))
        if index != len(right_items) - 1:
            right_column_items.append(Spacer(1, 1.7 * mm))

    owner_grid = Table(
        [[
            _stack(80 * mm, *left_column_items) if left_column_items else Spacer(1, 1),
            _stack(80 * mm, *right_column_items) if right_column_items else Spacer(1, 1),
        ]],
        colWidths=[84 * mm, 84 * mm],
    )
    owner_grid.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )

    content = [
        [_paragraph(owner.label, styles["section_kicker"])],
        [_paragraph("Oddělená sekce vlastníka", styles["section_title"])],
        [_paragraph("Kontaktní a identifikační údaje vlastníka oddělené od veřejně ověřitelné části dokumentu.", styles["body_small"])],
        [owner_grid],
    ]
    table = Table(content, colWidths=[180 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), COLOR_ORANGE_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.9, COLOR_ORANGE_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _build_history_row(record: VehicleReportServiceRecord, styles: dict[str, ParagraphStyle]) -> list:
    primary_title = record.title or record.performed_work or "Servisní záznam"
    secondary_bits: list[str] = []
    if str(record.source_type or "").strip().lower() == "stk_history":
        secondary_bits.append("Import STK / tachometr")
    elif "ověř" in str(record.verification_status or "").lower():
        secondary_bits.append("Ověřený servisní doklad")
    secondary_line = " | ".join(
        part for part in [
            *secondary_bits,
            record.workshop or record.supplier,
            record.technician,
            record.verification_status,
        ] if part
    )
    row = Table(
        [[
            _paragraph(_fmt_date(record.date), styles["history_date"]),
            _stack(
                90 * mm,
                _paragraph(primary_title, styles["history_title"]),
                _paragraph(secondary_line or (record.performed_work or "Bez detailního popisu"), styles["history_meta"]),
            ),
            _history_stat_block("Nájezd", _fmt_km(record.odometer_km), width=26 * mm, styles=styles),
            _history_stat_block("Cena", _fmt_money_totals(record.totals), width=34 * mm, styles=styles),
        ]],
        colWidths=[22 * mm, 92 * mm, 28 * mm, 38 * mm],
    )
    row.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, COLOR_LINE),
            ]
        )
    )
    details: list = [row]
    extra_bits = []
    if int(record.attachments_count or 0) > 0:
        extra_bits.append(f"Doklady: {int(record.attachments_count)}")
    if record.parts:
        extra_bits.append(f"Díly: {', '.join(record.parts[:4])}")
    if record.notes:
        extra_bits.append(f"Poznámka: {record.notes}")
    if record.audit_note:
        extra_bits.append(record.audit_note)
    if extra_bits:
        details.extend(
            [
                _card(
                    _paragraph(" | ".join(extra_bits), styles["history_extra"]),
                    width=176 * mm,
                    background=COLOR_SURFACE,
                    border=COLOR_BORDER,
                    padding=7,
                ),
                Spacer(1, 1.2 * mm),
            ]
        )
    return details


def _build_history_timeline(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> list:
    story: list = []
    for year, records in _group_records_by_year(payload.service_records):
        story.extend(
            [
                CondPageBreak(48 * mm),
                Spacer(1, 1.4 * mm),
                _paragraph(year, styles["year_heading"]),
                HRFlowable(width="100%", thickness=0.8, color=COLOR_ORANGE),
                Spacer(1, 1.4 * mm),
            ]
        )
        for record in records:
            story.extend(_build_history_row(record, styles))
    return story


def _build_document_integrity_cards(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    cards = [
        _metric_badge(
            "Záznamy s dokladem",
            str(_count_records_with_attachments(payload)),
            "faktury a přílohy",
            styles,
        ),
        _metric_badge(
            "Ověřené položky",
            str(_count_verified_records(payload)),
            "doklad nebo auditní stopa",
            styles,
        ),
        _metric_badge(
            "STK / tachometr",
            str(_count_stk_import_records(payload)),
            "importované read-only body",
            styles,
        ),
        _metric_badge(
            "Datová rizika",
            str(len(payload.summary.record_quality_flags) + int(payload.mileage_timeline.anomalies_count or 0)),
            "flagy a anomálie",
            styles,
        ),
    ]
    table = Table([cards], colWidths=[43.5 * mm, 43.5 * mm, 43.5 * mm, 43.5 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_source_overview_table(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    service_count = sum(1 for record in payload.service_records if str(record.source_type or "").strip().lower() != "stk_history")
    stk_count = _count_stk_import_records(payload)
    owner_scope = "Oddělená sekce vlastníka" if payload.owner else "Bez osobních údajů ve veřejném režimu"
    rows = [
        ("Servisní záznamy", str(service_count), "Ruční zápisy a servisní úkony uložené v aplikaci."),
        ("STK / tachometr", str(stk_count), "Read-only importy z kontrolatachometru.cz a související body km."),
        ("Doklady a přílohy", str(_count_records_with_attachments(payload)), "Přiložené faktury, zakázkové listy a vytěžené položky."),
        ("Vlastník a GDPR", owner_scope, "Veřejné ověření zobrazuje jen omezený rozsah údajů."),
    ]
    data = [[
        _paragraph("Původ dat", styles["meta_label"]),
        _paragraph("Rozsah", styles["meta_label"]),
        _paragraph("Poznámka", styles["meta_label"]),
    ]]
    for label, value, note in rows:
        data.append([
            _paragraph(label, styles["history_title"]),
            _paragraph(value, styles["history_value_left"]),
            _paragraph(note, styles["body_small"]),
        ])
    table = Table(data, colWidths=[40 * mm, 30 * mm, 110 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_SURFACE_ALT),
                ("BOX", (0, 0), (-1, -1), 0.8, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_quality_overview_cards(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    quality_lines = payload.summary.record_quality_flags or ["Nevznikly žádné kritické quality flagy."]
    recommendation_lines = payload.summary.open_recommendations or ["Systém aktuálně neeviduje otevřená doporučení."]
    left = _card(
        _stack(
            84 * mm,
            _paragraph("Datová kvalita", styles["section_kicker"]),
            _paragraph("Zjištěné quality flagy", styles["section_title_small"]),
            _bullet_list(quality_lines, styles["body_small"]),
        ),
        width=88 * mm,
        background=COLOR_SURFACE,
        border=COLOR_BORDER,
        padding=10,
    )
    right = _card(
        _stack(
            84 * mm,
            _paragraph("Doporučení systému", styles["section_kicker"]),
            _paragraph("Automaticky odvozená doporučení", styles["section_title_small"]),
            _bullet_list(recommendation_lines, styles["body_small"]),
        ),
        width=88 * mm,
        background=COLOR_GREEN_SOFT if payload.summary.open_recommendations else COLOR_SURFACE,
        border=COLOR_BORDER,
        padding=10,
    )
    table = Table([[left, right]], colWidths=[89 * mm, 89 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def _build_document_origin_card(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> Table:
    fingerprint = str(payload.document.fingerprint or "").strip()
    fingerprint_short = fingerprint[:20] + "…" if len(fingerprint) > 20 else (fingerprint or "Neuvedeno")
    manual_count = _count_manual_records(payload)
    items = [
        ("Dokument ID", payload.document.document_id or "Neuvedeno"),
        ("Ověřovací kód", payload.document.verification_code or "Neuvedeno"),
        ("Režim exportu", _resolve_export_mode_label(payload)),
        ("Vystavil", payload.document.issued_by or "Správa vozidel"),
        ("Generováno", _fmt_datetime(payload.document.generated_at)),
        ("Fingerprint", fingerprint_short),
        ("Ruční záznamy", str(manual_count)),
    ]
    if payload.document.verification_url:
        items.append(("Veřejné ověření", "hub.toozservis.cz/verify"))
    return _card(
        _stack(
            176 * mm,
            _paragraph("Původ dokumentu a ověření", styles["section_kicker"]),
            _paragraph("Auditovatelnost vystaveného výpisu", styles["section_title_small"]),
            _kv_table(items, styles=styles, col_widths=[36 * mm, 136 * mm]),
            Spacer(1, 1.2 * mm),
            _paragraph(
                "Pravost dokumentu lze ověřit QR kódem nebo ověřovacím kódem. Veřejné ověření záměrně neodhaluje plné osobní údaje vlastníka vozidla.",
                styles["body_small"],
            ),
        ),
        width=180 * mm,
        background=COLOR_SURFACE,
        border=COLOR_BORDER,
        padding=10,
    )


def _build_provenance_appendix(payload: VehicleServiceReportPayload, styles: dict[str, ParagraphStyle]) -> list:
    return [
        PageBreak(),
        _paragraph("Důvěryhodnost a původ dat", styles["section_kicker"]),
        _paragraph("Auditovatelnost a rozsah zdrojů", styles["section_title"]),
        _paragraph(
            "Tato část shrnuje, z jakých podkladů byl výpis sestaven, jaké typy záznamů pokrývá a kde systém sám označil možné limity nebo rizika kvality dat.",
            styles["body"],
        ),
        Spacer(1, 1.6 * mm),
        _build_document_integrity_cards(payload, styles),
        Spacer(1, 2.2 * mm),
        _build_source_overview_table(payload, styles),
        Spacer(1, 2.2 * mm),
        _build_quality_overview_cards(payload, styles),
        Spacer(1, 2.2 * mm),
        _build_document_origin_card(payload, styles),
    ]


def render_vehicle_service_report_pdf(payload: VehicleServiceReportPayload) -> bytes:
    _register_fonts()
    styles_base = getSampleStyleSheet()
    styles = {
        "brand": ParagraphStyle("brand", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=8.6, leading=10, textColor=COLOR_TEXT),
        "brand_caps": ParagraphStyle("brand_caps", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=9.5, leading=10.8, textColor=COLOR_TEXT),
        "brand_meta": ParagraphStyle("brand_meta", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.1, leading=8.4, textColor=COLOR_MUTED),
        "doc_title_center": ParagraphStyle("doc_title_center", parent=styles_base["Heading1"], fontName=FONT_BOLD, fontSize=14.2, leading=15.8, textColor=COLOR_TEXT, alignment=TA_CENTER),
        "doc_subtitle_center": ParagraphStyle("doc_subtitle_center", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.6, leading=8.8, textColor=COLOR_MUTED, alignment=TA_CENTER),
        "doc_meta_center": ParagraphStyle("doc_meta_center", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.1, leading=8.4, textColor=COLOR_MUTED, alignment=TA_CENTER),
        "verify_title": ParagraphStyle("verify_title", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=6.7, leading=7.6, textColor=COLOR_TEXT, alignment=TA_CENTER),
        "verify_code": ParagraphStyle("verify_code", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=7.2, leading=8.1, textColor=COLOR_TEXT, alignment=TA_CENTER),
        "verify_hint": ParagraphStyle("verify_hint", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=5.9, leading=6.9, textColor=COLOR_MUTED, alignment=TA_CENTER),
        "verify_link": ParagraphStyle("verify_link", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=5.8, leading=6.8, textColor=COLOR_BLUE, alignment=TA_CENTER),
        "hero_title": ParagraphStyle("hero_title", parent=styles_base["Heading1"], fontName=FONT_BOLD, fontSize=24.5, leading=28, textColor=colors.white),
        "section_kicker": ParagraphStyle("section_kicker", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=8.2, leading=9.2, textColor=COLOR_BLUE, spaceAfter=0.2),
        "section_title": ParagraphStyle("section_title", parent=styles_base["Heading2"], fontName=FONT_BOLD, fontSize=13.5, leading=15.6, textColor=COLOR_TEXT, spaceAfter=4),
        "metric_label": ParagraphStyle("metric_label", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=7.6, leading=9, textColor=COLOR_TEXT, alignment=TA_LEFT),
        "metric_value": ParagraphStyle("metric_value", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=17, leading=19.8, textColor=COLOR_TEXT, alignment=TA_LEFT),
        "metric_note": ParagraphStyle("metric_note", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.2, leading=8.8, textColor=COLOR_MUTED, alignment=TA_LEFT),
        "meta_label": ParagraphStyle("meta_label", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.4, leading=9, textColor=COLOR_TEXT),
        "meta_value": ParagraphStyle("meta_value", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=8.1, leading=10, textColor=COLOR_TEXT),
        "brand_showcase": ParagraphStyle("brand_showcase", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=15.4, leading=18.2, textColor=COLOR_TEXT, alignment=TA_CENTER),
        "brand_showcase_sub": ParagraphStyle("brand_showcase_sub", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=9.3, leading=11.2, textColor=COLOR_MUTED, alignment=TA_CENTER),
        "brand_vin": ParagraphStyle("brand_vin", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=7.7, leading=9.2, textColor=COLOR_TEXT, alignment=TA_CENTER),
        "hero_name": ParagraphStyle("hero_name", parent=styles_base["Heading2"], fontName=FONT_BOLD, fontSize=15.2, leading=17.8, textColor=COLOR_TEXT),
        "hero_subtitle": ParagraphStyle("hero_subtitle", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.8, leading=9.8, textColor=COLOR_MUTED),
        "hero_chip_label": ParagraphStyle("hero_chip_label", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=6.7, leading=8.1, textColor=COLOR_MUTED),
        "hero_chip_value": ParagraphStyle("hero_chip_value", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=8.8, leading=10.4, textColor=COLOR_TEXT),
        "owner_label": ParagraphStyle("owner_label", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.3, leading=8.8, textColor=COLOR_MUTED),
        "owner_value": ParagraphStyle("owner_value", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=9.2, leading=11.2, textColor=COLOR_TEXT),
        "history_date": ParagraphStyle("history_date", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=8.1, leading=9.4, textColor=COLOR_TEXT),
        "history_title": ParagraphStyle("history_title", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=8.8, leading=10.6, textColor=COLOR_TEXT),
        "history_meta": ParagraphStyle("history_meta", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.2, leading=8.8, textColor=COLOR_MUTED),
        "history_value": ParagraphStyle("history_value", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=7.9, leading=9.4, textColor=COLOR_TEXT, alignment=TA_RIGHT),
        "history_value_left": ParagraphStyle("history_value_left", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=7.9, leading=9.4, textColor=COLOR_TEXT, alignment=TA_LEFT),
        "history_extra": ParagraphStyle("history_extra", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.1, leading=8.6, textColor=COLOR_MUTED),
        "history_metric_label": ParagraphStyle("history_metric_label", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=6.4, leading=7.6, textColor=COLOR_MUTED, alignment=TA_RIGHT),
        "history_metric_value": ParagraphStyle("history_metric_value", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=8.5, leading=10.1, textColor=COLOR_TEXT, alignment=TA_RIGHT),
        "year_heading": ParagraphStyle("year_heading", parent=styles_base["Normal"], fontName=FONT_BOLD, fontSize=11.4, leading=13, textColor=COLOR_ORANGE),
        "body": ParagraphStyle("body", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=8.8, leading=12.2, textColor=COLOR_TEXT, alignment=TA_LEFT),
        "body_small": ParagraphStyle("body_small", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=7.6, leading=10.2, textColor=COLOR_TEXT, alignment=TA_LEFT),
        "empty_state": ParagraphStyle("empty_state", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=10.2, leading=14.4, textColor=colors.HexColor("#334155"), alignment=TA_CENTER),
        "note": ParagraphStyle("note", parent=styles_base["Normal"], fontName=FONT_REGULAR, fontSize=8.5, leading=11, textColor=COLOR_MUTED, alignment=TA_RIGHT),
        "section_title_small": ParagraphStyle("section_title_small", parent=styles_base["Heading2"], fontName=FONT_BOLD, fontSize=11.2, leading=13.2, textColor=COLOR_TEXT, spaceAfter=4),
    }

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=18 * mm,
        title="Digitální servisní výpis vozidla",
        author="Správa vozidel",
    )

    story = [
        _build_header(payload, styles),
        Spacer(1, 2.1 * mm),
    ]
    handover = _build_new_owner_handover_banner(payload, styles)
    if handover is not None:
        story.append(handover)
        story.append(Spacer(1, 2.4 * mm))
    story.extend(
        [
        _build_hero(payload, styles),
        Spacer(1, 1.1 * mm),
        _build_summary_cards(payload, styles),
        Spacer(1, 2.2 * mm),
        ]
    )

    if payload.owner:
        story.extend(
            [
                _build_owner_block(payload.owner, styles),
                Spacer(1, 3.2 * mm),
            ]
        )

    story.extend(_build_mileage_timeline_section(payload, styles))

    story.extend(
        [
            _paragraph("Servisní historie", styles["section_kicker"]),
            _paragraph("Chronologický přehled provedených úkonů", styles["section_title"]),
        ]
    )

    if payload.service_records:
        story.extend(_build_history_timeline(payload, styles))
    else:
        empty_table = _card(
            _paragraph(
                "K tomuto vozidlu zatím nejsou evidovány žádné servisní záznamy. Výpis je připraven jako oficiální servisní dokument a automaticky se rozšíří s další historií údržby.",
                styles["empty_state"],
            ),
            width=180 * mm,
            background=COLOR_SURFACE,
            border=COLOR_BORDER,
            padding=18,
        )
        story.append(empty_table)
        story.append(Spacer(1, 4 * mm))

    if payload.summary.open_recommendations:
        story.extend(
            [
                _paragraph("Doporučení a upozornění", styles["section_kicker"]),
                _paragraph("Automaticky odvozené servisní poznámky", styles["section_title"]),
                _bullet_list(payload.summary.open_recommendations, styles["body"]),
                Spacer(1, 2 * mm),
            ]
        )

    story.extend(
        [
            Spacer(1, 1.2 * mm),
            _card(
                _stack(
                    176 * mm,
                    _paragraph("Původ dokumentu", styles["section_kicker"]),
                    _paragraph(
                        "Pravost tohoto dokumentu lze ověřit pomocí QR kódu nebo ověřovacího kódu na adrese hub.toozservis.cz/verify. Veřejné ověření zobrazuje jen omezený rozsah údajů kvůli ochraně osobních údajů.",
                        styles["body"],
                    ),
                    Spacer(1, 1.2 * mm),
                    _paragraph(
                        "Součástí další strany je také auditovatelnost exportu, přehled použitých zdrojů, kvalita dat a vysvětlení rozsahu veřejného ověření.",
                        styles["body_small"],
                    ),
                ),
                width=180 * mm,
                background=COLOR_SURFACE,
                border=COLOR_BORDER,
                padding=10,
            ),
        ]
    )

    story.extend(_build_provenance_appendix(payload, styles))

    footer_text = "Tento dokument byl vygenerován ze systému digitální servisní knihy vozidla ToozServis / Správa vozidel."
    version_text = f"Verze dokumentu {payload.document.version} | Revize {payload.document.revision} | ID {payload.document.document_id} | Ověřovací kód {payload.document.verification_code}"
    doc.build(
        story,
        canvasmaker=_canvas_factory(footer_text=footer_text, version_text=version_text),
    )
    return buffer.getvalue()
