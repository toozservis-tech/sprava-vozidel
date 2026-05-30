# Document Types Specification

**Fáze:** C1-PREP — Document Platform Design  
**Status:** **SCHVÁLENO** (2026-05-30)  
**Podřízeno:** [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md) §7–10, [PDF_STANDARDS.md](./PDF_STANDARDS.md)

Související: [DOCUMENT_PLATFORM_ARCHITECTURE.md](./DOCUMENT_PLATFORM_ARCHITECTURE.md), [DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md), [DOCUMENT_LIFECYCLE.md](./DOCUMENT_LIFECYCLE.md)

---

## Společná struktura specifikace

Každý typ dokumentu níže obsahuje:

1. Wireframe (stránka 1 PDF)
2. Sekce dokumentu a povinná pole
3. Zdroj dat (modely, pole)
4. API (existující + plánované)
5. PDF layout
6. Preview layout (UI karta + panel)
7. Mobile layout
8. E2E scénář

Master layout: [DOCUMENT_VISUAL_SYSTEM.md](./DOCUMENT_VISUAL_SYSTEM.md) Zone A–J.

---

# 1. Faktura (`service_invoice`)

## 1.1 Wireframe — PDF stránka 1

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [LOGO]  Autoservis Novák s.r.o.                    ┌─────────────────┐   │
│         IČO 12345678 · DIČ CZ12345678              │   VYSTAVENO     │   │
│         Hlavní 1, Praha                            │   2026-0042     │   │
│                                                    │   28.05.2026    │   │
│                                                    └─────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│  FAKTURA — daňový doklad                                                   │
│  Variabilní symbol: 20260042    Konstantní: —    Forma úhrady: převod    │
├──────────────────────────────────────────────────────────────────────────┤
│  ODBĚRATEL                          │  VOZIDLO                           │
│  Jan Novák                          │  Škoda Octavia 2.0 TDI             │
│  Nová 5, Brno                       │  SPZ: 1AB 2345                     │
│  jan@email.cz                       │  VIN: TMB***7890                   │
├──────────────────────────────────────────────────────────────────────────┤
│  Popis                    │ MJ │ Množ. │ Cena    │ DPH % │ Celkem         │
│  Výměna motorového oleje  │ ks │ 1     │ 890,00  │ 21    │ 890,00 Kč      │
│  Olej 5W-30               │ l  │ 4,5   │ 120,00  │ 21    │ 540,00 Kč      │
├──────────────────────────────────────────────────────────────────────────┤
│                                    Mezisoučet bez DPH:    1 347,11 Kč    │
│                                    DPH:                     282,89 Kč    │
│                                    CELKEM K ÚHRADĚ:       1 630,00 Kč    │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────────┐  QR platba · SPD                                           │
│  │ QR PAY │  Ověření: /verify/{token}  Kód: XXXX-XXXX                 │
│  └────────┘  Splatnost: 11.06.2026                                       │
├──────────────────────────────────────────────────────────────────────────┤
│  Účet: 123456789/0100 · IBAN · SWIFT    │  Vystavil: J. Novák, servis   │
│  Strana 1/1 · hash abc123…              │  Razítko / podpis servisu     │
└──────────────────────────────────────────────────────────────────────────┘
```

## 1.2 Sekce a povinná pole

| Sekce | Pole | Povinné |
|-------|------|---------|
| Header | logo, název servisu, IČO, DIČ, adresa | ano |
| Meta | číslo faktury, stav, datum vystavení, splatnost | ano |
| Platební | variabilní symbol, forma úhrady, QR platba (issued) | ano (issued) |
| Odběratel | jméno/firma, adresa, IČO (B2B) | ano |
| Vozidlo | značka, model, SPZ, VIN | ano (pokud `vehicle_id`) |
| Položky | popis, množství, MJ, cena, DPH %, řádkový total | ano |
| Souhrn | mezisoučet, DPH, celkem | ano |
| Footer | bankovní účet, kontakt | ano |
| Verify | QR verify URL, kód | doporučeno |

## 1.3 Zdroj dat

| Model | Pole |
|-------|------|
| `ServiceInvoice` | `invoice_number`, `status`, `issued_at`, `due_at`, `subtotal`, `tax_total`, `total`, `currency`, `notes`, `extra_json`, `vehicle_id`, `customer_id`, `work_order_id` |
| `ServiceInvoiceLine` | `description`, `quantity`, `unit`, `unit_price`, `tax_rate`, `line_total`, `sort_order` |
| `Customer` (servis) | `name`, `ico`, `dic`, adresa, logo |
| `Customer` (odběratel) | `name`, `ico`, adresa, email |
| `VehicleModel` | `brand`, `model`, `plate`, `vin` |
| `extra_json` | `payment_method`, `variable_symbol`, `order_number`, bank account |

**Payload builder (plán):** `documents/payload/invoice.py` ← rozšířit `_pdf_payload()` ze `service_invoices.py`

## 1.4 API

| Method | Path | Stav |
|--------|------|------|
| GET | `/api/service/invoices/{id}/pdf` | existuje — swap renderer |
| GET | `/api/v1/vehicles/{vid}/invoices/{id}/pdf` | existuje — swap renderer |
| POST | `/api/service/invoices/{id}/issue` | existuje |
| GET | `/api/v1/vehicles/documents/hub` | rozšířit o invoice cards |

## 1.5 PDF layout

Zones: A (header+status) → B (title+VS) → C (customer+vehicle) → E (line table) → G (totals) → H (QR platba + verify) → J (footer).

Draft: watermark „KONCEPT — neplatný doklad".

## 1.6 Preview layout (UI)

**Karta:** thumbnail, „FAKTURA", status badge, číslo, datum, částka, vozidlo.  
**Panel:** pdf.js full PDF. Akce: Otevřít, Stáhnout, Ověřit (issued), Sdílet (ne — interní).

**Umístění:** Service → Faktury, WO billing panel, Vehicle detail → Faktury (C2).

## 1.7 Mobile layout

Karta stack; preview full-screen drawer; primary = Stáhnout / Otevřít.

## 1.8 E2E scénář

```
service-shell-invoice-pdf-platform.spec.ts
1. Přihlásit servis
2. Vytvořit fakturu z WO (draft)
3. Náhled draft — badge KONCEPT, watermark v PDF
4. Vystavit fakturu (issue)
5. Document card — thumbnail visible, status VYSTAVENO
6. Otevřít preview — pdf.js canvas, text „2026-0042" visible
7. Stáhnout PDF — soubor > 10KB, obsahuje SPZ
8. Ověřit — /verify/{token} returns valid
9. Reload, odhlásit, přihlásit — stav persisted
10. Mobil 390px — karta + akce 44px
```

---

# 2. Nabídka (`service_quote`)

## 2.1 Wireframe — PDF stránka 1

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [LOGO]  Autoservis Novák                           ┌─────────────────┐   │
│                                                    │   K ODSOUHL.    │   │
│                                                    │   CN-2026-018   │   │
│                                                    │   Platná do:    │   │
│                                                    │   11.06.2026    │   │
│                                                    └─────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│  CENOVÁ NABÍDKA                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  ZÁKAZNÍK                           │  VOZIDLO                           │
│  Jan Novák                          │  Škoda Octavia · 1AB 2345          │
├──────────────────────────────────────────────────────────────────────────┤
│  Položka / popis              │ Hod │ Sazba     │ DPH │ Celkem           │
│  Diagnostika                  │ 1   │ 990,00    │ 21% │ 990,00 Kč        │
│  Výměna brzd                  │ 2h  │ 850/h     │ 21% │ 1 700,00 Kč      │
│  Materiál — destičky          │ 1   │ 2 400,00  │ 21% │ 2 400,00 Kč      │
├──────────────────────────────────────────────────────────────────────────┤
│  Odhad celkem: 5 090,00 Kč · Práce: 2h · Materiál: 2 400,00 Kč          │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────────┐  Schválení: /public-quote.html?token=…                       │
│  │ QR     │  Ověření: /verify/{token}                                     │
│  └────────┘                                                              │
├──────────────────────────────────────────────────────────────────────────┤
│  Poznámka: Cena orientační do dokončení diagnostiky.                       │
└──────────────────────────────────────────────────────────────────────────┘
```

## 2.2 Sekce a povinná pole

| Sekce | Pole | Povinné |
|-------|------|---------|
| Header | logo, servis | ano |
| Meta | číslo nabídky, stav, platnost do | ano |
| Zákazník + vozidlo | jméno, SPZ, VIN | ano |
| Položky | `items_json` + labor | ano |
| Souhrn | total, labor_hours, labor_rate | ano |
| QR | public approve link + verify | ano |
| Poznámky | podmínky | doporučeno |

## 2.3 Zdroj dat

| Model | Pole |
|-------|------|
| `ServiceQuote` | `items_json`, `labor_hours`, `labor_rate`, `total_price`, `status`, `vehicle_id`, `customer_id`, `work_order_id` |
| `ServiceQuoteAccessToken` | `token`, `expires_at` |
| `VehicleModel`, `Customer` | standardní |

**Payload builder:** `documents/payload/quote.py` ← `service_dashboard.py` quote PDF call

## 2.4 API

| Method | Path | Stav |
|--------|------|------|
| GET | `/api/service/quotes/{id}/pdf` | existuje — swap renderer |
| GET | `/api/public/quote/{token}` | existuje |
| POST | `/api/public/quote/{token}/approve` | existuje |

## 2.5–2.7 Layout

Stejný card/panel pattern jako faktura. Status: K ODSOUHLASENÍ / SCHVÁLENO / ZAMÍTNUTO / EXPIROVÁNO.

Public link akce na kartě servisu: „Sdílet s zákazníkem".

## 2.8 E2E scénář

```
service-shell-quote-pdf-platform.spec.ts
1. Vytvořit nabídku z WO
2. Preview card + PDF obsahuje CN- číslo
3. Sdílet public link
4. Anonymní public-quote.html — zobrazí stejný layout
5. Schválit nabídku → status SCHVÁLENO v PDF/card
6. Verify URL valid
7. Mobil 390px
```

---

# 3. Zakázkový list (`work_order`)

## 3.1 Wireframe — PDF stránka 1

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [LOGO]  Autoservis Novák                           ┌─────────────────┐   │
│                                                    │  PROBÍHÁ        │   │
│                                                    │  WO-2026-0312   │   │
│                                                    └─────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│  ZAKÁZKOVÝ LIST                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│  VOZIDLO                            │  ZAKÁZKA                           │
│  Škoda Octavia · 1AB 2345           │  Příjem: 28.05.2026 09:15          │
│  VIN: TMB***7890 · 142 350 km       │  Plán dokončení: 29.05.2026        │
│  Palivo: nafta · 3/4 nádrž          │  Technik: P. Svoboda                 │
├──────────────────────────────────────────────────────────────────────────┤
│  ● Příjem 09:15  →  ● Schváleno 09:30  →  ● Práce 10:00  →  ○ Předání   │
├──────────────────────────────────────────────────────────────────────────┤
│  POŽADAVEK ZÁKAZNÍKA                                                     │
│  „Prasklina na čelním skle, kontrola brzd"                               │
├──────────────────────────────────────────────────────────────────────────┤
│  PRÁCE A DÍLY                                                            │
│  Typ     │ Název              │ Množ. │ MJ │ Mechanik │ Stav             │
│  práce   │ Diagnostika podvozku │ 1     │ ks │ Svoboda  │ hotovo           │
│  díl     │ Destičky přední      │ 1     │ sada│ —       │ objednáno        │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐  Fotodokumentace příjmu                    │
├──────────────────────────────────────────────────────────────────────────┤
│  Podpis zákazníka _____________    Podpis servisu _____________          │
│  ┌────────┐  Ověření: /verify/{token}                                     │
│  │ QR     │                                                              │
│  └────────┘                                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

## 3.2 Sekce a povinná pole

| Sekce | Pole (§8 ústavy) |
|-------|------------------|
| Header | logo, číslo zakázky, **stav** |
| Vozidlo | VIN, SPZ, km, palivo |
| Termíny | datum příjmu, plán/ skutečné dokončení |
| Timeline | fáze zakázky |
| Požadavek | customer request |
| Práce + díly | `ServiceWorkOrderItem` |
| Fotky | WO photos |
| Podpisy | zákazník + servis |
| QR verify | ano |

## 3.3 Zdroj dat

| Model | Pole |
|-------|------|
| `ServiceWorkOrder` | `title`, `description`, `status`, `due_date`, `approved_at`, `started_at`, `completed_at`, `source_intake_id`, `technician_id`, `vehicle_id` |
| `ServiceWorkOrderItem` | `item_type`, `name`, `quantity`, `unit`, `mechanic_id`, prices |
| `ServiceIntake` | km, palivo, customer_request (via source) |
| Photos API | `/api/service/work-orders/{id}/photos` |

**Payload builder:** `documents/payload/work_order.py` — **nový**

## 3.4 API

| Method | Path | Stav |
|--------|------|------|
| GET | `/api/service/work-orders/{id}/pdf` | **nový C1.3** |
| GET | `/api/service/work-orders/{id}` | existuje |

## 3.5–3.7 Layout

**Karta:** typ ZAKÁZKOVÝ LIST, stav WO, číslo, vozidlo, datum příjmu.  
**Umístění:** WO detail (completion panel akce „Tisk zakázkového listu"), Vehicle detail → Zakázky (C2).

## 3.8 E2E scénář

```
service-shell-work-order-pdf.spec.ts
1. Intake → WO
2. Přidat položky + fotky
3. Generovat PDF — obsahuje WO- číslo, SPZ, položku
4. Document card v WO detail
5. Preview = download binary match
6. Complete WO → PDF stav DOKONČENO
7. Mobil 390px
```

---

# 4. Příjmový protokol (`intake_protocol`)

## 4.1 Wireframe — PDF stránka 1

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [LOGO]  Autoservis Novák                           ┌─────────────────┐   │
│                                                    │  PŘIJATO        │   │
│                                                    │  INT-2026-0088  │   │
│                                                    └─────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│  PROTOKOL O PŘÍJMU VOZIDLA                                               │
├──────────────────────────────────────────────────────────────────────────┤
│  VOZIDLO                            │  PŘÍJEM                            │
│  Škoda Octavia · 1AB 2345           │  28.05.2026 09:15                    │
│  VIN: TMB***7890                    │  Přijal: recepce                     │
│  Stav km: 142 350                   │  Režim: propojeno s majitelem        │
│  Palivo: nafta · hladina OK         │                                      │
├──────────────────────────────────────────────────────────────────────────┤
│  STAV VOZIDLA / POŠKOZENÍ                                                │
│  Levý přední blatník — promáčklinina 3 cm. Kapota bez poškození.          │
├──────────────────────────────────────────────────────────────────────────┤
│  POŽADAVEK ZÁKAZNÍKA                                                     │
│  „Kontrola úniku oleje, výměna filtrů"                                   │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────┐ ┌────┐ ┌────┐   ┌────┐ ┌────┐ ┌────┐                             │
│  │Před│ │Zad │ │Levá│   │Prav│ │Int.│ │Pošk│  Fotodokumentace příjmu     │
│  │ní  │ │ní  │ │    │   │á   │ │    │ │ození│  (embedded, ne odkaz)      │
│  └────┘ └────┘ └────┘   └────┘ └────┘ └────┘                             │
├──────────────────────────────────────────────────────────────────────────┤
│  Podpis zákazníka [img]              Podpis servisu [img]                │
│  ┌────────┐  Ověření: /verify/{token}                                     │
│  │ QR     │                                                              │
│  └────────┘                                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

## 4.2 Sekce a povinná pole

| Sekce | Pole |
|-------|------|
| Vozidlo | SPZ, VIN, km, palivo, fluids |
| Příjem | datetime, recepce, režim přístupu |
| Poškození | `damage_description` |
| Požadavek | `customer_request` |
| Fotky | intake photos — **6 slotů embedded** (viz lifecycle §8.1) |
| Podpisy | `signature` |
| QR verify | ano |

### 4.2a Fotodokumentace — povinné sloty

| Slot key | Label PDF | Finalized |
|----------|-----------|-----------|
| `front` | Přední část | povinné |
| `rear` | Zadní část | povinné |
| `left` | Levá strana | povinné |
| `right` | Pravá strana | povinné |
| `interior` | Interiér | doporučeno |
| `damage` | Poškození | pokud damage popis |

## 4.3 Zdroj dat

| Model | Pole |
|-------|------|
| `ServiceIntake` | `odometer_km`, `fluids_ok`, `damage_description`, `photos`, `signature`, `customer_request`, `intake_note`, `intake_status`, SPZ fields, timestamps |

**Payload builder:** `documents/payload/intake_protocol.py` — **nový**

## 4.4 API

| Method | Path | Stav |
|--------|------|------|
| GET | `/api/v1/service/intake/{id}/pdf` | **nový C1.4** |
| POST | `/api/v1/service/intake` | existuje |

## 4.5–3.7 Layout

**Karta:** typ PŘÍJEM, INT- číslo, vozidlo, datum.  
**Umístění:** Intake wizard krok 4 „Náhled protokolu", Vehicle detail → Dokumenty.

## 4.8 E2E scénář

```
service-shell-intake-protocol-pdf.spec.ts
1. Intake kroky 1–4 s fotkami a podpisem
2. „Náhled protokolu" — preview panel
3. PDF obsahuje km, poškození, SPZ
4. Submit intake → dokument v archive
5. Verify URL
6. Mobil 390px — podpis canvas 44px
```

---

# 5. Servisní zpráva (`service_record`)

## 5.1 Wireframe — PDF stránka 1

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [LOGO]  Autoservis Novák                           ┌─────────────────┐   │
│                                                    │  PUBLIKOVÁNO    │   │
│                                                    │  ZS-2026-0441   │   │
│                                                    └─────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│  SERVISNÍ ZPRÁVA / ZÁZNAM O ZÁSAHU                                       │
├──────────────────────────────────────────────────────────────────────────┤
│  Zásah: Výměna oleje a filtrů                                            │
│  Datum: 28.05.2026 · Stav km: 142 350 · Kategorie: údržba                │
├──────────────────────────────────────────────────────────────────────────┤
│  VOZIDLO: Škoda Octavia · 1AB 2345 · VIN TMB***7890                     │
├──────────────────────────────────────────────────────────────────────────┤
│  PROVEDENÉ PRÁCE                                                         │
│  • Výměna motorového oleje 5W-30                                        │
│  • Výměna olejového filtru                                               │
│  • Kontrola hladiny provozních kapalin                                   │
├──────────────────────────────────────────────────────────────────────────┤
│  VYMĚNĚNÉ DÍLY                                                           │
│  Olej 5W-30 4,5 l · Filtr oleje 1 ks                                     │
├──────────────────────────────────────────────────────────────────────────┤
│  DOPORUČENÍ                                                              │
│  Kontrola rozvodů do 150 000 km.                                         │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────┐ ┌────┐  Fotodokumentace                                          │
│  Technik: P. Svoboda · Servis: Autoservis Novák                          │
│  ┌────────┐  Ověření: /verify/{token}                                     │
│  │ QR     │                                                              │
│  └────────┘                                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

## 5.2 Sekce a povinná pole (§9)

Název zásahu, datum, km, fotografie, práce, díly, doporučení, servis, technik.

## 5.3 Zdroj dat

| Model | Pole |
|-------|------|
| `ServiceRecord` | `description`, `performed_at`, `mileage`, `category`, `attachments`, `price`, `work_order_id`, `record_status`, `visibility_scope` |
| WO items | linked parts/labor |
| Technician | via WO |

**Payload builder:** `documents/payload/service_record.py` — **nový** (dnes `auto-from-document` ingest opačným směrem)

## 5.4 API

| Method | Path | Stav |
|--------|------|------|
| GET | `/api/v1/vehicles/{vid}/records/{id}/report.pdf` | **nový C1.5** |
| POST | `.../records/auto-from-document` | existuje (inbound) |

## 5.5–5.7 Layout

**Karta:** SERVISNÍ ZPRÁVA, datum, vozidlo, shrnutí zásahu.  
**Umístění:** Service record detail, Vehicle detail → Historie, User documents hub.

## 5.8 E2E scénář

```
service-record-report-pdf.spec.ts
1. Dokončit WO → vytvořit servisní záznam
2. Generovat servisní zprávu PDF
3. User vidí kartu v documents hub
4. Preview + download
5. Verify
6. visibility_scope = owner → user vidí; service_only → user ne
7. Mobil 390px
```

---

# 6. Předávací protokol (`handover_protocol`)

## 6.1 Wireframe — PDF stránka 1

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [LOGO]  Autoservis Novák                           ┌─────────────────┐   │
│                                                    │  PŘEDÁNO        │   │
│                                                    │  HD-2026-0312   │   │
│                                                    └─────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│  PROTOKOL O PŘEDÁNÍ VOZIDLA                                             │
├──────────────────────────────────────────────────────────────────────────┤
│  VOZIDLO                            │  PŘEDÁNÍ                           │
│  Škoda Octavia · 1AB 2345           │  28.05.2026 16:45                    │
│  VIN: TMB***7890                    │  Km při předání: 142 355              │
│                                     │  Zakázka: WO-2026-0312               │
├──────────────────────────────────────────────────────────────────────────┤
│  SHRNUTÍ PROVEDENÝCH PRACÍ                                               │
│  Výměna brzd, diagnostika — viz servisní zpráva ZS-2026-0441            │
├──────────────────────────────────────────────────────────────────────────┤
│  STAV PŘI PŘEDÁNÍ                                                        │
│  Vozidlo předáno čisté. Zákazník seznámen s doporučením.                 │
├──────────────────────────────────────────────────────────────────────────┤
│  Faktura: 2026-0042 · Celkem: 1 630,00 Kč · Zaplaceno: převodem         │
├──────────────────────────────────────────────────────────────────────────┤
│  Podpis zákazníka [img]              Podpis servisu [img]                │
│  ┌────────┐  Ověření: /verify/{token}                                     │
│  │ QR     │                                                              │
│  └────────┘                                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

## 6.2 Sekce a povinná pole

Shrnutí WO, km in/out, stav při předání, vazba na fakturu, oba podpisy.

## 6.3 Zdroj dat

| Model | Pole |
|-------|------|
| `ServiceWorkOrder` | completed state, mileage |
| `ServiceIntake` | mileage in |
| `ServiceInvoice` | linked invoice |
| `ServiceRecord` | summary |
| Nový: `HandoverProtocol` | `signed_at`, signatures, notes — **model C1.6** |

**UI trigger:** `service-shell.js` — tlačítko „Vytvořit předávací protokol" (dnes existuje label, chybí PDF).

## 6.4 API

| Method | Path | Stav |
|--------|------|------|
| POST | `/api/service/work-orders/{id}/handover-protocol` | **nový C1.6** |
| GET | `.../handover-protocol/pdf` | **nový C1.6** |

## 6.5–6.7 Layout

**Karta:** PŘEDÁNÍ, WO ref, datum, vozidlo.  
**Umístění:** WO completion panel, dashboard „handover_ready" KPI.

## 6.8 E2E scénář

```
service-shell-handover-protocol.spec.ts
1. Complete WO + invoice issued
2. „Vytvořit předávací protokol"
3. Oba podpisy
4. PDF + card + verify
5. Dashboard handover_ready count --
6. Mobil 390px
```

---

# 7. Historie vozidla (`vehicle_history`)

## 7.1 Wireframe — PDF stránka 1

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [LOGO]  TooZ / vystavující servis                  ┌─────────────────┐   │
│                                                    │  PLATNÝ         │   │
│                                                    │  DOC-2026-9912  │   │
│                                                    └─────────────────┘   │
├──────────────────────────────────────────────────────────────────────────┤
│  DIGITÁLNÍ SERVISNÍ VÝPIS VOZIDLA                                        │
│  Verze 3 · režim: majitel / servis / veřejný                             │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────── VOZIDLO ───────────────┐  ┌──── STK / PLATNOST ────┐  │
│  │ Škoda Octavia 2.0 TDI                 │  │ STK do: 15.03.2027     │  │
│  │ SPZ 1AB 2345 · VIN TMB***7890         │  │ Emise: OK              │  │
│  │ 142 350 km · foto vozidla             │  └────────────────────────┘  │
│  └───────────────────────────────────────┘                               │
├──────────────────────────────────────────────────────────────────────────┤
│  GRAF NÁJEZDU KM (timeline)                                              │
│  ▁▂▃▅▆█                                                                  │
├──────────────────────────────────────────────────────────────────────────┤
│  SERVISNÍ ZÁZNAMY (tabulka/timeline)                                     │
│  28.05.2026 · Autoservis Novák · Výměna oleje · 142 350 km               │
│  12.01.2026 · STK stanice · Technická kontrola · 138 100 km              │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌────────┐  Ověření: /verify/{token}  Kód: XXXX-XXXX                     │
│  │ QR     │  hub.toozservis.cz/verify/…                                   │
│  └────────┘                                                              │
└──────────────────────────────────────────────────────────────────────────┘
```

## 7.2 Sekce a povinná pole

Vehicle block, STK, mileage chart, service records timeline, owners (dle režimu), verify QR.

## 7.3 Zdroj dat

| Model / modul | Pole |
|---------------|------|
| `VehicleReportDocument` | verify tokens, versioning |
| `vehicle_report_builder.py` | `VehicleServiceReportPayload` |
| `vehicle_report_models.py` | dataclasses |
| `vehicle_report_pdf.py` | **existující renderer — align to platform** |

## 7.4 API

| Method | Path | Stav |
|--------|------|------|
| GET | `/api/v1/vehicles/{id}/report.pdf` | existuje — refactor to platform |
| GET | `/api/v1/vehicles/{id}/pdf` | alias |
| GET | `/api/public/documents/verify/{token}` | verify |
| GET | `/api/public/vehicle-history/{token}` | separátní QR historie |

## 7.5–7.7 Layout

**Karta:** HISTORIE VOZIDLA, verze, datum, vozidlo, verify badge.  
**Umístění:** User documents, Vehicle detail → Dokumenty, Vehicle detail → Přehled export.

**C1.7 scope:** Refactor layout zones to match master template; zachovat kvalitu obsahu.

## 7.8 E2E scénář

```
vehicle-history-pdf-platform.spec.ts
1. Vozidlo se záznamy
2. Export report.pdf
3. Document card s thumbnail
4. Preview = finalize hash
5. /verify/{token} — valid, VIN masked
6. Superseded po novém exportu
7. Mobil 390px
```

---

# Příloha A — Matice dokument × surface

| Typ | Service shell | User app | Vehicle detail | Public |
|-----|---------------|----------|----------------|--------|
| Faktura | ✅ billing | ✅ invoices | C2 tab | — |
| Nabídka | ✅ quotes | — | C2 | public-quote |
| Zakázkový list | ✅ WO | — | C2 | — |
| Příjmový protokol | ✅ intake | — | C2 | — |
| Servisní zpráva | ✅ records | ✅ hub | C2 | — |
| Předávací protokol | ✅ WO complete | ✅ hub | C2 | — |
| Historie vozidla | ✅ workspace | ✅ hub | C2 | verify + history QR |

---

# Příloha B — Implementační pořadí (po schválení)

| Fáze | Typ | Důvod pořadí |
|------|-----|--------------|
| C1.0 | Platform | Shared layout |
| C1.1 | Faktura | Největší business impact, data hotová |
| C1.2 | Nabídka | Sdílená tabulka s fakturou |
| C1.3 | Zakázkový list | WO data hotová |
| C1.4 | Příjmový protokol | Intake data hotová |
| C1.5 | Servisní zpráva | Historie viditelná userovi |
| C1.6 | Předávací protokol | Vyžaduje model + WO complete |
| C1.7 | Historie vozidla | Align existující k platformě |
| C1.8 | Hub unified cards | UI vrstva |

---

# Příloha C — E2E souhrn

Každý spec musí pokrýt **plný lifecycle cyklus** ([DOCUMENT_LIFECYCLE.md](./DOCUMENT_LIFECYCLE.md) §12):

create → edit → finalize → card thumbnail → preview = download → share → verify → archive → reload → re-login → mobile → delete draft

| Spec soubor | Typ | Viewport |
|-------------|-----|----------|
| `service-shell-invoice-pdf-platform.spec.ts` | Faktura | 1280 + 390 |
| `service-shell-quote-pdf-platform.spec.ts` | Nabídka | 1280 + 390 |
| `service-shell-work-order-pdf.spec.ts` | WO | 1280 + 390 |
| `service-shell-intake-protocol-pdf.spec.ts` | Intake | 390 |
| `service-record-report-pdf.spec.ts` | Záznam | 1280 + 390 |
| `service-shell-handover-protocol.spec.ts` | Předání | 1280 + 390 |
| `vehicle-history-pdf-platform.spec.ts` | Historie | 1280 + 390 |
| `user-documents-preview-cards.spec.ts` | Hub cards | 390 |

Každý spec: create → preview card → open → download → verify → reload → re-login → mobile.

**Poznámka:** Po schválení lifecycle (§12) je povinný i krok edit, archive a delete draft.

---

*Vytvořeno: 2026-05-30 — C1-PREP Document Platform Design*
