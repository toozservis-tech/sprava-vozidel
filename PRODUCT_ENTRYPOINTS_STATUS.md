# Product Entrypoints Status

Tento dokument je canonical přehled aktivních produktových vstupů projektu `Správa vozidel`.

## Aktivní produktové větve

### Web frontend
- Runtime cesta: `/web/index.html`
- Zdrojový soubor: `web/index.html`
- Stav: aktivní produkční větev
- Důvod:
  - root `/` přesměrovává na `/web/index.html`
  - backend `api` metadata uvádí `/web/index.html` jako hlavní web interface
  - e2e testy a veřejné odkazy míří na `/web/index.html`

### Admin frontend
- Runtime cesta: `/web_admin/`
- Zdrojové soubory:
  - `web_admin/index.html`
  - `web_admin/admin.js`
- Stav: aktivní interní/admin větev
- Důvod:
  - backend mountuje `web_admin/` jako samostatnou statickou admin aplikaci

### iOS klient
- Typ: nativní klient
- Zdrojový projekt: `ios/TooZHubiOS`
- Stav: aktivní klientská větev
- Důvod:
  - klient používá přímé API volání na backend
  - není závislý na `web/index_iframe.html` ani `web/index_minimal.html`

## Legacy / compat větve

### `web/index_minimal.html`
- Stav: legacy / compat / vývojářská větev
- Použití:
  - minimální standalone HTML varianta
  - obsahuje vlastní API URL logiku
  - stále používá legacy endpoint `/user/ares`
- Poznámka:
  - není hlavní produktová větev
  - nemá být cílem běžných produktových úprav

### `web/index_iframe.html`
- Stav: legacy / compat Webnode iframe větev
- Použití:
  - wrapper, který načítá hlavní aplikaci přes iframe
- Poznámka:
  - není current primary production path

### `web/index_iframe_production.html`
- Stav: legacy / compat Webnode iframe větev
- Použití:
  - produkčně pojmenovaný iframe wrapper z dřívějšího nasazovacího postupu
- Poznámka:
  - název je historický
  - current primary production path je `/web/index.html`

## Backup / šum

### `web/index.html.backup_now`
- Stav: backup artefakt
- Poznámka:
  - není aktivní produktová větev
  - neslouží jako zdroj pro běžné úpravy

### `web_admin/index.html.bak`
### `web_admin/admin.js.bak`
- Stav: backup artefakty
- Poznámka:
  - nejsou aktivní admin aplikace

## Kompatibilita, kterou je nutné zachovat

- Legacy endpoint `/user/ares` musí zůstat, protože jej stále používá iOS klient a `web/index_minimal.html`.
- Webnode / iframe materiály mohou dočasně zůstat kvůli historickému nasazení a compat provozu, ale nejsou canonical produktovou cestou.

## Co je riziko pro další vývoj

- Starší dokumentace a některé helper skripty stále preferují iframe/minimal větev.
- Nejrizikovější aktuální tooling stopa:
  - `scripts/webnode_auto_upload.py`
  - preferuje `web/index_iframe.html`, pak `web/index_minimal.html`, a až nakonec `web/index.html`
- To je compat/tooling dluh, ne canonical runtime pravda.

## Pravidlo pro další práci

- Produktové změny webu dělat primárně v `web/index.html`.
- Produktové změny adminu dělat primárně v `web_admin/index.html` a `web_admin/admin.js`.
- Legacy/compat soubory neupravovat bez explicitního důvodu a bez ověření, že jde opravdu o compat scénář.
