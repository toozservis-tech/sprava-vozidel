#!/bin/bash

# Skript pro přidání MDČR API klíče do .env souboru

ENV_FILE="/opt/toozhub2/app/.env"

echo "=========================================="
echo "Přidání MDČR API klíče do .env souboru"
echo "=========================================="
echo ""

# Zkontrolovat, zda .env existuje
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env soubor neexistuje!"
    exit 1
fi

# Zkontrolovat, zda už klíč není nastaven
if grep -q "^DATAOVO_API_KEY=" "$ENV_FILE" && ! grep -q "^DATAOVO_API_KEY=$" "$ENV_FILE"; then
    echo "✅ DATAOVO_API_KEY už je nastaven v .env"
    echo ""
    echo "Aktuální hodnota:"
    grep "^DATAOVO_API_KEY=" "$ENV_FILE" | sed 's/=.*/=***/' 
    echo ""
    read -p "Chceš ho přepsat? (ano/ne): " overwrite
    if [ "$overwrite" != "ano" ]; then
        echo "Zrušeno."
        exit 0
    fi
    # Odstranit starý řádek
    sed -i '/^DATAOVO_API_KEY=/d' "$ENV_FILE"
fi

# Požádat uživatele o API klíč
echo "Zadej MDČR API klíč (z dataovozidlech.cz):"
read -s api_key

if [ -z "$api_key" ]; then
    echo "❌ API klíč nemůže být prázdný!"
    exit 1
fi

# Odstranit prázdný řádek DATAOVO_API_KEY= pokud existuje
sed -i '/^DATAOVO_API_KEY=$/d' "$ENV_FILE"

# Přidat klíč na konec souboru
echo "" >> "$ENV_FILE"
echo "# MDČR API (dataovozidlech.cz)" >> "$ENV_FILE"
echo "DATAOVO_API_KEY=$api_key" >> "$ENV_FILE"

echo ""
echo "✅ API klíč byl přidán do .env souboru"
echo ""
echo "⚠️  DŮLEŽITÉ: Restartuj backend, aby se změny projevily:"
echo "   pkill -f 'uvicorn.*main:app'"
echo "   cd /opt/toozhub2/app && source .venv/bin/activate && nohup python3 -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000 > /tmp/toozhub.log 2>&1 &"
echo ""
