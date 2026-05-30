# Document Lifecycle — životní cyklus dokumentů

**Fáze:** C1-PREP — doplnění schváleného návrhu  
**Status:** **SCHVÁLENO** — závazné před C1.0  
**Podřízeno:** [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md) §1, §6–10, [WORKFLOW_STANDARDS.md](./WORKFLOW_STANDARDS.md)

Související:

- [DOCUMENT_PLATFORM_ARCHITECTURE.md](./DOCUMENT_PLATFORM_ARCHITECTURE.md)
- [DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md)
- [DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md)

---

## 1. Základní zákon

> **Dokument patří vozidlu. Nikdy uživateli.**

Vlastník se může měnit. Vozidlo zůstává. Historie dokumentů zůstává navázaná na `vehicle_id`.

| Povinné | Zakázané |
|---------|----------|
| `vehicle_documents` | `user_documents` |
| `GET /api/v1/vehicles/{vehicle_id}/documents` | primární klíč `customer_id` |
| Document center v detailu vozidla | samostatná „Dokumenty" sekce mimo vozidlo |

---

## 2. Kanonický model `VehicleDocument`

Jednotná metadata vrstva pro všechny typy (implementace v C1.0):

| Pole | Typ | Popis |
|------|-----|-------|
| `id` | int | Primární klíč platformy |
| `vehicle_id` | int | **Povinné.** Jediný primární owner dokumentu |
| `document_type` | enum | `service_invoice`, `service_quote`, `work_order`, … |
| `document_status` | enum | Unified lifecycle status (§4) |
| `source_type` | string | `service_invoice`, `service_work_order`, … |
| `source_id` | int | ID zdrojového záznamu (invoice_id, wo_id, …) |
| `document_number` | string | Číslo dokladu (2026-0042, WO-0312, …) |
| `created_at` | datetime | Vytvoření |
| `created_by` | int | `customers.id` — kdo vytvořil |
| `service_customer_id` | int | Servis, který dokument vystavil |
| `owner_visibility` | enum | `owner`, `service_only`, `public_verify` |
| `verification_token` | string | Public token pro `/verify/{token}` |
| `verification_code` | string | Lidsky čitelný kód (XXXX-XXXX) |
| `hash_sha256` | string | Hash finálního PDF |
| `file_path` | string | Cesta k uloženému PDF (finalized) |
| `finalized_at` | datetime | Dokončení / vystavení |
| `archived_at` | datetime | Archivace |
| `superseded_by_id` | int | Novější verze stejného typu |

**Vztah ke stávajícím modelům:** `ServiceInvoice`, `ServiceQuote`, `ServiceWorkOrder`, `ServiceIntake`, `ServiceRecord`, `VehicleReportDocument` zůstávají **zdrojovými entitami**. `VehicleDocument` je **platformní index + verify + UI metadata** nad nimi.

---

## 3. Dokumentové centrum — příprava na C2 (Vehicle Hub)

Dokumenty nejsou globální sekce aplikace. Jsou **podstrom detailu vozidla**:

```
Vozidlo
└── Dokumenty                          ← C2 tab (nativní shell)
    ├── Faktury                        ← filter: document_type=service_invoice
    ├── Nabídky                        ← filter: document_type=service_quote
    ├── Zakázkové listy                ← filter: document_type=work_order
    ├── Příjmové protokoly             ← filter: document_type=intake_protocol
    ├── Servisní zprávy                ← filter: document_type=service_record
    ├── Předávací protokoly            ← filter: document_type=handover_protocol
    └── Historie vozidla               ← filter: document_type=vehicle_history
```

### 3.1 API pro C2

| Method | Path | Popis |
|--------|------|-------|
| GET | `/api/v1/vehicles/{vehicle_id}/documents` | Všechny dokumenty vozidla |
| GET | `/api/v1/vehicles/{vehicle_id}/documents?type=service_invoice` | Filtr podle typu |
| GET | `/api/v1/vehicles/{vehicle_id}/documents/summary` | Počty per typ (KPI v hubu) |

**C1 požadavek:** Platform API a `VehicleDocument` index musí být navrženy tak, aby C2 pouze přidalo UI tab — **bez refactoru datového modelu**.

### 3.2 Kdo vidí co

| Aktér | Vidí |
|-------|------|
| Majitel vozidla | Dokumenty s `owner_visibility` ∈ {`owner`, `public_verify`} |
| Servis s přístupem | Všechny dokumenty vystavené tímto servisem + dokumenty vozidla dle grantu |
| Veřejnost | Pouze přes `verification_token` / public link |

---

## 4. Jednotný stavový systém

Všechny typy dokumentů mapují interní stavy na **6 platformních stavů**:

| Platform status | Význam | UI badge | Barva |
|-----------------|--------|----------|-------|
| `draft` | Koncept, editovatelný | KONCEPT | warning |
| `pending` | Čeká na akci (schválení, podpis, platba) | ČEKÁ | warning |
| `approved` | Schváleno (nabídka, zakázka) | SCHVÁLENO | success |
| `completed` | Dokončeno / vystaveno / platné | DOKONČENO / VYSTAVENO | success |
| `cancelled` | Zrušeno / zamítnuto | ZRUŠENO | danger |
| `archived` | Archivováno, read-only | ARCHIV | muted |

### 4.1 Mapování ze stávajících stavů

| Typ | Interní stav (dnes) | Platform status |
|-----|---------------------|-----------------|
| Faktura | `draft` | `draft` |
| Faktura | `issued` | `completed` |
| Faktura | `cancelled` | `cancelled` |
| Nabídka | `draft` | `draft` |
| Nabídka | pending approval | `pending` |
| Nabídka | `approved` | `approved` |
| Nabídka | `rejected` | `cancelled` |
| Zakázka | draft / new | `draft` |
| Zakázka | in_progress / waiting | `pending` |
| Zakázka | `completed` | `completed` |
| Zakázka | `cancelled` | `cancelled` |
| Intake | draft | `draft` |
| Intake | submitted | `completed` |
| Servisní záznam | `draft` | `draft` |
| Servisní záznam | published | `completed` |
| Historie vozidla | `valid` | `completed` |
| Historie vozidla | `superseded` | `archived` |
| Historie vozidla | `revoked` | `cancelled` |
| Předávací protokol | unsigned | `pending` |
| Předávací protokol | signed | `completed` |

**Pravidlo C1:** Renderer a UI **vždy** zobrazují platform status. Typ-specifický label jen jako subtitle (např. „K úhradě" u faktury = `pending` + payment flag).

---

## 5. Dokumentová karta — povinný obsah

Karta **není** miniatura sama o sobě. Povinná pole:

| # | Prvek | Zdroj |
|---|-------|-------|
| 1 | **Miniatura** | pdf.js render str. 1 (ne ikona PDF) |
| 2 | **Typ dokumentu** | `document_type` → label CZ |
| 3 | **Stav** | unified `document_status` badge |
| 4 | **Datum** | `created_at` nebo `finalized_at` |
| 5 | **Servis** | `service_customer_id` → název servisu |
| 6 | **Vozidlo** | brand, model, SPZ (kontext v hubu; v detailu vozidla volitelně skrýt) |
| 7 | **Akce** | viz §6 |

Wireframe: [DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md) §4.1.

---

## 6. Akce dokumentu

Každá akce musí mít definované A–E (ústava §3):

| Akce | Kdy dostupná | API / UI |
|------|--------------|----------|
| **Otevřít** | vždy (auth) | Inline preview panel, pdf.js |
| **Stáhnout** | vždy (auth) | GET `.../pdf` |
| **Sdílet** | finalized + typ podporuje | Public link / token |
| **Ověřit** | `verification_token` existuje | `/verify/{token}` |
| **Upravit** | `draft` / `pending` | existující edit endpoint |
| **Dokončit** | dle typu (issue, sign, publish) | typ-specifický |
| **Archivovat** | `completed` | PATCH status → `archived` |
| **Smazat** | pouze `draft` | DELETE + audit log |

**Zákaz:** Akce bez handleru. Sdílet u konceptu. Ověřit u draftu.

---

## 7. Náhled PDF — skutečný náhled

Audit vytkl: ikona PDF + název ≠ náhled.

| Požadavek | Implementace C1 |
|-----------|-----------------|
| Thumbnail první stránky | pdf.js → canvas → `<img>` nebo CSS background v kartě |
| Metadata vedle thumbnailu | typ, stav, datum, servis, vozidlo |
| Full preview | Inline panel — **stejný soubor** jako download |
| Fallback | Gradient + typ (ne holá ikona `.pdf`) |
| Mobil | Full-width canvas, 44px akce |

**PASS/FAIL:** Pokud karta nemá renderovanou str. 1 do 3 s po načtení → FAIL.

---

## 8. Fotodokumentace uvnitř PDF

Fotografie nejsou odkaz. Jsou **embedded sekce** v PDF.

### 8.1 Příjmový protokol — povinné sloty

| Slot | Label v PDF | Povinný |
|------|-------------|---------|
| `front` | Přední část | ano |
| `rear` | Zadní část | ano |
| `left` | Levá strana | ano |
| `right` | Pravá strana | ano |
| `interior` | Interiér | doporučeno |
| `damage` | Poškození | pokud `damage_description` |

Layout: mřížka 2×3, každý slot = náhled 120×90 px + popisek. Prázdný slot = šedý placeholder „Nepořízeno" (draft); finalized bez `front`+`rear` = **FAIL**.

### 8.2 Zakázkový list

| Slot | Label |
|------|-------|
| Příjem | Fotodokumentace příjmu (z intake) |
| Průběh | Fotky z WO (`work-orders/{id}/photos`) |
| Max | 8 náhledů / dokument, stránkování |

### 8.3 Servisní zpráva

| Slot | Label |
|------|-------|
| Před/po | Fotky z `ServiceRecord.attachments` |
| Max | 6 náhledů |

### 8.4 Předávací protokol

| Slot | Label |
|------|-------|
| Předání | Stav vozidla při předání (volitelné) |
| Max | 4 náhledy |

### 8.5 Technická pravidla (platform `photos.py`)

- JPEG embed, max 120×90 px náhled, aspect crop center
- Popisek 8 pt pod každým náhledem
- EXIF strip (GDPR)
- Zdroj: API file URL → backend fetch → embed (ne externí hyperlink)

---

## 9. Workflow operace — jednotný cyklus

Každý typ dokumentu prochází těmito operacemi (dostupnost dle typu):

```
┌──────────┐    ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐
│ Vytvoření│ →  │  Úprava  │ →  │ Dokončení │ →  │ Archivace│    │  Mazání  │
└──────────┘    └──────────┘    └───────────┘    └──────────┘    └──────────┘
                                      │                ↑
                    ┌─────────────────┼────────────────┘
                    │                 │
              ┌─────▼─────┐    ┌──────▼──────┐
              │  Sdílení  │    │  Ověření   │
              └───────────┘    └─────────────┘
```

| Operace | Popis | Audit |
|---------|-------|-------|
| Vytvoření | Nový záznam + draft PDF preview | API persist |
| Úprava | Pouze draft/pending | verze hash se mění |
| Dokončení | Issue / sign / publish → immutable PDF + verify token | hash + token |
| Archivace | Read-only, skrytí z aktivního seznamu | status archived |
| Sdílení | Public link nebo QR | token expiry |
| Ověření | `/verify/{token}` | public API |
| Mazání | Pouze draft, soft-delete + audit | GDPR log |

---

## 10. Řetězce mezi dokumenty

### 10.1 Servisní flow (hlavní)

```
Příjmový protokol (intake)
        │
        ▼
Zakázkový list (work_order)  ←── fotky z intake
        │
        ├──► Servisní zpráva (service_record)
        │           │
        │           ▼
        └──► Faktura (service_invoice)
                    │
                    ▼
            Předávací protokol (handover_protocol)
                    │
                    ▼
              Archivace (všechny typy)
                    │
                    ▼
         Historie vozidla (vehicle_history) ← agregovaný výpis
```

**Vazby v `VehicleDocument`:**

| Pole | Popis |
|------|-------|
| `parent_document_id` | Např. faktura → WO |
| `related_document_ids[]` | JSON — související doklady |

### 10.2 Nabídkový flow

```
Nabídka (service_quote) [draft]
        │
        ▼
   pending — odeslána zákazníkovi (public link)
        │
   ┌────┴────┐
   ▼         ▼
approved   cancelled
   │
   ▼
Faktura (service_invoice)  ← from-quote endpoint existuje
   │
   ▼
Archivace
```

### 10.3 Historie vozidla

```
Servisní záznamy + STK + dokumenty
        │
        ▼
Export historie (vehicle_history) [draft preview]
        │
        ▼
Finalize → verification_token + supersede prior version
        │
        ▼
archived (starší verze automaticky)
```

---

## 11. Lifecycle per typ — detail

### 11.1 Faktura

| Fáze | Status | Akce | Výstup |
|------|--------|------|--------|
| Vytvoření | draft | edit lines | draft PDF |
| Úprava | draft | PATCH lines | regenerace preview |
| Dokončení | completed | POST issue | číslo, QR platba, verify token |
| Sdílení | — | email/download | PDF zákazníkovi |
| Ověření | completed | /verify | valid |
| Archivace | archived | manual / auto po X letech | read-only |
| Mazání | draft only | DELETE | — |
| Zrušení | cancelled | POST cancel | watermark ZRUŠENO |

### 11.2 Nabídka

| Fáze | Status | Akce |
|------|--------|------|
| Vytvoření | draft | edit items |
| Odeslání | pending | share public link |
| Schválení | approved | public approve |
| Zamítnutí | cancelled | public reject |
| → Faktura | — | from-quote |

### 11.3 Zakázkový list

| Fáze | Status | Akce |
|------|--------|------|
| Vytvoření | draft | z intake nebo ručně |
| Průběh | pending | add items, photos |
| Dokončení | completed | complete WO → final PDF |
| Archivace | archived | — |

### 11.4 Příjmový protokol

| Fáze | Status | Akce |
|------|--------|------|
| Vytvoření | draft | intake kroky 1–3 |
| Fotodokumentace | draft | 6 slotů |
| Podpis | pending | customer + service sign |
| Dokončení | completed | submit intake → PDF + verify |
| → Zakázka | — | auto WO draft |

### 11.5 Servisní zpráva

| Fáze | Status | Akce |
|------|--------|------|
| Vytvoření | draft | z WO nebo ručně |
| Úprava | draft | edit description, attachments |
| Publikace | completed | publish → owner_visibility=owner |
| Ověření | completed | verify token |

### 11.6 Předávací protokol

| Fáze | Status | Akce |
|------|--------|------|
| Vytvoření | pending | z completed WO |
| Podpisy | pending | oba podpisy |
| Dokončení | completed | final PDF |
| Vazba | — | link na fakturu + WO |

### 11.7 Historie vozidla

| Fáze | Status | Akce |
|------|--------|------|
| Preview | draft | generate without finalize |
| Finalize | completed | token + hash |
| Supersede | archived | prior version |
| Revoke | cancelled | admin revoke |

---

## 12. E2E — povinný cyklus (každý typ)

Každý typ dokumentu musí mít E2E spec pokrývající:

```
1. Vytvoření (draft)
2. Úprava (změna viditelná v preview)
3. Dokončení (finalized)
4. Document card — thumbnail + metadata + stav
5. Otevřít — inline preview = download bytes
6. Stáhnout
7. Sdílet (pokud typ podporuje)
8. Ověřit — /verify valid
9. Archivace (pokud typ podporuje)
10. Reload → stav persisted
11. Odhlásit → přihlásit → stav persisted
12. Mobil 390px — karta + akce 44px
13. Mazání draftu (cleanup)
```

Soubor specifikací: [DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md) Příloha C.

---

## 13. Rozhodnutí schválená uživatelem (2026-05-30)

| # | Rozhodnutí | Status |
|---|------------|--------|
| 1 | Jedna dokumentová platforma | ✅ Schváleno |
| 2 | PDF = Preview = Tisk | ✅ Schváleno |
| 3 | Vehicle report jako vzor kvality | ✅ Schváleno |
| 4 | Document cards místo tabulek | ✅ Schváleno |
| 5 | Inline preview, ne modal v modalu | ✅ Schváleno |
| 6 | QR verify u důležitých dokumentů | ✅ Schváleno |
| 7 | Jednotný vizuální systém user + service | ✅ Schváleno |
| 8 | Pořadí C1.1 → C1.7 | ✅ Schváleno |
| 9 | Dokument = vozidlo, ne user | ✅ Schváleno (tento doc §1–2) |
| 10 | Document center v Vehicle Hub | ✅ Schváleno (§3) |
| 11 | Karta = thumbnail + metadata + akce | ✅ Schváleno (§5–6) |
| 12 | Fotky embedded v PDF | ✅ Schváleno (§8) |
| 13 | Unified status system | ✅ Schváleno (§4) |
| 14 | Skutečný PDF náhled | ✅ Schváleno (§7) |
| 15 | Lifecycle před C1.0 | ✅ Schváleno (tento dokument) |

---

## 14. Další krok

Po merge tohoto dokumentu:

1. **C1.0** — Shared Document Platform (`VehicleDocument`, registry, layout, unified status, verify router fix)
2. **C1.1** — Faktura end-to-end (nejvyšší návratnost dle auditu)

---

*Vytvořeno: 2026-05-30 — schválení C1-PREP s doplněním*
