"""
Volitelná validace JWT z Cloudflare Access (hlavička Cf-Access-Jwt-Assertion).
Dok.: https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
"""
from __future__ import annotations

import threading
from typing import Any

import jwt

try:
    from jwt import PyJWKClient  # PyJWT>=2.x
except ImportError:
    PyJWKClient = None  # type: ignore[misc, assignment]


_jwks_lock = threading.Lock()
_jwks_clients: dict[str, Any] = {}


def normalize_cf_access_team_domain(raw: str) -> str | None:
    r = raw.strip()
    if not r:
        return None
    if r.startswith("https://"):
        return r.rstrip("/")
    if r.startswith("http://"):
        return f"https://{r[len('http://'):].lstrip('/').rstrip('/')}"
    return f"https://{r.lstrip('/').rstrip('/')}"


def parse_cf_access_audiences(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def parse_cf_access_allowed_emails(raw: str) -> set[str]:
    return {part.strip().lower() for part in (raw or "").split(",") if part.strip()}


def cloudflare_access_admin_protection_enabled() -> bool:
    import os

    return os.getenv("CLOUDFLARE_ACCESS_PROTECT_ADMIN", "").strip().lower() in {"1", "true", "yes", "on"}


def validate_cloudflare_access_admin_env() -> list[str]:
    import os

    if not cloudflare_access_admin_protection_enabled():
        return []
    errs: list[str] = []
    td = normalize_cf_access_team_domain(os.getenv("CLOUDFLARE_ACCESS_TEAM_DOMAIN", "").strip())
    if not td:
        errs.append("CLOUDFLARE_ACCESS_TEAM_DOMAIN musí obsahovat váš Zero Trust Team (např. https://muj-tym.cloudflareaccess.com).")
    aus = parse_cf_access_audiences(os.getenv("CLOUDFLARE_ACCESS_AUDIENCE", ""))
    if not aus:
        errs.append(
            "CLOUDFLARE_ACCESS_AUDIENCE musí obsahovat Application Audience tag (AUD) z Cloudflare Dashboard (oddělte čárkou u více aplikací)."
        )
    return errs


def _jwks_for_team(team_domain_https: str) -> Any:
    if PyJWKClient is None:
        raise RuntimeError("PyJWT s PyJWKClient není k dispozici")
    certs_url = f"{team_domain_https}/cdn-cgi/access/certs"
    with _jwks_lock:
        existing = _jwks_clients.get(certs_url)
        if existing is not None:
            return existing
        client = PyJWKClient(
            certs_url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=600,
            max_cached_keys=8,
        )
        _jwks_clients[certs_url] = client
        return client


def verify_cf_access_jwt_assertion(
    token: str,
    *,
    team_domain: str,
    audiences: list[str],
    allowed_emails: set[str],
) -> tuple[bool, str | None]:
    """
    Ověří podpis JWT a audience/issuer podle dokumentace Cloudflare Access.
    """
    tok = token.strip()
    if not tok:
        return False, "missing_token"
    try:
        jwk_client = _jwks_for_team(team_domain)
        signing_key = jwk_client.get_signing_key_from_jwt(tok)
        payload = jwt.decode(
            tok,
            signing_key.key,
            algorithms=["RS256"],
            audience=audiences,
            issuer=team_domain,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.InvalidTokenError:
        return False, "invalid_token"
    except Exception:
        return False, "verification_error"
    if allowed_emails:
        email = str(payload.get("email") or "").strip().lower()
        if email not in allowed_emails:
            return False, "email_not_allowed"
    return True, None
