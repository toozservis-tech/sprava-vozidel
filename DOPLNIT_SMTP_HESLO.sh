#!/bin/bash
# Skript pro doplnění SMTP hesla

ENV_FILE="/opt/toozhub2/app/.env"

echo "=========================================="
echo "DOPLNĚNÍ SMTP HESLA"
echo "=========================================="
echo ""
echo "Aktuální konfigurace:"
grep "^SMTP_" "$ENV_FILE"
echo ""
echo "Zadejte SMTP heslo pro info@toozservis.cz:"
read -sp "SMTP_PASSWORD: " smtp_password
echo ""

if [ -z "$smtp_password" ]; then
    echo "❌ Heslo nemůže být prázdné!"
    exit 1
fi

# Aktualizovat heslo v .env
sed -i "s/^SMTP_PASSWORD=.*/SMTP_PASSWORD=$smtp_password/" "$ENV_FILE"

echo ""
echo "✓ SMTP heslo bylo přidáno"
echo ""
echo "Nyní restartujte backend:"
echo "  sudo systemctl restart toozhub-server"
echo ""
echo "A otestujte:"
echo "  cd /opt/toozhub2/app && python3 test_smtp_simple.py"
