# 🚀 Rychlý start - Nasazení na hub.toozservis.cz

## ✅ Co už je hotovo

1. ✅ Konfigurace v `src/core/config.py` - podpora `PUBLIC_API_BASE_URL` a produkčních CORS
2. ✅ Dokumentace v `NASAZENI_HUB_TOOZSERVIS.md`
3. ✅ Hlavní produkční webová cesta je `web/index.html`
4. ✅ Iframe/Webnode materiály zůstávají jen jako legacy/compat varianta
5. ✅ Příklad `.env` souboru v `.env.example`

---

## 🎯 Rychlý postup nasazení

### 1. Cloudflare DNS (5 minut)

V Cloudflare Dashboard → DNS přidat:

```
Type: CNAME
Name: hub
Target: [váš-tunnel-hostname].cfargotunnel.com
Proxy: 🟡 Proxied
```

### 2. Cloudflare Tunnel config (2 minuty)

V `/etc/cloudflared/config.yml` přidat:

```yaml
ingress:
  - hostname: hub.toozservis.cz
    service: http://127.0.0.1:8000
  # ... ostatní hostname
```

```bash
sudo systemctl restart cloudflared
```

### 3. Konfigurace projektu (5 minut)

```bash
cd /home/toozservis/sprava-vozidel

# Vytvořit .env z příkladu
cp .env.example .env

# Upravit .env
nano .env
```

V `.env` nastavit:
```bash
ENVIRONMENT=production
PUBLIC_API_BASE_URL=https://hub.toozservis.cz
ALLOWED_ORIGINS=https://www.toozservis.cz,https://toozservis.cz
JWT_SECRET_KEY=[vygenerovat silný klíč]
```

Generování JWT secret:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 4. Webnode napojení (1 minuta)

```bash
# Doporučená produkční varianta:
# ve Webnode nastavit přesměrování na:
# https://hub.toozservis.cz/web/index.html
```

### 5. Restart serveru (1 minuta)

```bash
sudo systemctl restart toozhub-server
sudo systemctl status toozhub-server
```

### 6. Test (2 minuty)

```bash
# Health check
curl https://hub.toozservis.cz/health

# Web interface
curl -I https://hub.toozservis.cz/web/index.html
```

### 7. Vložení do Webnode (5 minut)

1. Otevřít Webnode editor
2. Otevřít stránku "SPRÁVA VOZIDEL" nebo vytvořit novou
3. Přidat HTML blok
4. Nastavit přesměrování na:
   `https://hub.toozservis.cz/web/index.html`
5. Uložit a publikovat

---

## 📋 Shrnutí

**Čas:** ~20 minut  
**Obtížnost:** Snadná  

**Po nasazení:**
- ✅ API běží na `https://hub.toozservis.cz`
- ✅ Web UI dostupný na `https://hub.toozservis.cz/web/index.html`
- ✅ Hlavní produktová cesta je `https://hub.toozservis.cz/web/index.html`
- ✅ Iframe varianta je pouze legacy/compat
- ✅ CORS správně nastaven
- ✅ Bezpečnostní klíče generovány

---

## 🔍 Kontrola, že vše funguje

1. **API health:**
   ```bash
   curl https://hub.toozservis.cz/health
   ```
   Očekáváno: `{"status":"online","service":"Správa vozidel API","version":"2.0.0"}`

2. **Web UI v prohlížeči:**
   Otevřít: `https://hub.toozservis.cz/web/index.html`

3. **Webnode redirect / compat varianta:**
   Ověřit, že stránka na Webnode vede na `https://hub.toozservis.cz/web/index.html`

---

## ❓ Problémy?

Viz `NASAZENI_HUB_TOOZSERVIS.md` sekce "🔟 Troubleshooting"

---

## 📝 Co dál?

Po úspěšném nasazení můžete:

1. Testovat API endpointy
2. Vytvořit uživatele přes `/user/register`
3. Přidat vozidla přes web UI
4. Nastavit automatické aktualizace Webnode (pokud chcete)

---

## ℹ️ Canonical mapa aktivních větví

Viz `PRODUCT_ENTRYPOINTS_STATUS.md`.

**Hotovo!** 🎉


