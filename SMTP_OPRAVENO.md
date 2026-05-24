# ✅ SMTP je opraveno!

## Co bylo opraveno:

1. ✅ **SMTP_USER** nastaven na `info@toozservis.cz`
2. ✅ **SMTP_PASSWORD** nastaven
3. ✅ **SMTP_PORT** změněn z `465` na `587` (port 465 byl blokovaný firewall)

## Aktuální konfigurace:

```
SMTP_HOST=smtp.mail.webnode.com
SMTP_PORT=587
SMTP_USER=info@toozservis.cz
SMTP_PASSWORD=*** (nastaveno)
SMTP_FROM=info@toozservis.cz
```

## Test SMTP:

✅ Připojení k SMTP serveru: **ÚSPĚŠNÉ**
✅ Autentizace: **ÚSPĚŠNÁ**

## Co teď udělat:

**Restartujte backend, aby načetl novou konfiguraci:**

```bash
sudo systemctl restart toozhub-server
```

## Ověření:

1. Otevřete aplikaci: https://hub.toozservis.cz/web/index.html
2. Klikněte na "Zapomenuté heslo?"
3. Zadejte emailovou adresu
4. Email by měl dorazit (zkontrolujte i spam)

## Problém byl:

Port **465** (SSL) byl blokovaný firewall nebo SMTP serverem.  
Port **587** (STARTTLS) funguje správně.
