# MVP Scope Freeze (2026-02-22)

Tento dokument uzamyka scope pro stabilni release.

## Cíl

- Udrzet produkcni API stabilni.
- Odpojit experimentalni moduly, ktere maji otevrene TODO.
- Nezablokovat core flow (auth, vozidla, reminders, reservations, VIN/ARES).

## Stav po implementaci

- `ENABLE_AI_FEATURES`:
  - development default: `true`
  - production default: `false`
- `ENABLE_CUSTOMER_COMMANDS`:
  - development default: `true`
  - production default: `false`
- `ENABLE_AUTOPILOT_API`:
  - default: `true`

Feature flags jsou v `src/core/config.py` a jsou vystaveny i v `GET /api`.

## Dotcene casti serveru

- Podminkovane registrace routeru:
  - `AI Features` (`/api/v1/ai-features/*`)
  - `Customer Commands` (`/api/customer-commands/*`)
  - `Autopilot API` (`/api/autopilot/*`)
- Startup log vypise, pokud je modul preskocen pres feature flag.

## Operacni doporuceni

- Produkce:
  - nechat `ENABLE_AI_FEATURES=false`
  - nechat `ENABLE_CUSTOMER_COMMANDS=false`
- Pokud je potreba experimentalni modul zapnout:
  - nastavit flag v `.env`
  - restartovat server
  - overit endpointy pres smoke/E2E
