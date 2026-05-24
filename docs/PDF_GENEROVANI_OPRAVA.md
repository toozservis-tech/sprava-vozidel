# 🔧 Oprava generování PDF - UTF-8 kódování

## Problém
Chyba při generování PDF: `'latin-1' codec can't encode character '\u0160'`

## Příčina
1. **Content-Disposition header** - název souboru s českými znaky nebyl správně kódován
2. **PDF obsah** - texty v PDF nebyly správně escapovány pro UTF-8

## Opravy

### 1. ✅ Kódování názvu souboru
- Použití RFC 5987 encoding pro UTF-8 znaky v Content-Disposition headeru
- ASCII-safe fallback název souboru
- URL encoding pro UTF-8 verzi

### 2. ✅ Escape HTML v PDF obsahu
- Všechny texty jsou escapovány pomocí `escape_html()` funkce
- Odstranění diakritiky z názvu souboru pomocí `unicodedata.normalize()`

### 3. ✅ Footer bez diakritiky
- Footer používá text bez českých znaků (drawString limitation)

## Co je potřeba

**⚠️ DŮLEŽITÉ: Restartovat server!**

Server musí být restartován, aby se načetl nový kód. Pokud server běží, je potřeba ho restartovat.

## Testování

Po restartu serveru:
1. Zkusit vygenerovat PDF pro vozidlo s českými znaky v názvu
2. Zkontrolovat, že se PDF stáhne bez chyby
3. Ověřit, že PDF obsahuje správně zobrazené české znaky

---

**Datum opravy:** 12. prosince 2025  
**Status:** ✅ Opraveno - čeká na restart serveru

