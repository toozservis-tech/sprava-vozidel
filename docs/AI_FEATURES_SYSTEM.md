# 🤖 AI Feature Suggestion System

Automatický systém pro navrhování a správu nových funkcí v aplikaci Správa vozidel.

## 📋 Přehled

Systém automaticky analyzuje použití aplikace a navrhuje nové funkce, které by mohly zlepšit uživatelský zážitek. Všechny návrhy jsou kontrolovány na závislosti a kompatibilitu, aby vše na sebe krásně navazovalo.

## 🎯 Hlavní funkce

### 1. Analytics systém
- Sledování použití endpointů, modulů a funkcí
- Analýza vzorců použití
- Statistiky výkonu a chybovosti
- Sledování aktivních uživatelů

### 2. AI Feature Suggestion Engine
- Automatická analýza použití aplikace
- Navrhování nových funkcí na základě vzorců
- Identifikace chybějících integrací mezi moduly
- Detekce možností optimalizace výkonu
- Návrhy na automatizaci opakujících se úkolů

### 3. Dependency Checker
- Kontrola závislostí mezi funkcemi
- Validace kompatibility
- Detekce konfliktů
- Vytváření grafu závislostí

### 4. Feature Integration Manager
- Příprava plánu integrace
- Identifikace ovlivněných souborů
- Generování kódu pro automatickou implementaci
- Odhad složitosti implementace

### 5. UI komponenta
- Zobrazení navrhovaných funkcí
- Hlasování o návrzích
- Schvalování/odmítání návrhů
- Zobrazení statistik použití

## 🚀 Instalace

### 1. Migrace databáze

Spusťte migrační skript pro vytvoření tabulek:

```bash
python scripts/migrate_ai_features.py
```

### 2. Restart serveru

Restartujte FastAPI server, aby se načetly nové routery:

```bash
# Windows
python -m uvicorn src.server.main:app --host 0.0.0.0 --port 8000

# Nebo použijte start skript
.\start_server_production.bat
```

## 📊 Použití

### Spuštění analýzy

1. Otevřete aplikaci v prohlížeči
2. Přejděte na záložku "🤖 AI Návrhy"
3. Klikněte na tlačítko "🔍 Analyzovat a navrhnout"
4. Systém automaticky analyzuje použití aplikace za posledních 30 dní
5. Nové návrhy se zobrazí v seznamu

### Zobrazení návrhů

Všechny návrhy jsou zobrazeny na záložce "🤖 AI Návrhy" s následujícími informacemi:
- **Název a popis** funkce
- **Priorita** (0-100)
- **Jistota AI** (0-100%)
- **Kategorie** (vehicle, email, pdf, integration, atd.)
- **Složitost implementace** (low, medium, high)
- **Odhadovaný čas** implementace

### Schvalování návrhů

1. Klikněte na tlačítko "✅ Schválit" u návrhu
2. Návrh se přesune do stavu "approved"
3. Můžete zobrazit plán integrace kliknutím na "📋 Detail"

### Hlasování

Uživatelé mohou hlasovat o návrzích:
- 👍 **Pro** (vote = 1)
- 👎 **Proti** (vote = -1)
- 😐 **Neutrální** (vote = 0)

## 🔧 API Endpointy

### Získat návrhy
```
GET /api/v1/ai-features/suggestions
Query params:
  - status: suggested|approved|rejected|implemented|testing
  - category: vehicle|email|pdf|integration|...
  - limit: počet výsledků (default: 50)
```

### Spustit analýzu
```
POST /api/v1/ai-features/suggestions/analyze
Query params:
  - days: počet dní pro analýzu (default: 30)
```

### Schválit návrh
```
POST /api/v1/ai-features/suggestions/{id}/approve
```

### Odmítnout návrh
```
POST /api/v1/ai-features/suggestions/{id}/reject
```

### Hlasovat o návrhu
```
POST /api/v1/ai-features/suggestions/{id}/vote
Body:
{
  "vote": 1,  // 1 = pro, -1 = proti, 0 = neutrální
  "comment": "Volitelný komentář"
}
```

### Získat plán integrace
```
GET /api/v1/ai-features/suggestions/{id}/integration-plan
```

### Získat statistiky
```
GET /api/v1/ai-features/analytics/stats
Query params:
  - days: počet dní (default: 30)
```

## 📁 Struktura souborů

```
src/modules/ai_features/
├── __init__.py              # Export modulů
├── models.py                # Databázové modely
├── analytics.py             # Analytics systém
├── feature_engine.py        # AI Feature Suggestion Engine
├── dependency_checker.py    # Dependency Checker
├── integration_manager.py   # Feature Integration Manager
└── routers.py               # API routery

web/
└── ai-features.js           # UI komponenta

scripts/
└── migrate_ai_features.py   # Migrační skript
```

## 🗄️ Databázové tabulky

### usage_analytics
Sledování použití aplikace (endpointy, moduly, funkce)

### feature_suggestions
Navrhované funkce s metadaty a AI analýzou

### feature_votes
Hlasování uživatelů o návrzích

### feature_feedback
Zpětná vazba na implementované funkce

### feature_dependencies
Mapování závislostí mezi funkcemi

### auto_implementation_logs
Log automatických implementací

## 🎨 Typy návrhů

### Integrace
Navrhuje propojení mezi existujícími moduly (např. automatické emaily při změnách vozidel)

### Optimalizace výkonu
Identifikuje pomalé endpointy a navrhuje optimalizace

### Automatizace
Navrhuje automatizaci opakujících se úkolů

### Nové funkce
Navrhuje zcela nové funkce na základě vzorců použití

## 🔮 Budoucí vylepšení

- [ ] Automatická implementace jednoduchých funkcí
- [ ] Machine learning pro lepší předpovědi
- [ ] Integrace s GitHub Issues
- [ ] Notifikace o nových návrzích
- [ ] A/B testování navrhovaných funkcí
- [ ] Analýza konkurenčních aplikací

## 📝 Poznámky

- Systém analyzuje použití za posledních 30 dní (lze změnit)
- Návrhy jsou specifické pro každého tenanta (multi-tenant podpora)
- Automatická implementace je zatím v plánu, zatím se generují pouze plány integrace

## 🤝 Přispívání

Pokud máte nápad na vylepšení systému, vytvořte návrh pomocí samotného systému! 😊
