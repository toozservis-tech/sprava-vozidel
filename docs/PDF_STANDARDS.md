# PDF a dokumentové standardy

**STATUS: ZÁVAZNÉ** — podřízeno [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md)

---

## Zásada

**PDF není export textu.** Každý výstup musí vypadat jako dokument, který servis nebo zákazník může vytisknout, archivovat nebo poslat úřadu / pojišťovně.

**FAIL**, pokud:

- PDF = několik řádků monospace textu
- chybí branding servisu / produktu
- chybí vazba na vozidlo (VIN, SPZ, název)
- náhled v UI = pouze ikona bez preview karty

---

## Typy dokumentů

| Typ | Minimální obsah | Vizuální laťka |
|-----|-----------------|----------------|
| **Faktura** | §7 ústavy | Moderní účetní doklad 2026 |
| **Zakázkový list** | §8 ústavy | Profesionální autoservisní formulář |
| **Servisní záznam** | §9 ústavy | Historický servisní report |
| **Příjmový protokol** | vozidlo, km, palivo, fotky, podpisy | Servisní protokol |
| **STK / technický výpis** | metadata vozidla, platnost | Úředně čitelný layout |
| **Report vozidla (PDF)** | souhrn historie, STK, km | Marketingově čistý report |

---

## Faktura — povinná pole

- Logo a hlavička firmy (servis)
- Číslo faktury, variabilní symbol
- QR platba (CZ standard, kde applicable)
- Datum vystavení, datum splatnosti
- Odběratel (fakturační údaje)
- Vozidlo: název, **VIN**, **SPZ**
- Tabulka položek (popis, množství, cena, DPH)
- Mezisoučet, DPH, celkem
- Patička (IČO, DIČ, účet, kontakt)
- Místo pro podpis / razítko (volitelně digitální)

---

## Zakázkový list — povinná pole

- Logo, číslo zakázky, **stav zakázky**
- Vozidlo, VIN, SPZ, kilometry, palivo
- Datum příjmu, datum dokončení (nebo plán)
- Fotodokumentace (min. náhledy)
- Poznámky zákazníka a servisu
- Práce, díly, čas práce
- Podpis zákazníka, podpis servisu

---

## Servisní záznam — povinná pole

- Název zásahu, datum, kilometry
- Fotografie (pokud existují)
- Provedené práce, vyměněné díly
- Doporučení
- Servis, technik

---

## Náhled v aplikaci (§10 ústavy)

Každý dokument v UI musí mít **kartu náhledu**, ne jen odkaz:

| Prvek | Povinný |
|-------|---------|
| Náhled první stránky (thumbnail nebo embed) | ano |
| Typ dokumentu | ano |
| Stav (koncept / vystaveno / zaplaceno / …) | ano |
| Datum | ano |
| Vozidlo | ano |
| Akce: otevřít, stáhnout, sdílet, ověřit | dle typu |

Layout: moderní karty v rámci `service-pro-card` nebo `uapp-next-*` dokumentové sekce.

---

## Technická implementace

| Oblast | Umístění (orientační) |
|--------|------------------------|
| Generování PDF | backend moduly + šablony |
| Náhled | `/web`, API blob / signed URL |
| Ověření | verify URL + QR kde applicable |

Před novou PDF šablonou: wireframe + schválení proti tomuto dokumentu.

---

## Audit checklist (Fáze B)

- [ ] Faktury — layout, QR, vozidlo
- [ ] Zakázkové listy — intake → WO PDF
- [ ] Servisní záznamy — historie
- [ ] Náhledy v UI — karty vs. ikony
- [ ] Mobil — čitelnost náhledu a akcí

Očekávaný dluh (2026-05): **PDF ~35 %**, **náhledy dokumentů ~41 %** — doplní audit Fáze B.

---

*Poslední aktualizace: 2026-05-30 — Fáze A Governance Layer*
