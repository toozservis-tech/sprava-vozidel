# UI Governance — jednotný vzhled

**STATUS: ZÁVAZNÉ** — podřízeno [PRODUKTOVA-USTAVA.md](./PRODUKTOVA-USTAVA.md)

---

## Cíl

Každá obrazovka musí působit jako **součást stejného systému**. Nová funkce nesmí zavést paralelní design language.

---

## Servisní aplikace (`web/service-shell.*`, servisní routy)

### Povinné layoutové třídy

| Třída | Účel |
|-------|------|
| `service-dashboard-pro` | Obal stránky / dashboard sekce |
| `service-page-header` | Nadpis, breadcrumb, primární akce |
| `service-pro-grid` | Hlavní mřížka obsahu |
| `service-pro-card` | Karta sekce nebo bloku dat |
| `service-pro-kpis` | KPI / souhrnné metriky |
| `service-pro-main` / `service-pro-aside` | Hlavní sloupec + postranní panel |

### Stylesheet

Primární: `web/service-shell.css`

### Zakázáno

- Nové „card“ třídy mimo `service-pro-*` bez schválení
- Inline styly pro layout (výjimka: dočasný hotfix s TODO a datem)
- Bootstrap-style tabulky bez responsivní varianty
- Druhý modal pro stejnou akci (viz ústava §5)

---

## Uživatelská aplikace (`web/user-app-next.*`, `web/user-settings.*`)

### Povinné vzory

| Prefix / soubor | Účel |
|-----------------|------|
| `uapp-next-*` | Dashboard, vozidla, detail, sidebar |
| `uapp-settings-*` | Nastavení účtu |
| `user-app-next.css` | Tokeny a komponenty |

### Design reference

- [APP_WIDE_DESIGN_MAP_20260518.md](./APP_WIDE_DESIGN_MAP_20260518.md) — cílové tokeny (`--sv-*`)
- [USER_APP_VISUAL_REFERENCE_MAP_20260518.md](./USER_APP_VISUAL_REFERENCE_MAP_20260518.md)

### Zakázáno

- Ad hoc dashboard karty mimo existující grid (výjimka: schválený pattern v design mapě)
- Legacy `index.html` styly pro nové user features bez migrace do `uapp-next`

---

## Společná pravidla

### Barvy a stavy

| Význam | Barva / token |
|--------|----------------|
| Primary akce | modrá (`--sv-blue` / `--uapp-*` primary) |
| OK / schváleno | zelená |
| Pozor / pending | amber/orange |
| Nebezpečí / po termínu | červená |

### Tlačítka

Každé tlačítko: viz ústava §3 (A–E). V UI review checklist:

- [ ] Má `data-testid` nebo `data-uapp-action` / ekvivalent
- [ ] Volá reálné API nebo handler
- [ ] Po akci aktualizuje viditelný stav
- [ ] Mobil: min-height **44px**

### Tabulky

- Desktop: tabulka v `service-pro-card` nebo `uapp-settings-table`
- Mobil: stack / karty, **žádný horizontální scroll** celé stránky

### Modaly

- Max. **jeden** aktivní modal na viewport
- Preferovat **inline panel** (např. completion panel v detailu zakázky)
- Zakázáno: modal v modalu

---

## Review před merge

1. Screenshot desktop + mobil (390px)
2. Ověření, že nepřibyly nové CSS soubory bez důvodu
3. `node --check` na dotčené JS soubory
4. Playwright smoke na dotčené `data-testid`

---

## Audit (Fáze B — plánováno)

Oblasti k hodnocení souladu:

- Dashboard servisu
- Dashboard uživatele
- Detail vozidla
- Dokumenty (náhledy)
- Mobil (390×844, 412×915, 768×1024)

---

*Poslední aktualizace: 2026-05-30 — Fáze A Governance Layer*
