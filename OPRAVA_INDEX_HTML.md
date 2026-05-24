# Oprava duplicitního obsahu v index.html

## Problém
Soubor `web/index.html` obsahuje 3 kompletní HTML dokumenty, což způsobuje:
- Duplicitní ID elementů
- Chyby v konzoli prohlížeče
- Problémy s funkcionalitou aplikace

## Řešení

**DŮLEŽITÉ: Před spuštěním opravy ZAVŘETE soubor `web/index.html` v editoru!**

### Metoda 1: Python skript (doporučeno)

**PowerShell:**
```powershell
cd c:\Projects\sprava-vozidel
python -c "with open('web/index.html','r',encoding='utf-8') as f: lines=f.readlines(); first=[i for i,l in enumerate(lines) if '</html>' in l][0]; open('web/index.html','w',encoding='utf-8').writelines(lines[:first+1]); print(f'Opraveno: {len(lines[:first+1])} řádků z původních {len(lines)}')"
```

**Nebo použijte Python skript:**
```powershell
cd c:\Projects\sprava-vozidel
python fix_index_duplicates.py
```

### Metoda 2: PowerShell

```powershell
cd c:\Projects\sprava-vozidel\web
$lines = Get-Content index.html -Encoding UTF8
$firstEnd = ($lines | Select-String -Pattern '</html>' | Select-Object -First 1).LineNumber - 1
$lines[0..$firstEnd] | Set-Content index.html -Encoding UTF8
```

### Metoda 3: Ruční úprava

1. Otevřete `web/index.html` v textovém editoru
2. Najděte první výskyt `</html>` (mělo by být kolem řádku 4525)
3. Odstraňte vše od řádku 4526 až do konce souboru
4. Uložte soubor

## Ověření

Po opravě by měl soubor obsahovat pouze **1 výskyt** `</html>`:

```bash
grep -c "</html>" web/index.html
```

Mělo by vrátit: `1`

## Záloha

Před opravou je vytvořena záloha: `web/index.html.backup_duplicate_fix`








