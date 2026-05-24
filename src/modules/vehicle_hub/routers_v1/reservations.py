"""
Reservations API v1.0 router (Objednávky do servisu)
"""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import secrets

from src.core.config import FRONTEND_BASE_URL
from src.core.rbac import is_admin
from src.modules.vehicle_hub.workspace_entitlements import (
    customer_acts_as_service_operator,
    customer_has_user_workspace_access,
    effective_workspace_kinds,
)
from ..database import get_db
from ..models import (
    Reservation as ReservationModel,
    Vehicle as VehicleModel,
    Customer,
    ServiceCustomerLink,
    ServiceCustomerInvite,
    ServiceVehicleAccess,
    VehicleOwnership,
)
from ..schema_management import assert_module_ready
from .auth import get_current_user
from .schemas import (
    ReservationCreateV1,
    ReservationUpdateV1,
    ReservationOutV1,
    ReservationVehicleOptionOutV1,
)
from ..email_notifications import (
    send_reservation_created_email,
    send_reservation_status_email,
    send_reservation_rescheduled_email,
)
from ..ownership import get_owned_vehicle, get_owned_vehicle_rows, get_primary_vehicle_owner
from ...licensing.service import assert_feature

router = APIRouter(prefix="/reservations", tags=["reservations-v1"])

VALID_RESERVATION_STATUSES = {"PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"}
RESERVATION_AUTO_LINK_PREFIX = "__RESERVATION_AUTO_LINK__:"
class ReservationClaimLinkRequest(BaseModel):
    token: str = Field(min_length=12, max_length=512)


def _normalize_status(status: str) -> str:
    return str(status or "").strip().upper()


def _ensure_reservations_schema(db: Session) -> None:
    assert_module_ready(db, "reservations", detail_prefix="Rezervace nejsou připravené")


def _assert_user_reservations_enabled(db: Session, current_user: Customer) -> None:
    if "user" not in effective_workspace_kinds(current_user):
        return
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        return
    assert_feature(db, int(tenant_id), "reservations")


def _is_admin_role(role: Optional[str]) -> bool:
    return is_admin(role)


def _ensure_reservation_rw_access(current_user: Customer, reservation: ReservationModel) -> None:
    if _is_admin_role(current_user.role):
        return
    kinds = effective_workspace_kinds(current_user)
    if "user" in kinds and reservation.customer_id == current_user.id:
        return
    if "service" in kinds and reservation.service_id == current_user.id:
        return
    raise HTTPException(status_code=403, detail="Nemáte přístup k této rezervaci")


def _reservation_mutation_role_key(current_user: Customer, reservation: ReservationModel) -> str:
    if _is_admin_role(current_user.role):
        return "admin"
    kinds = effective_workspace_kinds(current_user)
    if "service" in kinds and reservation.service_id == current_user.id:
        return "service"
    if "user" in kinds and reservation.customer_id == current_user.id:
        return "user"
    raise HTTPException(status_code=403, detail="Nemáte přístup k této rezervaci")


def _normalize_email(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _has_active_service_customer_link(db: Session, *, service_id: int, customer_id: int) -> bool:
    link = (
        db.query(ServiceCustomerLink.id)
        .filter(
            ServiceCustomerLink.service_customer_id == service_id,
            ServiceCustomerLink.customer_id == customer_id,
            ServiceCustomerLink.status == "active",
        )
        .first()
    )
    return link is not None


def _upsert_service_vehicle_access(
    db: Session,
    *,
    service_id: int,
    customer_id: int,
    vehicle_id: int,
) -> None:
    existing = (
        db.query(ServiceVehicleAccess)
        .filter(
            ServiceVehicleAccess.service_customer_id == service_id,
            ServiceVehicleAccess.customer_id == customer_id,
            ServiceVehicleAccess.vehicle_id == vehicle_id,
        )
        .first()
    )
    if existing:
        existing.status = "active"
        existing.granted_by_customer_id = customer_id
        existing.revoked_at = None
        existing.updated_at = datetime.utcnow()
        db.flush()
        return

    db.add(
        ServiceVehicleAccess(
            service_customer_id=service_id,
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            status="active",
            granted_by_customer_id=customer_id,
            revoked_at=None,
        )
    )
    db.flush()


def _resolve_vehicle_name(vehicle: VehicleModel) -> Optional[str]:
    if not vehicle:
        return None
    if getattr(vehicle, "nickname", None):
        return vehicle.nickname

    brand = str(getattr(vehicle, "brand", "") or "").strip()
    model = str(getattr(vehicle, "model", "") or "").strip()
    name = " ".join([part for part in [brand, model] if part]).strip()
    if name:
        return name

    if getattr(vehicle, "plate", None):
        return vehicle.plate
    return None


def _reservation_vehicle_label(vehicle: VehicleModel) -> str:
    value = _resolve_vehicle_name(vehicle)
    if value:
        return value
    return f"Vozidlo #{int(getattr(vehicle, 'id', 0) or 0)}"


def _build_reservation_auto_link_message(reservation_id: int) -> str:
    return f"{RESERVATION_AUTO_LINK_PREFIX}{int(reservation_id)}"


def _parse_reservation_id_from_auto_link_message(raw_message: Optional[str]) -> Optional[int]:
    message = str(raw_message or "").strip()
    if not message.startswith(RESERVATION_AUTO_LINK_PREFIX):
        return None
    raw_id = message[len(RESERVATION_AUTO_LINK_PREFIX):].strip()
    if not raw_id.isdigit():
        return None
    return int(raw_id)


def _build_reservation_claim_url(token: str, reservation_id: int) -> str:
    base = str(FRONTEND_BASE_URL or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:8000"

    params = urlencode({
        "reservation_claim_token": token,
        "reservation_id": str(int(reservation_id)),
    })

    if base.endswith("/web/index.html"):
        return f"{base}?{params}"
    if base.endswith("/index.html"):
        return f"{base}?{params}"
    if base.endswith("/web"):
        return f"{base}/index.html?{params}"
    return f"{base}/web/index.html?{params}"


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


def _create_reservation_auto_link_invite(
    db: Session,
    *,
    reservation: ReservationModel,
    service: Customer,
    customer: Customer,
) -> ServiceCustomerInvite:
    now = datetime.utcnow()
    email_key = _normalize_email(customer.email)
    marker = f"{RESERVATION_AUTO_LINK_PREFIX}%"
    (
        db.query(ServiceCustomerInvite)
        .filter(
            ServiceCustomerInvite.service_customer_id == service.id,
            func.lower(ServiceCustomerInvite.invite_email) == email_key,
            ServiceCustomerInvite.status == "pending",
            ServiceCustomerInvite.invite_message.like(marker),
        )
        .update(
            {
                ServiceCustomerInvite.status: "cancelled",
                ServiceCustomerInvite.updated_at: now,
            },
            synchronize_session=False,
        )
    )

    invite = ServiceCustomerInvite(
        service_tenant_id=service.tenant_id,
        service_customer_id=service.id,
        invite_email=customer.email,
        invite_name=customer.name,
        invite_message=_build_reservation_auto_link_message(reservation.id),
        token=secrets.token_urlsafe(32),
        status="pending",
        sent_at=now,
        expires_at=now + timedelta(days=30),
    )
    db.add(invite)
    db.flush()
    return invite


def _enrich_reservations(db: Session, reservations: List[ReservationModel]) -> List[ReservationModel]:
    if not reservations:
        return reservations

    service_ids = {
        reservation.service_id
        for reservation in reservations
        if getattr(reservation, "service_id", None) is not None
    }
    customer_ids = {
        reservation.customer_id
        for reservation in reservations
        if getattr(reservation, "customer_id", None) is not None
    }
    vehicle_ids = {
        reservation.vehicle_id
        for reservation in reservations
        if getattr(reservation, "vehicle_id", None) is not None
    }

    service_map: Dict[int, Customer] = {}
    customer_map: Dict[int, Customer] = {}
    vehicle_map: Dict[int, VehicleModel] = {}

    if service_ids:
        service_query = db.query(Customer).filter(
            Customer.id.in_(list(service_ids)),
            Customer.role.in_(["service", "developer_admin"])
        )
        service_map = {item.id: item for item in service_query.all()}

    if customer_ids:
        customer_query = db.query(Customer).filter(Customer.id.in_(list(customer_ids)))
        customer_map = {item.id: item for item in customer_query.all()}

    if vehicle_ids:
        vehicle_query = db.query(VehicleModel).filter(VehicleModel.id.in_(list(vehicle_ids)))
        vehicle_map = {item.id: item for item in vehicle_query.all()}

    for reservation in reservations:
        service = service_map.get(getattr(reservation, "service_id", None))
        customer = customer_map.get(getattr(reservation, "customer_id", None))
        vehicle = vehicle_map.get(getattr(reservation, "vehicle_id", None))

        setattr(reservation, "service_name", getattr(service, "name", None) or getattr(service, "email", None))
        setattr(reservation, "service_email", getattr(service, "email", None))
        setattr(reservation, "customer_name", getattr(customer, "name", None) or getattr(customer, "email", None))
        setattr(reservation, "customer_email", getattr(customer, "email", None))
        setattr(reservation, "vehicle_name", _resolve_vehicle_name(vehicle))
        setattr(reservation, "vehicle_plate", getattr(vehicle, "plate", None))

    return reservations


def _vehicle_options_for_user_reservations(
    db: Session,
    current_user: Customer,
    *,
    tenant_id: Optional[int],
) -> List[Dict]:
    vehicles = get_owned_vehicle_rows(db, current_user, tenant_id=tenant_id)
    return [
        {
            "id": int(vehicle.id),
            "name": _reservation_vehicle_label(vehicle),
            "plate": getattr(vehicle, "plate", None),
            "owner_email": getattr(get_primary_vehicle_owner(db, vehicle), "email", None)
            or getattr(vehicle, "user_email", None),
            "is_shared": False,
            "source": "owner",
        }
        for vehicle in vehicles
    ]


def _vehicle_options_for_service_reservations(db: Session, *, service_id: int) -> List[Dict]:
    source_by_vehicle: dict[int, str] = {}

    shared_rows = (
        db.query(ServiceVehicleAccess.vehicle_id)
        .filter(
            ServiceVehicleAccess.service_customer_id == service_id,
            ServiceVehicleAccess.status == "active",
            ServiceVehicleAccess.vehicle_id.isnot(None),
        )
        .all()
    )
    for (vehicle_id,) in shared_rows:
        if vehicle_id is None:
            continue
        source_by_vehicle[int(vehicle_id)] = "service_access"

    reservation_rows = (
        db.query(ReservationModel.vehicle_id)
        .filter(
            ReservationModel.service_id == service_id,
            ReservationModel.vehicle_id.isnot(None),
        )
        .all()
    )
    for (vehicle_id,) in reservation_rows:
        if vehicle_id is None:
            continue
        source_by_vehicle.setdefault(int(vehicle_id), "reservation_history")

    linked_vehicle_rows = (
        db.query(VehicleOwnership.vehicle_id)
        .join(
            ServiceCustomerLink,
            ServiceCustomerLink.customer_id == VehicleOwnership.customer_id,
        )
        .filter(
            VehicleOwnership.is_active.is_(True),
            ServiceCustomerLink.service_customer_id == service_id,
            ServiceCustomerLink.status == "active",
        )
        .all()
    )
    for (vehicle_id,) in linked_vehicle_rows:
        if vehicle_id is None:
            continue
        source_by_vehicle.setdefault(int(vehicle_id), "linked_customer")

    linked_customer_ids = [
        int(link.customer_id)
        for link in db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == service_id,
            ServiceCustomerLink.status == "active",
        )
        .all()
        if link.customer_id is not None
    ]
    if linked_customer_ids:
        linked_customers = db.query(Customer).filter(Customer.id.in_(linked_customer_ids)).all()
        for customer in linked_customers:
            for row in _vehicle_options_for_user_reservations(
                db,
                customer,
                tenant_id=getattr(customer, "tenant_id", None),
            ):
                source_by_vehicle.setdefault(int(row["id"]), "linked_customer")

    vehicle_ids = sorted(source_by_vehicle.keys())
    if not vehicle_ids:
        return []

    query = db.query(VehicleModel).filter(VehicleModel.id.in_(vehicle_ids))
    vehicles = query.order_by(VehicleModel.created_at.desc(), VehicleModel.id.desc()).all()

    return [
        {
            "id": int(vehicle.id),
            "name": _reservation_vehicle_label(vehicle),
            "plate": getattr(vehicle, "plate", None),
            "owner_email": getattr(get_primary_vehicle_owner(db, vehicle), "email", None)
            or getattr(vehicle, "user_email", None),
            "is_shared": True,
            "source": source_by_vehicle.get(int(vehicle.id), "service_access"),
        }
        for vehicle in vehicles
    ]


@router.get("/vehicle-options", response_model=List[ReservationVehicleOptionOutV1])
def get_reservation_vehicle_options(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vozidla dostupná pro vytvoření rezervace.

    - user: vlastní vozidla
    - service: vozidla se sdíleným přístupem + vozidla z dřívějších rezervací servisu
    - admin/developer_admin: tenantová vozidla
    - kombinace user+service (entitlements): sjednocený seznam (vlastní + servisní)
    """
    _ensure_reservations_schema(db)
    role_key = str(current_user.role or "").strip().lower()
    tenant_id = getattr(current_user, "tenant_id", None)
    kinds = effective_workspace_kinds(current_user)

    if _is_admin_role(role_key):
        query = db.query(VehicleModel)
        if tenant_id is not None:
            query = query.filter(VehicleModel.tenant_id == tenant_id)
        vehicles = query.order_by(VehicleModel.created_at.desc(), VehicleModel.id.desc()).limit(500).all()
        return [
            {
                "id": int(vehicle.id),
                "name": _reservation_vehicle_label(vehicle),
                "plate": getattr(vehicle, "plate", None),
                "owner_email": getattr(get_primary_vehicle_owner(db, vehicle), "email", None)
                or getattr(vehicle, "user_email", None),
                "is_shared": True,
                "source": "tenant_admin",
            }
            for vehicle in vehicles
        ]

    merged: Dict[int, Dict] = {}
    if "user" in kinds:
        for row in _vehicle_options_for_user_reservations(db, current_user, tenant_id=tenant_id):
            merged[int(row["id"])] = row
    if "service" in kinds:
        service_id = int(current_user.id)
        for row in _vehicle_options_for_service_reservations(db, service_id=service_id):
            vid = int(row["id"])
            if vid not in merged:
                merged[vid] = row

    return sorted(merged.values(), key=lambda r: int(r["id"]), reverse=True)


@router.post("", response_model=ReservationOutV1)
def create_reservation(
    reservation_data: ReservationCreateV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří novou rezervaci"""
    _ensure_reservations_schema(db)
    client_platform = str(request.headers.get("x-client-platform") or "").strip().lower()
    if not client_platform:
        user_agent = str(request.headers.get("user-agent") or "").lower()
        if "mozilla/" in user_agent:
            client_platform = "web_browser"
        elif "iphone" in user_agent or "ios" in user_agent:
            client_platform = "ios_client"
        else:
            client_platform = "unknown"
    created_via = str(reservation_data.created_via or "").strip().lower() or client_platform

    # Ověřit, že vozidlo existuje
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == reservation_data.vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    # Ověřit, že servis existuje
    service = db.query(Customer).filter(
        Customer.id == reservation_data.service_id,
        Customer.role.in_(["service", "developer_admin"])
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servis nebyl nalezen")

    kinds = effective_workspace_kinds(current_user)
    tenant_id_cu = getattr(current_user, "tenant_id", None)
    owns_vehicle = (
        get_owned_vehicle(db, current_user, int(vehicle.id), tenant_id=tenant_id_cu) is not None
    )

    if _is_admin_role(current_user.role):
        customer = get_primary_vehicle_owner(db, vehicle)
        if not customer:
            raise HTTPException(status_code=404, detail="Zákazník nenalezen")
        customer_id = customer.id
    elif "user" in kinds and owns_vehicle:
        _assert_user_reservations_enabled(db, current_user)
        customer = current_user
        customer_id = current_user.id
    elif "service" in kinds:
        if reservation_data.service_id != current_user.id:
            raise HTTPException(status_code=403, detail="Servis může vytvářet rezervace pouze pro sebe")
        customer = get_primary_vehicle_owner(db, vehicle)
        if not customer:
            raise HTTPException(status_code=404, detail="Zákazník nenalezen")
        customer_id = customer.id
    else:
        raise HTTPException(
            status_code=403,
            detail="Nemáte oprávnění vytvořit rezervaci pro toto vozidlo (chybí vlastnictví nebo servisní režim).",
        )

    # Pokud link není aktivní, vytvoříme rezervaci i tak a pošleme servisu 1-klik potvrzení propojení.
    requires_service_link_confirmation = (
        (not _is_admin_role(current_user.role))
        and (not _has_active_service_customer_link(db, service_id=service.id, customer_id=customer_id))
    )
    
    # Kontrola kolize časů (základní)
    existing = db.query(ReservationModel).filter(
        ReservationModel.service_id == reservation_data.service_id,
        ReservationModel.start_datetime == reservation_data.start_datetime,
        ReservationModel.status != "CANCELLED"
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Rezervace na tento čas již existuje")
    
    # Vytvořit rezervaci
    reservation = ReservationModel(
        tenant_id=getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 1,
        service_id=reservation_data.service_id,
        customer_id=customer_id,
        vehicle_id=reservation_data.vehicle_id,
        service_type=reservation_data.service_type,
        note=reservation_data.note,
        start_datetime=reservation_data.start_datetime,
        end_datetime=reservation_data.end_datetime,
        status="PENDING",
        source_platform=created_via[:64] if created_via else None,
    )
    
    db.add(reservation)
    db.flush()
    print(
        "[RESERVATION] create",
        {
            "reservation_id": int(reservation.id),
            "source": created_via,
            "client_platform_header": client_platform,
            "actor_role": str(current_user.role or ""),
            "actor_id": int(current_user.id),
            "service_id": int(reservation.service_id),
            "vehicle_id": int(reservation.vehicle_id),
        },
    )
    _upsert_service_vehicle_access(
        db,
        service_id=reservation.service_id,
        customer_id=customer_id,
        vehicle_id=reservation.vehicle_id,
    )

    service_link_claim_url: Optional[str] = None
    if requires_service_link_confirmation:
        try:
            invite = _create_reservation_auto_link_invite(
                db,
                reservation=reservation,
                service=service,
                customer=customer,
            )
            service_link_claim_url = _build_reservation_claim_url(invite.token, reservation.id)
        except Exception as invite_exc:
            print(f"[RESERVATION] Nepodařilo se připravit auto-link pozvánku: {invite_exc}")

    db.commit()
    db.refresh(reservation)
    
    # Odeslat e-mail notifikace (na pozadí, neblokovat odpověď)
    try:
        send_reservation_created_email(
            db,
            reservation,
            service_link_claim_url=service_link_claim_url,
            requires_service_link_confirmation=requires_service_link_confirmation,
        )
    except Exception as e:
        print(f"[RESERVATION] Chyba při odesílání e-mailu: {e}")
        # Nevyvolat chybu - rezervace byla úspěšně vytvořena

    _enrich_reservations(db, [reservation])
    return reservation


@router.post("/claim-link")
def claim_reservation_service_link(
    payload: ReservationClaimLinkRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Servis potvrdí propojení klienta z e-mailového odkazu a vazbu aktivuje jedním klikem."""
    if not customer_acts_as_service_operator(current_user):
        raise HTTPException(status_code=403, detail="Potvrzení propojení je dostupné pouze pro servisní účet.")

    token = str(payload.token or "").strip()
    invite = db.query(ServiceCustomerInvite).filter(ServiceCustomerInvite.token == token).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Odkaz pro propojení nebyl nalezen.")

    if not _is_admin_role(current_user.role) and invite.service_customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tento odkaz patří jinému servisnímu účtu.")

    reservation_id = _parse_reservation_id_from_auto_link_message(invite.invite_message)
    if not reservation_id:
        raise HTTPException(status_code=400, detail="Token není určený pro potvrzení rezervace.")

    reservation = db.query(ReservationModel).filter(ReservationModel.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace k propojení nebyla nalezena.")

    if reservation.service_id != invite.service_customer_id:
        raise HTTPException(status_code=409, detail="Token neodpovídá cílovému servisu rezervace.")

    now = datetime.utcnow()
    if invite.status == "accepted":
        return {
            "linked": True,
            "already_linked": True,
            "reservation_id": reservation.id,
            "message": "Propojení už bylo dříve potvrzeno.",
        }

    if invite.status != "pending":
        raise HTTPException(status_code=400, detail="Tento odkaz už není aktivní.")

    if invite.expires_at and invite.expires_at < now:
        invite.status = "expired"
        invite.updated_at = now
        db.commit()
        raise HTTPException(status_code=400, detail="Platnost odkazu vypršela.")

    customer = db.query(Customer).filter(Customer.id == reservation.customer_id).first()
    if not customer:
        customer = (
            db.query(Customer)
            .filter(func.lower(Customer.email) == _normalize_email(invite.invite_email))
            .first()
        )
    if not customer:
        raise HTTPException(status_code=404, detail="Zákaznický účet k propojení nebyl nalezen.")

    try:
        _, created = _upsert_service_customer_link(
            db,
            service_customer_id=invite.service_customer_id,
            service_tenant_id=invite.service_tenant_id or reservation.tenant_id or current_user.tenant_id,
            target_customer=customer,
            note="Propojeno potvrzením rezervace z e-mailu",
        )
        invite.status = "accepted"
        invite.accepted_at = now
        invite.linked_customer_id = customer.id
        invite.linked_customer_tenant_id = customer.tenant_id
        invite.updated_at = now
        db.commit()
        return {
            "linked": True,
            "already_linked": not created,
            "reservation_id": reservation.id,
            "message": "Klient byl přiřazen k servisu a rezervace je připravena ke zpracování.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Potvrzení propojení selhalo: {exc}") from exc


@router.get("/my", response_model=List[ReservationOutV1])
def get_my_reservations(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací rezervace přihlášeného účtu v uživatelském kontextu."""
    if not customer_has_user_workspace_access(current_user):
        raise HTTPException(
            status_code=403,
            detail="Tento účet nemá povolený uživatelský přehled rezervací (/reservations/my).",
        )
    reservations = db.query(ReservationModel).filter(
        ReservationModel.customer_id == current_user.id,
    ).order_by(ReservationModel.start_datetime.desc()).all()

    _enrich_reservations(db, reservations)
    return reservations


@router.get("/service", response_model=List[ReservationOutV1])
def get_service_reservations(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací rezervace pro servis (role service) nebo admin přehled v tenantovi."""
    if not customer_acts_as_service_operator(current_user):
        raise HTTPException(status_code=403, detail="Tento endpoint je pouze pro servis nebo admin")

    query = db.query(ReservationModel)
    role_key = str(current_user.role or "").strip().lower()
    if role_key in {"service", "developer_admin"}:
        query = query.filter(ReservationModel.service_id == current_user.id)
    elif "service" in effective_workspace_kinds(current_user) and role_key == "user":
        query = query.filter(ReservationModel.service_id == current_user.id)
    elif not _is_admin_role(current_user.role):
        raise HTTPException(status_code=403, detail="Nemáte oprávnění pro servisní přehled rezervací")

    reservations = query.order_by(ReservationModel.start_datetime.desc()).all()

    _enrich_reservations(db, reservations)
    return reservations


@router.get("/{reservation_id}", response_model=ReservationOutV1)
def get_reservation(
    reservation_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní rezervaci"""
    reservation = db.query(ReservationModel).filter(
        ReservationModel.id == reservation_id
    ).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace nenalezena")

    _ensure_reservation_rw_access(current_user, reservation)

    _enrich_reservations(db, [reservation])
    return reservation


@router.put("/{reservation_id}", response_model=ReservationOutV1)
def update_reservation(
    reservation_id: int,
    reservation_data: ReservationUpdateV1,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje rezervaci"""
    reservation = db.query(ReservationModel).filter(
        ReservationModel.id == reservation_id
    ).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace nenalezena")

    role_key = _reservation_mutation_role_key(current_user, reservation)
    fields_set = set(getattr(reservation_data, "model_fields_set", set()) or set())
    old_start_datetime = reservation.start_datetime
    old_end_datetime = reservation.end_datetime
    old_status = reservation.status
    status_changed = False
    schedule_changed = False

    # Uživatelský účet může rezervaci pouze zrušit (ne měnit termín ani obsah)
    if role_key == "user":
        if any([
            "service_type" in fields_set,
            "note" in fields_set,
            "start_datetime" in fields_set,
            "end_datetime" in fields_set,
        ]):
            raise HTTPException(
                status_code=403,
                detail="Uživatel nemůže měnit termín ani parametry rezervace. Může ji pouze zrušit."
            )
    elif role_key == "service" and _normalize_status(reservation.status) in {"CANCELLED", "COMPLETED"}:
        if any([
            "service_type" in fields_set,
            "note" in fields_set,
            "start_datetime" in fields_set,
            "end_datetime" in fields_set,
        ]):
            raise HTTPException(
                status_code=400,
                detail="Ukončenou rezervaci již nelze přeplánovat."
            )

    # Aktualizace polí
    if reservation_data.service_type is not None:
        reservation.service_type = reservation_data.service_type
    if reservation_data.note is not None:
        reservation.note = reservation_data.note
    if reservation_data.start_datetime is not None:
        # Ochrana proti dvojitému slotu v rámci stejného servisu
        conflict = db.query(ReservationModel).filter(
            ReservationModel.id != reservation.id,
            ReservationModel.service_id == reservation.service_id,
            ReservationModel.start_datetime == reservation_data.start_datetime,
            ReservationModel.status != "CANCELLED",
        ).first()
        if conflict:
            raise HTTPException(status_code=400, detail="Na zvolený termín už existuje jiná aktivní rezervace")
        reservation.start_datetime = reservation_data.start_datetime
    if "end_datetime" in fields_set:
        reservation.end_datetime = reservation_data.end_datetime

    if reservation.end_datetime is not None and reservation.end_datetime <= reservation.start_datetime:
        raise HTTPException(status_code=400, detail="Datum a čas konce musí být po začátku")

    schedule_changed = (
        reservation.start_datetime != old_start_datetime
        or reservation.end_datetime != old_end_datetime
    )

    if reservation_data.status is not None:
        requested_status = _normalize_status(reservation_data.status)
        if requested_status not in VALID_RESERVATION_STATUSES:
            raise HTTPException(status_code=400, detail="Neplatný status rezervace")

        if role_key == "user":
            if requested_status != "CANCELLED":
                raise HTTPException(status_code=403, detail="Uživatel může rezervaci pouze zrušit")
            if _normalize_status(reservation.status) in {"CANCELLED", "COMPLETED"}:
                raise HTTPException(status_code=400, detail="Rezervace již byla ukončena")
        elif role_key == "service":
            if requested_status == "PENDING":
                raise HTTPException(status_code=403, detail="Servis nemůže vrátit rezervaci do stavu čeká")

        reservation.status = requested_status
        status_changed = old_status != reservation.status
    
    db.commit()
    db.refresh(reservation)

    update_source = str(request.headers.get("x-client-platform") or "").strip().lower()
    if not update_source:
        user_agent = str(request.headers.get("user-agent") or "").lower()
        update_source = "web_browser" if "mozilla/" in user_agent else ("ios_client" if ("iphone" in user_agent or "ios" in user_agent) else "unknown")
    print(
        "[RESERVATION] update",
        {
            "reservation_id": int(reservation.id),
            "source": update_source,
            "actor_role": str(current_user.role or ""),
            "actor_id": int(current_user.id),
            "status": str(reservation.status or ""),
            "schedule_changed": bool(schedule_changed),
        },
    )
    
    # Odeslat e-mail o změně termínu (primárně zákazníkovi)
    if schedule_changed:
        try:
            send_reservation_rescheduled_email(
                db,
                reservation,
                old_start_datetime=old_start_datetime,
                old_end_datetime=old_end_datetime,
                changed_by_role=current_user.role,
            )
        except Exception as e:
            print(f"[RESERVATION] Chyba při odesílání e-mailu o změně termínu: {e}")
            # Nevyvolat chybu - rezervace byla úspěšně aktualizována

    # Odeslat e-mail při změně statusu (CONFIRMED nebo CANCELLED).
    # Pokud byl termín zároveň změněn, status řešíme samostatně pouze u zrušení,
    # aby uživatel nedostal duplicitní e-maily při "přeplánování + potvrzení".
    if status_changed and (not schedule_changed or _normalize_status(reservation.status) == "CANCELLED"):
        try:
            send_reservation_status_email(db, reservation, old_status)
        except Exception as e:
            print(f"[RESERVATION] Chyba při odesílání e-mailu: {e}")
            # Nevyvolat chybu - rezervace byla úspěšně aktualizována

    _enrich_reservations(db, [reservation])
    return reservation


@router.delete("/{reservation_id}")
def delete_reservation(
    reservation_id: int,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Smaže rezervaci"""
    reservation = db.query(ReservationModel).filter(
        ReservationModel.id == reservation_id
    ).first()
    
    if not reservation:
        raise HTTPException(status_code=404, detail="Rezervace nenalezena")

    _ensure_reservation_rw_access(current_user, reservation)
    
    delete_source = str(request.headers.get("x-client-platform") or "").strip().lower()
    if not delete_source:
        user_agent = str(request.headers.get("user-agent") or "").lower()
        delete_source = "web_browser" if "mozilla/" in user_agent else ("ios_client" if ("iphone" in user_agent or "ios" in user_agent) else "unknown")
    print(
        "[RESERVATION] delete",
        {
            "reservation_id": int(reservation.id),
            "source": delete_source,
            "actor_role": str(current_user.role or ""),
            "actor_id": int(current_user.id),
            "service_id": int(reservation.service_id),
            "vehicle_id": int(reservation.vehicle_id),
        },
    )

    db.delete(reservation)
    db.commit()
    
    return {"message": "Rezervace byla smazána"}
