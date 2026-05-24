# Rozhodovací pravidla — Správa vozidel

Tyto zásady platí pro vývoj, deploy a provoz. Porušení vyžaduje explicitní schválení.

## Source of truth

1. **Backend/server** definuje API kontrakty a business logiku.
2. **Web** je primární UI klient.
3. **Mobilní klienti** (iOS/Android) se přizpůsobují backendu.
4. **Staging** slouží k testování — není produkční source of truth.
5. **Nový repo** `toozservis-tech/sprava-vozidel` je source of truth pro kód.
6. **Starý repo** `toozservis-tech/TOOZHUB2` je archiv historie — nepoužívat pro deploy.

## Deploy a migrace

- **Žádný deploy bez zálohy DB.**
- **Žádné migrace bez migračního plánu** (co se mění, rollback, odhad downtime).
- **Žádné produkční změny bez plánu rollbacku** (git tag, snapshot DB, postup návratu).
- Produkční `.env` se nemění bez dokumentace a restartu backendu.

## Funkční omezení

- **Faktury** nejsou aktivní v produkci, dokud nebude dokončen účetní workflow a schválení.
- **GDPR VIN guard** je povinný: cizí VIN nesmí vracet SPZ, MDČR data ani data jiného uživatele.

## Git a repozitář

- Do Gitu **nikdy**: `.env`, DB soubory, `data/`, uploady, zálohy, private keys.
- Commit messages popisují *proč*, ne jen *co*.
- Feature větve merge do `main` přes review; produkční tagy pro každý deploy.

## Testování

- Automatické testy nesmí vytvářet náhodné uživatele v produkční nebo staging DB.
- Používejte pouze fixní E2E účty (`E2E_USER_EMAIL`, `E2E_SERVICE_EMAIL`).

## Kontakty (produkce)

- podpora@toozservis.cz
- +420 731 552 299

## Schvalování výjimek

Výjimku z těchto pravidel schvaluje vlastník produkce nebo `developer_admin` s písemným zdůvodněním v ticketu/PR.
