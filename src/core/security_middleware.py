"""
Security Middleware pro Správu vozidel
- Security headers
- Rate limiting
- Anti-tampering
- Source code probing guard
- Admin síťová politika (volitelný allowlist)
- HTTPS redirect (za reverse proxy)
"""
import ipaddress
import os
import threading
import time
from collections import defaultdict
from urllib.parse import parse_qsl, unquote
from typing import Any, Callable, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.core.branding import APP_SERVER_PRODUCT_TOKEN
from src.core.cloudflare_access import (
    cloudflare_access_admin_protection_enabled,
    normalize_cf_access_team_domain,
    parse_cf_access_allowed_emails,
    parse_cf_access_audiences,
    verify_cf_access_jwt_assertion,
)
from src.core.config import ALLOWED_ORIGINS, ENVIRONMENT
from src.server.security_tracking import extract_client_ip

# Rate limiting - ukládání požadavků
rate_limit_store = defaultdict(list)

_SOURCE_PROTECTION_ENABLED = os.getenv("ENABLE_SOURCE_PROTECTION", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
_SOURCE_ALERT_EMAIL_ENABLED = os.getenv("ENABLE_SOURCE_PROTECTION_EMAIL_ALERTS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_SOURCE_PROTECTED_ROOT_SEGMENTS = {
    ".git",
    ".github",
    ".pytest_cache",
    ".mypy_cache",
    ".ssh",
    "__pycache__",
    "alembic",
    "backups",
    "cloudflared",
    "data",
    "logs",
    "scripts",
    "src",
    "tests",
    "tray",
    "venv",
    ".venv",
}
_SOURCE_PROTECTED_EXACT_NAMES = {
    ".env",
    ".env.backup",
    ".env.example",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
}
_SOURCE_PROTECTED_SUFFIXES = (
    ".bak",
    ".backup",
    ".crt",
    ".db",
    ".key",
    ".pem",
    ".py",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sql",
)
try:
    _SOURCE_ALERT_EMAIL_THROTTLE_SEC = max(
        60,
        int(os.getenv("SOURCE_PROTECTION_ALERT_THROTTLE_SEC", "900")),
    )
except ValueError:
    _SOURCE_ALERT_EMAIL_THROTTLE_SEC = 900
_source_alert_email_last: dict[str, float] = {}


def _decode_repeated(value: str) -> str:
    decoded = str(value or "")
    for _ in range(3):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return decoded


def _looks_like_source_probe(value: str) -> tuple[bool, str | None]:
    decoded = _decode_repeated(value).replace("\\", "/").strip()
    if not decoded:
        return False, None

    normalized = decoded.lower().split("?", 1)[0].split("#", 1)[0]
    parts = [part for part in normalized.strip("/").split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        return True, "path_traversal"
    if not parts:
        return False, None

    first = parts[0]
    if first in _SOURCE_PROTECTED_ROOT_SEGMENTS:
        return True, f"protected_root:{first}"

    for part in parts:
        if part.startswith("."):
            return True, f"hidden_segment:{part}"
        if part in _SOURCE_PROTECTED_EXACT_NAMES:
            return True, f"protected_name:{part}"
        if any(part.endswith(suffix) for suffix in _SOURCE_PROTECTED_SUFFIXES):
            return True, "protected_suffix"

    return False, None


def _log_source_probe(request: Request, reason: str) -> None:
    try:
        from src.server.security_tracking import log_security_event

        log_security_event(
            event_type="source_probe_blocked",
            request=request,
            endpoint=str(request.url.path or ""),
            details={
                "reason": reason,
                "path": str(request.url.path or ""),
                "query": str(request.url.query or "")[:500],
                "method": request.method,
            },
        )
    except Exception as exc:  # noqa: BLE001 - security logging must not break request handling.
        print(f"[SECURITY] Source probe logging failed: {exc}")


def _parse_alert_recipients() -> list[str]:
    recipients: set[str] = set()
    raw_values = [
        os.getenv("SECURITY_ALERT_EMAILS", ""),
        os.getenv("DEVELOPER_ALERT_EMAIL", ""),
        os.getenv("REGISTRATION_ALERT_EMAILS", ""),
    ]
    for raw_value in raw_values:
        for part in str(raw_value or "").split(","):
            email = part.strip().lower()
            if email and "@" in email:
                recipients.add(email)
    return sorted(recipients)


def _send_source_probe_alert_email(*, ip: str, path: str, query: str, reason: str, user_agent: str) -> None:
    try:
        recipients = _parse_alert_recipients()
        if not recipients:
            return

        from src.core.branding import APP_DISPLAY_NAME
        from src.modules.email_client.service import EmailMessage, EmailService

        email_service = EmailService()
        if not email_service.is_configured():
            return

        subject = f"[{APP_DISPLAY_NAME}] Bezpečnostní alert: pokus o zdrojový kód"
        body = "\n".join(
            [
                f"Aplikace zablokovala pokus o přístup ke zdrojovému kódu nebo konfiguraci.",
                "",
                f"IP: {ip or '-'}",
                f"Cesta: {path or '-'}",
                f"Query: {query or '-'}",
                f"Důvod: {reason or '-'}",
                f"User-Agent: {user_agent or '-'}",
                "",
                "Událost je zapsaná také v Developer Control Center > Security monitor.",
            ]
        )
        email_service.send_email(EmailMessage(to=recipients, subject=subject, body=body))
    except Exception as exc:  # noqa: BLE001 - alert nesmí blokovat bezpečnostní middleware.
        print(f"[SECURITY] Source probe email alert failed: {exc}")


def _maybe_send_source_probe_alert(request: Request, reason: str) -> None:
    if not _SOURCE_ALERT_EMAIL_ENABLED:
        return

    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{reason}"
    now = time.time()
    last_sent = _source_alert_email_last.get(key)
    if last_sent is not None and (now - last_sent) < _SOURCE_ALERT_EMAIL_THROTTLE_SEC:
        return
    _source_alert_email_last[key] = now

    thread = threading.Thread(
        target=_send_source_probe_alert_email,
        kwargs={
            "ip": ip,
            "path": str(request.url.path or ""),
            "query": str(request.url.query or "")[:500],
            "reason": reason,
            "user_agent": str(request.headers.get("user-agent") or "")[:500],
        },
        daemon=True,
    )
    thread.start()


def _query_looks_like_source_probe(query: str) -> tuple[bool, str | None]:
    should_block, reason = _looks_like_source_probe(query)
    if should_block:
        return should_block, reason

    for key, value in parse_qsl(query or "", keep_blank_values=True):
        for candidate in (key, value):
            should_block, reason = _looks_like_source_probe(candidate)
            if should_block:
                return should_block, reason

    return False, None


class SourceCodeProtectionMiddleware(BaseHTTPMiddleware):
    """Blokuje a zapisuje pokusy o stažení zdrojáků, konfigurace a databází."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _SOURCE_PROTECTION_ENABLED:
            return await call_next(request)

        path = str(request.url.path or "")
        query = str(request.url.query or "")
        should_block, reason = _looks_like_source_probe(path)

        if not should_block and path.lower().startswith("/files") and query:
            # Dočasný file browser používá query parametr path=..., proto kontrolujeme i dotaz.
            should_block, reason = _query_looks_like_source_probe(query)

        if should_block:
            _log_source_probe(request, reason or "source_probe")
            _maybe_send_source_probe_alert(request, reason or "source_probe")
            print(
                "[SECURITY] Blocked source probe: "
                f"method={request.method} path={path} reason={reason}"
            )
            response = Response(
                content='{"detail":"Přístup odepřen"}',
                status_code=403,
                media_type="application/json",
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Source-Protection"] = "blocked"
            return response

        return await call_next(request)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware pro přidání security headers"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Security headers - povinné základní ochrana
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Geolokaci povolime pro self, aby slo presnejsi urceni polohy po souhlasu uzivatele.
        response.headers.setdefault("Permissions-Policy", "geolocation=(self), microphone=(), camera=()")
        
        # HSTS - pouze pro HTTPS
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
        
        # Content Security Policy - CSP hlavně pro ochranu proti embedování z jiných webů
        # Webové rozhraní se embeduje do Webnode jen z těchto domén:
        # - https://www.toozservis.cz
        # - https://toozservis.cz
        if ENVIRONMENT == "production":
            # Produkce: povolit pouze toozservis.cz domény (bez hub.toozservis.cz - nechceme, aby se embedoval sám do sebe)
            frame_ancestors = "https://www.toozservis.cz https://toozservis.cz"
        else:
            # Development: povolit všechny (pro testování)
            frame_ancestors = "*"
        
        # CSP - kompatibilní se stávajícími skripty a API voláními
        if ENVIRONMENT == "production":
            # Produkce: povolit embed jen z toozservis.cz domén, API volání na hub.toozservis.cz
            csp = (
                "default-src 'self' https://hub.toozservis.cz; "
                "img-src 'self' data: https: blob:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "connect-src 'self' https://hub.toozservis.cz https://api.dataovozidlech.cz https://ares.gov.cz; "
                "frame-ancestors 'self' https://www.toozservis.cz https://toozservis.cz;"
            )
        else:
            # Development: povolit všechny (pro testování)
            csp = (
                "default-src 'self'; "
                "img-src 'self' data: https: blob:; "
                "style-src 'self' 'unsafe-inline'; "
                "script-src 'self' 'unsafe-inline'; "
                "connect-src 'self' http://localhost:* https:; "
                "frame-ancestors *;"
            )
        
        # Nenahrazuj existující CSP, pokud už existuje
        if "content-security-policy" not in (k.lower() for k in response.headers.keys()):
            response.headers["Content-Security-Policy"] = csp
        
        # Hide server info (ASCII token; avoid raw stack identifiers in headers)
        response.headers["Server"] = APP_SERVER_PRODUCT_TOKEN
        
        return response


PUBLIC_API_RATE_LIMIT_PREFIX = "/api/public/"
ADMIN_API_PREFIX = "/admin-api"

try:
    _ADMIN_API_RATE_LIMIT_PER_MIN = max(20, int(os.getenv("ADMIN_API_RATE_LIMIT_PER_MIN", "90")))
except ValueError:
    _ADMIN_API_RATE_LIMIT_PER_MIN = 90


def _parse_admin_allowlist_entry(token: str) -> Optional[Any]:
    raw = (token or "").strip()
    if not raw:
        return None
    try:
        if "/" in raw:
            return ipaddress.ip_network(raw, strict=False)
        addr = ipaddress.ip_address(raw)
        if addr.version == 4:
            return ipaddress.ip_network(f"{raw}/32", strict=False)
        return ipaddress.ip_network(f"{raw}/128", strict=False)
    except ValueError:
        print(f"[SECURITY] ADMIN_NETWORK_ALLOWLIST — ignoruji neplatnou položku: {raw!r}")
        return None


def load_admin_network_allowlist() -> List[Any]:
    raw = os.getenv("ADMIN_NETWORK_ALLOWLIST", "").strip()
    if not raw:
        return []
    nets: List[Any] = []
    for part in raw.split(","):
        net = _parse_admin_allowlist_entry(part)
        if net is not None:
            nets.append(net)
    return nets


# /api/admin — alias pro vybrané admin routery (např. vehicle-lifecycle); musí projít stejnými guardy jako /admin-api.
_ADMIN_PATH_PREFIXES = ("/admin-api", "/api/admin", "/web_admin", "/admin-static")


class HttpsRedirectMiddleware(BaseHTTPMiddleware):
    """Přesměruje HTTP na HTTPS, pokud proxy hlásí nebo je vynuceno (produkční hygiena)."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if os.getenv("ENFORCE_HTTPS", "").strip().lower() not in {"1", "true", "yes", "on"}:
            return await call_next(request)

        path = request.url.path or ""
        if path.startswith("/health"):
            return await call_next(request)

        forwarded = (request.headers.get("x-forwarded-proto") or "").strip().lower()
        # Přímé lokální spojení k Uvicornu (bez proxy) nemá TLS na :PORT — výjimka umožní http://127.0.0.1:…
        # při ENFORCE_HTTPS=1 (SSH tunel, lokální test). Za reverse proxy zůstává X-Forwarded-Proto: https.
        client_host = getattr(getattr(request, "client", None), "host", None) or ""
        ch = client_host.lower()
        if ch.startswith("::ffff:"):
            ch = ch[7:]
        if forwarded == "" and ch in {"127.0.0.1", "::1", "localhost"}:
            return await call_next(request)

        scheme = forwarded or (request.url.scheme or "http")
        if scheme != "https":
            host = request.headers.get("host") or request.url.netloc
            if not host:
                return await call_next(request)
            qs = request.url.query
            target = f"https://{host}{path}"
            if qs:
                target = f"{target}?{qs}"
            return RedirectResponse(target, status_code=308)

        return await call_next(request)


class AdminNetworkGuardMiddleware(BaseHTTPMiddleware):
    """
    Volitelně omezí přístup k admin rozhraní na IP/CIDR v ADMIN_NETWORK_ALLOWLIST.
    Prázdný seznam = bez omezení (zpětná kompatibilita).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path or ""
        if not any(path.startswith(p) for p in _ADMIN_PATH_PREFIXES):
            return await call_next(request)

        allow_nets = load_admin_network_allowlist()
        if not allow_nets:
            return await call_next(request)

        client_ip = extract_client_ip(request)
        if not client_ip:
            return Response(
                content='{"detail":"Přístup k administraci není z této sítě povolen (neznámá IP)."}',
                status_code=403,
                media_type="application/json",
            )
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return Response(
                content='{"detail":"Přístup k administraci není z této sítě povolen."}',
                status_code=403,
                media_type="application/json",
            )
        if not any(addr in net for net in allow_nets):
            return Response(
                content='{"detail":"Přístup k administraci není z této sítě povolen."}',
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)


class CloudflareAccessAdminMiddleware(BaseHTTPMiddleware):
    """Na /admin-api, /web_admin, /admin-static volitelně vyžádá platný JWT z Cloudflare Access."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not cloudflare_access_admin_protection_enabled():
            return await call_next(request)

        path = request.url.path or ""
        if not any(path.startswith(p) for p in _ADMIN_PATH_PREFIXES):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)

        team = normalize_cf_access_team_domain(os.getenv("CLOUDFLARE_ACCESS_TEAM_DOMAIN", "").strip())
        audiences = parse_cf_access_audiences(os.getenv("CLOUDFLARE_ACCESS_AUDIENCE", "").strip())
        if not team or not audiences:
            return Response(
                content='{"detail":"Cloudflare Access ochrana administrace není dokončená (TEAM_DOMAIN nebo AUDIENCE)."}',
                status_code=503,
                media_type="application/json",
            )
        allowed_mail = parse_cf_access_allowed_emails(os.getenv("CLOUDFLARE_ACCESS_ALLOWED_EMAILS", ""))
        token = (
            (request.headers.get("cf-access-jwt-assertion") or request.headers.get("CF-Access-Jwt-Assertion") or "").strip()
        )
        if not token:
            return Response(
                content='{"detail":"Přístup k administraci vyžaduje Cloudflare Access."}',
                status_code=403,
                media_type="application/json",
            )
        ok, _reason = verify_cf_access_jwt_assertion(
            token,
            team_domain=team,
            audiences=audiences,
            allowed_emails=allowed_mail,
        )
        if not ok:
            return Response(
                content='{"detail":"Ověření Cloudflare Access selhalo."}',
                status_code=403,
                media_type="application/json",
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware pro rate limiting"""
    
    def __init__(
        self,
        app,
        calls: int = 100,
        period: int = 60,
        *,
        public_calls: int = 30,
        public_period: int = 60,
    ):
        super().__init__(app)
        self.calls = calls  # Počet požadavků (běžné API)
        self.period = period  # Období v sekundách
        self.public_calls = public_calls  # Společný bucket pro /api/public/*
        self.public_period = public_period
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # OPTIONS requests (CORS preflight) nejsou rate-limited
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Health check endpoints nejsou rate-limited (včetně sub-paths jako /health/config)
        # Použít prefix matching místo exact match, aby všechny health endpoints byly vyňaty
        if request.url.path.startswith("/health"):
            return await call_next(request)
        
        client_ip = extract_client_ip(request) or (request.client.host if request.client else None) or "unknown"
        
        path = request.url.path or ""
        if path.startswith(ADMIN_API_PREFIX) or path.startswith("/api/admin"):
            key = f"{client_ip}:admin_api_bucket"
            limit = _ADMIN_API_RATE_LIMIT_PER_MIN
            period = 60
        elif path.startswith(PUBLIC_API_RATE_LIMIT_PREFIX):
            # Jedna IP nesmí paralelně „probíhat“ stovkami různých tokenů v cestě —
            # sdílený bucket místo client_ip:full_path.
            key = f"{client_ip}:public_api"
            limit = self.public_calls
            period = self.public_period
        else:
            key = f"{client_ip}:{path}"
            limit = self.calls
            period = self.period
        
        # Vyčistit staré záznamy
        now = time.time()
        rate_limit_store[key] = [
            timestamp for timestamp in rate_limit_store[key]
            if now - timestamp < period
        ]
        
        # Kontrola limitu
        if len(rate_limit_store[key]) >= limit:
            return Response(
                content='{"detail":"Rate limit exceeded. Please try again later."}',
                status_code=429,
                media_type="application/json"
            )
        
        # Přidat aktuální požadavek
        rate_limit_store[key].append(now)
        
        # Pokračovat
        response = await call_next(request)
        
        # Přidat rate limit headers
        remaining = limit - len(rate_limit_store[key])
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(now + period))
        
        return response


class AntiTamperingMiddleware(BaseHTTPMiddleware):
    """Middleware pro detekci manipulace s požadavky"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Kontrola podezřelých headers
        suspicious_headers = [
            "x-forwarded-for",
            "x-real-ip",
            "x-originating-ip",
            "x-remote-ip",
            "x-remote-addr"
        ]
        
        # Log podezřelých požadavků (v produkci)
        for header in suspicious_headers:
            if header in request.headers:
                print(f"[SECURITY] Suspicious header detected: {header} = {request.headers[header]}")
        
        response = await call_next(request)
        
        # Přidat anti-tampering headers
        response.headers["X-Request-ID"] = str(int(time.time() * 1000))
        
        return response
