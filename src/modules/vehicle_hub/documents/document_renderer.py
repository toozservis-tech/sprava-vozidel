from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from .document_layout import (
    COLOR_BORDER,
    build_document_styles,
    build_header_table,
    build_qr_block,
    build_vehicle_customer_table,
    status_label,
)
from .document_registry import get_document_type
from .document_schemas import PlatformDocumentPayload


def render_platform_document_pdf(payload: PlatformDocumentPayload) -> bytes:
    """Generic C1.0 platform PDF — block layout, not text export."""
    type_def = get_document_type(payload.document_type)
    styles = build_document_styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=payload.title or type_def.label,
    )

    story = []
    story.append(
        build_header_table(
            service_name=payload.service_name,
            service_ico=payload.service_ico,
            document_type_label=type_def.label,
            document_status=payload.document_status,
            document_number=payload.document_number,
            styles=styles,
        )
    )
    story.append(Spacer(1, 8))
    story.append(Paragraph(payload.title or type_def.label, styles["title"]))
    story.append(Spacer(1, 6))
    story.append(
        build_vehicle_customer_table(
            vehicle_label=payload.vehicle_label,
            vehicle_plate=payload.vehicle_plate,
            vehicle_vin_masked=payload.vehicle_vin_masked,
            customer_label=payload.customer_label,
            styles=styles,
        )
    )
    story.append(Spacer(1, 10))
    story.append(Paragraph("Obsah dokumentu (platformní náhled)", styles["section"]))
    body_lines = payload.body_lines or [
        f"Typ: {type_def.label}",
        f"Stav: {status_label(payload.document_status)}",
        "Toto je generický proof-of-platform PDF pro C1.0.",
        "Typ-specifický renderer bude doplněn v C1.1+.",
    ]
    for line in body_lines:
        story.append(Paragraph(str(line), styles["body"]))
        story.append(Spacer(1, 3))
    story.append(Spacer(1, 8))
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
        Paragraph(
            f"Správa vozidel · Document Platform {payload.platform_version} · {type_def.renderer_status}",
            styles["muted"],
        )
    )

    doc.build(story)
    content = buffer.getvalue()
    if len(content) < 2048:
        raise RuntimeError("Platform PDF too small — likely failed render.")
    return content
