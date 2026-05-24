#!/bin/bash
# Jednoduchý skript pro přidání SMTP údajů

ENV_FILE="/opt/toozhub2/app/.env"

echo "=========================================="
echo "PŘIDÁNÍ SMTP ÚDAJŮ"
echo "=========================================="
echo ""
echo "Zadejte SMTP údaje (nechte prázdné pro přeskočení):"
echo ""

read -p "SMTP_USER (email adresa): " smtp_user
read -sp "SMTP_PASSWORD (heslo): " smtp_password
echo ""

if [ -z "$smtp_user" ] || [ -z "$smtp_password" ]; then
    echo "❌ SMTP_USER a SMTP_PASSWORD jsou povinné!"
    exit 1
fi

# Aktualizovat .env soubor
sed -i "s/^SMTP_USER=.*/SMTP_USER=$smtp_user/" "$ENV_FILE"
sed -i "s/^SMTP_PASSWORD=.*/SMTP_PASSWORD=$smtp_password/" "$ENV_FILE"

echo ""
echo "✓ SMTP údaje byly přidány do .env souboru"
echo ""
echo "Nyní restartujte backend:"
echo "  sudo systemctl restart toozhub-server"
echo ""
echo "A otestujte:"
echo "  cd /opt/toozhub2/app && python3 test_smtp_simple.py"
