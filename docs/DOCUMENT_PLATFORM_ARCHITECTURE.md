# Document Platform Architecture

**Fáze:** C1-PREP — Document Platform Design  
**Status:** NÁVRH KE SCHVÁLENÍ — žádná implementace  
**Závaznost:** Po schválení má prioritu nad ad hoc PDF implementací  
**Podřízeno:** [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md) §6–10, [PDF_STANDARDS.md](./PDF_STANDARDS.md), [UI_GOVERNANCE.md](./UI_GOVERNANCE.md)

Související návrhové dokumenty:

- [DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md) — layout, wireframy, komponenty
- [DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md) — specifikace 7 typů dokumentů

---

## 1. Problém

Backend umí generovat data pro faktury, nabídky, zakázky, intake, servisní záznamy a historii vozidla. **Prezentace dokumentů nesplňuje ústavu:**

| Oblast | Audit skóre | Hlavní příčina |
|--------|-------------|----------------|
| PDF výstupy | 35 % | Faktura/nabídka = textový export; chybí WO/intake PDF |
| Dokumenty / náhledy | 41 % | Tabulka + ikony místo preview karet |

Bez jednotné platformy hrozí **7 různých stylů** při paralelní implementaci.

---

## 2. Cíl platformy

Jeden render pipeline pro všechny produktové dokumenty:

```
Zdroj dat (DB) → Payload builder → Šablona (shared layout) → PDF bytes
                                                      ↓
                                            Metadata + verify token
                                                      ↓
                              Náhled v UI = stejný PDF (pdf.js / thumbnail)
                                                      ↓
                                    Tisk = identický soubor
```

**Zásada:** PDF ≠ export textu. Náhled ≠ ikona. Tisk = náhled = stažený soubor.

---

## 3. Referenční implementace (dnes)

| Soubor | Kvalita | Role v C1 |
|--------|---------|-----------|
| `reports/vehicle_report_pdf.py` | ✅ Profesionální | **Gold standard** — barvy, logo, QR, tabulky, footer |
| `reports/large_technical_certificate_pdf.py` | ✅ Profesionální | Vzor pro úřední/technický layout |
| `reports/service_invoice_pdf.py` | ❌ Text export | Nahradit platformou |
| `reports/service_quote_pdf.py` | ❌ Text export | Nahradit platformou |
| — | ❌ Chybí | WO PDF, intake PDF, handover PDF, service record PDF |

Vizuální systém: viz [DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md).

---

## 4. Architektura modulů (cílový stav)

```
src/modules/vehicle_hub/documents/
├── __init__.py
├── registry.py              # DocumentType enum, metadata, capabilities
├── payload/
│   ├── invoice.py           # ServiceInvoice → InvoiceDocumentPayload
│   ├── quote.py
│   ├── work_order.py
│   ├── intake_protocol.py
│   ├── service_record.py
│   ├── handover_protocol.py
│   └── vehicle_history.py   # wrap VehicleServiceReportPayload
├── platform/
│   ├── layout.py            # Shared header, footer, zones (from vehicle_report patterns)
│   ├── typography.py        # DejaVu, styles, formatters
│   ├── qr.py                # QR platba + verify URL
│   ├── signatures.py        # Signature blocks
│   ├── photos.py            # Photo grid embedding
│   ├── tables.py            # Line items, parts, timeline
│   └── renderer.py          # render_document_pdf(type, payload) → bytes
├── verification/
│   ├── tokens.py            # public_token, verification_code, hash
│   └── serialize.py         # API response for /verify
├── storage/
│   ├── paths.py             # DATA_DIR/documents/{type}/{vehicle_id}/{doc_id}.pdf
│   └── cache.py             # Optional thumbnail cache
└── templates/
    ├── invoice.py
    ├── quote.py
    ├── work_order.py
    ├── intake_protocol.py
    ├── service_record.py
    ├── handover_protocol.py
    └── vehicle_history.py
```

**Pravidlo:** Nový typ dokumentu = nový payload builder + template. **Nikdy** nový ad hoc `Canvas.drawString` renderer.

---

## 5. Document registry

Centralizovaný registr typů (implementace v `registry.py`):

| `document_type` | Název CZ | Verify QR | QR platba | Podpisy | Fotky | Finalizace |
|-----------------|----------|-----------|-----------|---------|-------|------------|
| `service_invoice` | Faktura | volitelně | ano (issued) | volitelně | ne | issue → immutable |
| `service_quote` | Nabídka | ano (public link) | ne | ne | ne | approve/reject |
| `work_order` | Zakázkový list | ano | ne | ano | ano | complete → PDF |
| `intake_protocol` | Příjmový protokol | ano | ne | ano | ano | submit intake |
| `service_record` | Servisní zpráva | ano | ne | ne | ano | publish record |
| `handover_protocol` | Předávací protokol | ano | ne | ano | volitelně | sign both |
| `vehicle_history` | Historie vozidla | ano | ne | ne | ano | finalize report |

Každý záznam v registru definuje:

- `payload_builder` — funkce z DB → dataclass
- `template_renderer` — funkce payload → bytes
- `api_pdf_path` — REST endpoint pattern
- `ui_surfaces` — kde se zobrazuje (service shell, user app, vehicle detail)
- `verify_strategy` — `document_verify` | `public_quote` | `vehicle_history` | `none`

---

## 6. Datový tok

### 6.1 Payload layer

Payload je **normalizovaný dataclass** nezávislý na ReportLab. Sdílené bloky:

```python
# Konceptuální — implementace až C1.0
DocumentHeader(service_logo, service_name, ico, dic, address, contact)
DocumentMeta(type, number, status, status_label, issued_at, due_at)
VehicleBlock(brand, model, plate, vin_masked, odometer_km, fuel)
CustomerBlock(name, ico, dic, address, email, phone)
VerificationBlock(verify_url, verification_code, qr_payload)
SignatureBlock(customer_signed_at, service_signed_at, signature_images)
PhotoBlock(photos: list[PhotoRef])
LineItemsBlock(lines, subtotal, tax, total, currency)
TimelineBlock(events)
FooterBlock(bank_account, legal_text, page_number)
```

Typ-specifické payloady rozšiřují base o vlastní sekce (viz [DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md)).

### 6.2 Render layer

1. `_register_fonts()` — DejaVuSans (stejně jako `vehicle_report_pdf.py`)
2. `build_document_story(payload, template)` — ReportLab platypus flowables
3. `NumberedCanvas` — footer se stránkováním (reuse z vehicle report)
4. Output: `bytes` + `content_hash_sha256`

### 6.3 Persistence layer

| Varianta | Kdy | Cesta |
|----------|-----|-------|
| **On-demand** | Draft / koncept | Generovat při každém GET, neukládat |
| **Stored** | Issued / finalized | `DATA_DIR/documents/{type}/{vehicle_id}/{id}.pdf` |
| **Versioned** | Vehicle history | `VehicleReportDocument` (existující model) |

Metadata tabulka (rozšíření nebo nová `VehicleDocument` — rozhodnutí v C1.0):

- `id`, `vehicle_id`, `document_type`, `source_id` (invoice_id, wo_id, …)
- `status`, `file_path`, `hash_sha256`, `public_token`, `verification_code`
- `thumbnail_path` (optional), `finalized_at`, `issued_by_service_id`

---

## 7. API design

### 7.1 Unified document API (nové — C1.0)

| Method | Path | Popis |
|--------|------|-------|
| GET | `/api/v1/vehicles/{vehicle_id}/documents` | Seznam všech dokumentů vozidla (unified metadata) |
| GET | `/api/v1/vehicles/{vehicle_id}/documents/{document_id}` | Detail + actions |
| GET | `/api/v1/vehicles/{document_id}/pdf` | PDF blob (auth) |
| GET | `/api/v1/vehicles/{document_id}/preview` | Metadata pro UI kartu (thumbnail URL, status, actions) |

Alternativa: zachovat existující per-type endpointy a přidat **facade** v documents hub — méně breaking, doporučeno pro C1.

### 7.2 Existující endpointy (zachovat, sjednotit výstup)

| Typ | Existující PDF endpoint | Akce C1 |
|-----|-------------------------|---------|
| Faktura | `GET /api/service/invoices/{id}/pdf` | Swap renderer |
| Faktura (user) | `GET /api/v1/vehicles/{vid}/invoices/{id}/pdf` | Swap renderer |
| Nabídka | `GET /api/service/quotes/{id}/pdf` | Swap renderer |
| Historie | `GET /api/v1/vehicles/{id}/report.pdf` | Align layout to platform |
| Historie (alias) | `GET /api/v1/vehicles/{id}/pdf` | Stejný renderer |
| Velký TP | `GET .../large-technical-certificate.pdf` | Mimo C1 scope (už OK) |
| WO | — | **Nový** `GET /api/service/work-orders/{id}/pdf` |
| Intake | — | **Nový** `GET /api/v1/service/intake/{id}/pdf` |
| Servisní záznam | attachments only | **Nový** `GET /api/v1/vehicles/{vid}/records/{id}/report.pdf` |
| Předávací | — | **Nový** `POST/GET .../handover-protocol` |

### 7.3 Hub API (existující — rozšířit)

`GET /api/v1/vehicles/documents/hub` — dnes agreguje attachments, reports, tachometer, large TP.

**C1 cíl:** Hub vrací unified `DocumentCardItem[]` s:

- `document_type`, `document_id`, `title`, `status`, `status_label`
- `vehicle_id`, `vehicle_label`, `issued_at`
- `preview_url` (thumbnail nebo pdf first-page endpoint)
- `pdf_url`, `verify_url`, `actions[]`

### 7.4 Verify / public API

| Flow | Endpoint | Stav |
|------|----------|------|
| Document verify | `GET /api/public/documents/verify/{token}` | ⚠️ Router existuje, **ověřit registraci v bootstrap** |
| Verify by code | `POST /api/public/documents/verify-by-code` | Stejně |
| Verify page | `GET /verify/{token}` → `verify.html` | OK |
| Public quote | `GET /api/public/quote/{token}` | OK — jiný token model |
| Vehicle history QR | `GET /api/public/vehicle-history/{token}` | OK — separátní od document verify |

**C1 rozhodnutí:** Všechny finalizované dokumenty s verify používají **jednotný** `DocumentVerification` model (rozšířit `VehicleReportDocument` nebo abstraktní `VerifiedDocument`).

Env: `PUBLIC_VERIFY_BASE_URL` → QR payload.

### 7.5 Thumbnail API (nové — C1.0)

| Method | Path | Popis |
|--------|------|-------|
| GET | `/api/v1/documents/{id}/thumbnail.png` | Server-side first page (optional) |
| — | Client-side | pdf.js render page 1 do canvas (preferováno pro MVP C1) |

**Doporučení C1:** Client-side thumbnail z pdf.js při prvním otevření → cache v `sessionStorage` / IndexedDB. Server thumbnail až při performance potřebě.

---

## 8. FakturyWeb integrace

Existující paralelní cesta: `fakturyweb_pdf_url` po exportu do FakturyWeb.

| Strategie | Popis |
|-----------|-------|
| **A — Primární interní PDF** | Platform renderer = default; FakturyWeb = optional export pro účetnictví |
| **B — FakturyWeb jako PDF** | Pouze pokud sync proběhl — jinak platform PDF |

**Schválený návrh:** Strategie **A**. UI náhled vždy ukazuje **platform PDF**. FakturyWeb PDF = sekundární odkaz „Účetní verze (FakturyWeb)“ pokud existuje.

---

## 9. UI integrace (bez implementace — mapa)

| Surface | Soubor | Dnešní stav | Cíl C1 |
|---------|--------|-------------|--------|
| User documents | `user-app-next.js` | Tabulka + ikony | `uapp-doc-card` grid |
| User vehicle detail → Dokumenty | `user-app-next.js` | Placeholder → legacy | Nativní sekce (C2), karty z C1 |
| Legacy hub | `index.html` | pdf.js modal, funguje | Deprecate po C2 |
| Service invoices | `service-shell.js` | `openAuthenticatedPdf` new tab | Inline preview panel + karta |
| Service quotes | `service-shell.js` | PDF new tab | Karta + share |
| Service WO | `service-shell.js` | Chybí PDF | Tlačítko „Zakázkový list PDF“ |
| Service intake | `service-shell.js` | Wizard bez PDF | „Protokol PDF“ po kroku 4 |
| Workspace docs | `service-shell.js` | Text preview ingest | Oddělený ingest flow; produktové PDF = platform |

**Pravidlo UI:** Jeden preview mechanismus — **inline panel** nebo **full-width drawer**, ne modal v modalu (ústava §5).

Komponenty: viz [DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md) § Document Card, § PDF Preview Panel.

---

## 10. Bezpečnost a GDPR

| Požadavek | Implementace |
|-----------|--------------|
| Auth na PDF | JWT / session; servis vidí jen svá vozidla; user jen svá |
| Maskování VIN ve verify | `vehicle_vin_masked` (existující pattern) |
| Immutable issued docs | Hash + status; draft regenerovatelný |
| Audit trail | `finalized_at`, `finalized_by`, `hash_sha256` |
| Public token expiry | Konfigurovatelné per document type |
| PII v PDF | Minimální nutná sada; faktura = plné fakturační údaje |

---

## 11. Testovací strategie

| Vrstva | Co testovat |
|--------|-------------|
| API unit | Payload builders — pole, formát, edge cases |
| PDF integration | Bytes non-empty, obsahuje text marker (číslo dokladu), hash stable |
| Visual regression | Snapshot první stránky PDF (per template) — `tests/api/` |
| E2E | Create → preview card → open → download → verify URL (per type) |
| Mobile E2E | 390px — karta, preview, akce 44px |

E2E scénáře per typ: [DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md).

---

## 12. Migrační plán (implementační fáze po schválení)

| Fáze | Rozsah | Závislost |
|------|--------|-----------|
| **C1.0** | Platform module + layout + registry + verify fix | Schválení tohoto balíku |
| **C1.1** | Faktura end-to-end (PDF + karta + E2E) | C1.0 |
| **C1.2** | Nabídka end-to-end | C1.0 |
| **C1.3** | Zakázkový list | C1.0 |
| **C1.4** | Příjmový protokol | C1.0 |
| **C1.5** | Servisní zpráva | C1.0 |
| **C1.6** | Předávací protokol | C1.0 + WO flow |
| **C1.7** | Historie vozidla — align to platform | C1.0 |
| **C1.8** | Hub unified cards + deprecate legacy preview | C1.1–C1.7 |

**C1 PASS kritérium:** Žádný produktový dokument ≠ text export; každý typ má preview kartu; PDF = náhled = tisk.

---

## 13. Otevřené body ke schválení

| # | Otázka | Doporučení |
|---|--------|------------|
| 1 | Nová tabulka `VehicleDocument` vs rozšířit `VehicleReportDocument` | Abstraktní `VehicleDocument` pro všechny typy |
| 2 | Server thumbnail vs client pdf.js | Client first; server optional |
| 3 | Podpis — canvas capture vs upload | Canvas v intake/WO UI → PNG v payload |
| 4 | Logo servisu — zdroj | `Customer` (service) logo field nebo default TooZ |
| 5 | `public_documents` router v bootstrap | **P0 fix** v C1.0 — registrace routeru |

---

## 14. Schvalovací checklist

- [ ] Architektura modulů schválena
- [ ] Unified vs per-type API strategie schválena
- [ ] FakturyWeb strategie A schválena
- [ ] Verify model sjednocen
- [ ] UI preview = inline panel (ne nested modal)
- [ ] Pořadí C1.1–C1.7 schváleno
- [ ] Vizuální systém schválen ([DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md))
- [ ] Všechny typy specifikovány ([DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md))

---

*Vytvořeno: 2026-05-30 — C1-PREP Document Platform Design*  
*Audit reference: GOVERNANCE_AUDIT_2026-05-29.md (PDF 35 %, Dokumenty 41 %)*
