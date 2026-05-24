# Licensing Module

Centralizovaný modul pro správu licencí a limitů v aplikaci Správa vozidel.

## Struktura

- `types.py` - Typy a enumy (LicenseStatus, EffectiveEntitlement)
- `licensing_service.py` - Hlavní logika (get_effective_entitlement, enforce_vehicle_limit)
- `dependencies.py` - FastAPI dependencies (get_current_plan, require_feature)

## Použití

### Kontrola limitu vozidel

```python
from src.modules.licensing import enforce_vehicle_limit

@router.post("/vehicles")
def create_vehicle(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Automaticky zkontroluje limit a vrátí 403 pokud je překročen
    enforce_vehicle_limit(db, current_user)
    
    # Vytvořit vozidlo...
```

### Kontrola feature flagu

```python
from src.modules.licensing import require_feature

@router.get("/advanced-report")
def get_advanced_report(
    _: None = Depends(require_feature("feature_advanced_reports")),
    current_user: Customer = Depends(get_current_user)
):
    # Tento endpoint je dostupný pouze pro licence s feature_advanced_reports=True
    return {"report": "..."}
```

### Získání efektivního oprávnění

```python
from src.modules.licensing import get_effective_entitlement

entitlement = get_effective_entitlement(db, customer)
print(f"Plán: {entitlement.plan.name}")
print(f"Status: {entitlement.status.value}")
print(f"Vozidla: {entitlement.vehicles_count}/{entitlement.vehicles_limit}")
print(f"Over limit: {entitlement.is_over_limit}")
```

## Integrace s TOOZ_service_hub

Pro budoucí integraci použijte `request_plan_change_via_service_hub()` - aktuálně je to placeholder.


















