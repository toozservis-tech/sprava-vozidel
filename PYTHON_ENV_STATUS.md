# PYTHON_ENV_STATUS

## Co bylo rozbité
- Systémový Python byl `3.9.6` bez runtime stacku projektu.
- Původní `.venv` obsahovala rozbité shebangy na cizí cestu `/opt/toozhub2/app/.venv/bin/python3`.
- `pytest`, `pip` a další entrypointy z původní `.venv` nebyly spustitelné konzistentně.

## Jak je to opravené
- Oficiální lokální interpreter je `python3.12` z Homebrew.
- Aktivní virtuální prostředí je znovu vytvořená `.venv`.
- Staré prostředí je vyřazené z workflow; bootstrap obstarává `scripts/bootstrap_dev.sh`.
- Dev a helper závislosti se instalují přes `requirements-dev.txt`.

## Oficiální cesta pro lokální vývoj
1. `brew install python@3.12`
2. `scripts/bootstrap_dev.sh`
3. `source .venv/bin/activate`
4. `scripts/migrate_database.py`
5. `scripts/run_tests.sh local`
