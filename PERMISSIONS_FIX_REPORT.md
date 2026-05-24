# Report: Oprava oprávnění souborů

## Problém
VS Code Remote/Cursor nemohl ukládat soubory:
- `/opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/license_status.py`
- `/opt/toozhub2/app/src/modules/licensing/service.py`

Chyba: `EACCES permission denied (NoPermissions FileSystemError)`

## Diagnostika (před opravou)

### Stav souborů:
```
-rw-r--r-- 1 root root 7171 Dec 30 19:09 /opt/toozhub2/app/src/modules/licensing/service.py
-rw-r--r-- 1 root root 1311 Dec 30 19:09 /opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/license_status.py
```

**Problém:** Oba soubory byly vlastněny uživatelem `root` s právy `-rw-r--r--` (644), což znamená:
- Vlastník (root): rw- (čtení + zápis)
- Skupina: r-- (pouze čtení)
- Ostatní: r-- (pouze čtení)

Uživatel `toozhub2` nemohl zapisovat do těchto souborů.

### Stav složek:
```
drwxrwxr-x 18 toozhub2 toozhub2 12288 Jan  4 18:44 /opt/toozhub2/app
drwxrwxr-x  8 toozhub2 toozhub2  4096 Dec 28 13:20 /opt/toozhub2/app/src
drwxrwxr-x 11 toozhub2 toozhub2  4096 Dec 28 13:20 /opt/toozhub2/app/src/modules
```

Složky byly již správně vlastněny uživatelem `toozhub2`.

### ACL:
ACL byly přítomny, ale nebyly omezující. Vlastník byl nastaven jako `root`.

### Běžící služba:
```
toozhub2 1081602 ... uvicorn src.server.main:app ...
```
Uvicorn běží jako uživatel `toozhub2`, takže po opravě nebude potřeba měnit vlastníka služby.

---

## Oprava

Byl vytvořen skript `/opt/toozhub2/app/fix_permissions.sh`, který provede:

1. **Změna vlastnictví:**
   ```bash
   sudo chown -R toozhub2:toozhub2 /opt/toozhub2/app
   ```

2. **Odstranění ACL:**
   ```bash
   sudo setfacl -bR /opt/toozhub2/app
   ```

3. **Nastavení práv pro složky:**
   ```bash
   sudo find /opt/toozhub2/app -type d -exec chmod 775 {} \;
   ```
   - `775` = `rwxrwxr-x` (vlastník a skupina: rwx, ostatní: r-x)

4. **Nastavení práv pro soubory:**
   ```bash
   sudo find /opt/toozhub2/app -type f -exec chmod 664 {} \;
   ```
   - `664` = `rw-rw-r--` (vlastník a skupina: rw-, ostatní: r--)

---

## Spuštění opravy

**Spusťte následující příkaz na serveru jako uživatel toozhub2:**
```bash
cd /opt/toozhub2/app
./fix_permissions.sh
```

Nebo ručně:
```bash
sudo chown -R toozhub2:toozhub2 /opt/toozhub2/app
sudo setfacl -bR /opt/toozhub2/app
sudo find /opt/toozhub2/app -type d -exec chmod 775 {} \;
sudo find /opt/toozhub2/app -type f -exec chmod 664 {} \;
```

---

## Očekávaný výsledek

Po spuštění opravy:
- ✅ Všechny soubory budou vlastněny `toozhub2:toozhub2`
- ✅ Složky budou mít práva `775` (rwxrwxr-x)
- ✅ Soubory budou mít práva `664` (rw-rw-r--)
- ✅ VS Code Remote bude moci ukládat soubory bez EACCES chyby
- ✅ Uvicorn služba (běží jako toozhub2) bude moci číst soubory

---

## Ověření

Po opravě ověřte:
```bash
# Zkontrolovat vlastníka a práva
ls -l /opt/toozhub2/app/src/modules/licensing/service.py
ls -l /opt/toozhub2/app/src/modules/vehicle_hub/routers_v1/license_status.py

# Test zápisu
echo "test" >> /opt/toozhub2/app/src/modules/licensing/service.py
# (pak řádek smažte)
```

---

**Poznámka:** Pokud stále máte problémy po spuštění opravy, zkontrolujte:
- Zda VS Code Remote běží jako uživatel `toozhub2`
- Zda nejsou nastaveny další ACL omezující přístup
- Zda nejsou soubory zamčené jiným procesem
