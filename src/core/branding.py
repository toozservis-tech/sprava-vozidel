"""
Display and lightweight technical branding for Správa vozidel.

User-facing strings must use APP_DISPLAY_NAME (and related helpers).

Heavy technical identifiers (Python package paths, Xcode target names, some env
vars, GitHub repo slug) may still use legacy tokens until a compatibility
refactor — see TECHNICAL_RENAME_BACKLOG.md.
"""

APP_DISPLAY_NAME = "Správa vozidel"
APP_DISPLAY_NAME_GENITIVE = "Správy vozidel"

# Transakční e-maily: pouze název produktu (APP_DISPLAY_NAME), bez legacy obchodních slov v textu.
APP_EMAIL_TAGLINE = "Servisní historie, dokumenty a připomínky — přehledně na jednom místě."
# Krátká nálada v těle e-mailu (pod hlavičkou značky)
APP_EMAIL_MOOD_LINE = "Vozidla, servis a termíny — přehledně, bez papírování."
APP_API_DISPLAY_NAME = f"{APP_DISPLAY_NAME} API"
APP_SUPPORT_DISPLAY_NAME = f"{APP_DISPLAY_NAME} Podpora"
APP_EXPORT_DISPLAY_NAME = APP_DISPLAY_NAME

# Health / JSON ops fields (human-readable, stable for dashboards)
APP_OPS_PROJECT_LABEL = APP_DISPLAY_NAME

# HTTP Server header and User-Agent product token (ASCII, no spaces)
APP_SERVER_PRODUCT_TOKEN = "SpravaVozidel"

# Web Push: postMessage type between service worker and page (must match sw.js + web client)
WEB_PUSH_CLIENT_MESSAGE_TYPE = "SPRAVA_VOZIDEL_NOTIFICATION_CLICK"

# Standalone file-share mini app (FastAPI title + HTML)
APP_FILESHARE_DISPLAY_NAME = f"{APP_DISPLAY_NAME} – sdílení souborů"
