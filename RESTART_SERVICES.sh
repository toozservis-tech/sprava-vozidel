#!/bin/bash

# Skript pro restart backend serveru a Cloudflare tunnelu

echo "=========================================="
echo "Restart TooZ Hub 2 Services"
echo "=========================================="
echo ""

# Restart backend serveru
echo "🔄 Restartuji backend server (toozhub-server)..."
sudo systemctl restart toozhub-server

if [ $? -eq 0 ]; then
    echo "✅ Backend server restartován"
else
    echo "❌ Chyba při restartu backend serveru"
    exit 1
fi

# Počkat 2 sekundy
sleep 2

# Restart Cloudflare tunnelu
echo "🔄 Restartuji Cloudflare tunnel (cloudflared)..."
sudo systemctl restart cloudflared

if [ $? -eq 0 ]; then
    echo "✅ Cloudflare tunnel restartován"
else
    echo "❌ Chyba při restartu Cloudflare tunnelu"
    exit 1
fi

# Počkat 3 sekundy
sleep 3

# Ověření stavu
echo ""
echo "=========================================="
echo "Ověření stavu služeb"
echo "=========================================="
echo ""

echo "📊 Backend server:"
systemctl status toozhub-server --no-pager | head -5

echo ""
echo "📊 Cloudflare tunnel:"
systemctl status cloudflared --no-pager | head -5

echo ""
echo "🌐 Test lokálního serveru:"
curl -s http://127.0.0.1:8000/web/index.html 2>&1 | grep -o '<title>.*</title>' | head -1

echo ""
echo "✅ Restart dokončen!"
echo ""
echo "⚠️  Pokud vidíš chyby, zkontroluj logy:"
echo "   sudo journalctl -u toozhub-server -n 20"
echo "   sudo journalctl -u cloudflared -n 20"
