# MIGRATION RUNBOOK

## 1. Instalace závislostí

```bash
pip install -r requirements.txt
```

## 2. Spuštění migrací

```bash
python scripts/migrate_database.py
```

Alternativně přímo:

```bash
python -m alembic upgrade head
```

## 3. Založení čisté DB

- Canonical runtime source-of-truth je `src/core/config.py`.
- Priorita DB URL je:
  - `DATABASE_URL`
  - legacy `VEHICLE_DB_URL`
  - fallback `sqlite:///<workspace>/data/vehicles.db`
- Pokud není nastaveno nic, backend i migrace použijí stejnou runtime DB v `/opt/toozhub2/data/vehicles.db` resp. `<workspace>/data/vehicles.db`.
- Produkční runtime DB v tomto projektu je `/opt/toozhub2/data/vehicles.db`.
- Soubor `app/data/vehicles.db` může na serveru existovat jako starý volume snapshot; není to source of truth, pokud `DATABASE_URL` míří na `/opt/toozhub2/data/vehicles.db`.
- Pro čistou DB vytvořte prázdný soubor / nový PostgreSQL schema a spusťte migrace.

## 4. Ověření schématu

```bash
pytest tests/api/test_schema_migration_smoke.py
```

Nebo runtime kontrola:

```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/v1/system/capabilities
```

Všechny aktivní moduly musí vracet `available: true`.

## 5. Migrace existujících dat

- Baseline migrace automaticky doplní chybějící tabulky a sloupce.
- Legacy ownership z `vehicles.user_email` se backfilluje do `vehicle_ownerships`.
- Existující servisní záznamy zůstávají zachované; nové soft-delete/audit sloupce se doplní aditivně.

## 6. Provozní pravidla

- Nespouštět runtime `create_all` v request flow.
- Nepřidávat další jednorázové `ALTER TABLE` skripty mimo Alembic.
- Po každé změně modelu vytvořit novou migraci a ověřit `system/capabilities`.
