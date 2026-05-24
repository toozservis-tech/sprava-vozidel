#!/bin/bash
# Ověření, že TOOZHUB_ADMIN_TENANT_ID je správně načteno

cd /opt/toozhub2/app
source .venv/bin/activate

echo "=== Ověření TOOZHUB_ADMIN_TENANT_ID ==="
echo ""

# Zkontrolovat .env soubor
echo "1. Kontrola .env souboru:"
if grep -q "TOOZHUB_ADMIN_TENANT_ID" .env; then
    echo "   ✅ TOOZHUB_ADMIN_TENANT_ID nalezeno v .env"
    grep "TOOZHUB_ADMIN_TENANT_ID" .env
else
    echo "   ❌ TOOZHUB_ADMIN_TENANT_ID NENALEZENO v .env"
fi
echo ""

# Ověřit načtení v Pythonu
echo "2. Ověření načtení v Pythonu:"
python3 << 'EOF'
import os
import sys
sys.path.insert(0, '/opt/toozhub2/app')

from dotenv import load_dotenv
load_dotenv('/opt/toozhub2/app/.env')

from src.modules.licensing.service import ADMIN_TENANT_ID

print(f"   ADMIN_TENANT_ID hodnota: {ADMIN_TENANT_ID}")
print(f"   Typ: {type(ADMIN_TENANT_ID)}")

if ADMIN_TENANT_ID is not None:
    print(f"   ✅ TOOZHUB_ADMIN_TENANT_ID je správně načteno")
else:
    print(f"   ❌ TOOZHUB_ADMIN_TENANT_ID není načteno (None)")
    
# Zkontrolovat také ENV proměnnou přímo
env_value = os.getenv("TOOZHUB_ADMIN_TENANT_ID")
print(f"   ENV proměnná (přímo): {env_value}")
EOF

echo ""
echo "=== Ověření dokončeno ==="
