"""
Version management pro Správa vozidel
Funkce pro správu verzí a historie verzí
"""
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional

from src.core.branding import APP_DISPLAY_NAME

# Cesta ke kořenovému adresáři projektu
_project_root = Path(__file__).parent.parent.parent
_version_file = _project_root / "VERSION"


def read_version() -> str:
    """Načte verzi ze souboru VERSION"""
    try:
        if _version_file.exists():
            version = _version_file.read_text(encoding="utf-8").strip()
            return version
        else:
            # Fallback pokud soubor neexistuje
            return "2.1.0"
    except Exception as e:
        print(f"[VERSION] Warning: Nepodařilo se načíst verzi ze souboru VERSION: {e}")
        return "2.1.0"


def get_version_info() -> dict:
    """Vrací informace o verzi projektu"""
    version = read_version()
    build_time = datetime.now().isoformat()
    
    return {
        "project": APP_DISPLAY_NAME,
        "version": version,
        "build_time": build_time
    }


def log_version_update(db: Session, version: str, description: Optional[str] = None) -> bool:
    """Zapíše aktualizaci verze do historie"""
    try:
        from src.modules.vehicle_hub.models import VersionHistory
        
        # Kontrola, zda už tento záznam neexistuje (podle verze)
        existing = db.query(VersionHistory).filter(VersionHistory.version == version).first()
        if existing:
            print(f"[VERSION] Verze {version} už existuje v historii, přeskakuji")
            return True
        
        version_entry = VersionHistory(
            version=version,
            description=description,
            applied_at=datetime.utcnow()
        )
        
        db.add(version_entry)
        db.commit()
        db.refresh(version_entry)
        
        print(f"[VERSION] Zaznamenána aktualizace verze: {version} - {description or 'Bez popisu'}")
        return True
    except Exception as e:
        print(f"[VERSION] Chyba při zapisování verze do historie: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return False
