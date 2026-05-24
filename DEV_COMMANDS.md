# DEV_COMMANDS

```bash
# bootstrap
scripts/bootstrap_dev.sh

# backend sanity minimum
scripts/backend_sanity_gate.sh

# aktivace
source .venv/bin/activate

# run server
scripts/run_backend.sh

# start server na pozadí
./start_server.sh

# migrate
scripts/migrate_database.py
scripts/migrate_database.py current

# local smoke tests
scripts/run_tests.sh local

# integration tests
scripts/run_tests.sh integration

# schema smoke
scripts/schema_smoke.sh
```
