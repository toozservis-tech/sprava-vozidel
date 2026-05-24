"""
Licensing API routery - webhooky a public endpointy
"""
import hmac
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Načíst konfiguraci z core/config.py (načítá .env soubor)
try:
    from ...core.config import load_dotenv
except ImportError:
    pass

from ..vehicle_hub.database import get_db
from ..vehicle_hub.models import Customer
from ..vehicle_hub.routers_v1.auth import get_current_user
from .licensing_service import get_entitlement, enforce_vehicle_limit
import httpx

router = APIRouter(prefix="/api", tags=["licensing"])

# Security
security = HTTPBearer()

# Environment variables - načíst dynamicky při každém použití
# Poznámka: Načítáme z os.environ přímo, aby se reflektovaly změny po restartu
def get_service_hub_url():
    """Získá SERVICE_HUB_URL z environment (dynamicky)"""
    return os.getenv("SERVICE_HUB_URL", "").strip()

def get_service_hub_token():
    """Získá SERVICE_HUB_SERVICE_TOKEN z environment (dynamicky)"""
    return os.getenv("SERVICE_HUB_SERVICE_TOKEN", "").strip()

def get_shared_secret():
    """Získá SERVICE_HUB_SHARED_SECRET z environment (dynamicky)"""
    return os.getenv("SERVICE_HUB_SHARED_SECRET", "").strip()

# Logging setup - absolutní cesta k log souboru
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
WEBHOOK_LOG_FILE = LOGS_DIR / "licensing_webhook.log"

# Zajistit, že logs složka existuje
LOGS_DIR.mkdir(exist_ok=True)


# ============= PYDANTIC MODELY =============

class LicenseWebhookPayload(BaseModel):
    """Payload pro webhook od TOOZ_SERVICE_HUB"""
    event: str
    email: str
    plan: str  # FREE, BASIC, PREMIUM
    status: str  # ACTIVE, PENDING_PAYMENT, PAST_DUE, CANCELED, EXPIRED
    period_end: Optional[str] = None  # ISO format datetime
    updated_at: Optional[str] = None


class LicenseSelectRequest(BaseModel):
    """Request pro výběr licence"""
    plan: str  # FREE, BASIC, PREMIUM


class LicenseResponse(BaseModel):
    """Response s licenčními informacemi"""
    email: str
    plan: str
    status: str
    period_end: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ============= HELPER FUNKCE =============

def log_webhook_event(email: str, plan: str, status: str, period_end: Optional[str], success: bool, error: Optional[str] = None, request_host: Optional[str] = None, request_path: Optional[str] = None):
    """
    Loguje webhook event do souboru.
    
    Args:
        email: Email uživatele
        plan: Licenční plán
        status: Licenční status
        period_end: Datum konce období (ISO format)
        success: True pokud byl update úspěšný
        error: Chybová zpráva (pokud success=False)
        request_host: Host z requestu (pro rozlišení prod vs lokál)
        request_path: Path z requestu
    """
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{timestamp}] received_at={timestamp} email={email} plan={plan} status={status} period_end={period_end or 'null'} success={success}"
        if request_host:
            log_entry += f" request_host={request_host}"
        if request_path:
            log_entry += f" request_path={request_path}"
        if error:
            log_entry += f" error={error}"
        log_entry += "\n"
        
        # Zajistit, že složka existuje
        LOGS_DIR.mkdir(exist_ok=True)
        
        # Zapsat do souboru (append mode)
        with open(WEBHOOK_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        # Pokud se nepodaří zapsat do logu, alespoň vytisknout na stdout
        print(f"[LICENSE WEBHOOK LOG ERROR] Failed to write to log file: {e}")


def verify_hmac_signature(body: bytes, signature: str, secret: str) -> bool:
    """
    Ověří HMAC SHA256 signature.
    
    Args:
        body: Raw request body
        signature: Signature z headeru X-Signature
        secret: Shared secret
        
    Returns:
        True pokud je signature validní
    """
    if not secret:
        return False
    
    expected_signature = hmac.new(
        secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


# ============= INTERNAL ENDPOINTY =============

async def _handle_webhook_internal(
    payload: LicenseWebhookPayload,
    request: Request,
    x_signature: Optional[str],
    db: Session,
    authorization: Optional[str] = Header(None),
):
    """
    Interní handler pro webhook - používá se jak pro /internal tak pro /public endpoint.
    Ověřuje HMAC signature (SERVICE_HUB_SHARED_SECRET) a bearer token (SERVICE_HUB_SERVICE_TOKEN).
    """
    # Získat request host a path pro logování (před jakýmkoliv try/except)
    request_host = request.headers.get("host", "unknown")
    request_path = str(request.url.path)
    
    # Načíst raw body (musí být před jakýmkoliv ověřením, abychom mohli logovat)
    body = await request.body()
    
    # Ověření bearer tokenu (SERVICE_HUB_SERVICE_TOKEN) - POVINNÉ
    SERVICE_HUB_SERVICE_TOKEN = get_service_hub_token()
    if not SERVICE_HUB_SERVICE_TOKEN:
        log_webhook_event(
            email=payload.email if hasattr(payload, 'email') else "unknown",
            plan=payload.plan if hasattr(payload, 'plan') else "unknown",
            status=payload.status if hasattr(payload, 'status') else "unknown",
            period_end=payload.period_end if hasattr(payload, 'period_end') else None,
            success=False,
            error="SERVICE_HUB_SERVICE_TOKEN není nastaven",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=500,
            detail="SERVICE_HUB_SERVICE_TOKEN není nastaven"
        )
    
    if not authorization or not authorization.startswith("Bearer "):
        log_webhook_event(
            email=payload.email if hasattr(payload, 'email') else "unknown",
            plan=payload.plan if hasattr(payload, 'plan') else "unknown",
            status=payload.status if hasattr(payload, 'status') else "unknown",
            period_end=payload.period_end if hasattr(payload, 'period_end') else None,
            success=False,
            error="Missing or invalid Authorization header",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header"
        )
    
    token = authorization.replace("Bearer ", "").strip()
    if token != SERVICE_HUB_SERVICE_TOKEN:
        log_webhook_event(
            email=payload.email if hasattr(payload, 'email') else "unknown",
            plan=payload.plan if hasattr(payload, 'plan') else "unknown",
            status=payload.status if hasattr(payload, 'status') else "unknown",
            period_end=payload.period_end if hasattr(payload, 'period_end') else None,
            success=False,
            error="Invalid bearer token",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token"
        )
    
    # Ověření HMAC signature (SERVICE_HUB_SHARED_SECRET) - POVINNÉ
    SERVICE_HUB_SHARED_SECRET = get_shared_secret()
    if not SERVICE_HUB_SHARED_SECRET:
        log_webhook_event(
            email=payload.email if hasattr(payload, 'email') else "unknown",
            plan=payload.plan if hasattr(payload, 'plan') else "unknown",
            status=payload.status if hasattr(payload, 'status') else "unknown",
            period_end=payload.period_end if hasattr(payload, 'period_end') else None,
            success=False,
            error="SERVICE_HUB_SHARED_SECRET není nastaven",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=500,
            detail="SERVICE_HUB_SHARED_SECRET není nastaven"
        )
    
    if not x_signature:
        log_webhook_event(
            email=payload.email if hasattr(payload, 'email') else "unknown",
            plan=payload.plan if hasattr(payload, 'plan') else "unknown",
            status=payload.status if hasattr(payload, 'status') else "unknown",
            period_end=payload.period_end if hasattr(payload, 'period_end') else None,
            success=False,
            error="Missing X-Signature header",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=401,
            detail="Missing X-Signature header"
        )
    
    # Ověřit signature
    if not verify_hmac_signature(body, x_signature, SERVICE_HUB_SHARED_SECRET):
        log_webhook_event(
            email=payload.email if hasattr(payload, 'email') else "unknown",
            plan=payload.plan if hasattr(payload, 'plan') else "unknown",
            status=payload.status if hasattr(payload, 'status') else "unknown",
            period_end=payload.period_end if hasattr(payload, 'period_end') else None,
            success=False,
            error="Invalid signature",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid signature"
        )
    
    # Validovat event
    if payload.event != "license.updated":
        log_webhook_event(
            email=payload.email,
            plan=payload.plan,
            status=payload.status,
            period_end=payload.period_end,
            success=False,
            error=f"Unknown event: {payload.event}",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event: {payload.event}"
        )
    
    # Najít customer podle emailu
    customer = db.query(Customer).filter(Customer.email == payload.email).first()
    if not customer:
        log_webhook_event(
            email=payload.email,
            plan=payload.plan,
            status=payload.status,
            period_end=payload.period_end,
            success=False,
            error=f"Customer not found: {payload.email}",
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=404,
            detail=f"Customer not found: {payload.email}"
        )
    
    # Parsovat period_end pokud existuje
    period_end_dt = None
    if payload.period_end:
        try:
            period_end_dt = datetime.fromisoformat(payload.period_end.replace('Z', '+00:00'))
        except Exception as e:
            print(f"[LICENSE WEBHOOK] WARNING: Failed to parse period_end: {e}")
    
    # Aktualizovat cache pole
    try:
        customer.license_plan_cached = payload.plan
        customer.license_status_cached = payload.status
        customer.license_period_end_cached = period_end_dt
        customer.license_last_sync_at = datetime.now(timezone.utc)
        customer.license_source = "service_hub"
        
        db.commit()
        db.refresh(customer)
        
        # Logovat úspěšný update
        log_webhook_event(
            email=payload.email,
            plan=payload.plan,
            status=payload.status,
            period_end=payload.period_end,
            success=True,
            request_host=request_host,
            request_path=request_path
        )
        
        print(f"[LICENSE WEBHOOK] Updated license for {payload.email}: plan={payload.plan}, status={payload.status}")
        
        return {
            "ok": True,
            "email": payload.email,
            "plan": payload.plan,
            "status": payload.status
        }
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        log_webhook_event(
            email=payload.email,
            plan=payload.plan,
            status=payload.status,
            period_end=payload.period_end,
            success=False,
            error=error_msg,
            request_host=request_host,
            request_path=request_path
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update license cache: {error_msg}"
        )


# ============= WEBHOOK ENDPOINTY =============

@router.post("/internal/license/webhook")
async def webhook_internal(
    payload: LicenseWebhookPayload,
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Interní webhook endpoint pro přijímání licenčních aktualizací z TOOZ_SERVICE_HUB.
    Pouze pro lokální komunikaci (127.0.0.1).
    Ověřuje HMAC signature (X-Signature) a bearer token (Authorization: Bearer <token>).
    """
    return await _handle_webhook_internal(payload, request, x_signature, authorization, db)


@router.post("/license/webhook")
async def webhook_public(
    payload: LicenseWebhookPayload,
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Veřejný webhook endpoint pro přijímání licenčních aktualizací z TOOZ_SERVICE_HUB.
    Používá se pro produkci přes Cloudflare Tunnel.
    Ověřuje HMAC signature (X-Signature) a bearer token (Authorization: Bearer <token>).
    """
    return await _handle_webhook_internal(payload, request, x_signature, authorization, db)


@router.post("/api/v1/license/webhook")
async def webhook_v1(
    payload: LicenseWebhookPayload,
    request: Request,
    x_signature: Optional[str] = Header(None, alias="X-Signature"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Webhook endpoint v1 API pro přijímání licenčních aktualizací z TOOZ_SERVICE_HUB.
    Ověřuje HMAC signature (X-Signature) a bearer token (Authorization: Bearer <token>).
    """
    return await _handle_webhook_internal(payload, request, x_signature, authorization, db)


# ============= DIAGNOSTICKÉ ENDPOINTY =============

@router.get("/internal/license/debug/customer")
async def debug_customer_license(
    email: str = Query(..., description="Email zákazníka"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Diagnostický endpoint pro ověření licenčního stavu zákazníka.
    Pouze pro lokální vývoj - vyžaduje SERVICE_HUB_SERVICE_TOKEN v Authorization headeru.
    """
    # Načíst ENV dynamicky
    SERVICE_HUB_SERVICE_TOKEN = get_service_hub_token()
    
    # Ověření service tokenu
    if not SERVICE_HUB_SERVICE_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="SERVICE_HUB_SERVICE_TOKEN není nastaven"
        )
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    if token != SERVICE_HUB_SERVICE_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid service token"
        )
    
    # Najít customer podle emailu
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Customer not found: {email}"
        )
    
    return {
        "email": customer.email,
        "license_plan_cached": customer.license_plan_cached,
        "license_status_cached": customer.license_status_cached,
        "license_period_end_cached": customer.license_period_end_cached.isoformat() if customer.license_period_end_cached else None,
        "license_last_sync_at": customer.license_last_sync_at.isoformat() if customer.license_last_sync_at else None,
        "license_source": customer.license_source,
    }


@router.get("/internal/license/debug/config")
async def debug_license_config(
    authorization: Optional[str] = Header(None),
):
    """
    Diagnostický endpoint pro ověření konfigurace licenčního systému.
    Vyžaduje SERVICE_HUB_SERVICE_TOKEN v Authorization headeru.
    Vrací stav ENV proměnných (bez hodnot tokenů).
    """
    # Načíst ENV dynamicky
    SERVICE_HUB_SERVICE_TOKEN = get_service_hub_token()
    SERVICE_HUB_URL = get_service_hub_url()
    SERVICE_HUB_SHARED_SECRET = get_shared_secret()
    
    # Ověření service tokenu
    if not SERVICE_HUB_SERVICE_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="SERVICE_HUB_SERVICE_TOKEN není nastaven"
        )
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header"
        )
    
    token = authorization.replace("Bearer ", "")
    if token != SERVICE_HUB_SERVICE_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid service token"
        )
    
    # Maskovat URL (zobrazit pouze host, ne celou URL s potenciálně citlivými částmi)
    effective_url = SERVICE_HUB_URL
    if effective_url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(effective_url)
            effective_url = f"{parsed.scheme}://{parsed.netloc}"  # Jen scheme + host
        except:
            effective_url = "invalid_url"
    
    return {
        "service_hub_url_set": bool(SERVICE_HUB_URL),
        "service_hub_token_set": bool(SERVICE_HUB_SERVICE_TOKEN),
        "shared_secret_set": bool(SERVICE_HUB_SHARED_SECRET),
        "effective_service_hub_url": effective_url if effective_url else None,
    }


# ============= PUBLIC ENDPOINTY =============

@router.post("/v1/license/select", response_model=LicenseResponse)
def license_select(
    request: LicenseSelectRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Public endpoint pro výběr licence uživatelem.
    Zavolá TOOZ_SERVICE_HUB API a uloží response do cache polí.
    """
    # Validovat plán
    valid_plans = ["FREE", "BASIC", "PREMIUM"]
    if request.plan not in valid_plans:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan. Must be one of: {', '.join(valid_plans)}"
        )
    
    # Zavolat TOOZ_SERVICE_HUB API
    # Načíst ENV dynamicky (aby se reflektovaly změny po restartu)
    SERVICE_HUB_URL = get_service_hub_url()
    SERVICE_HUB_SERVICE_TOKEN = get_service_hub_token()
    
    # Kontrola, zda je konfigurace nastavena
    missing_config = []
    if not SERVICE_HUB_URL:
        missing_config.append("SERVICE_HUB_URL")
    if not SERVICE_HUB_SERVICE_TOKEN:
        missing_config.append("SERVICE_HUB_SERVICE_TOKEN")
    
    if missing_config:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Licenční služba není dostupná. Chybí konfigurace: {', '.join(missing_config)}. "
                f"Pro změnu licence kontaktujte administrátora nebo použijte TOOZ_SERVICE_HUB admin rozhraní."
            )
        )
    
    try:
        # Volání service hub API
        response = httpx.post(
            f"{SERVICE_HUB_URL}/api/public/license/request-change",
            json={
                "email": current_user.email,
                "desired_plan": request.plan,
            },
            headers={
                "Authorization": f"Bearer {SERVICE_HUB_SERVICE_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Service hub API error: {response.text}"
            )
        
        data = response.json()
        
        # Parsovat period_end pokud existuje
        period_end_dt = None
        if data.get("period_end"):
            try:
                period_end_dt = datetime.fromisoformat(data["period_end"].replace('Z', '+00:00'))
            except Exception as e:
                print(f"[LICENSE SELECT] WARNING: Failed to parse period_end: {e}")
        
        # Aktualizovat cache pole
        current_user.license_plan_cached = data["plan"]
        current_user.license_status_cached = data["status"]
        current_user.license_period_end_cached = period_end_dt
        current_user.license_last_sync_at = datetime.now(timezone.utc)
        current_user.license_source = "service_hub"
        
        db.commit()
        db.refresh(current_user)
        
        return LicenseResponse(
            email=data["email"],
            plan=data["plan"],
            status=data["status"],
            period_end=period_end_dt,
            updated_at=datetime.now(timezone.utc),
        )
        
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to connect to service hub: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing license change: {str(e)}"
        )


