# PROJECT NAMING STATUS

## Kanonický dokument

Kompletní přehled přejmenování a plán: **`PROJECT_RENAME_STATUS.md`** a **`TECHNICAL_RENAME_BACKLOG.md`**.

## Oficiální brand

- Uživatelský a admin brand je **Správa vozidel**.
- Konstanty v `src/core/branding.py` jsou jednotným zdrojem pro UI texty, e-maily, OpenAPI titulek, část health odpovědí a bezpečné HTTP metadata.

## Kde technicky zůstává legacy

- **iOS / Xcode:** target `TooZHubiOS`, zdrojová cesta `Sources/TooZHub/` (viz backlog).
- **GitHub:** slug repozitáře může být stále `TOOZHUB2` – URL v `docs/` jsou platné dokud se repo nepřejmenuje.
- **Env:** `TOOZHUB_API_URL`, `TOOZHUB_ADMIN_*` – nasazení.
- **Web push:** stránka dočasně přijímá i typ `TOOZHUB_NOTIFICATION_CLICK` kvůli starým service workerům.

## Budoucí refaktor

Podrobnosti a priority: **`TECHNICAL_RENAME_BACKLOG.md`**.
