# Správa vozidel — produktová ústava

**STATUS: ZÁVAZNÉ**

Tento dokument má **vyšší prioritu než jednotlivé feature prompty**, task specifikace a ad hoc požadavky agentů.

Související dokumenty (pořadí priority viz [DECISION_RULES.md](./DECISION_RULES.md)):

- [DECISION_RULES.md](./DECISION_RULES.md) — pořadí rozhodování a PASS/FAIL
- [UI_GOVERNANCE.md](./UI_GOVERNANCE.md) — jednotný vzhled
- [WORKFLOW_STANDARDS.md](./WORKFLOW_STANDARDS.md) — end-to-end procesy
- [PDF_STANDARDS.md](./PDF_STANDARDS.md) — dokumenty a výstupy
- [ARCHITECTURE.md](./ARCHITECTURE.md) — technická mapa systému

---

## 1. Hlavní cíl produktu

Nevytváříme evidenci vozidel.  
Nevytváříme autoservisní software.  
Nevytváříme CRM.

**Vytváříme jednotný ekosystém historie vozidel.**

Každé vozidlo existuje v systému **pouze jednou**. Kolem vozidla existují:

- majitelé
- servisy
- servisní zásahy
- dokumenty
- fotodokumentace
- STK
- faktury
- zakázky
- připomínky
- rezervace

Vše musí být navázané na **jedno vozidlo**. Nikdy primárně na uživatele.

---

## 2. Zákon pro grafiku

Grafika má **vyšší prioritu než implementace nové funkce**.

Pokud funkce funguje, ale rozbíjí vzhled nebo jednotu systému:

**VERDIKT = FAIL**

Každá nová servisní obrazovka musí používat existující vzory:

- `service-dashboard-pro`
- `service-pro-card`
- `service-pro-grid`
- `service-page-header`
- `service-pro-kpis`

Uživatelská aplikace musí používat odpovídající **`uapp-next-*`** / schválené tokeny z design mapy — ne ad hoc styly.

**Zakázáno:**

- nový styl karet, formulářů, tabulek, modalů nebo dashboardů bez schválení v UI governance
- hybrid starého a nového UI na stejné obrazovce
- dekorativní karty bez funkčního handleru

Detail: [UI_GOVERNANCE.md](./UI_GOVERNANCE.md)

---

## 3. Zákon pro navigaci

Každý prvek musí mít jasný cíl.

**Zakázáno:** mrtvé odkazy, placeholder tlačítka, fake success, tlačítka bez akce.

Každé tlačítko musí mít definované:

| Písmeno | Otázka |
|---------|--------|
| A | Co spouští? |
| B | Kam zapisuje? |
| C | Co aktualizuje? |
| D | Kam přesměrovává? |
| E | Co se změní po dokončení? |

---

## 4. Zákon pro workflow

Každá funkce musí být navázaná na **celý proces**, ne na izolovaný krok.

Referenční servisní flow (příjem vozidla):

1. Vyhledání vozidla  
2. Volba režimu (propojení s majitelem / jednorázový zásah)  
3. Fotodokumentace příjmu  
4. Příjmový protokol  
5. Návrh zakázky  
6. Přijetí technikem  
7. Práce  
8. Dokončení  
9. Doklady  
10. Servisní historie  

Každý krok musí navazovat na další. Detail: [WORKFLOW_STANDARDS.md](./WORKFLOW_STANDARDS.md)

---

## 5. Modaly

**Zakázáno:**

- modal v modalu
- popup nad popupem
- druhý floating dialog pro stejnou akci

**Povoleno:**

- inline panel
- detail panel v rámci stránky
- jeden centrální modal na akci

---

## 6. Dokumenty

**nepřipouští se:**

- PDF = několik řádků textu
- PDF = obyčejný export
- PDF = technický výpis bez layoutu

Každý dokument musí vypadat jako **skutečný dokument**. Detail: [PDF_STANDARDS.md](./PDF_STANDARDS.md)

---

## 7. Faktura

Musí obsahovat: logo, hlavičku firmy, číslo faktury, QR platbu, variabilní symbol, datum vystavení a splatnosti, odběratele, vozidlo, VIN, SPZ, tabulku položek, DPH, mezisoučet, celkovou cenu, podpis, patičku.

Vzhled: **moderní účetní dokument roku 2026**, ne textový export.

---

## 8. Zakázkový list

Musí obsahovat: logo, číslo zakázky, stav, vozidlo, VIN, SPZ, kilometry, palivo, datum příjmu a dokončení, fotky, poznámky, práce, díly, čas práce, podpis zákazníka, podpis servisu.

Vizuálně: **servisní formulář profesionálního autoservisu**.

---

## 9. Servisní záznam

Musí obsahovat: název zásahu, datum, kilometry, fotografie, provedené práce, vyměněné díly, doporučení, servis, technika.

Vizuálně: **historický servisní report**.

---

## 10. Náhledy PDF

Ne pouze ikona PDF. Musí existovat: náhled první stránky, stav dokumentu, typ, datum, vozidlo, rychlé akce (otevřít, stáhnout, sdílet, ověřit) — ve formě moderních karet.

---

## 11. Detail vozidla

Hlavní **centrum systému**. Sekce (každá vlastní karta):

- Přehled
- Dokumenty
- Servisní historie
- Fotky
- Přístupy servisů
- STK
- Připomínky
- Rezervace
- Audit

---

## 12. Mobil

Povinné viewporty pro test: **390×844**, **412×915**, **768×1024**.

Podmínky: žádný horizontální scroll, min. **44px** tap cíle, žádné překryvy, žádné skryté akce.

---

## 13. E2E povinnost

Každá nová funkce musí projít: vytvoření → editace → smazání → detail → reload → odhlášení → přihlášení → mobil.

Pokud některý krok nefunguje: **PASS je zakázán**.

---

## 14. Před implementací

Před každou novou funkcí nejprve:

1. Grafický návrh  
2. Workflow  
3. Datový model  
4. API tok  
5. Mobilní návrh  
6. Dokumenty  
7. E2E scénář  

Teprve potom kód.

---

## 15. Povinný výstup každé fáze

1. PASS/FAIL  
2. Commit hash  
3. Grafický audit  
4. UX audit  
5. Workflow audit  
6. API audit  
7. Dokumentový audit  
8. Mobilní audit  
9. E2E audit  
10. Runtime audit  
11. Screenshot audit  
12. Seznam nových prokliků  
13. Seznam nových modalů  
14. Seznam nových dokumentů  
15. Seznam nových vazeb mezi uživatelem a servisem  

**PASS nedávej, pokud:**

- UI není jednotné  
- workflow není kompletní  
- dokumenty vypadají jako export  
- PDF nemají profesionální vzhled  
- mobil má chyby  
- existují mrtvé prokliky  
- není dokončen celý proces end-to-end  

---

*Poslední aktualizace: 2026-05-30 — Fáze A Governance Layer*
