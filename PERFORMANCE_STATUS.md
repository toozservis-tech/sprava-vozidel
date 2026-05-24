# Performance Status

## Hlavní brzdy před sanací
- Web dashboard po přihlášení eager načítal více modulů najednou: capabilities, licence, Comgate config, push sync, managed service contacts, invite/claim token flow, reservations a reminders.
- `web/index.html` opakovaně znovu načítal stejné sekce při každém přepnutí tabu, i když už byly čerstvě vyrenderované.
- Web při startu spouštěl duplicitní `checkServerStatus()` a resize handler bez debounce.
- iOS taby znovu vytvářely vlastní `APIClient` a `StateObject` view modely, takže přepínání sekcí znovu spouštělo fetch a přepočet UI.
- `DashboardViewModel` na iOS tahal při prvním načtení vše najednou včetně sekundárních dat.
- `ServiceViewModel` na iOS načítal připomínky, discovery, kontakty, granty a settings bez ohledu na aktivní subrežim.
- Hlavní seznamové obrazovky na iOS používaly eager `VStack` v `ScrollView`, včetně detailu vozidla a seznamu servisních záznamů.

## Co bylo optimalizováno
- Sdílené iOS view modely jsou nyní vytvořené jednou v `AppEnvironment` a injektované přes `EnvironmentObject`.
- Dashboard na iOS načítá core payload prioritně a sekundární data (`monthlyCosts`, `notifications`) až po prvním renderu.
- Vehicles, Reservations, Service a Account view modely na iOS mají `loadIfNeeded`/TTL cache.
- `ServiceView` načítá podle aktivního režimu jen připomínky nebo servisní kontakty, ne obojí naráz.
- Hlavní iOS obrazovky a detail vozidla byly přepnuté na `LazyVStack`.
- `VehicleDetailView` už neblokuje první obraz kompletním renderem servisní historie. Nejprve zobrazí hero a základní statistiky, servisní historii odkládá až po prvním viditelném renderu.
- `VehicleDetailView` už nepřepočítává při každém redraw celé summary a filtrování záznamů přímo v `body`; používá lehký derived cache stav.
- Detail vozidla na iOS teď renderuje delší servisní historii po dávkách. Bez aktivního hledání/filtru se nejdřív vykreslí jen první sada záznamů a zbytek se otevře explicitně.
- Web dashboard odkládá ne-kritické úlohy přes idle/deferred scheduler místo eager startu.
- Web sekce `vehicles`, `reminders`, `reservations`, `profile`, `support` a `system capabilities` používají cache-aware načítání a při návratu do tabu nespouštějí zbytečný fetch.
- Web reminder settings listenery se po renderu navěšují přes `requestAnimationFrame`, ne fixní timeout.
- Web má základní performance debug markery pro dashboard primary load, vehicles render, reminders render a reservations render.

## Co je teď lazy / deferred
- `loadSystemCapabilities`
- licenční dropdown init a periodický licence refresh
- Comgate config a pending payment return info
- managed service contacts footer
- pending invite / reservation claim token flow
- silent push subscription sync
- service reservations/reminders prefetch po přihlášení servisního účtu
- iOS dashboard secondary metrics a notifications
- iOS service sekce mimo aktivní submode
- iOS detail vozidla: servisní historie a její plný seznam až po prvním viditelném renderu detailu
- iOS detail vozidla: delší seznam záznamů po dávkách místo eager vykreslení všeho najednou

## Co zůstává jako výkonový dluh
- `web/index.html` je stále jeden velmi velký soubor a render vozidel/připomínek stále skládá velké HTML stringy.
- `web_admin/admin.js` nebyl v této sanaci refaktorovaný, jen analyzovaný.
- `VehicleDetailView.swift` zůstává velmi rozsáhlý soubor; detail je rychlejší, ale soubor dál míchá lehký read-only detail s velmi těžkým formulářovým editorem servisního záznamu.
- `VehicleDetailViewModel` stále eager načítá detail vozidla a servisní historii paralelně už při vstupu do obrazovky. Perceived performance je lepší díky odloženému renderu, ale fetch orchestrace ještě není oddělená na primary a secondary payload.
- `MainTabView.swift` stále používá `switch` shell, takže view hierarchie tabů se přestavuje; sdílené view modely to zlevnily, ale neeliminovaly úplně.
- Web seznamy zatím nemají virtualizaci ani incremental DOM render pro extrémně velké datasety.

## Detail vozidla na iOS
- Kritická data pro první obraz: karta vozidla a základní servisní statistiky.
- Odložené sekce: servisní historie, její filtrační UI a delší seznam záznamů.
- Přidané debug markery: `open detail start`, `first visible render`, `service history render`.
- Aktuální cíl je perceived performance bez změny API a bez velkého refaktoru view modelů.
