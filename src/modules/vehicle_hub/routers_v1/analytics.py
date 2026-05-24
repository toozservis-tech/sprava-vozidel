"""
Analytics API v1.0 router
Souhrny nákladů a základní statistiky nad service_records.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from src.core.rbac import is_admin, is_service
from ..database import get_db
from ..models import (
    Customer,
    Reminder as ReminderModel,
    ServiceRecord as ServiceRecordModel,
    ServiceVehicleAccess,
    Vehicle as VehicleModel,
    VehicleOwnership,
    VehiclePhotoAsset,
    VehicleServiceLink,
)
from ..ownership import get_owned_vehicle_ids
from ...licensing.service import get_license_status
from .auth import can_access_vehicle, get_current_user
from .schemas import (
    AnalyticsCategoryBreakdownOutV1,
    AnalyticsCategoryItemV1,
    AnalyticsMonthlyCostsOutV1,
    AnalyticsMonthlyEntryV1,
    AnalyticsSummaryOutV1,
)

router = APIRouter(prefix="/analytics", tags=["analytics-v1"])


class DashboardRecentActivityItemV1(BaseModel):
    vehicle_id: int
    vehicle_name: str
    performed_at: Optional[datetime] = None
    description: str


class DashboardAttentionItemV1(BaseModel):
    kind: str
    vehicle_id: Optional[int] = None
    vehicle_name: Optional[str] = None
    label: str
    severity: str = "info"
    days_remaining: Optional[int] = None
    action_label: Optional[str] = None
    action_target: Optional[str] = None


class DashboardLicenseSummaryV1(BaseModel):
    plan: str
    vehicles_count: Optional[int] = None
    license_limit: Optional[int] = None
    is_over_limit: Optional[bool] = None
    vin_decode_enabled: bool = False
    reminders_enabled: bool = True
    reservations_enabled: bool = False
    vehicle_history_enabled: bool = False
    documents_enabled: bool = False
    costs_tracking_enabled: bool = False
    statistics_enabled: bool = False
    sharing_with_service_enabled: bool = False


class DashboardExtrasV1(BaseModel):
    newest_vehicle_id: Optional[int] = None
    newest_vehicle_name: Optional[str] = None
    top_mileage_vehicle_id: Optional[int] = None
    top_mileage_vehicle_name: Optional[str] = None
    top_mileage_km: Optional[int] = None


class DashboardSummaryOutV1(BaseModel):
    scope: str
    vehicles_total: int
    active_reminders: int
    stk_soon: int
    stk_expired: int
    records_missing_history: int
    missing_main_photo: int
    recent_activity: list[DashboardRecentActivityItemV1]
    attention: list[DashboardAttentionItemV1]
    extras: DashboardExtrasV1
    license: Optional[DashboardLicenseSummaryV1] = None


def _vehicle_name(vehicle: VehicleModel) -> str:
    return str(vehicle.nickname or vehicle.plate or f"Vozidlo #{vehicle.id}")


def _vehicle_has_primary_photo(vehicle: VehicleModel) -> bool:
    """
    Hlavní fotka: buď legacy sloupec photo_path, nebo nové primary_photo_asset_id (promoce z galerie).
    Po uploadu z galerie může být photo_path v DB prázdný — stejná sémantika jako v API vozidla.
    """
    if getattr(vehicle, "primary_photo_asset_id", None):
        return True
    p = getattr(vehicle, "photo_path", None)
    return bool(p and str(p).strip())


def _visible_vehicle_ids_for_dashboard(db: Session, *, current_user: Customer) -> list[int]:
    role_key = _normalize_role(getattr(current_user, "role", None))
    tenant_id = getattr(current_user, "tenant_id", None)

    if is_admin(role_key):
        query = db.query(VehicleModel.id).filter(VehicleModel.status != "archived")
        if tenant_id:
            query = query.filter(VehicleModel.tenant_id == tenant_id)
        return [int(row[0]) for row in query.all()]

    if is_service(role_key):
        explicit_ids = (
            db.query(VehicleServiceLink.vehicle_id)
            .filter(
                VehicleServiceLink.service_customer_id == current_user.id,
                VehicleServiceLink.status == "approved",
            )
            .all()
        )
        legacy_ids = (
            db.query(ServiceVehicleAccess.vehicle_id)
            .filter(
                ServiceVehicleAccess.service_customer_id == current_user.id,
                ServiceVehicleAccess.status == "active",
            )
            .all()
        )
        merged = {int(row[0]) for row in explicit_ids + legacy_ids if row and row[0] is not None}
        return sorted(merged)

    return sorted(get_owned_vehicle_ids(db, current_user, tenant_id=tenant_id))


def _active_reminders_count(db: Session, *, current_user: Customer) -> int:
    role_key = _normalize_role(getattr(current_user, "role", None))
    tenant_id = getattr(current_user, "tenant_id", None)
    query = db.query(func.count(ReminderModel.id)).filter(ReminderModel.is_completed.is_(False))
    if is_admin(role_key):
        if tenant_id:
            query = query.filter(ReminderModel.tenant_id == tenant_id)
        return int(query.scalar() or 0)
    query = query.filter(ReminderModel.customer_id == current_user.id)
    return int(query.scalar() or 0)


def _normalize_role(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _normalize_email(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _add_months(month_anchor: date, months_delta: int) -> date:
    month_index = (month_anchor.year * 12 + (month_anchor.month - 1)) + int(months_delta)
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _apply_date_filters(
    query,
    *,
    date_from: Optional[date],
    date_to: Optional[date],
):
    if date_from:
        query = query.filter(ServiceRecordModel.performed_at >= datetime.combine(date_from, time.min))
    if date_to:
        end_exclusive = datetime.combine(date_to + timedelta(days=1), time.min)
        query = query.filter(ServiceRecordModel.performed_at < end_exclusive)
    return query


def _stk_counts(vehicles: list[VehicleModel]) -> tuple[int, int]:
    today = date.today()
    soon_threshold = today + timedelta(days=60)
    stk_soon = 0
    stk_expired = 0
    for vehicle in vehicles:
        valid_to = getattr(vehicle, "stk_valid_until", None)
        if valid_to is None:
            continue
        if valid_to < today:
            stk_expired += 1
        elif valid_to <= soon_threshold:
            stk_soon += 1
    return stk_soon, stk_expired


def _build_dashboard_license_summary(status: dict) -> DashboardLicenseSummaryV1:
    return DashboardLicenseSummaryV1(
        plan=str(status.get("plan") or "free"),
        vehicles_count=status.get("vehicles_count"),
        license_limit=status.get("license_limit"),
        is_over_limit=status.get("is_over_limit"),
        vin_decode_enabled=bool(status.get("vin_decode_enabled", False)),
        reminders_enabled=bool(status.get("reminders_enabled", True)),
        reservations_enabled=bool(status.get("reservations_enabled", False)),
        vehicle_history_enabled=bool(status.get("vehicle_history_enabled", False)),
        documents_enabled=bool(status.get("documents_enabled", False)),
        costs_tracking_enabled=bool(status.get("costs_tracking_enabled", False)),
        statistics_enabled=bool(status.get("statistics_enabled", False)),
        sharing_with_service_enabled=bool(status.get("sharing_with_service_enabled", False)),
    )


@router.get("/dashboard", response_model=DashboardSummaryOutV1)
def get_dashboard_summary(
    recent_limit: int = Query(default=8, ge=1, le=20),
    attention_limit: int = Query(default=14, ge=1, le=30),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle_ids = _visible_vehicle_ids_for_dashboard(db, current_user=current_user)
    role_key = _normalize_role(getattr(current_user, "role", None))
    scope = "tenant" if is_admin(role_key) else ("service" if is_service(role_key) else "user")

    if not vehicle_ids:
        license_summary = None
        if scope == "user" and getattr(current_user, "tenant_id", None):
            status = get_license_status(db, current_user.tenant_id, current_user.email)
            license_summary = _build_dashboard_license_summary(status)
        return DashboardSummaryOutV1(
            scope=scope,
            vehicles_total=0,
            active_reminders=_active_reminders_count(db, current_user=current_user),
            stk_soon=0,
            stk_expired=0,
            records_missing_history=0,
            missing_main_photo=0,
            recent_activity=[],
            attention=[],
            extras=DashboardExtrasV1(),
            license=license_summary,
        )

    vehicles = (
        db.query(VehicleModel)
        .filter(
            VehicleModel.id.in_(vehicle_ids),
            VehicleModel.status != "archived"
        )
        .order_by(VehicleModel.created_at.desc(), VehicleModel.id.desc())
        .all()
    )
    vehicle_by_id = {int(vehicle.id): vehicle for vehicle in vehicles}
    stk_soon, stk_expired = _stk_counts(vehicles)

    records_count_rows = (
        db.query(ServiceRecordModel.vehicle_id, func.count(ServiceRecordModel.id))
        .filter(
            ServiceRecordModel.vehicle_id.in_(vehicle_ids),
            ServiceRecordModel.is_deleted.is_(False),
        )
        .group_by(ServiceRecordModel.vehicle_id)
        .all()
    )
    records_count_by_vehicle = {int(vehicle_id): int(count or 0) for vehicle_id, count in records_count_rows}

    photo_rows = (
        db.query(VehiclePhotoAsset.vehicle_id, func.count(VehiclePhotoAsset.id))
        .filter(
            VehiclePhotoAsset.vehicle_id.in_(vehicle_ids),
            VehiclePhotoAsset.role == "gallery",
            VehiclePhotoAsset.deleted_at.is_(None),
        )
        .group_by(VehiclePhotoAsset.vehicle_id)
        .all()
    )
    photo_count_by_vehicle = {int(vehicle_id): int(count or 0) for vehicle_id, count in photo_rows}

    recent_rows = (
        db.query(ServiceRecordModel, VehicleModel)
        .join(VehicleModel, VehicleModel.id == ServiceRecordModel.vehicle_id)
        .filter(
            ServiceRecordModel.vehicle_id.in_(vehicle_ids),
            ServiceRecordModel.is_deleted.is_(False),
            VehicleModel.status != "archived",
        )
        .order_by(ServiceRecordModel.performed_at.desc(), ServiceRecordModel.id.desc())
        .limit(recent_limit)
        .all()
    )
    recent_activity = [
        DashboardRecentActivityItemV1(
            vehicle_id=int(vehicle.id),
            vehicle_name=_vehicle_name(vehicle),
            performed_at=record.performed_at,
            description=str(record.description or "").strip() or "Servisní záznam",
        )
        for record, vehicle in recent_rows
    ]

    attention: list[DashboardAttentionItemV1] = []
    for vehicle in vehicles:
        vehicle_id = int(vehicle.id)
        vehicle_name = _vehicle_name(vehicle)
        valid_to = getattr(vehicle, "stk_valid_until", None)
        if valid_to is not None:
            days_remaining = (valid_to - date.today()).days
            if days_remaining < 0:
                attention.append(
                    DashboardAttentionItemV1(
                        kind="stk_expired",
                        vehicle_id=vehicle_id,
                        vehicle_name=vehicle_name,
                        label=f"{vehicle_name} — STK po platnosti",
                        severity="critical",
                        days_remaining=days_remaining,
                        action_label="Aktualizovat z VIN",
                        action_target="vin_sync",
                    )
                )
            elif days_remaining <= 60:
                attention.append(
                    DashboardAttentionItemV1(
                        kind="stk_soon",
                        vehicle_id=vehicle_id,
                        vehicle_name=vehicle_name,
                        label=f"{vehicle_name} — blíží se STK ({days_remaining} dní)",
                        severity="warning",
                        days_remaining=days_remaining,
                        action_label="Aktualizovat z VIN",
                        action_target="vin_sync",
                    )
                )

        gallery_count = photo_count_by_vehicle.get(vehicle_id, 0)
        has_primary_photo = _vehicle_has_primary_photo(vehicle)
        if not has_primary_photo:
            attention.append(
                DashboardAttentionItemV1(
                    kind="missing_primary_photo" if gallery_count > 0 else "missing_photo",
                    vehicle_id=vehicle_id,
                    vehicle_name=vehicle_name,
                    label=(
                        f"{vehicle_name} — galerie existuje, ale chybí hlavní fotka"
                        if gallery_count > 0
                        else f"{vehicle_name} — chybí hlavní fotka"
                    ),
                    severity="info",
                    action_label="Doplnit fotku" if gallery_count <= 0 else "Nastavit hlavní",
                    action_target="photo" if gallery_count <= 0 else "gallery_primary",
                )
            )
        if records_count_by_vehicle.get(vehicle_id, 0) == 0:
            attention.append(
                DashboardAttentionItemV1(
                    kind="missing_history",
                    vehicle_id=vehicle_id,
                    vehicle_name=vehicle_name,
                    label=f"{vehicle_name} — zatím bez servisní historie",
                    severity="info",
                    action_label="Přidat servis",
                    action_target="service_record",
                )
            )

    attention.sort(
        key=lambda item: (
            {"critical": 0, "warning": 1, "info": 2}.get(item.severity, 9),
            item.days_remaining if item.days_remaining is not None else 999999,
            item.label.lower(),
        )
    )

    newest_vehicle = vehicles[0] if vehicles else None
    top_mileage_vehicle = None
    for vehicle in vehicles:
        mileage = getattr(vehicle, "current_mileage_km", None)
        if mileage is None:
            continue
        if top_mileage_vehicle is None or int(mileage) > int(getattr(top_mileage_vehicle, "current_mileage_km", 0) or 0):
            top_mileage_vehicle = vehicle

    license_summary = None
    if scope == "user" and getattr(current_user, "tenant_id", None):
        status = get_license_status(db, current_user.tenant_id, current_user.email)
        license_summary = _build_dashboard_license_summary(status)

    missing_main_photo = sum(1 for vehicle in vehicles if not _vehicle_has_primary_photo(vehicle))
    records_missing_history = sum(1 for vehicle in vehicles if records_count_by_vehicle.get(int(vehicle.id), 0) == 0)

    return DashboardSummaryOutV1(
        scope=scope,
        vehicles_total=len(vehicles),
        active_reminders=_active_reminders_count(db, current_user=current_user),
        stk_soon=stk_soon,
        stk_expired=stk_expired,
        records_missing_history=records_missing_history,
        missing_main_photo=missing_main_photo,
        recent_activity=recent_activity,
        attention=attention[:attention_limit],
        extras=DashboardExtrasV1(
            newest_vehicle_id=int(newest_vehicle.id) if newest_vehicle else None,
            newest_vehicle_name=_vehicle_name(newest_vehicle) if newest_vehicle else None,
            top_mileage_vehicle_id=int(top_mileage_vehicle.id) if top_mileage_vehicle else None,
            top_mileage_vehicle_name=_vehicle_name(top_mileage_vehicle) if top_mileage_vehicle else None,
            top_mileage_km=int(top_mileage_vehicle.current_mileage_km) if top_mileage_vehicle and top_mileage_vehicle.current_mileage_km is not None else None,
        ),
        license=license_summary,
    )


def _build_scoped_query(
    db: Session,
    *,
    current_user: Customer,
    vehicle_id: Optional[int],
):
    query = db.query(ServiceRecordModel).join(
        VehicleModel,
        VehicleModel.id == ServiceRecordModel.vehicle_id,
    )

    role_key = _normalize_role(getattr(current_user, "role", None))
    tenant_id = getattr(current_user, "tenant_id", None)

    if vehicle_id is not None:
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        query = query.filter(ServiceRecordModel.vehicle_id == vehicle_id)
        if role_key == "admin" and tenant_id:
            query = query.filter(ServiceRecordModel.tenant_id == tenant_id)
        return query

    if role_key == "user":
        owned_vehicle_ids = sorted(get_owned_vehicle_ids(db, current_user, tenant_id=tenant_id))
        if not owned_vehicle_ids:
            return query.filter(ServiceRecordModel.id == -1)
        query = query.filter(VehicleModel.id.in_(owned_vehicle_ids))
        return query

    if role_key in {"service", "developer_admin"}:
        query = query.filter(ServiceRecordModel.user_id == current_user.id)
        return query

    if role_key == "admin" and tenant_id:
        query = query.filter(ServiceRecordModel.tenant_id == tenant_id)
        return query

    return query.filter(ServiceRecordModel.user_id == current_user.id)


@router.get("/summary", response_model=AnalyticsSummaryOutV1)
def get_analytics_summary(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from nesmí být větší než date_to")

    query = _build_scoped_query(db, current_user=current_user, vehicle_id=vehicle_id)
    query = _apply_date_filters(query, date_from=date_from, date_to=date_to)
    rows = query.all()

    prices = [float(item.price) for item in rows if item.price is not None]
    mileages = [int(item.mileage) for item in rows if item.mileage is not None]
    performed_values = [item.performed_at for item in rows if item.performed_at is not None]

    total_cost = round(sum(prices), 2) if prices else 0.0
    priced_count = len(prices)
    average_cost = round(total_cost / priced_count, 2) if priced_count else None

    return AnalyticsSummaryOutV1(
        scope="vehicle" if vehicle_id else "all",
        vehicle_id=vehicle_id,
        date_from=date_from,
        date_to=date_to,
        total_records=len(rows),
        priced_records=priced_count,
        total_cost_czk=total_cost,
        average_cost_czk=average_cost,
        min_cost_czk=(round(min(prices), 2) if prices else None),
        max_cost_czk=(round(max(prices), 2) if prices else None),
        mileage_min=(min(mileages) if mileages else None),
        mileage_max=(max(mileages) if mileages else None),
        latest_service_at=(max(performed_values) if performed_values else None),
    )


@router.get("/categories", response_model=AnalyticsCategoryBreakdownOutV1)
def get_analytics_categories(
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from nesmí být větší než date_to")

    query = _build_scoped_query(db, current_user=current_user, vehicle_id=vehicle_id)
    query = _apply_date_filters(query, date_from=date_from, date_to=date_to)
    rows = query.all()

    buckets: dict[str, dict[str, object]] = {}
    for item in rows:
        category = str(item.category or "").strip() or "NEZARAZENO"
        bucket = buckets.setdefault(
            category,
            {
                "records_count": 0,
                "priced_records_count": 0,
                "total_cost_czk": 0.0,
                "latest_service_at": None,
            },
        )
        bucket["records_count"] = int(bucket["records_count"]) + 1

        if item.price is not None:
            bucket["priced_records_count"] = int(bucket["priced_records_count"]) + 1
            bucket["total_cost_czk"] = float(bucket["total_cost_czk"]) + float(item.price)

        latest_value = bucket["latest_service_at"]
        if item.performed_at and (latest_value is None or item.performed_at > latest_value):
            bucket["latest_service_at"] = item.performed_at

    items = []
    for category, bucket in buckets.items():
        priced_records_count = int(bucket["priced_records_count"])
        total_cost = round(float(bucket["total_cost_czk"]), 2)
        items.append(
            AnalyticsCategoryItemV1(
                category=category,
                records_count=int(bucket["records_count"]),
                priced_records_count=priced_records_count,
                total_cost_czk=total_cost,
                average_cost_czk=(
                    round(total_cost / priced_records_count, 2) if priced_records_count else None
                ),
                latest_service_at=bucket["latest_service_at"],
            )
        )

    items.sort(key=lambda row: (-row.total_cost_czk, -row.records_count, row.category))

    return AnalyticsCategoryBreakdownOutV1(
        scope="vehicle" if vehicle_id else "all",
        vehicle_id=vehicle_id,
        date_from=date_from,
        date_to=date_to,
        total_records=len(rows),
        categories=items,
    )


@router.get("/monthly-costs", response_model=AnalyticsMonthlyCostsOutV1)
def get_analytics_monthly_costs(
    months: int = Query(default=12, ge=1, le=36),
    vehicle_id: Optional[int] = Query(default=None, ge=1),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    month_count = int(months)
    today = date.today()
    last_month = _month_start(today)
    first_month = _add_months(last_month, -(month_count - 1))
    end_exclusive = _add_months(last_month, 1)

    query = _build_scoped_query(db, current_user=current_user, vehicle_id=vehicle_id)
    query = query.filter(
        ServiceRecordModel.performed_at >= datetime.combine(first_month, time.min),
        ServiceRecordModel.performed_at < datetime.combine(end_exclusive, time.min),
    )
    rows = query.all()

    entries_map: dict[str, dict[str, object]] = {}
    for offset in range(month_count):
        month_value = _add_months(first_month, offset)
        month_key = f"{month_value.year:04d}-{month_value.month:02d}"
        entries_map[month_key] = {
            "month": month_key,
            "label": f"{month_value.month:02d}/{month_value.year}",
            "records_count": 0,
            "priced_records_count": 0,
            "total_cost_czk": 0.0,
        }

    for item in rows:
        source_dt = item.performed_at or item.created_at
        if source_dt is None:
            continue

        month_key = f"{source_dt.year:04d}-{source_dt.month:02d}"
        bucket = entries_map.get(month_key)
        if not bucket:
            continue

        bucket["records_count"] = int(bucket["records_count"]) + 1
        if item.price is not None:
            bucket["priced_records_count"] = int(bucket["priced_records_count"]) + 1
            bucket["total_cost_czk"] = float(bucket["total_cost_czk"]) + float(item.price)

    entries = [
        AnalyticsMonthlyEntryV1(
            month=payload["month"],
            label=payload["label"],
            records_count=int(payload["records_count"]),
            priced_records_count=int(payload["priced_records_count"]),
            total_cost_czk=round(float(payload["total_cost_czk"]), 2),
        )
        for payload in entries_map.values()
    ]

    total_records = sum(item.records_count for item in entries)
    priced_records = sum(item.priced_records_count for item in entries)
    total_cost = round(sum(item.total_cost_czk for item in entries), 2)

    return AnalyticsMonthlyCostsOutV1(
        scope="vehicle" if vehicle_id else "all",
        vehicle_id=vehicle_id,
        months=month_count,
        generated_at=datetime.utcnow(),
        total_records=total_records,
        priced_records=priced_records,
        total_cost_czk=total_cost,
        entries=entries,
    )
