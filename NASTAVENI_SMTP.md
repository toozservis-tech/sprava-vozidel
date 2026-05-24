# Nastavení SMTP pro odesílání emailů

## Problém
Email nedorazí, protože SMTP údaje nejsou nastaveny v `.env` souboru.

## Řešení

### 1. Přidat SMTP údaje do `.env` souboru

Otevřete soubor `/opt/toozhub2/app/.env` a přidejte následující řádky:

```bash
# SMTP konfigurace pro odesílání emailů
SMTP_HOST=smtp.mail.webnode.com
SMTP_PORT=465
SMTP_USER=vase-emailova-adresa@example.com
SMTP_PASSWORD=vase-heslo-nebo-app-password
SMTP_FROM=info@toozservis.cz
```

### 2. Kde získat SMTP údaje?

#### Pro Webnode:
- **SMTP_HOST**: `smtp.mail.webnode.com` (již nastaveno)
- **SMTP_PORT**: `465` (již nastaveno)
- **SMTP_USER**: Vaše emailová adresa (např. `info@toozservis.cz`)
- **SMTP_PASSWORD**: Heslo k emailu nebo "App Password" (pokud máte zapnutou 2FA)
- **SMTP_FROM**: Emailová adresa odesílatele (obvykle stejná jako SMTP_USER)

#### Pro jiné poskytovatele:
- **Gmail**: 
  - SMTP_HOST: `smtp.gmail.com`
  - SMTP_PORT: `465` (SSL) nebo `587` (STARTTLS)
  - SMTP_USER: vaše Gmail adresa
  - SMTP_PASSWORD: App Password (musíte vytvořit v Google účtu)
  
- **Outlook/Office365**:
  - SMTP_HOST: `smtp-mail.outlook.com`
  - SMTP_PORT: `587`
  - SMTP_USER: vaše Outlook adresa
  - SMTP_PASSWORD: vaše heslo

### 3. Testování SMTP konfigurace

Po přidání údajů do `.env` souboru můžete otestovat konfiguraci:

```bash
cd /opt/toozhub2/app
python3 test_smtp_simple.py
```

### 4. Restart backendu

Po přidání SMTP údajů je potřeba restartovat backend:

```bash
sudo systemctl restart toozhub-server
```

### 5. Ověření, že email funguje

1. Otevřete aplikaci: https://hub.toozservis.cz/web/index.html
2. Klikněte na "Zapomenuté heslo?"
3. Zadejte emailovou adresu
4. Zkontrolujte, zda dorazil email (i ve složce spam)

## Bezpečnost

⚠️ **DŮLEŽITÉ**: 
- `.env` soubor obsahuje citlivé údaje (hesla)
- Nikdy ho necommitněte do Gitu
- Ujistěte se, že má správná oprávnění: `chmod 600 .env`

## Řešení problémů

### Email stále nedorazí:

1. **Zkontrolujte logy backendu:**
   ```bash
   sudo journalctl -u toozhub-server -n 50 --no-pager | grep -i "email\|smtp\|reset"
   ```

2. **Otestujte SMTP připojení:**
   ```bash
   cd /opt/toozhub2/app
   python3 test_smtp_simple.py
   ```

3. **Běžné problémy:**
   - Chyba autentizace → zkontrolujte SMTP_USER a SMTP_PASSWORD
   - Chyba připojení → zkontrolujte SMTP_HOST a SMTP_PORT
   - Email dorazí do spamu → zkontrolujte SPF/DKIM záznamy v DNS

## Kontakt

Pokud máte problémy s nastavením SMTP, kontaktujte administrátora.
