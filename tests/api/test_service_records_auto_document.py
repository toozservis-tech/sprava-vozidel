"""
Testy pro automatické vytvoření servisního záznamu z dokladu.
"""
from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
import requests

from src.modules.vehicle_hub.routers_v1.service_workspace import _parse_document_payload
from src.modules.vehicle_hub.routers_v1 import service_records as service_records_router


def _create_vehicle(api_url: str, headers: dict[str, str]) -> int:
    response = requests.post(
        f"{api_url}/api/v1/vehicles",
        headers=headers,
        json={
            "nickname": "Test Auto Doc",
            "brand": "Skoda",
            "model": "Octavia",
            "year": 2021,
            "plate": f"TEST{uuid4().hex[:4].upper()}",
            "stk_valid_until": (date.today() + timedelta(days=365)).isoformat(),
        },
        timeout=8,
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


def test_auto_create_service_record_from_document(api_url, authenticated_headers, cleanup_test_data):
    if not authenticated_headers:
        pytest.skip("No auth token available")

    vehicle_id = _create_vehicle(api_url, authenticated_headers)
    invoice_text = (
        "Faktura č.: FV-2026-100\n"
        "Dodavatel: Auto Test Servis s.r.o.\n"
        "Datum vystavení: 01.03.2026\n"
        "Výměna oleje 1 ks 1200 Kč\n"
        "DPH 21% 252 Kč\n"
        "Celkem k úhradě 1452 Kč\n"
        "Stav tachometru: 154320 km\n"
    )
    payload = {
        "source_type": "invoice",
        "file_name": "faktura.txt",
        "file_mime_type": "text/plain",
        "file_content_base64": base64.b64encode(invoice_text.encode("utf-8")).decode("ascii"),
        "manual_note": "Automatický import",
        "fallback_category": "OLEJ",
    }

    response = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/records/auto-from-document",
        headers=authenticated_headers,
        json=payload,
        timeout=10,
    )
    if response.status_code == 507 and "Permission denied" in response.text:
        pytest.skip("Runtime attachment directory is not writable for this local test run.")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("processing_status") in {"processed", "needs_review"}
    assert isinstance(body.get("parse_confidence"), (float, int))
    record = body.get("record") or {}
    assert int(record.get("vehicle_id")) == vehicle_id
    assert str(record.get("description") or "").strip() != ""

    parsed_data = body.get("parsed_data") or {}
    assert parsed_data.get("document_number")
    # parser by měl vytěžit cenu z řádku "Celkem k úhradě"
    assert float(record.get("price")) == 1452.0


def test_auto_create_includes_downloadable_attachment(api_url, authenticated_headers, cleanup_test_data):
    if not authenticated_headers:
        pytest.skip("No auth token available")

    vehicle_id = _create_vehicle(api_url, authenticated_headers)
    invoice_text = (
        "Faktura č.: FV-2026-101\n"
        "Dodavatel: Auto Test Servis s.r.o.\n"
        "Datum vystavení: 02.03.2026\n"
        "Položka: Servis klimatizace 2200 Kč\n"
        "Celkem k úhradě 2200 Kč\n"
        "Stav tachometru: 160100 km\n"
    )
    payload = {
        "source_type": "invoice",
        "file_name": "faktura_2.txt",
        "file_mime_type": "text/plain",
        "file_content_base64": base64.b64encode(invoice_text.encode("utf-8")).decode("ascii"),
        "fallback_category": "KLIMATIZACE",
    }

    create_response = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/records/auto-from-document",
        headers=authenticated_headers,
        json=payload,
        timeout=10,
    )
    if create_response.status_code == 507 and "Permission denied" in create_response.text:
        pytest.skip("Runtime attachment directory is not writable for this local test run.")
    assert create_response.status_code == 200, create_response.text
    body = create_response.json()
    record = body.get("record") or {}
    attachments_raw = str(record.get("attachments") or "[]")
    attachments = json.loads(attachments_raw)
    assert isinstance(attachments, list) and attachments, attachments_raw

    first_attachment = attachments[0] or {}
    download_url = str(first_attachment.get("download_url") or "").strip()
    assert download_url.startswith("/api/v1/vehicles/"), download_url

    download_response = requests.get(
        f"{api_url}{download_url}",
        headers=authenticated_headers,
        timeout=10,
    )
    assert download_response.status_code == 200, download_response.text
    disposition = str(download_response.headers.get("content-disposition") or "").lower()
    assert "inline" in disposition
    assert download_response.content, "Attachment download is empty"
    assert b"Faktura" in download_response.content


def test_document_prefill_returns_service_report_fields(api_url, authenticated_headers, cleanup_test_data):
    if not authenticated_headers:
        pytest.skip("No auth token available")

    vehicle_id = _create_vehicle(api_url, authenticated_headers)
    invoice_text = (
        "Faktura č.: 20260008\n"
        "Dodavatel: Tooz Servis s.r.o.\n"
        "Odběratel: Tomáš Zachurčok\n"
        "Gorkého 2351/19a, 56802 Svitavy, IČO: 87854716\n"
        "Položka: Přezutí pneu 1 ks 2500 Kč\n"
        "Položka: Vyvážení kol 1 ks 1800 Kč\n"
        "Celkem k úhradě 4300 Kč\n"
        "Stav tachometru: 163450 km\n"
    )
    payload = {
        "source_type": "invoice",
        "file_name": "faktura_prefill.txt",
        "file_mime_type": "text/plain",
        "file_content_base64": base64.b64encode(invoice_text.encode("utf-8")).decode("ascii"),
    }

    response = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/records/document-prefill",
        headers=authenticated_headers,
        json=payload,
        timeout=10,
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body.get("processing_status") in {"processed", "needs_review"}
    prefill = body.get("prefill") or {}
    report = prefill.get("service_report") or {}
    assert str(report.get("supplier_name") or "").strip() != ""
    assert str(report.get("customer_name") or "").strip() != ""
    assert float(prefill.get("price")) == 4300.0
    assert int(prefill.get("mileage")) == 163450

    items = report.get("items") or []
    assert any("přezut" in str(item.get("name", "")).lower() or "prezut" in str(item.get("name", "")).lower() for item in items)
    # Adresa/IČO se nesmí dostat jako servisní položka.
    assert not any("ičo" in str(item.get("name", "")).lower() or "ico" in str(item.get("name", "")).lower() for item in items)


def test_document_parser_ignores_address_dates_and_summary_lines():
    extracted_like_pdf_text = (
        "DAŇOVÝ DOKLAD FAKTURA 20260008\n"
        "ToozServis Auto/Pneu\n"
        "Tomáš Zachurčok\n"
        "Gorkého 2351/19a\n"
        "56802 Svitavy\n"
        "IČO: 87854716\n"
        "Forma úhrady: peněžní převod Variabilní symbol: 20260008\n"
        "Odběratel\n"
        "IZOKONT s.r.o.\n"
        "Datum vystavení Datum zdanitelného plnění Datum splatnosti\n"
        "20.2.2026 20.2.2026 25.2.2026\n"
        "Popis položky Množství MJ Cena za MJ Celková částka\n"
        "geometrie 1 KS 1 200,00 1 200,00\n"
        "vyvážení pneu 1 KS 600,00 600,00\n"
        "práce přední a zadní náprava 10 H 650,00 6 500,00\n"
        "Celková částka: 8 300,00 Kč\n"
        "Zbývá uhradit: 8 300,00 Kč\n"
    )
    parsed = _parse_document_payload(
        source_type="invoice",
        extracted_text=extracted_like_pdf_text,
        manual_text=None,
        manual_note=None,
        extraction_engine="text",
        extraction_warning=None,
    )
    items = parsed.get("items") or []

    assert len(items) == 3
    names = [str(item.get("name") or "").lower() for item in items]
    assert any("geometrie" in name for name in names)
    assert any("vyvážen" in name or "vyvazen" in name for name in names)
    assert any("náprava" in name or "naprava" in name for name in names)

    assert not any("gorkého" in name or "gorkeho" in name for name in names)
    assert not any("20.2.2026" in name for name in names)
    assert not any("celková částka" in name or "celkova castka" in name for name in names)
    assert not any("zbývá uhradit" in name or "zbyva uhradit" in name for name in names)


def test_document_parser_extracts_supplier_company_contact_and_technician():
    extracted_like_pdf_text = (
        "DAŇOVÝ DOKLAD FAKTURA 20260008\n"
        "ToozServis Auto/Pneu\n"
        "Tomáš Zachurčok\n"
        "Gorkého 2351/19a\n"
        "56802 Svitavy\n"
        "IČO: 87854716\n"
        "EMAIL: info@toozservis.cz\n"
        "WEB: www.toozservis.cz\n"
        "Odběratel\n"
        "IZOKONT s.r.o.\n"
        "Datum vystavení Datum zdanitelného plnění Datum splatnosti\n"
        "20.2.2026 20.2.2026 25.2.2026\n"
        "servis přední a zadní nápravy VW MULTIVAN\n"
        "Popis položky Množství MJ Cena za MJ Celková částka\n"
        "geometrie 1 KS 1 200,00 1 200,00\n"
        "vyvážení pneu 1 KS 600,00 600,00\n"
        "práce přední a zadní náprava 10 H 650,00 6 500,00\n"
        "Vyhotovil: Tomáš Zachurčok\n"
    )
    parsed = _parse_document_payload(
        source_type="invoice",
        extracted_text=extracted_like_pdf_text,
        manual_text=None,
        manual_note=None,
        extraction_engine="text",
        extraction_warning=None,
    )
    assert "toozservis" in str(parsed.get("supplier_name") or "").lower()
    assert str(parsed.get("supplier_email") or "").lower() == "info@toozservis.cz"
    assert str(parsed.get("supplier_website") or "").lower().startswith("https://www.toozservis.cz")
    assert str(parsed.get("service_link") or "").lower().startswith("https://www.toozservis.cz")
    assert "servis přední a zadní nápravy" in str(parsed.get("service_summary") or "").lower()
    assert str(parsed.get("technician_name") or "").lower().startswith("tomáš zachurčok")
    assert str(parsed.get("technician_initials") or "").upper() == "TZ"


def test_record_detail_refreshes_stale_parsed_summary():
    invoice_text = (
        "DAŇOVÝ DOKLAD FAKTURA 20260008\n"
        "Gorkého 2351/19a\n"
        "Datum vystavení Datum zdanitelného plnění Datum splatnosti\n"
        "20.2.2026 20.2.2026 25.2.2026\n"
        "Popis položky Množství MJ Cena za MJ Celková částka\n"
        "geometrie 1 KS 1 200,00 1 200,00\n"
        "vyvážení pneu 1 KS 600,00 600,00\n"
        "práce přední a zadní náprava 10 H 650,00 6 500,00\n"
        "Celková částka: 8 300,00 Kč\n"
        "Zbývá uhradit: 8 300,00 Kč\n"
    )
    target_dir = service_records_router.SERVICE_RECORD_ATTACHMENTS_DIR / "tenant_1" / "vehicle_9999"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"stale_summary_{uuid4().hex[:8]}.txt"
    target_file.write_text(invoice_text, encoding="utf-8")

    stale_attachments = [
        {
            "kind": "user_document",
            "file_name": "stale_summary_invoice.txt",
            "mime_type": "text/plain",
            "file_size": target_file.stat().st_size,
            "storage_key": str(target_file.relative_to(service_records_router.SERVICE_RECORD_ATTACHMENTS_DIR)).replace("\\", "/"),
            "download_url": "/api/v1/vehicles/9999/records/attachments/download?key=dummy",
            "source_type": "invoice",
            "parsed_summary": {
                "source_type": "invoice",
                "document_number": "20260008",
                "currency": "CZK",
                "total_with_vat": 8300.0,
                "items": [
                    {"name": "Gorkého 2351/19a", "total_price": 19.0, "currency": "CZK"},
                    {"name": "20.2.2026 20.2.2026 25.2.2026", "total_price": 2026.0, "currency": "CZK"},
                ],
            },
        }
    ]
    record = type("RecordStub", (), {})()
    record.attachments = json.dumps(stale_attachments, ensure_ascii=False)
    record.description = "Import faktury 20260008: Gorkého 2351/19a, 20.2.2026 20.2.2026 25.2.2026"

    try:
        changed = service_records_router._refresh_record_attachments_summary(record)
        assert changed is True

        attachments = json.loads(record.attachments or "[]")
        summary = attachments[0].get("parsed_summary") or {}
        items = summary.get("items") or []
        names = [str(item.get("name") or "").lower() for item in items]

        assert len(items) == 3
        assert any("geometrie" in name for name in names)
        assert any("vyvážen" in name or "vyvazen" in name for name in names)
        assert any("náprava" in name or "naprava" in name for name in names)
        assert not any("gorkého" in name or "gorkeho" in name for name in names)
        assert not any("20.2.2026" in name for name in names)
    finally:
        target_file.unlink(missing_ok=True)
