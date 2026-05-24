"""
Jeden soubor „Velký technický průkaz“ na vozidlo — přepisuje se při přegenerování technického přehledu (např. po VIN).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from src.core.config import DATA_DIR

from src.modules.vehicle_hub.reports.large_technical_certificate_pdf import render_large_technical_certificate_pdf

logger = logging.getLogger(__name__)

_LARGE_TP_ROOT = DATA_DIR / "vehicle_large_technical_certificates"


def certificate_pdf_path(*, tenant_id: int, vehicle_id: int) -> Path:
    return _LARGE_TP_ROOT / f"tenant_{int(tenant_id)}" / f"vehicle_{int(vehicle_id)}" / "large_technical_certificate.pdf"


def technical_certificate_generated_at(*, tenant_id: int, vehicle_id: int) -> Optional[datetime]:
    path = certificate_pdf_path(tenant_id=tenant_id, vehicle_id=vehicle_id)
    if not path.is_file():
        return None
    try:
        return datetime.utcfromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def regenerate_vehicle_large_technical_certificate_pdf(vehicle: Any) -> bytes:
    """
    Vygeneruje PDF z aktuálního stavu vozidla, uloží ho na jednu kanonickou cestu (overwrite)
    a vrátí obsah pro okamžité odeslání klientovi.
    """
    pdf = render_large_technical_certificate_pdf(vehicle)
    tenant_id = int(getattr(vehicle, "tenant_id", 0) or 0)
    vehicle_id = int(getattr(vehicle, "id", 0) or 0)
    if tenant_id <= 0 or vehicle_id <= 0:
        return pdf
    target = certificate_pdf_path(tenant_id=tenant_id, vehicle_id=vehicle_id)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf)
    except Exception as exc:
        logger.warning(
            "[LARGE_TP] uložení PDF selhalo tenant=%s vehicle_id=%s err=%s",
            tenant_id,
            vehicle_id,
            exc,
            exc_info=True,
        )
    return pdf


def try_refresh_vehicle_large_technical_certificate_disk(vehicle: Any) -> None:
    """Best-effort přegenerování a zápis na disk (bez výjimky ven)."""
    try:
        regenerate_vehicle_large_technical_certificate_pdf(vehicle)
    except Exception as exc:
        logger.warning(
            "[LARGE_TP] přegenerování selhalo vehicle_id=%s err=%s",
            getattr(vehicle, "id", None),
            exc,
            exc_info=True,
        )
