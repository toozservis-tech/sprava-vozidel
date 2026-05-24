"""
Velký technický průkaz — interní přehled v aplikaci Správa vozidel.
Účel: přehledné čtení údajů z aplikace a dostupných zdrojů; není úředním dokladem.
"""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
from reportlab.platypus.doctemplate import BaseDocTemplate, Frame, PageTemplate, _doNothing

FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

_DEJAVU_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
_DEJAVU_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")

_CLR_INK = colors.HexColor("#111827")
_CLR_RULE = colors.HexColor("#1f2937")
_CLR_MUTED = colors.HexColor("#4b5563")
_CLR_LINE = colors.HexColor("#d1d5db")
_CLR_LABEL_BG = colors.HexColor("#f3f4f6")
_CLR_SECTION_BG = colors.HexColor("#e5e7eb")
_CLR_WARN = colors.HexColor("#991b1b")
_CLR_WM = colors.HexColor("#64748b")

_PAGE_W_MM = 210.0
# Jediný vodoznak přes stránku — nízká kryvost, dokument zůstane čitelný
_WM_ALPHA = 0.11


class _LargeTechnicalCertificateDoc(BaseDocTemplate):
    """Overlay (vodoznak + patička) v afterPage() — poslední krok před uzavřením stránky."""

    def __init__(self, filename: Any, *, otp_vehicle_id: int, **kw: Any):
        super().__init__(filename, **kw)
        self._otp_vehicle_id = otp_vehicle_id

    def afterPage(self) -> None:
        super().afterPage()
        canv, doc, vid = self.canv, self, self._otp_vehicle_id
        canv.saveState()
        try:
            _draw_watermark(canv, doc, vid)
            _draw_footer(canv, doc, vid)
        finally:
            canv.restoreState()


def _content_width_mm(left_margin_mm: float, right_margin_mm: float) -> float:
    return _PAGE_W_MM - left_margin_mm - right_margin_mm


def _register_fonts() -> None:
    registered = pdfmetrics.getRegisteredFontNames()
    if FONT_REGULAR in registered and FONT_BOLD in registered:
        return
    if not _DEJAVU_REGULAR.exists() or not _DEJAVU_BOLD.exists():
        raise RuntimeError("Na serveru chybí font DejaVuSans potřebný pro PDF.")
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(_DEJAVU_REGULAR)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_DEJAVU_BOLD)))


def _para_plain(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text or "").replace("\n", "<br/>"), style)


def _para_rich(markup: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(markup or "").replace("\n", "<br/>"), style)


def _fmt_scalar(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d.%m.%Y %H:%M")
    if isinstance(val, date):
        return val.strftime("%d.%m.%Y")
    return str(val).strip()


def _pairs_from_vehicle(vehicle: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    mapping = [
        ("Evidenční název / přezdívka", getattr(vehicle, "nickname", None)),
        ("SPZ", getattr(vehicle, "plate", None)),
        ("VIN", getattr(vehicle, "vin", None)),
        ("Číslo ORV", getattr(vehicle, "orv_number", None)),
        ("Značka / výrobce", getattr(vehicle, "brand", None)),
        ("Obchodní označení / model", getattr(vehicle, "model", None)),
        ("Rok výroby", getattr(vehicle, "year", None)),
        ("Motor (popis)", getattr(vehicle, "engine", None)),
        ("Palivo", getattr(vehicle, "fuel", None)),
        ("Karoserie", getattr(vehicle, "body_type", None)),
        ("Platnost STK do", getattr(vehicle, "stk_valid_until", None)),
        ("Stav tachometru [km]", getattr(vehicle, "current_mileage_km", None)),
        ("Poslední km ze STK [km]", getattr(vehicle, "last_stk_mileage_km", None)),
        ("Pojišťovna", getattr(vehicle, "insurance_provider", None)),
        ("Platnost pojištění do", getattr(vehicle, "insurance_valid_until", None)),
        ("Pneumatiky / poznámka k pneu", getattr(vehicle, "tyres_info", None)),
        ("Poznámky uživatele", getattr(vehicle, "notes", None)),
    ]
    for label, raw in mapping:
        text = _fmt_scalar(raw)
        if text:
            pairs.append((label, text))
    return pairs


def _overview_sections_to_pairs(overview: dict[str, Any] | None) -> list[tuple[str, list[tuple[str, str]]]]:
    if not overview or not isinstance(overview, dict):
        return []
    sections_in = overview.get("sections")
    if not isinstance(sections_in, list):
        return []
    out: list[tuple[str, list[tuple[str, str]]]] = []
    for sec in sections_in:
        if not isinstance(sec, dict):
            continue
        title = str(sec.get("title") or sec.get("key") or "Údaje").strip()
        rows_in = sec.get("rows") or []
        pairs: list[tuple[str, str]] = []
        if not isinstance(rows_in, list):
            continue
        for row in rows_in:
            if not isinstance(row, dict):
                continue
            lab = str(row.get("label") or "").strip()
            val_s = _fmt_scalar(row.get("value"))
            if lab and val_s:
                pairs.append((lab, val_s))
        if pairs:
            out.append((title, pairs))
    return out


def _kv_table(
    rows: list[tuple[str, str]],
    lbl_style: ParagraphStyle,
    val_style: ParagraphStyle,
    *,
    content_width: float,
    label_col_mm: float = 52.0,
) -> Table:
    vw = content_width - label_col_mm * mm
    lw = label_col_mm * mm
    data = [[_para_plain(lab, lbl_style), _para_plain(val, val_style)] for lab, val in rows]
    t = Table(data, colWidths=[lw, vw])
    ts: list[tuple[Any, ...]] = [
        ("BOX", (0, 0), (-1, -1), 0.75, _CLR_RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, _CLR_LINE),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, _CLR_RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (0, -1), _CLR_LABEL_BG),
        ("FONTNAME", (0, 0), (0, -1), FONT_BOLD),
        ("FONTSIZE", (0, 0), (0, -1), lbl_style.fontSize),
        ("FONTNAME", (1, 0), (1, -1), FONT_REGULAR),
    ]
    t.setStyle(TableStyle(ts))
    return t


def _section_bar(title: str, style: ParagraphStyle, *, content_width: float) -> Table:
    p = _para_plain(title.upper(), style)
    t = Table([[p]], colWidths=[content_width])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _CLR_SECTION_BG),
                ("LINEBELOW", (0, 0), (-1, -1), 0.85, _CLR_RULE),
                ("LINEABOVE", (0, 0), (-1, -1), 0.35, _CLR_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def _logo_image(*, width_mm: float = 52) -> RLImage:
    sc = 2
    w_px, h_px = 260 * sc, 56 * sc
    im = Image.new("RGBA", (w_px, h_px), (255, 255, 255, 255))
    dr = ImageDraw.Draw(im)
    try:
        f_b = ImageFont.truetype(str(_DEJAVU_BOLD), 17 * sc)
        f_r = ImageFont.truetype(str(_DEJAVU_REGULAR), 9 * sc)
    except OSError:
        f_b = f_r = ImageFont.load_default()

    pad = 5 * sc
    dr.rectangle([pad, pad, w_px - pad, h_px - pad], outline="#334155", width=2 * sc)
    dr.rectangle([pad + 6 * sc, pad + 6 * sc, pad + 10 * sc, h_px - pad - 6 * sc], fill="#1e40af")
    tx = pad + 18 * sc
    dr.text((tx, pad + 10 * sc), "Správa vozidel", fill="#111827", font=f_b)
    dr.text((tx, pad + 30 * sc), "Interní přehled vozidla", fill="#4b5563", font=f_r)

    bio = BytesIO()
    im.save(bio, format="PNG")
    bio.seek(0)
    aspect = h_px / w_px
    return RLImage(bio, width=width_mm * mm, height=width_mm * aspect * mm, kind="proportional")


def _fill_alpha(canv: Any, a: float, c: Any) -> None:
    canv.setFillColor(c)
    try:
        canv.setFillAlpha(min(1.0, max(0.0, a)))
    except Exception:
        pass


def _page_tint(canv: Any, doc: Any) -> None:
    pw, ph = doc.pagesize
    canv.saveState()
    canv.setFillColor(colors.HexColor("#fafafa"))
    canv.rect(0, 0, pw, ph, stroke=0, fill=1)
    canv.restoreState()


def _page_frame(canv: Any, doc: Any) -> None:
    pw, ph = doc.pagesize
    lm, bm, tm, rm = doc.leftMargin, doc.bottomMargin, doc.topMargin, doc.rightMargin
    canv.saveState()
    canv.setStrokeColor(_CLR_RULE)
    canv.setLineWidth(0.9)
    canv.rect(lm - 0.8 * mm, bm - 0.8 * mm, pw - lm - rm + 1.6 * mm, ph - bm - tm + 1.6 * mm, stroke=1, fill=0)
    canv.restoreState()


def _draw_watermark(canv: Any, doc: Any, vehicle_id: int) -> None:
    """Jediná vrstva: střed stránky, šikmo, bez mřížky a bez razítek."""
    pw, ph = doc.pagesize
    canv.saveState()
    canv.translate(pw / 2, ph / 2)
    canv.rotate(-32)
    _fill_alpha(canv, _WM_ALPHA, _CLR_WM)
    canv.setFont(FONT_BOLD, 26)
    canv.drawCentredString(0, 8, "SPRÁVA VOZIDEL")
    canv.setFont(FONT_REGULAR, 9)
    _fill_alpha(canv, _WM_ALPHA * 0.95, _CLR_WM)
    canv.drawCentredString(0, -14, "Informační dokument · bez právního účinku")
    canv.setFont(FONT_REGULAR, 8)
    _fill_alpha(canv, _WM_ALPHA * 0.85, _CLR_WM)
    canv.drawCentredString(0, -28, f"Záznam {vehicle_id}")
    canv.restoreState()


def _draw_footer(canv: Any, doc: Any, vehicle_id: int) -> None:
    pw = doc.pagesize[0]
    lm, rm = doc.leftMargin, doc.rightMargin
    bm = doc.bottomMargin
    sep_y, text_y = bm * 0.62, bm * 0.30

    canv.saveState()
    canv.setStrokeColor(_CLR_LINE)
    canv.setLineWidth(0.35)
    try:
        canv.setStrokeAlpha(1.0)
    except Exception:
        pass
    canv.line(lm + 4 * mm, sep_y, pw - rm - 4 * mm, sep_y)
    canv.restoreState()

    canv.saveState()
    canv.setFillColor(_CLR_MUTED)
    canv.setFont(FONT_REGULAR, 6.5)
    canv.drawCentredString(
        pw / 2,
        text_y,
        f"Správa vozidel · interní dokument · záznam č. {vehicle_id} · str. {doc.page}",
    )
    canv.restoreState()


def render_large_technical_certificate_pdf(vehicle: Any) -> bytes:
    from src.core.datetime_cz import format_prague_generated_label

    _register_fonts()
    base = getSampleStyleSheet()

    st_title = ParagraphStyle(
        "ltp_title",
        parent=base["Normal"],
        fontName=FONT_BOLD,
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        textColor=_CLR_INK,
        spaceAfter=3,
    )
    st_sub = ParagraphStyle(
        "ltp_sub",
        parent=base["Normal"],
        fontName=FONT_REGULAR,
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        textColor=_CLR_MUTED,
        spaceAfter=5,
    )
    st_warn = ParagraphStyle(
        "ltp_warn",
        parent=base["Normal"],
        fontName=FONT_BOLD,
        fontSize=8,
        leading=10,
        alignment=TA_CENTER,
        textColor=_CLR_WARN,
        spaceAfter=6,
    )
    st_meta = ParagraphStyle(
        "ltp_meta",
        parent=base["Normal"],
        fontName=FONT_REGULAR,
        fontSize=7.5,
        leading=9,
        alignment=TA_CENTER,
        textColor=_CLR_MUTED,
    )
    st_disclaimer = ParagraphStyle(
        "ltp_disc",
        parent=base["Normal"],
        fontName=FONT_REGULAR,
        fontSize=7.5,
        leading=11,
        alignment=TA_JUSTIFY,
        textColor=_CLR_INK,
    )
    st_sec = ParagraphStyle(
        "ltp_sec",
        parent=base["Normal"],
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=11,
        alignment=TA_LEFT,
        textColor=_CLR_INK,
    )
    st_lbl = ParagraphStyle(
        "ltp_lbl",
        parent=base["Normal"],
        fontName=FONT_BOLD,
        fontSize=7.8,
        leading=10,
        alignment=TA_LEFT,
        textColor=_CLR_INK,
        wordWrap="LTR",
    )
    st_val = ParagraphStyle(
        "ltp_val",
        parent=base["Normal"],
        fontName=FONT_REGULAR,
        fontSize=8,
        leading=10.5,
        alignment=TA_LEFT,
        textColor=_CLR_INK,
        wordWrap="LTR",
    )
    st_sec_sub = ParagraphStyle(
        "ltp_sec_sub",
        parent=base["Normal"],
        fontName=FONT_BOLD,
        fontSize=9,
        leading=12,
        textColor=_CLR_INK,
        spaceBefore=2,
        spaceAfter=4,
    )

    vid = int(getattr(vehicle, "id", 0) or 0)
    now = format_prague_generated_label()
    overview = getattr(vehicle, "vehicle_technical_overview", None)
    if overview is not None and not isinstance(overview, dict):
        overview = None

    pairs_a = _pairs_from_vehicle(vehicle)
    sections_b = _overview_sections_to_pairs(overview)

    margin_mm = 17.0
    cw = _content_width_mm(margin_mm, margin_mm) * mm
    pad_x = 7 * mm
    inner_w = cw - 2 * pad_x

    buf = BytesIO()
    doc = _LargeTechnicalCertificateDoc(
        buf,
        otp_vehicle_id=vid,
        pagesize=A4,
        leftMargin=margin_mm * mm,
        rightMargin=margin_mm * mm,
        topMargin=16 * mm,
        bottomMargin=24 * mm,
        title="Velký technický průkaz — Správa vozidel",
    )
    story: list[Any] = []

    def wrap(flow: Any) -> Table:
        t = Table([[flow]], colWidths=[cw])
        t.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), pad_x),
                    ("RIGHTPADDING", (0, 0), (-1, -1), pad_x),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return t

    logo = _logo_image(width_mm=50)
    hdr_inner = Table(
        [
            [logo],
            [Spacer(1, 4 * mm)],
            [_para_plain("Velký technický průkaz — informační přehled", st_title)],
            [
                _para_plain(
                    "Nejedná se o úřední technický průkaz ani o doklad platný vůči správním orgánům.",
                    st_sub,
                )
            ],
            [
                _para_plain(
                    "Není státní doklad — pouze export údajů ze Správy vozidel.",
                    st_warn,
                )
            ],
            [_para_plain(f"Záznam č. {vid} · vygenerováno {now}", st_meta)],
        ],
        colWidths=[inner_w],
    )
    hdr_inner.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 1), (0, 1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    hdr = Table([[hdr_inner]], colWidths=[cw])
    hdr.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.65, _CLR_LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), pad_x),
                ("RIGHTPADDING", (0, 0), (-1, -1), pad_x),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ]
        )
    )
    story.append(hdr)
    story.append(Spacer(1, 4 * mm))

    disc_txt = (
        "Tento dokument nenahrazuje technický průkaz vozidla. Slouží jako přehled údajů uložených v aplikaci "
        "a případně doplněných z veřejných zdrojů. Za správnost a aktuálnost odpovídá uživatel aplikace."
    )
    disc = Table([[(_para_plain(disc_txt, st_disclaimer))]], colWidths=[inner_w])
    disc.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, _CLR_LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f9fafb")),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(wrap(disc))
    story.append(Spacer(1, 5 * mm))

    story.append(wrap(_section_bar("Oddíl A — údaje z aplikace", st_sec, content_width=inner_w)))
    story.append(wrap(Spacer(1, 2 * mm)))
    if pairs_a:
        story.append(wrap(_kv_table(pairs_a, st_lbl, st_val, content_width=inner_w)))
    else:
        et = Table([[_para_plain("Žádné vyplněné údaje.", st_val)]], colWidths=[inner_w])
        et.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.65, _CLR_LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(wrap(et))
    story.append(Spacer(1, 5 * mm))

    if sections_b:
        story.append(
            wrap(
                _section_bar(
                    "Oddíl B — doplňující technické údaje (zdroje mimo aplikaci)",
                    st_sec,
                    content_width=inner_w,
                )
            )
        )
        story.append(wrap(Spacer(1, 2 * mm)))
        for sec_title, sec_rows in sections_b:
            st = Table([[(_para_plain(sec_title, st_sec_sub))]], colWidths=[inner_w])
            st.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            story.append(wrap(st))
            story.append(wrap(_kv_table(sec_rows, st_lbl, st_val, content_width=inner_w)))
            story.append(wrap(Spacer(1, 3 * mm)))
    else:
        idle_txt = (
            "Oddíl B se doplní po načtení rozšířených údajů vozidla (např. registr, VIN)."
            " Zatím použijte oddíl A."
        )
        it = Table([[(_para_plain(idle_txt, st_disclaimer))]], colWidths=[inner_w])
        it.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, _CLR_LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 9),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
                ]
            )
        )
        story.append(wrap(it))

    story.append(Spacer(1, 5 * mm))

    frame_norm = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")

    def _on_page_start(c: Any, d: Any) -> None:
        _page_tint(c, d)
        _page_frame(c, d)

    doc.addPageTemplates(
        [
            PageTemplate(
                id="ltp",
                frames=[frame_norm],
                onPage=_on_page_start,
                onPageEnd=_doNothing,
                pagesize=A4,
            )
        ]
    )
    doc.build(story)
    return buf.getvalue()
