# LEGAL_DIFF.md

## Co bylo právně slabé
- Obchodní podmínky měly obecné formulace, ale slabé vymezení digitální služby, technických limitů, kompatibility a důkazní síly logů.
- U spotřebitelských práv byly málo přesně popsány nároky z vad digitální služby (příliš obecný rámec, důraz na tradiční model reklamací).
- Odstoupení od smlouvy nebylo procesně dotaženo pro online digitální plnění po úhradě.
- Reklamační řád neodděloval dostatečně technickou vadu, platební chybu, nesoulad tarifu, uživatelskou chybu a neověřený AI/OCR výstup.
- GDPR dokument neodděloval systematicky data o vozidle, osobní údaje a provozní/auditní data; role správce vs. zpracovatele byly popsané jen obecně.
- Cookies dokument byl právně i technicky příliš obecný a neobsahoval konkrétní přehled reálných klíčů/úložišť.
- Platební podmínky měly slabší anti-fraud/chargeback obranu a méně přesný popis aktivace pouze po finálním platebním stavu.
- Dokumenty nebyly dost sjednocené v důkazních pravidlech, verzi dokumentu a systematickém cross-linkingu.

## Co bylo upraveno
- Kompletní přepis `web/obchodni-podminky.html` pro režim digitální služby včetně: hlavních vlastností, tarifních rozdílů, kompatibility/interoperability, technických požadavků, aktualizací/maintenance, AI/OCR disclaimeru, anti-abuse pravidel, bezpečnostních zásahů, důkazní role logů, režimu ukončení a exportu dat.
- V obchodních podmínkách i reklamačním řádu doplněn korektní spotřebitelský režim vad digitální služby: odstranění vady v přiměřené době, sleva/odstoupení při splnění zákonných podmínek, zákaz odstoupení pro nevýznamnou vadu.
- Zpřesněn režim odstoupení pro digitální službu zahájenou před uplynutím 14 dnů na základě aktivního potvrzení spotřebitele.
- Do obchodních a platebních podmínek doplněna logika důkazního záznamu souhlasu (timestamp, user ID, text souhlasu, verze dokumentu, IP/relace pokud dostupná) a doporučení potvrzovacího e-mailu na trvalém nosiči.
- Kompletní přepis `web/reklamacni-rad.html` na digitální službu Správa vozidel: přesné kategorie podání, co není reklamace, procesní workflow, možnost vyžádat součinnost, důkazní význam auditních/payment logů, pravidla refundací.
- Kompletní přepis `web/ochrana-osobnich-udaju.html` s novými sekcemi: „Údaje o vozidle vs. údaje o osobě“, role správce vs. zpracovatele, autorizace vložení údajů, ověření identity při výkonu práv, retenční kritéria, příjemci/zpracovatelé, třetí země, prevence podvodů a obhajoba nároků.
- Kompletní přepis `web/cookies.html` s technicky konkrétní tabulkou reálně používaných klíčů localStorage/sessionStorage a výslovným potvrzením, že nejsou aktivní analytické/marketingové cookies.
- Kompletní přepis `web/platebni-podminky.html` ve prospěch poskytovatele: aktivace pouze po `PAID`, explicitní vyloučení nároku při `PENDING/CANCELLED/FAILED/EXPIRED`, risk/fraud/chargeback kontrola, jasná refund logika.
- Ve všech dokumentech sjednocena identifikace poskytovatele, kontaktní e-mail, brand logika (Správa vozidel = služba; TooZ Servis = poskytovatel), verze dokumentu, datum účinnosti, věta o online aktuální verzi a cross-linking.
- Do každého HTML souboru doplněn závěrečný komentář `<!-- CHANGES: ... -->`.

## Proč je to lepší pro poskytovatele
- Vyšší obranyschopnost ve sporech: dokumenty explicitně pracují s auditními, systémovými, transakčními a časovými záznamy jako primárními důkazy.
- Silnější anti-abuse rámec umožňuje rychlejší zásahy při zneužití účtu, scrapingu, obcházení limitů a bezpečnostních incidentech.
- Platební režim je procesně přísnější a snižuje riziko neoprávněných aktivací, refund pressure a chargeback zneužití.
- Reklamace jsou nově strukturované podle typu problému, což omezuje falešné nebo nekonkrétní nároky.
- GDPR text lépe odděluje role a datové vrstvy, což snižuje regulatorní riziko a zvyšuje důkazní čistotu při kontrolách.
- Současně zůstává zachována zákonná ochrana spotřebitele a nejsou vložena zjevně neplatná ujednání.

## Co ještě závisí na skutečné implementaci aplikace
- Nutno potvrdit implementací: serverové ukládání „klik-through“ souhlasů před platbou v plném důkazním rozsahu (timestamp, user ID, text souhlasu, verze dokumentu, IP/relace).
- Nutno potvrdit implementací: automatické zaslání potvrzení uzavření smlouvy a právních dokumentů/jejich verze na trvalém nosiči po objednávce.
- Nutno potvrdit implementací: technická retence/purge logů podle deklarovaných retenčních kritérií (včetně záloh).
- Nutno potvrdit implementací: přesný seznam případných infrastrukturních cookies třetích stran v produkčním prostředí.
- Nutno potvrdit implementací: zda a kdy budou aktivovány externí AI/OCR subjekty a případné přenosy mimo EU/EHP.
- Nutno potvrdit implementací: budoucí consent banner pro volitelné cookies (accept all / reject all / settings) s rovnocenně snadným odmítnutím.
- Nutno potvrdit implementací: rozsah exportu dat při ukončení účtu v jednotlivých scénářích (běžné ukončení vs. okamžité smazání účtu) a případné limity mimo systémový export.
