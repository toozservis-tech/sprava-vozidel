# Správa vozidel - Webová verze

## Použití

Canonical přehled aktivních a legacy webových vstupů je v `PRODUCT_ENTRYPOINTS_STATUS.md`.

1. **Nastavte API URL:**
   - Otevřete `index.html` v textovém editoru
   - Najděte řádek: `const API_URL = ...`
   - Nastavte URL vašeho API serveru (např. `http://127.0.0.1:8001` nebo `https://hub.toozservis.cz`)

2. **Napojení na Webnode (produkční metoda):**
   - V nastavení stránky `/sprava-vozidel/` v Webnode nastavte přesměrování na:
   - `https://hub.toozservis.cz/web/index.html`
   - Viz podrobnější návod: `RYCHLY_POSTUP_WEBNODE.md` nebo `POSTUP_VLOZENI_DO_WEBNODE.md`

3. **Alternativní iframe varianta (legacy / compat, nedoporučeno pro produkci):**
   - Viz `WEBNODE_IFRAME_VARIANTA_DEV.md` pro vývojářskou iframe variantu

## Funkce

- ✅ Přihlášení a registrace
- ✅ Zobrazení vozidel
- ✅ Přidání nového vozidla
- ✅ Responzivní design

## Poznámky

- Webová verze komunikuje s backend API
- Všechna data se ukládají do backend databáze
- Pro plnou funkcionalitu je potřeba spuštěný backend server
- Hlavní produktová větev je `web/index.html`
- `index_minimal.html` a `index_iframe*.html` nejsou hlavní produktová cesta
