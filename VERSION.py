"""
Verzování aplikace Správa vozidel.
Čte semver ze souboru VERSION v kořenovém adresáři projektu.
"""
from pathlib import Path
from datetime import datetime

_project_root = Path(__file__).parent
_version_file = _project_root / "VERSION"


def _read_version():
    """Načte verzi ze souboru VERSION."""
    try:
        if _version_file.exists():
            return _version_file.read_text(encoding="utf-8").strip()
        return "2.1.0"
    except Exception as e:
        print(f"[VERSION] Warning: Nepodařilo se načíst verzi ze souboru VERSION: {e}")
        return "2.1.0"


__version__ = _read_version()
__version_name__ = f"Správa vozidel {__version__}"
__build_date__ = datetime.now().strftime("%Y-%m-%d")
__update_info__ = "Kompletní redesign UI + zavedení verzování"

VERSION = __version__
VERSION_NAME = __version_name__
BUILD_DATE = __build_date__
UPDATE_INFO = __update_info__
