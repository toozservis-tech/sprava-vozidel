# SANITATION NOTE

- Aktivní aplikace pro další vývoj a nasazení je `source-mirror/app`.
- `source-mirror/app_backup` je mimo aktivní vývoj a nesmí být používán jako source-of-truth pro změny.
- Runtime data, lokální databáze, Playwright reporty, build cache a podobné artefakty mají být drženy mimo verzovaný stav nebo explicitně ignorovány.
