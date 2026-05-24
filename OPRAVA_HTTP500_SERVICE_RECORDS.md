# Oprava HTTP 500 chyby v Service Records endpointu

## Problém
GET `/api/v1/vehicles/{id}/records` vrací HTTP 500 Internal Server Error.

## Provedené opravy

### 1. Oprava serializace záznamů
- ✅ Přidána kontrola a oprava None hodnot v `description` (model vyžaduje `nullable=False`)
- ✅ Přidán error handling pro každý záznam zvlášť - nevalidní záznamy se přeskočí místo selhání celého requestu
- ✅ Přidáno detailní logování chyb pro debugging

### 2. Oprava schema
- ✅ `ServiceRecordOutV1.performed_at` změněno na `Optional[datetime]`
- ✅ `ServiceRecordOutV1.description` má výchozí hodnotu `""`
- ✅ `ServiceRecordCreateV1.performed_at` změněno na `Optional[datetime]`
- ✅ `ServiceRecordCreateV1.description` má výchozí hodnotu `""`

### 3. Oprava vytváření záznamů
- ✅ Přidána kontrola, že `description` není None před uložením do databáze

## Testování

Pro otestování:
1. Restartujte server
2. Zkuste načíst servisní záznamy pro vozidlo
3. Zkontrolujte logy v `logs/toozhub2_stderr.log` pro případné chyby

## Možné další problémy

Pokud chyba přetrvává, zkontrolujte:
1. Zda jsou všechny záznamy v databázi validní (description není None)
2. Zda jsou všechny pole správně mapována mezi modelem a schema
3. Logy serveru pro detailní chybové zprávy
