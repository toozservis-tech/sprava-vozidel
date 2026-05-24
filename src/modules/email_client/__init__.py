"""Email Client modul"""
from .service import EmailService, EmailMessage

# GUI komponenta se importuje pouze pokud je potřeba (lazy import)
# aby se zabránilo importu PySide6 v backend API
try:
    from .controller import EmailClientWidget
    __all__ = ["EmailService", "EmailMessage", "EmailClientWidget"]
except ImportError:
    # GUI není dostupné (např. na serveru bez X11)
    __all__ = ["EmailService", "EmailMessage"]






