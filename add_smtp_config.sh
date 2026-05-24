#!/bin/bash
# Skript pro přidání SMTP konfigurace do .env souboru

ENV_FILE="/opt/toozhub2/app/.env"

echo "=========================================="
echo "Nastavení SMTP konfigurace"
echo "=========================================="
echo ""

# Zkontrolovat, zda .env soubor existuje
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Soubor .env neexistuje!"
    exit 1
fi

# Zkontrolovat, zda už SMTP proměnné existují
if grep -q "SMTP_HOST" "$ENV_FILE"; then
    echo "⚠️  SMTP proměnné už existují v .env souboru."
    echo ""
    echo "Aktuální SMTP konfigurace:"
    grep "SMTP_" "$ENV_FILE" || echo "  (nenalezeno)"
    echo ""
    read -p "Chcete je přepsat? (y/n): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Zrušeno."
        exit 0
    fi
    # Odstranit staré SMTP řádky
    sed -i '/^SMTP_/d' "$ENV_FILE"
fi

echo "Zadejte SMTP údaje:"
echo ""

# SMTP_HOST
read -p "SMTP_HOST [smtp.mail.webnode.com]: " smtp_host
smtp_host=${smtp_host:-smtp.mail.webnode.com}

# SMTP_PORT
read -p "SMTP_PORT [465]: " smtp_port
smtp_port=${smtp_port:-465}

# SMTP_USER
read -p "SMTP_USER (email adresa): " smtp_user
if [ -z "$smtp_user" ]; then
    echo "❌ SMTP_USER je povinný!"
    exit 1
fi

# SMTP_PASSWORD
read -sp "SMTP_PASSWORD (heslo): " smtp_password
echo ""
if [ -z "$smtp_password" ]; then
    echo "❌ SMTP_PASSWORD je povinný!"
    exit 1
fi

# SMTP_FROM
read -p "SMTP_FROM [$smtp_user]: " smtp_from
smtp_from=${smtp_from:-$smtp_user}

# Přidat do .env souboru
echo "" >> "$ENV_FILE"
echo "# SMTP konfigurace pro odesílání emailů" >> "$ENV_FILE"
echo "SMTP_HOST=$smtp_host" >> "$ENV_FILE"
echo "SMTP_PORT=$smtp_port" >> "$ENV_FILE"
echo "SMTP_USER=$smtp_user" >> "$ENV_FILE"
echo "SMTP_PASSWORD=$smtp_password" >> "$ENV_FILE"
echo "SMTP_FROM=$smtp_from" >> "$ENV_FILE"

echo ""
echo "✓ SMTP konfigurace byla přidána do .env souboru"
echo ""
echo "Nyní restartujte backend:"
echo "  sudo systemctl restart toozhub-server"
echo ""
echo "A pak otestujte SMTP:"
echo "  cd /opt/toozhub2/app && python3 test_smtp_simple.py"
