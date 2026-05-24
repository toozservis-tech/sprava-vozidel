"""
Services API v1.0 router
Endpointy pro správu servisů
"""
import json
import math
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME, APP_SERVER_PRODUCT_TOKEN
from src.core.rbac import ROLE_SERVICE, is_admin, normalize_role
from ..database import get_db
from ..models import (
    Customer,
    ServiceAccessRequest,
    ServiceCustomerLink,
    ServiceVehicleAccess,
    Vehicle,
    VehicleServiceLink,
)
from ..ownership import get_customer_by_email, get_owned_vehicle, get_owned_vehicle_ids
from ..partner_public_profile import partner_public_profile_from_db
from ..schema_management import assert_module_ready
from ..service_access import create_or_update_vehicle_service_link, finalize_service_access_decision, revoke_vehicle_service_link, vehicle_label
from ..user_in_app_notifications import notify_service_access_decided
from .auth import get_current_user
from .schemas import (
    ConnectServiceByEmailRequestV1,
    ServiceAccessRequestCreateV1,
    ServiceAccessRequestDecisionV1,
    ServiceAccessRequestListOutV1,
    ServiceApprovedVehicleListOutV1,
    ServiceVehicleLookupRequestV1,
    ServiceVehicleLookupResponseV1,
    VehicleServiceLinkListOutV1,
)

router = APIRouter(prefix="/services", tags=["services-v1"])

_SERVICE_GEO_CACHE: Dict[str, Dict[str, Any]] = {}
_SERVICE_GEO_CACHE_TTL_SEC = 7 * 24 * 60 * 60  # 7 dní
_SERVICE_GEO_CACHE_MAX_ITEMS = 3000
_SERVICE_GEO_SUGGEST_CACHE_TTL_SEC = 24 * 60 * 60  # 24 h (stejný zdroj jako vyhledávání na mapě)
_SERVICE_GEO_SUGGEST_CACHE_MAX_ITEMS = 8000
_LAST_NOMINATIM_CALL_MONO = 0.0
_SERVICE_GEOLOOKUP_URL = (
    "https://nominatim.openstreetmap.org/search?format=jsonv2&accept-language=cs&limit=1&q={query}"
)
_SERVICE_GEO_SUGGEST_URL = (
    "https://nominatim.openstreetmap.org/search?format=jsonv2&accept-language=cs"
    "&countrycodes=cz&limit={limit}&q={query}"
)
_SERVICE_GEOLOOKUP_TIMEOUT_SEC = 1.8
_DEFAULT_OWNER_DISCOVERY_RADIUS_KM = 0.0


def _unwrap_fastapi_query_param(value: Any) -> Any:
    """Normalizuje Query() default při přímém volání handleru mimo FastAPI (unit testy)."""
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if hasattr(value, "default"):
        default = value.default
        if default is ...:
            return None
        return default
    return value
_SERVICE_GEOLOOKUP_MAX_NEW_LOOKUPS_PER_REQUEST = 25


class VehicleAccessGrantRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=500)
    conflict_strategy: Optional[str] = Field(default="keep", max_length=32)  # ask | keep | replace


def _normalize_email(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _is_admin_role(role: Optional[str]) -> bool:
    return is_admin(role)


def _ensure_services_schema(db: Session) -> None:
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní propojení není připravené")


def _access_scope_summary() -> str:
    return "Čtení historie vozidla a možnost vytvářet nové servisní záznamy bez úprav starších cizích záznamů."


def _upsert_service_customer_link(
    db: Session,
    *,
    service_customer_id: int,
    service_tenant_id: Optional[int],
    target_customer: Customer,
    note: Optional[str] = None,
) -> tuple[ServiceCustomerLink, bool]:
    existing = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == service_customer_id,
            ServiceCustomerLink.customer_id == target_customer.id,
        )
        .first()
    )
    if existing:
        existing.status = "active"
        existing.service_tenant_id = service_tenant_id
        existing.customer_tenant_id = target_customer.tenant_id
        if note is not None:
            existing.note = note
        existing.updated_at = datetime.utcnow()
        db.flush()
        return existing, False

    link = ServiceCustomerLink(
        service_tenant_id=service_tenant_id,
        service_customer_id=service_customer_id,
        customer_tenant_id=target_customer.tenant_id,
        customer_id=target_customer.id,
        status="active",
        note=note,
    )
    db.add(link)
    db.flush()
    return link, True


def _serialize_access_request_row(request_row: ServiceAccessRequest, service: Customer, vehicle: Vehicle) -> dict[str, Any]:
    return {
        "id": int(request_row.id),
        "vehicle_id": int(request_row.vehicle_id),
        "service_id": int(request_row.service_customer_id),
        "service_name": service.name or service.email,
        "service_email": service.email,
        "vehicle_name": vehicle_label(vehicle),
        "vehicle_plate": vehicle.plate,
        "requested_at": request_row.requested_at.isoformat() if request_row.requested_at else None,
        "status": str(request_row.status or "pending"),
        "note": request_row.request_message,
        "scope_summary": _access_scope_summary(),
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_client_coordinates(request: Request) -> Optional[tuple[float, float]]:
    lat = _safe_float(request.headers.get("x-geo-lat"))
    lon = _safe_float(request.headers.get("x-geo-lon"))
    if lat is None or lon is None:
        return None
    if lat < -90 or lat > 90 or lon < -180 or lon > 180:
        return None
    return round(lat, 6), round(lon, 6)


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    cached = _SERVICE_GEO_CACHE.get(key)
    if not cached:
        return None
    if cached.get("expires_at", 0) < time.time():
        _SERVICE_GEO_CACHE.pop(key, None)
        return None
    return cached.get("payload")


def _cache_set(key: str, payload: Dict[str, Any]) -> None:
    if len(_SERVICE_GEO_CACHE) >= _SERVICE_GEO_CACHE_MAX_ITEMS:
        oldest_key = next(iter(_SERVICE_GEO_CACHE.keys()), None)
        if oldest_key is not None:
            _SERVICE_GEO_CACHE.pop(oldest_key, None)
    _SERVICE_GEO_CACHE[key] = {
        "expires_at": time.time() + _SERVICE_GEO_CACHE_TTL_SEC,
        "payload": payload,
    }


_SERVICE_GEO_SUGGEST_CACHE: Dict[str, Dict[str, Any]] = {}


def _suggest_cache_get(key: str) -> Optional[list]:
    cached = _SERVICE_GEO_SUGGEST_CACHE.get(key)
    if not cached:
        return None
    if cached.get("expires_at", 0) < time.time():
        _SERVICE_GEO_SUGGEST_CACHE.pop(key, None)
        return None
    val = cached.get("payload")
    return val if isinstance(val, list) else None


def _suggest_cache_set(key: str, payload: list) -> None:
    if len(_SERVICE_GEO_SUGGEST_CACHE) >= _SERVICE_GEO_SUGGEST_CACHE_MAX_ITEMS:
        oldest_key = next(iter(_SERVICE_GEO_SUGGEST_CACHE.keys()), None)
        if oldest_key is not None:
            _SERVICE_GEO_SUGGEST_CACHE.pop(oldest_key, None)
    _SERVICE_GEO_SUGGEST_CACHE[key] = {
        "expires_at": time.time() + _SERVICE_GEO_SUGGEST_CACHE_TTL_SEC,
        "payload": payload,
    }


def _respect_nominatim_interval() -> None:
    """OpenStreetMap Nominatim vyžaduje max. ~1 požadavek/s na projekt — držíme rozestup."""
    global _LAST_NOMINATIM_CALL_MONO
    gap = 1.08
    now = time.monotonic()
    elapsed = now - _LAST_NOMINATIM_CALL_MONO
    if elapsed < gap:
        time.sleep(gap - elapsed)
    _LAST_NOMINATIM_CALL_MONO = time.monotonic()


def _subtitle_from_nominatim_address(addr: Any) -> str:
    if not isinstance(addr, dict):
        return ""
    locality_keys = ("village", "town", "city", "municipality", "hamlet")
    loc = ""
    for k in locality_keys:
        v = addr.get(k)
        if v:
            loc = str(v)
            break
    county = addr.get("county") or addr.get("state_district") or ""
    region = addr.get("state") or ""
    parts_raw = [p for p in (loc, str(county) if county else "", str(region) if region else "") if p]
    seen: set[str] = set()
    parts: list[str] = []
    for p in parts_raw:
        if p not in seen:
            seen.add(p)
            parts.append(p)
    return ", ".join(parts)


def _nominatim_search_results(query: str, *, limit: int) -> list[Dict[str, Any]]:
    q = str(query or "").strip()
    if len(q) < 2:
        return []
    lim = max(1, min(int(limit), 12))
    cache_key = f"suggest:{lim}:{q.lower()}"
    cached_list = _suggest_cache_get(cache_key)
    if cached_list is not None:
        return [x for x in cached_list if isinstance(x, dict)]

    _respect_nominatim_interval()
    try:
        request_url = _SERVICE_GEO_SUGGEST_URL.format(limit=lim, query=quote(q, safe=""))
        req = UrlRequest(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"{APP_SERVER_PRODUCT_TOKEN}-ServicesDirectorySuggest/1.0",
            },
        )
        with urlopen(req, timeout=_SERVICE_GEOLOOKUP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        if not isinstance(data, list):
            _suggest_cache_set(cache_key, [])
            return []
        _suggest_cache_set(cache_key, data)
        return [x for x in data if isinstance(x, dict)]
    except Exception:
        return []


def _build_service_address(service: Customer) -> str:
    parts = []
    street = (service.street or "").strip()
    street_number = (service.street_number or "").strip()
    if street and street_number:
        parts.append(f"{street} {street_number}")
    elif street:
        parts.append(street)
    city = (service.city or "").strip()
    if city:
        parts.append(city)
    zip_code = (service.zip or "").strip()
    if zip_code:
        parts.append(zip_code)
    parts.append("Česká republika")
    return ", ".join(part for part in parts if part)


def _compose_service_address(service: Customer) -> str:
    street = (service.street or "").strip()
    street_number = (service.street_number or "").strip()
    line_one = f"{street} {street_number}".strip() if (street or street_number) else ""
    line_two = " ".join(part for part in [(service.zip or "").strip(), (service.city or "").strip()] if part).strip()
    return ", ".join(part for part in [line_one, line_two] if part)


def _geocode_address(address: str) -> Optional[Dict[str, Any]]:
    key = address.strip().lower()
    if not key:
        return None

    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        request_url = _SERVICE_GEOLOOKUP_URL.format(query=quote(address, safe=""))
        req = UrlRequest(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"{APP_SERVER_PRODUCT_TOKEN}-ServicesDirectory/1.0",
            },
        )
        with urlopen(req, timeout=_SERVICE_GEOLOOKUP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        if not isinstance(data, list) or not data:
            _cache_set(key, {})
            return None

        first = data[0] if isinstance(data[0], dict) else {}
        lat = _safe_float(first.get("lat"))
        lon = _safe_float(first.get("lon"))
        if lat is None or lon is None:
            _cache_set(key, {})
            return None
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            _cache_set(key, {})
            return None

        payload = {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "display_name": first.get("display_name"),
        }
        _cache_set(key, payload)
        return payload
    except Exception:
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(1 - a, 0)))
    return round(r * c, 1)


def _partner_ico_key(ico: Optional[str]) -> Optional[str]:
    digits = "".join(ch for ch in str(ico or "") if ch.isdigit())
    return digits or None


def _partner_phone_key(phone: Optional[str]) -> Optional[str]:
    """Číslo bez formátování (CZ: odstranění +420 / úvodní 0)."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return None
    if digits.startswith("420") and len(digits) >= 11:
        digits = digits[3:]
    if digits.startswith("0") and len(digits) >= 10:
        digits = digits[1:]
    if len(digits) >= 8:
        return digits
    return None


def _partner_cluster_union(services: List[Customer]) -> dict[int, int]:
    """Sloučí id do clusterů podle shodného IČO nebo telefonu (častý duplicitní pár v DB)."""
    ids = [int(s.id) for s in services]
    parent = {i: i for i in ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    key_members: dict[str, list[int]] = {}
    for svc in services:
        sid = int(svc.id)
        keys: list[str] = []
        ik = _partner_ico_key(svc.ico)
        if ik:
            keys.append(f"ico:{ik}")
        pk = _partner_phone_key(svc.phone)
        if pk:
            keys.append(f"ph:{pk}")
        if not keys:
            keys.append(f"id:{sid}")
        for k in keys:
            key_members.setdefault(k, []).append(sid)

    for members in key_members.values():
        if len(members) < 2:
            continue
        head = members[0]
        for other in members[1:]:
            union(head, other)

    return {i: find(i) for i in ids}


def _dedupe_discovery_services_for_owner(
    services: List[Customer],
) -> tuple[List[Customer], dict[int, set[int]]]:
    """
    Sloučí duplicitní servisní účty stejné firmy (stejné IČO a/nebo telefon).

    Kanonický záznam pro zobrazení = řádek s **nejnižším customers.id** (typicky první
    oficiální servis z adminu, např. firemní e-mail). Propojení a počty vozidel se agregují
    napříč celou skupinou při sestavování odpovědi.
    """
    if not services:
        return [], {}
    if len(services) == 1:
        sid = int(services[0].id)
        return services, {sid: {sid}}

    id_to_customer = {int(s.id): s for s in services}
    roots = _partner_cluster_union(services)
    clusters: dict[int, list[Customer]] = {}
    for sid, root in roots.items():
        clusters.setdefault(root, []).append(id_to_customer[sid])

    out: list[Customer] = []
    cluster_members: dict[int, set[int]] = {}
    for group in clusters.values():
        member_ids = {int(c.id) for c in group}
        primary = min(group, key=lambda c: int(c.id))
        pid = int(primary.id)
        out.append(primary)
        cluster_members[pid] = member_ids
    return out, cluster_members


@router.get("")
def get_services(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Vrátí seznam dostupných servisů.

    - admin: všechny servisy
    - user/service: pouze servisy ve stejném tenantovi
    """
    _ensure_services_schema(db)
    query = db.query(Customer).filter(Customer.role.in_(["service", "developer_admin"]))

    if current_user.role not in ["admin", "developer_admin"]:
        tenant_id = getattr(current_user, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant")
        query = query.filter(Customer.tenant_id == tenant_id)

    services = query.order_by(Customer.name.asc(), Customer.email.asc()).all()
    
    return [
        {
            "id": s.id,
            "email": s.email,
            "name": s.name,
            "role": s.role,
            "city": s.city,
            "phone": s.phone,
            "tenant_id": getattr(s, "tenant_id", None),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "vehicles_count": 0
        }
        for s in services
    ]


@router.get("/catalog")
def get_services_catalog(
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
    radius_km: float = Query(
        _DEFAULT_OWNER_DISCOVERY_RADIUS_KM,
        ge=0,
        le=500,
        description="Majitel vozidla: max. vzdálenost v km (0 = bez filtru).",
    ),
):
    """
    Canonical katalog servisů pro uživatelské UI.

    Stejně jako discovery vychází z backendové pravdy `customers.role=service`
    a vrací konzistentní výsledek pro všechny běžné uživatele.
    """
    return get_services_discovery(
        request=request,
        current_user=current_user,
        db=db,
        radius_km=radius_km,
    )


@router.get("/my-contacts")
def get_my_service_contacts(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kontakty na servisy, které mají aktivní propojení s aktuálním zákaznickým účtem.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key == "service":
        return {"services": [], "meta": {"total": 0}}

    rows = (
        db.query(ServiceCustomerLink, Customer)
        .join(Customer, ServiceCustomerLink.service_customer_id == Customer.id)
        .filter(
            ServiceCustomerLink.customer_id == current_user.id,
            ServiceCustomerLink.status == "active",
            Customer.role.in_(["service", "developer_admin"]),
        )
        .order_by(Customer.name.asc(), Customer.email.asc())
        .all()
    )

    services = []
    seen_ids = set()
    for _, service in rows:
        if not service or service.id in seen_ids:
            continue
        seen_ids.add(service.id)
        services.append(
            {
                "id": service.id,
                "name": service.name or service.email,
                "email": service.email,
                "phone": service.phone,
                "ico": service.ico,
                "city": service.city,
                "address": _compose_service_address(service),
            }
        )

    return {
        "services": services,
        "meta": {
            "total": len(services),
        },
    }


@router.get("/access-requests", response_model=ServiceAccessRequestListOutV1)
def get_service_access_requests(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vrátí čekající žádosti servisů o přístup k vozidlům aktuálního uživatele.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Endpoint je dostupný pouze v uživatelském režimu.")

    owned_vehicle_ids = sorted(get_owned_vehicle_ids(db, current_user, tenant_id=getattr(current_user, "tenant_id", None)))
    if not owned_vehicle_ids:
        return {"requests": []}

    rows = (
        db.query(ServiceAccessRequest, Customer, Vehicle)
        .join(Customer, ServiceAccessRequest.service_customer_id == Customer.id)
        .join(Vehicle, ServiceAccessRequest.vehicle_id == Vehicle.id)
        .filter(
            ServiceAccessRequest.owner_customer_id == current_user.id,
            ServiceAccessRequest.vehicle_id.in_(owned_vehicle_ids),
            ServiceAccessRequest.status == "pending",
        )
        .order_by(ServiceAccessRequest.requested_at.desc(), ServiceAccessRequest.id.desc())
        .all()
    )
    return {"requests": [_serialize_access_request_row(request_row, service, vehicle) for request_row, service, vehicle in rows]}


@router.put("/access-requests/{request_id}")
def resolve_service_access_request(
    request_id: int,
    payload: ServiceAccessRequestDecisionV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel schválí nebo zamítne pending žádost servisu o přístup k vozidlu.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže rozhodovat o zákaznických žádostech.")

    request_row = (
        db.query(ServiceAccessRequest)
        .filter(
            ServiceAccessRequest.id == request_id,
            ServiceAccessRequest.owner_customer_id == current_user.id,
        )
        .first()
    )
    if not request_row:
        raise HTTPException(status_code=404, detail="Žádost o přístup nebyla nalezena.")
    if str(request_row.status or "") != "pending":
        raise HTTPException(status_code=409, detail="Žádost už byla vyřízena.")

    vehicle = get_owned_vehicle(db, current_user, int(request_row.vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo už není dostupné pro rozhodnutí o přístupu.")

    service = (
        db.query(Customer)
        .filter(
            Customer.id == request_row.service_customer_id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Servis spojený se žádostí nebyl nalezen.")

    decision = str(payload.decision or "").strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Rozhodnutí musí být approved nebo rejected.")

    try:
        request_row.decided_at = datetime.utcnow()
        request_row.decided_by_customer_id = current_user.id
        request_row.decision_note = (payload.note or "").strip() or None

        if decision == "approved":
            finalize_service_access_decision(
                db,
                request_row=request_row,
                vehicle=vehicle,
                owner_customer=current_user,
                service_customer=service,
                decision="approved",
                decided_by=current_user,
                decision_note=(payload.note or "").strip() or None,
                source_route="put_access_requests",
            )
        else:
            finalize_service_access_decision(
                db,
                request_row=request_row,
                vehicle=vehicle,
                owner_customer=current_user,
                service_customer=service,
                decision="rejected",
                decided_by=current_user,
                decision_note=(payload.note or "").strip() or None,
                source_route="put_access_requests",
            )

        request_row.updated_at = datetime.utcnow()
        try:
            notify_service_access_decided(
                db,
                service_customer_id=int(service.id),
                vehicle=vehicle,
                approved=(decision == "approved"),
                owner=current_user,
            )
        except Exception as exc:
            print(f"[SERVICES] In-app oznámení servisu o rozhodnutí žádosti selhalo: {exc}")
        db.commit()
        return {
            "resolved": True,
            "request_id": int(request_row.id),
            "decision": decision,
            "vehicle_id": int(request_row.vehicle_id),
            "service_id": int(request_row.service_customer_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se uložit rozhodnutí o žádosti: {exc}") from exc


@router.get("/vehicle-access", response_model=VehicleServiceLinkListOutV1)
def get_vehicle_access_grants(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vrátí explicitní povolení vozidel pro konkrétní servisy.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Endpoint je dostupný pouze v uživatelském režimu.")

    owned_vehicle_ids = sorted(get_owned_vehicle_ids(db, current_user, tenant_id=getattr(current_user, "tenant_id", None)))
    if not owned_vehicle_ids:
        return {"grants": [], "meta": {"total": 0}}

    rows = (
        db.query(VehicleServiceLink, Customer, Vehicle)
        .join(Customer, VehicleServiceLink.service_customer_id == Customer.id)
        .join(Vehicle, VehicleServiceLink.vehicle_id == Vehicle.id)
        .filter(
            VehicleServiceLink.owner_customer_id == current_user.id,
            VehicleServiceLink.vehicle_id.in_(owned_vehicle_ids),
            VehicleServiceLink.status == "approved",
            Customer.role.in_(["service", "developer_admin"]),
        )
        .order_by(VehicleServiceLink.updated_at.desc())
        .all()
    )

    grants = []
    for access_row, service, vehicle in rows:
        grants.append(
            {
                "service_id": int(access_row.service_customer_id),
                "vehicle_id": int(access_row.vehicle_id),
                "customer_id": int(access_row.owner_customer_id),
                "service_name": service.name or service.email,
                "service_email": service.email,
                "vehicle_name": vehicle_label(vehicle),
                "vehicle_plate": vehicle.plate,
                "status": access_row.status,
                "updated_at": access_row.updated_at.isoformat() if access_row.updated_at else None,
            }
        )

    return {
        "grants": grants,
        "meta": {
            "total": len(grants),
        },
    }


@router.post("/vehicle-access")
def grant_vehicle_access_to_service(
    payload: VehicleAccessGrantRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel explicitně povolí servisu správu konkrétního vozidla.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže měnit oprávnění zákaznického vozidla.")

    vehicle = get_owned_vehicle(db, current_user, int(payload.vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno nebo vám nepatří.")

    service = (
        db.query(Customer)
        .filter(
            Customer.id == payload.service_id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Servis nebyl nalezen.")

    conflict_rows = (
        db.query(ServiceVehicleAccess, Customer)
        .join(Customer, ServiceVehicleAccess.service_customer_id == Customer.id)
        .filter(
            ServiceVehicleAccess.customer_id == current_user.id,
            ServiceVehicleAccess.vehicle_id == vehicle.id,
            ServiceVehicleAccess.status == "active",
            ServiceVehicleAccess.service_customer_id != service.id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .order_by(ServiceVehicleAccess.updated_at.desc())
        .all()
    )
    conflict_services = [
        {
            "service_id": int(conflict_access.service_customer_id),
            "service_name": conflict_service.name or conflict_service.email,
            "service_email": conflict_service.email,
            "updated_at": conflict_access.updated_at.isoformat() if conflict_access.updated_at else None,
        }
        for conflict_access, conflict_service in conflict_rows
    ]
    conflict_strategy = str(payload.conflict_strategy or "keep").strip().lower()
    if conflict_strategy not in {"ask", "keep", "replace"}:
        conflict_strategy = "keep"

    if conflict_services and conflict_strategy == "ask":
        conflict_names = ", ".join(
            str(item.get("service_name") or item.get("service_email") or f"#{item.get('service_id')}")
            for item in conflict_services[:6]
        )
        return {
            "granted": False,
            "requires_confirmation": True,
            "conflict": True,
            "service_id": int(service.id),
            "vehicle_id": int(vehicle.id),
            "conflict_services": conflict_services,
            "message": (
                "Vozidlo je už přiřazené k jinému servisu"
                + (f": {conflict_names}." if conflict_names else ".")
                + " Zvolte, zda původní přiřazení zachovat, nebo nahradit."
            ),
        }

    try:
        revoked_conflict_service_ids: list[int] = []
        if conflict_services and conflict_strategy == "replace":
            now = datetime.utcnow()
            for conflict_access, _conflict_service in conflict_rows:
                conflict_access.status = "revoked"
                conflict_access.revoked_at = now
                conflict_access.updated_at = now
                revoked_conflict_service_ids.append(int(conflict_access.service_customer_id))

        _upsert_service_customer_link(
            db,
            service_customer_id=service.id,
            service_tenant_id=service.tenant_id,
            target_customer=current_user,
            note="Propojeno přes explicitní povolení vozidla",
        )
        create_or_update_vehicle_service_link(
            db,
            tenant_id=vehicle.tenant_id or current_user.tenant_id or service.tenant_id,
            service_customer_id=service.id,
            owner_customer_id=current_user.id,
            vehicle_id=vehicle.id,
            approved_by_customer_id=current_user.id,
            source_type="direct_user_grant",
            note=(payload.note or "").strip() or None,
        )

        db.commit()
        return {
            "granted": True,
            "service_id": int(service.id),
            "vehicle_id": int(vehicle.id),
            "conflict": bool(conflict_services),
            "conflict_strategy": conflict_strategy,
            "conflict_services": conflict_services,
            "revoked_conflict_service_ids": sorted(set(revoked_conflict_service_ids)),
            "message": (
                "Servisu byl povolen přístup k vybranému vozidlu."
                if not revoked_conflict_service_ids
                else "Servisu byl povolen přístup a původní servisní přiřazení bylo odebráno."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se uložit oprávnění: {exc}") from exc


@router.delete("/vehicle-access/{service_id}/{vehicle_id}")
def revoke_vehicle_access_for_service(
    service_id: int,
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel odebere servisu explicitní oprávnění ke konkrétnímu vozidlu.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže měnit oprávnění zákaznického vozidla.")

    vehicle = get_owned_vehicle(db, current_user, int(vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno nebo vám nepatří.")

    link_row = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.service_customer_id == service_id,
            VehicleServiceLink.owner_customer_id == current_user.id,
            VehicleServiceLink.vehicle_id == vehicle_id,
            VehicleServiceLink.status == "approved",
        )
        .first()
    )
    if not link_row:
        return {
            "revoked": False,
            "service_id": int(service_id),
            "vehicle_id": int(vehicle_id),
            "message": "Pro danou kombinaci servis/vozidlo nebylo aktivní oprávnění.",
        }

    try:
        revoke_vehicle_service_link(
            db,
            service_customer_id=service_id,
            vehicle_id=vehicle_id,
            revoked_by_customer_id=current_user.id,
            reason="user_revoke",
        )
        db.commit()
        return {
            "revoked": True,
            "service_id": int(service_id),
            "vehicle_id": int(vehicle_id),
            "message": "Přístup servisu k vozidlu byl odebrán.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se odebrat oprávnění: {exc}") from exc


@router.delete("/my-contacts/{service_id}")
def disconnect_my_service_contact(
    service_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel odpojí servisní kontakt:
    - zneaktivní vazbu ServiceCustomerLink
    - odebere všechna aktivní oprávnění ServiceVehicleAccess vůči tomuto servisu
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže odpojovat zákaznické servisní kontakty.")

    service = (
        db.query(Customer)
        .filter(
            Customer.id == service_id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Servis nebyl nalezen.")

    link_row = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == service_id,
            ServiceCustomerLink.customer_id == current_user.id,
            ServiceCustomerLink.status == "active",
        )
        .first()
    )
    access_rows = (
        db.query(ServiceVehicleAccess)
        .filter(
            ServiceVehicleAccess.service_customer_id == service_id,
            ServiceVehicleAccess.customer_id == current_user.id,
            ServiceVehicleAccess.status == "active",
        )
        .all()
    )

    if not link_row and not access_rows:
        return {
            "disconnected": False,
            "service_id": int(service_id),
            "service_name": service.name or service.email,
            "revoked_vehicles_count": 0,
            "message": "Servis už není aktivně propojen s vaším účtem.",
        }

    try:
        now = datetime.utcnow()
        revoked_vehicle_ids: list[int] = []
        if link_row:
            link_row.status = "archived"
            link_row.updated_at = now
        for access in access_rows:
            access.status = "revoked"
            access.revoked_at = now
            access.updated_at = now
            if access.vehicle_id is not None:
                revoked_vehicle_ids.append(int(access.vehicle_id))
        db.commit()
        return {
            "disconnected": True,
            "service_id": int(service_id),
            "service_name": service.name or service.email,
            "revoked_vehicles_count": len(revoked_vehicle_ids),
            "revoked_vehicle_ids": sorted(set(revoked_vehicle_ids)),
            "message": "Servis byl odpojen a jeho přístup k vašim vozidlům byl odebrán.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se servis odpojit: {exc}") from exc


def _notify_service_link_from_customer_email(*, service: Customer, customer: Customer) -> bool:
    """Informuje servis e-mailem, že si jej zákazník přidal jako kontakt."""
    try:
        from src.modules.email_client.service import EmailService

        svc = EmailService()
        if not svc.is_configured():
            return False
        to_email = str(service.email or "").strip().lower()
        if not to_email or "@" not in to_email:
            return False
        cust_label = (customer.name or "").strip() or customer.email or "Zákazník"
        subject = f"[{APP_DISPLAY_NAME}] Propojení účtu — žádost od zákazníka"
        body = (
            f"Dobrý den,\n\n"
            f"zákazník {cust_label} ({customer.email}) v aplikaci {APP_DISPLAY_NAME} "
            f"potvrdil propojení s vaším servisním účtem.\n\n"
            f"Přihlaste se do servisního přehledu a zkontrolujte přístup klientů.\n\n"
            f"Tým {APP_DISPLAY_NAME}\n"
        )
        return bool(svc.send_simple_email(to_email, subject, body, html_body=None))
    except Exception as exc:
        print(f"[SERVICES] Oznámení servisu o propojení selhalo: {exc}")
        return False


@router.post("/connect-by-email")
def connect_my_account_to_service_by_email(
    payload: ConnectServiceByEmailRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Majitel vozidla zadá e-mail registrovaného servisu — účty se propojí (stejně jako při vzájemné pozvánce).
    """
    _ensure_services_schema(db)
    actor_role = normalize_role(current_user.role)
    if actor_role == ROLE_SERVICE:
        raise HTTPException(status_code=403, detail="Tuto akci lze použít jen z uživatelského účtu.")

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant")

    target_email = _normalize_email(payload.service_email)
    if not target_email:
        raise HTTPException(status_code=422, detail="Zadejte platný e-mail servisu.")

    if target_email == _normalize_email(current_user.email):
        raise HTTPException(status_code=400, detail="Nelze propojit účet sám se sebou.")

    service = get_customer_by_email(db, target_email)
    if not service or normalize_role(service.role) != ROLE_SERVICE:
        raise HTTPException(
            status_code=404,
            detail="Servis s tímto e-mailem není v aplikaci jako aktivní servisní účet evidován.",
        )

    if not service.password_hash:
        raise HTTPException(status_code=400, detail="Tento servisní účet ještě není aktivní.")

    if not bool(getattr(service, "partner_catalog_approved", False)):
        raise HTTPException(
            status_code=400,
            detail="Tento servis není ve veřejném adresáři schválených partnerů. Použijte údaje od ověřeného servisu nebo kontaktujte podporu.",
        )

    try:
        _upsert_service_customer_link(
            db,
            service_customer_id=int(service.id),
            service_tenant_id=service.tenant_id,
            target_customer=current_user,
            note="Propojeno podle e-mailu servisu z adresáře partnerů",
        )
        db.commit()
        email_sent = _notify_service_link_from_customer_email(service=service, customer=current_user)
        return {
            "linked": True,
            "service_id": int(service.id),
            "service_name": service.name or service.email,
            "email_sent": email_sent,
            "message": (
                "Účty jsou propojeny. Servis byl informován e-mailem."
                if email_sent
                else "Účty jsou propojeny. Oznámení e-mailem se nepodařilo odeslat (zkontrolujte SMTP)."
            ),
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se propojit účty: {exc}") from exc


@router.get("/geocode-suggest")
def geocode_suggest_places(
    q: str = Query("", min_length=2, max_length=180),
    limit: int = Query(8, ge=1, le=12),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Návrhy míst v ČR pro adresář servisních partnerů (OSM Nominatim, přednostně ČR).

    Použití: uživatel píše město / okres / ulici a vybere přesný bod; výpis partnerů se pak
    řadí a filtruje podle /services/discovery?s ref_lat & ref_lon.
    """
    _ensure_services_schema(db)
    raw_hits = _nominatim_search_results(q, limit=limit)
    items: list[dict[str, Any]] = []
    for hit in raw_hits:
        lat = _safe_float(hit.get("lat"))
        lon = _safe_float(hit.get("lon"))
        if lat is None or lon is None:
            continue
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            continue
        addr = hit.get("address")
        subtitle = _subtitle_from_nominatim_address(addr)
        disp = hit.get("display_name")
        label = str(disp).strip() if isinstance(disp, str) else subtitle or q
        if len(label) > 240:
            label = label[:237] + "…"
        items.append(
            {
                "label": label,
                "subtitle": subtitle or None,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "type": hit.get("type"),
                "category": hit.get("category"),
            }
        )
    return {"items": items}


@router.get("/discovery")
def get_services_discovery(
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
    radius_km: float = Query(
        _DEFAULT_OWNER_DISCOVERY_RADIUS_KM,
        ge=0,
        le=500,
        description="Majitel vozidla: max. vzdálenost v km od polohy (hlavičky / profil). 0 = bez omezení.",
    ),
    ref_lat: Optional[float] = Query(
        default=None,
        description="Volitelná referenční zeměpisná šířka (např. výběr z našeptávače adres). Spolu s ref_lon přebije GPS a profil.",
    ),
    ref_lon: Optional[float] = Query(
        default=None,
        description="Volitelná referenční zeměpisná délka.",
    ),
):
    """
    Katalog aktivních servisů pro uživatele.

    - Vrací servisní účty (role=service, případně developer_admin u interních výpisů).
    - Majitelé vozidel: jen účty schválené do veřejného adresáře (`partner_catalog_approved`)
      a účty s aktivním propojením; nikoli developer_admin ani neověřené servisy.
    - Majitel vozidla: pokud je známá reference poloha, výchozí filtr **do radius_km km**
      (výchozí 50 km); **propojené** servisy jsou vždy zahrnuty i mimo kruh.
    - Interně: servisní účty mají výpis omezený na vlastní tenant; propojení nadále přidá výjimku.
    - Geolokační řazení jako dříve (hlavičky / profilová adresa), nebo explicitní ref_lat/ref_lon
      (např. místo na dovolené — uživatel ho vybere z našeptávače adres).
    """
    radius_km = float(_unwrap_fastapi_query_param(radius_km) or 0)
    ref_lat = _unwrap_fastapi_query_param(ref_lat)
    ref_lon = _unwrap_fastapi_query_param(ref_lon)
    if ref_lat is not None and not isinstance(ref_lat, (int, float)):
        try:
            ref_lat = float(ref_lat)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Neplatné ref_lat.") from None
    if ref_lon is not None and not isinstance(ref_lon, (int, float)):
        try:
            ref_lon = float(ref_lon)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Neplatné ref_lon.") from None
    _ensure_services_schema(db)

    linked_service_ids: set[int] = set()
    actor_role = normalize_role(current_user.role)
    if actor_role != ROLE_SERVICE:
        linked_rows = (
            db.query(ServiceCustomerLink.service_customer_id)
            .join(Customer, Customer.id == ServiceCustomerLink.service_customer_id)
            .filter(
                ServiceCustomerLink.customer_id == current_user.id,
                ServiceCustomerLink.status == "active",
                Customer.role.in_(["service", "developer_admin"]),
            )
            .all()
        )
        linked_service_ids = {int(service_id) for (service_id,) in linked_rows if service_id is not None}

    if actor_role == ROLE_SERVICE or _is_admin_role(current_user.role):
        query = db.query(Customer).filter(Customer.role.in_(["service", "developer_admin"]))
    else:
        owner_parts = [
            and_(
                Customer.role == "service",
                Customer.partner_catalog_approved.is_(True),
            )
        ]
        if linked_service_ids:
            owner_parts.append(
                and_(
                    Customer.id.in_(list(linked_service_ids)),
                    Customer.role.in_(["service", "developer_admin"]),
                )
            )
        query = db.query(Customer).filter(or_(*owner_parts))

    if not _is_admin_role(current_user.role):
        tenant_id = getattr(current_user, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant")
        if actor_role == ROLE_SERVICE:
            if linked_service_ids:
                query = query.filter(or_(Customer.tenant_id == tenant_id, Customer.id.in_(list(linked_service_ids))))
            else:
                query = query.filter(Customer.tenant_id == tenant_id)

    if linked_service_ids:
        query = query.filter(or_(Customer.password_hash.isnot(None), Customer.id.in_(list(linked_service_ids))))
    else:
        query = query.filter(Customer.password_hash.isnot(None))

    query = query.filter(Customer.is_deleted.is_(False))

    services = query.order_by(Customer.name.asc(), Customer.email.asc()).all()

    vehicle_access_counts: dict[int, int] = {}
    if actor_role != ROLE_SERVICE and services:
        access_rows = (
            db.query(
                ServiceVehicleAccess.service_customer_id,
                func.count(ServiceVehicleAccess.id),
            )
            .filter(
                ServiceVehicleAccess.customer_id == current_user.id,
                ServiceVehicleAccess.status == "active",
            )
            .group_by(ServiceVehicleAccess.service_customer_id)
            .all()
        )
        vehicle_access_counts = {
            int(service_id): int(count or 0)
            for service_id, count in access_rows
            if service_id is not None
        }
        vsl_rows = (
            db.query(
                VehicleServiceLink.service_customer_id,
                func.count(VehicleServiceLink.id),
            )
            .filter(
                VehicleServiceLink.owner_customer_id == current_user.id,
                VehicleServiceLink.status == "approved",
            )
            .group_by(VehicleServiceLink.service_customer_id)
            .all()
        )
        for service_id, cnt in vsl_rows:
            if service_id is None:
                continue
            sid = int(service_id)
            v = int(cnt or 0)
            prev = int(vehicle_access_counts.get(sid, 0))
            vehicle_access_counts[sid] = max(prev, v)

    partner_clusters: dict[int, set[int]] = {
        int(s.id): {int(s.id)} for s in services
    }
    if actor_role != ROLE_SERVICE and not _is_admin_role(current_user.role):
        services, partner_clusters = _dedupe_discovery_services_for_owner(services)

    active_access_counts = vehicle_access_counts

    reference_coords: Optional[tuple[float, float]] = None
    reference_source = "none"

    if ref_lat is not None and ref_lon is not None:
        flat = float(ref_lat)
        flon = float(ref_lon)
        if flat < -90 or flat > 90 or flon < -180 or flon > 180:
            raise HTTPException(status_code=422, detail="Neplatné souřadnice ref_lat/ref_lon.")
        reference_coords = (round(flat, 6), round(flon, 6))
        reference_source = "explore_place"
    elif ref_lat is not None or ref_lon is not None:
        raise HTTPException(status_code=422, detail="Zadejte společně ref_lat i ref_lon, nebo je vynechte.")

    if reference_coords is None:
        reference_coords = _extract_client_coordinates(request)
        reference_source = "browser"

    if reference_coords is None:
        profile_address = _build_service_address(current_user)
        if profile_address:
            geocoded_user = _geocode_address(profile_address)
            if geocoded_user and geocoded_user.get("lat") is not None and geocoded_user.get("lon") is not None:
                reference_coords = (float(geocoded_user["lat"]), float(geocoded_user["lon"]))
                reference_source = "profile_address"

    ref_lat = reference_coords[0] if reference_coords else None
    ref_lon = reference_coords[1] if reference_coords else None

    rows = []
    used_new_lookups = 0
    for service in services:
        address = _build_service_address(service)
        cache_key = address.strip().lower()
        cached = _cache_get(cache_key) if cache_key else None

        geocoded = cached
        if geocoded is None and address:
            if used_new_lookups < _SERVICE_GEOLOOKUP_MAX_NEW_LOOKUPS_PER_REQUEST:
                geocoded = _geocode_address(address)
                used_new_lookups += 1
            else:
                geocoded = None

        lat = _safe_float((geocoded or {}).get("lat"))
        lon = _safe_float((geocoded or {}).get("lon"))
        distance_km = None
        if ref_lat is not None and ref_lon is not None and lat is not None and lon is not None:
            distance_km = _haversine_km(ref_lat, ref_lon, lat, lon)

        sid = int(service.id)
        members = partner_clusters.get(sid, {sid})
        row_linked = any(mid in linked_service_ids for mid in members)
        row_vehicles = sum(int(vehicle_access_counts.get(mid, 0)) for mid in members)

        rows.append(
            {
                "id": service.id,
                "name": service.name or "Neznámý servis",
                "email": service.email,
                "phone": service.phone,
                "city": service.city,
                "street": service.street,
                "street_number": service.street_number,
                "zip": service.zip,
                "ico": service.ico,
                "distance_km": distance_km,
                "has_precise_distance": distance_km is not None,
                "coordinates": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None,
                "is_linked": row_linked,
                "shared_vehicles_count": row_vehicles,
                "created_at": service.created_at.isoformat() if service.created_at else None,
                "partner_public_profile": partner_public_profile_from_db(
                    getattr(service, "partner_public_profile", None)
                ),
            }
        )

    rows.sort(key=lambda item: (item["distance_km"] is None, item["distance_km"] or 10**9, (item.get("name") or "").lower()))

    apply_radius = (
        actor_role != ROLE_SERVICE
        and not _is_admin_role(current_user.role)
        and ref_lat is not None
        and ref_lon is not None
        and float(radius_km) > 0
    )
    eff_radius = float(radius_km) if apply_radius else None
    if apply_radius:
        rmax = float(radius_km)
        rows = [
            r
            for r in rows
            if bool(r.get("is_linked"))
            or r.get("distance_km") is None
            or float(r["distance_km"]) <= rmax
        ]

    return {
        "meta": {
            "total": len(rows),
            "linked_total": sum(1 for item in rows if bool(item.get("is_linked"))),
            "reference_source": reference_source if reference_coords else "none",
            "reference_coordinates": {"lat": ref_lat, "lon": ref_lon} if reference_coords else None,
            "distance_sorted": bool(reference_coords),
            "discovery_radius_km": eff_radius,
            "within_radius_filter": bool(apply_radius),
        },
        "services": rows,
    }


# -----------------------------------------------------------------------------
# Propojení servis–vozidlo: kanonické cesty (stejná logika jako /services/workspace/*)
# -----------------------------------------------------------------------------


@router.post("/vehicle-lookup", response_model=ServiceVehicleLookupResponseV1)
def vehicle_lookup_for_service_product_path(
    payload: ServiceVehicleLookupRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SPZ/VIN lookup bez historie + audit; viz ``service_workspace.lookup_vehicle_for_service``."""
    from . import service_workspace as _service_workspace

    return _service_workspace.lookup_vehicle_for_service(payload, current_user, db)


@router.post("/access-requests")
def create_service_access_request_product_path(
    payload: ServiceAccessRequestCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Servis odešle žádost o přístup; viz ``service_workspace.create_service_access_request``."""
    from . import service_workspace as _service_workspace

    return _service_workspace.create_service_access_request(payload, current_user, db)


@router.get("/approved-vehicles", response_model=ServiceApprovedVehicleListOutV1)
def list_approved_service_vehicles_product_path(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Schválená vozidla servisu; viz ``service_workspace.list_approved_service_vehicles``."""
    from . import service_workspace as _service_workspace

    return _service_workspace.list_approved_service_vehicles(current_user, db)


class ServiceCustomerLinkConfirmRequestV1(BaseModel):
    confirm_token: str = Field(..., min_length=12, max_length=4096)


@router.post("/customer-links/confirm-as-owner")
def confirm_service_customer_link_as_owner(
    payload: ServiceCustomerLinkConfirmRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Zákazník potvrdí žádost servisu o propojení účtu (e-mailový odkaz)."""
    from ..service_workspace_customer_centre import confirm_service_customer_link_core

    return confirm_service_customer_link_core(db, token=payload.confirm_token, acting_customer=current_user)
