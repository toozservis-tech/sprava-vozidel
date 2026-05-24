"""
Migrační skript pro vytvoření tabulek AI Feature Suggestion System
"""
import sys
from pathlib import Path

# Přidat kořenový adresář do path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.modules.vehicle_hub.database import engine, Base
# Importovat modely z vehicle_hub, aby byly v Base.metadata (pro foreign keys)
from src.modules.vehicle_hub.models import Tenant, Customer, Vehicle
from src.modules.ai_features.models import (
    UsageAnalytics,
    FeatureSuggestion,
    FeatureVote,
    FeatureFeedback,
    FeatureDependency,
    AutoImplementationLog
)

def migrate():
    """Vytvořit všechny tabulky pro AI Features"""
    
    print("[MIGRATION] Vytváření tabulek pro AI Feature Suggestion System...")
    
    try:
        # Vytvořit všechny tabulky (včetně závislostí jako tenants)
        # Base.metadata.create_all vytvoří všechny tabulky, které jsou definované v Base
        Base.metadata.create_all(bind=engine)
        
        print("[MIGRATION] OK: Tabulky uspesne vytvoreny!")
        print("[MIGRATION] Vytvorene tabulky:")
        print("  - usage_analytics")
        print("  - feature_suggestions")
        print("  - feature_votes")
        print("  - feature_feedback")
        print("  - feature_dependencies")
        print("  - auto_implementation_logs")
        
    except Exception as e:
        print(f"[MIGRATION] CHYBA: Chyba pri vytvareni tabulek: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    migrate()

