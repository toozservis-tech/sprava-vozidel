# Document Visual System

**Fáze:** C1-PREP — Document Platform Design  
**Status:** NÁVRH KE SCHVÁLENÍ  
**Podřízeno:** [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md) §6–10, [UI_GOVERNANCE.md](./UI_GOVERNANCE.md), [PDF_STANDARDS.md](./PDF_STANDARDS.md)

Související: [DOCUMENT_PLATFORM_ARCHITECTURE.md](./DOCUMENT_PLATFORM_ARCHITECTURE.md), [DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md)

---

## 1. Design princip

**Jeden vizuální jazyk** pro PDF, náhled v aplikaci, tisk a veřejnou verify stránku.

Referenční kvalita: `vehicle_report_pdf.py` — barvy, typografie, logo, QR, tabulky, footer.

**Zákaz:** Helvetica text dump, tabulka uprostřed prázdné stránky, ikona PDF bez náhledu.

---

## 2. Design tokeny (PDF + UI)

Převzato z existujícího vehicle report rendereru a sjednoceno s `--sv-*` / `--uapp-*` tokeny.

### 2.1 Barvy

| Token | Hex | Použití |
|-------|-----|---------|
| `doc-color-dark` | `#0f172a` | Nadpisy, hlavní text |
| `doc-color-muted` | `#64748b` | Popisky, footer |
| `doc-color-border` | `#dbe5f0` | Rámečky sekcí |
| `doc-color-surface` | `#f8fafc` | Pozadí bloků |
| `doc-color-surface-alt` | `#eef2ff` | Vehicle block |
| `doc-color-primary` | `#2563eb` | Akcent, odkazy |
| `doc-color-success` | `#059669` | Stav: vystaveno, zaplaceno, schváleno |
| `doc-color-warning` | `#f59e0b` | Stav: koncept, čeká |
| `doc-color-danger` | `#dc2626` | Stav: zrušeno, po termínu |

### 2.2 Typografie (PDF)

| Role | Font | Velikost |
|------|------|----------|
| Document title | DejaVuSans-Bold | 18–22 pt |
| Section heading | DejaVuSans-Bold | 12–14 pt |
| Body | DejaVuSans | 10–11 pt |
| Caption / footer | DejaVuSans | 8–9 pt |
| Table header | DejaVuSans-Bold | 10 pt |
| Status badge | DejaVuSans-Bold | 9 pt |

**Povinné:** DejaVuSans pro českou diakritiku (server font path již v vehicle report).

### 2.3 Typografie (UI karty)

| Role | CSS | Velikost |
|------|-----|----------|
| Card title | `font-weight: 600` | 15–16px |
| Meta label | `color: var(--doc-color-muted)` | 12px |
| Status badge | pill, uppercase | 11px |
| Action button | min-height 44px | 14px |

---

## 3. PDF page layout — master template

Formát: **A4** (210 × 297 mm). Okraje: **16 mm** left/right, **20 mm** top, **18 mm** bottom (footer zone).

### 3.1 Wireframe — stránka 1 (master)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ZONE A — HEADER                                              ~20mm tall │
│  ┌─────────────┐                                    ┌──────────────────┐  │
│  │    LOGO     │  NÁZEV SERVISU                    │ STAV DOKUMENTU   │  │
│  │   48×48px   │  IČO · DIČ · adresa               │  [ VYSTAVENO ]   │  │
│  └─────────────┘                                    │  číslo dokladu   │  │
│                                                      │  datum vystavení │  │
│                                                      └──────────────────┘  │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE B — DOCUMENT TITLE                                                 │
│  FAKTURA č. 2026-0042                              Variabilní symbol: 42 │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE C — TWO COLUMN META                                                │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐      │
│  │ ODBĚRATEL / ZÁKAZNÍK        │  │ VOZIDLO                     │      │
│  │ Jméno / firma               │  │ Škoda Octavia               │      │
│  │ IČO, adresa                 │  │ SPZ: 1AB 2345               │      │
│  │ email, telefon              │  │ VIN: WVW***1234             │      │
│  └─────────────────────────────┘  │ km: 142 350 · palivo: nafta │      │
│                                    └─────────────────────────────┘      │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE D — TIMELINE (volitelné — WO, intake, historie)                    │
│  ● Příjem 28.5. 09:00  →  ● Práce 28.5. 11:00  →  ● Předání 28.5. 16:00│
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE E — MAIN CONTENT (tabulka / text / fotky — dle typu)               │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Položka          │ Množ. │ MJ │ Cena/j. │ DPH │ Celkem            │  │
│  │──────────────────│───────│────│─────────│─────│───────────────────│  │
│  │ Výměna oleje     │ 1     │ ks │ 890     │ 21% │ 890 Kč            │  │
│  └────────────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE F — ATTACHMENTS / PHOTOS (volitelné)                               │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐                                            │
│  │ 📷 │ │ 📷 │ │ 📷 │ │ 📷 │   Fotodokumentace (max 4 náhledy / řada)   │
│  └────┘ └────┘ └────┘ └────┘                                            │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE G — TOTALS / NOTES (faktura, nabídka)                              │
│                              Mezisoučet:     12 450,00 Kč                │
│                              DPH 21%:         2 614,50 Kč                │
│                              CELKEM:         15 064,50 Kč                │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE H — QR + VERIFY                                                    │
│  ┌────────┐  Ověření dokumentu: hub.toozservis.cz/verify/abc…           │
│  │ QR     │  Kód: 7X4K-9M2P                                              │
│  │ PLATBA │  (faktura: QR platba SPD; ostatní: verify URL)               │
│  └────────┘                                                              │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE I — SIGNATURES (volitelné)                                         │
│  ┌─────────────────────────┐    ┌─────────────────────────┐            │
│  │ Podpis zákazníka        │    │ Podpis servisu          │            │
│  │ ___________________     │    │ ___________________     │            │
│  │ datum · jméno           │    │ datum · technik         │            │
│  └─────────────────────────┘    └─────────────────────────┘            │
├──────────────────────────────────────────────────────────────────────────┤
│  ZONE J — FOOTER                                                         │
│  Bankovní účet · IČO · DIČ · kontakt          Strana 1/2 · v1.0 · hash  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Umístění prvků — závazná pravidla

| Prvek | Pozice | Pravidlo |
|-------|--------|----------|
| **Logo servisu** | Zone A, vlevo nahoře | 48×48 px max; fallback: TooZ ikona (`toozservis-logo-icon.png`) |
| **Stav dokumentu** | Zone A, vpravo nahoře | Badge: KONCEPT / VYSTAVENO / ZAPLACENO / ZRUŠENO / SCHVÁLENO |
| **QR** | Zone H, vlevo | Faktura issued: **QR platba** (SPD string). Ostatní: **verify URL** |
| **Číslo dokladu** | Zone A nebo B | Vždy viditelné na str. 1 |
| **Vozidlo (VIN, SPZ)** | Zone C | Povinné u všech typů kromě čisté faktury bez vozidla |
| **Podpisy** | Zone I | Intake, WO, handover — povinné; faktura — volitelné |
| **Fotografie** | Zone F | Grid 2×2 nebo 1×4 náhledy, max 120×90 px each |
| **Patička** | Zone J | Bankovní údaje, stránkování, verze šablony |

### 3.3 Status badge — barvy

| Stav | Barva pozadí | Text |
|------|--------------|------|
| Koncept | `#fff7ed` / orange border | KONCEPT |
| Vystaveno | `#ecfdf5` / green | VYSTAVENO |
| Schváleno | `#ecfdf5` | SCHVÁLENO |
| Zamítnuto | `#fef2f2` / red | ZAMÍTNUTO |
| Zrušeno | `#fef2f2` | ZRUŠENO |
| Platba čeká | `#fff7ed` | K ÚHRADĚ |
| Zapaceno | `#ecfdf5` | ZAPLACENO |

---

## 4. UI komponenty

### 4.1 Document Card (`doc-card`)

Jednotná karta pro service i user app. CSS třídy:

- Service: `service-pro-card service-pro-doc-card`
- User: `uapp-next-card uapp-doc-card`

#### Wireframe — desktop card

```
┌─────────────────────────────────────────────────────────────┐
│  ┌──────────────────┐                                       │
│  │                  │  FAKTURA · VYSTAVENO                  │
│  │  PDF THUMBNAIL   │  č. 2026-0042                         │
│  │  (first page)    │  28.05.2026 · 15 064,50 Kč            │
│  │  120 × 170 px    │                                       │
│  │                  │  🚗 Škoda Octavia · 1AB 2345          │
│  └──────────────────┘                                       │
│                                                             │
│  [ Otevřít ]  [ Stáhnout ]  [ Ověřit ]  [ Sdílet ]         │
└─────────────────────────────────────────────────────────────┘
```

#### Wireframe — mobile card (390px)

```
┌─────────────────────────────────────┐
│ ┌─────────┐  FAKTURA · VYSTAVENO   │
│ │ THUMB   │  č. 2026-0042          │
│ │ 80×113  │  28.05.2026            │
│ └─────────┘  Škoda Octavia         │
│              15 064,50 Kč          │
│ ┌─────────────────────────────────┐│
│ │ Otevřít          (full width)   ││
│ └─────────────────────────────────┘│
│ [ Stáhnout ]  [ Ověřit ]  [ ⋮ ]   │
└─────────────────────────────────────┘
```

**Povinná pole karty (§10 ústavy):**

| Prvek | Povinný |
|-------|---------|
| Náhled první stránky | ano |
| Typ dokumentu | ano |
| Stav | ano |
| Datum | ano |
| Vozidlo | ano (pokud vázáno) |
| Akce | dle typu |

### 4.2 Document Card Grid

```
Desktop (≥1024px):  3 sloupce v service-pro-grid / uapp-next-grid
Tablet (768px):     2 sloupce
Mobile (390px):     1 sloupec, full width
```

Filtry nad gridem: typ dokumentu, stav, období, vozidlo.

### 4.3 PDF Preview Panel (inline — ne modal v modalu)

Preferovaný pattern: **drawer / inline panel** v rámci stránky.

#### Wireframe — desktop preview panel

```
┌─ Dokumenty ─────────────────────────────────────────────────────────────┐
│  ← Zpět na seznam          Faktura 2026-0042 · VYSTAVENO                │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                 │   │
│  │                    pdf.js CANVAS                                │   │
│  │                    (stejný soubor jako download)                │   │
│  │                                                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  [ ◀ Strana ]  1 / 2  [ Strana ▶ ]     [ − ] 100% [ + ]               │
│  [ Stáhnout PDF ]  [ Tisk ]  [ Ověřit ]  [ Sdílet odkaz ]             │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Wireframe — mobile preview (390px)

```
┌─────────────────────────────┐
│ ←  Faktura 2026-0042        │
├─────────────────────────────┤
│                             │
│     pdf.js full width       │
│     pinch zoom enabled      │
│                             │
├─────────────────────────────┤
│  ◀  1/2  ▶        100%      │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │      Stáhnout PDF       │ │
│ └─────────────────────────┘ │
│ [ Tisk ]  [ Ověřit ]        │
└─────────────────────────────┘
```

**Technologie:** Existující `web/assets/pdfjs/` — reuse z `index.html`, migrace do shared helper (`documentPreview.js` — nový soubor až C1.0).

**Zákaz:** Otevření preview v legacy `index.html` modalu z `user-app-next` (současný stav — odstranit v C1).

### 4.4 Thumbnail generování (UI)

| Fáze | Mechanismus |
|------|-------------|
| C1 MVP | pdf.js render page 1 → `<canvas>` → CSS background / `<img>` v kartě |
| Cache | `data-thumbnail-cache-key="{doc_id}:{hash}"` v DOM |
| Fallback | Typová ikona + gradient (ne holá ikona PDF) |

Fallback wireframe:

```
┌──────────────────┐
│  ░░░░░░░░░░░░░░  │  gradient doc-color-surface-alt
│  ░  FAKTURA  ░  │  typ dokumentu centered
│  ░░░░░░░░░░░░░░  │
└──────────────────┘
```

---

## 5. Sekce dle typu dokumentu — vizuální variace

| Typ | Zone D obsah | Zone F fotky | Zone H QR | Zone I podpisy |
|-----|--------------|--------------|-----------|----------------|
| Faktura | Tabulka položek + DPH | ne | QR platba | volitelně |
| Nabídka | Tabulka + platnost nabídky | ne | verify URL | ne |
| Zakázkový list | Práce + díly + čas | ano | verify URL | ano |
| Příjmový protokol | Stav vozidla, km, palivo, poškození | ano | verify URL | ano |
| Servisní zpráva | Provedené práce, díly, doporučení | ano | verify URL | ne |
| Předávací protokol | Shrnutí WO, stav při předání | volitelně | verify URL | ano |
| Historie vozidla | Timeline + záznamy + graf km | ano | verify URL | ne |

Detailní pole: [DOCUMENT_TYPES_SPECIFICATION.md](./DOCUMENT_TYPES_SPECIFICATION.md).

---

## 6. Fotografie v PDF

| Parametr | Hodnota |
|----------|---------|
| Max na stránku | 4 náhledy (1 řada) nebo 8 (2 řady) |
| Náhled rozměr | 120 × 90 px (aspect crop center) |
| Formát | JPEG embedded v PDF |
| Zdroj | `ServiceWorkOrderPhoto`, intake photos, record attachments |
| Popisek | 8 pt muted pod náhledem |
| Prázdný stav | Sekce se nevykresluje (ne „žádné fotky") |

---

## 7. Podpisy v PDF

| Parametr | Hodnota |
|----------|---------|
| Zdroj | Canvas capture z intake/WO UI → PNG base64 → uložit v DB |
| V PDF | Embedded image max 200 × 60 px nad linkou |
| Linka | 1 pt `#dbe5f0`, šířka 70 mm |
| Popisek | „Podpis zákazníka" / „Podpis servisu" + datum + jméno |
| Chybí podpis | Prázdná linka + „Nepodepsáno" (protokoly — FAIL před finalizací) |

---

## 8. Přílohy vs produktové PDF

| Kategorie | Vzhled | UI |
|-----------|--------|-----|
| **Produktový dokument** | Platform template | `doc-card` s náhledem |
| **Nahraná příloha** (faktura od dodavatele) | Originální soubor | `doc-card--attachment` s file-type badge |
| **Ingest workspace** | OCR text preview | Oddělená sekce „Nahrané podklady" |

Produktové PDF **vždy** platform layout. Přílohy **nikdy** nemíchat do stejné karty bez rozlišení typu.

---

## 9. Verify stránka (`verify.html`)

Verify stránka musí vizuálně korespondovat s PDF:

```
┌─────────────────────────────────────────┐
│  ✓ Dokument ověřen                      │
│  Faktura / Historie vozidla / …         │
│  Vystaveno: 28.05.2026 · Servis XY      │
│  Vozidlo: Škoda Octavia · VIN WVW***    │
│  Verze: 3 · Platný                      │
│  [ Zobrazit detail ]                    │
└─────────────────────────────────────────┘
```

Barvy a typografie: stejné tokeny jako PDF header.

---

## 10. Responsivita — checklist

| Viewport | PDF preview | Document card | Akce |
|----------|-------------|---------------|------|
| 390×844 | Full width canvas | 1 sloupec | 44px min-height |
| 412×915 | Stejně | 1 sloupec | Stejně |
| 768×1024 | 2 sloupce grid + panel | 2 sloupce | Stejně |
| ≥1280 | Grid + side preview optional | 3 sloupce | Stejně |

**Zákaz:** horizontální scroll celé stránky; skryté akce za hover-only.

---

## 11. testid konvence (pro E2E)

| Prvek | data-testid |
|-------|-------------|
| Document card | `doc-card-{type}-{id}` |
| Card thumbnail | `doc-card-thumbnail` |
| Card status | `doc-card-status` |
| Open action | `doc-action-open` |
| Download | `doc-action-download` |
| Verify | `doc-action-verify` |
| Preview panel | `doc-preview-panel` |
| Preview canvas | `doc-preview-canvas` |
| Page nav | `doc-preview-page-next` |

---

## 12. Schvalovací checklist

- [ ] Master PDF wireframe (Zone A–J) schválen
- [ ] Document card desktop + mobile schválen
- [ ] Preview panel (inline, ne nested modal) schválen
- [ ] Status badge barvy schváleny
- [ ] QR umístění (platba vs verify) schváleno
- [ ] Fotografie a podpisy spec schváleny
- [ ] Tokeny sjednoceny s design mapou

---

*Vytvořeno: 2026-05-30 — C1-PREP Document Platform Design*
