#!/bin/bash
# Skript pro opravu oprávnění souborů v projektu

set -e

echo "========================================="
echo "Oprava oprávnění pro /opt/toozhub2/app"
echo "========================================="
echo ""

# 1. Diagnostika před opravou
echo "📋 DIAGNOSTIKA PŘED OPRAVOU:"
echo "---"
echo "Soubor: /opt/toozhub2/app/src/modules/licensing/service.py"
ls -l /opt/toozhub2/app/src/modules/licensing/service.py || echo "Soubor neexistuje"
echo ""
echo "Soubor: /opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/license_status.py"
ls -l /opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/license_status.py || echo "Soubor neexistuje"
echo ""

# 2. Oprava vlastnictví
echo "🔧 OPRAVA VLASTNICTVÍ:"
echo "Nastavuji vlastníka toozhub2:toozhub2 pro celý projekt..."
sudo chown -R toozhub2:toozhub2 /opt/toozhub2/app
echo "✅ Vlastnictví změněno"
echo ""

# 3. Odstranění ACL (pokud existují)
echo "🔧 ODSTRANĚNÍ ACL:"
sudo setfacl -bR /opt/toozhub2/app 2>&1 || echo "ACL odstraněny nebo neexistují"
echo ""

# 4. Nastavení práv pro složky
echo "🔧 NASTAVENÍ PRÁV PRO SLOŽKY (775):"
sudo find /opt/toozhub2/app -type d -exec chmod 775 {} \;
echo "✅ Práva pro složky nastavena"
echo ""

# 5. Nastavení práv pro soubory
echo "🔧 NASTAVENÍ PRÁV PRO SOUBORY (664):"
sudo find /opt/toozhub2/app -type f -exec chmod 664 {} \;
echo "✅ Práva pro soubory nastavena"
echo ""

# 6. Ověření po opravě
echo "📋 OVĚŘENÍ PO OPRAVĚ:"
echo "---"
echo "Soubor: /opt/toozhub2/app/src/modules/licensing/service.py"
ls -l /opt/toozhub2/app/src/modules/licensing/service.py
echo ""
echo "Soubor: /opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/license_status.py"
ls -l /opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/license_status.py
echo ""

# 7. Test zápisu
echo "🧪 TEST ZÁPISU:"
echo "Testuji zápis do service.py..."
if echo "#perm-test" | tee -a /opt/toozhub2/app/src/modules/licensing/service.py >/dev/null 2>&1; then
    echo "✅ Zápis do service.py: OK"
    sed -i '/#perm-test/d' /opt/toozhub2/app/src/modules/licensing/service.py
    echo "✅ Testovací řádek odstraněn"
else
    echo "❌ Zápis do service.py: FAILED"
fi

echo ""
echo "Testuji vytvoření souboru..."
if touch /opt/toozhub2/app/.perm_write_test 2>/dev/null && rm /opt/toozhub2/app/.perm_write_test 2>/dev/null; then
    echo "✅ Vytvoření a mazání souboru: OK"
else
    echo "❌ Vytvoření souboru: FAILED"
fi

echo ""
echo "========================================="
echo "✅ OPRAVA DOKONČENA"
echo "========================================="
echo ""
echo "Výsledek:"
echo "- Vlastník: toozhub2:toozhub2"
echo "- Složky: 775 (rwxrwxr-x)"
echo "- Soubory: 664 (rw-rw-r--)"
echo ""
echo "VS Code Remote by nyní měl umět ukládat soubory bez EACCES chyby."
