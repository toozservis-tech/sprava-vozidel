"""
Reminders API v1.0 router (Připomínky)
Kompletní CRUD operace pro automatické i ruční připomínky
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, inspect, or_
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from src.core.branding import APP_DISPLAY_NAME
from src.core.datetime_cz import (
    prague_day_bounds_naive_utc,
    prague_day_start_as_naive_utc,
    prague_today,
)

from ..database import get_db
from ..models import (
    Vehicle as VehicleModel,
    ServiceRecord as ServiceRecordModel,
    Customer,
    Reminder as ReminderModel,
    EmailNotificationLog,
    PushSubscription,
)
from .auth import get_current_user
from .schemas import (
    ReminderOutV1,
    ReminderCreateV1,
    ReminderUpdateV1,
)
from ..email_notifications import send_reminder_email, send_reminder_created_email
from ..ownership import get_owned_vehicle, get_owned_vehicle_rows
from ..push_notifications import send_push_to_customer
from ..schema_management import assert_module_ready
from ..user_in_app_notifications import create_user_in_app_notification
from .reminder_settings import get_reminder_settings
from ...licensing.service import (
    FREE_ACTIVE_MANUAL_REMINDERS_LIMIT,
    get_license_status,
)

router = APIRouter(prefix="/reminders", tags=["reminders-v1"])

REMINDER_COMPLETION_BLOCK_MESSAGE = (
    "Tento typ připomínky nelze uzavřít jednorázovým přepnutím. "
    "Automatické a opakované připomínky upravte změnou termínu nebo celé série."
)


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Převede datetime na UTC bez timezone info (DB ukládá naive UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _ensure_reminders_schema(db: Session) -> None:
    assert_module_ready(db, "reminders", detail_prefix="Připomínky nejsou připravené")


def _get_user_owned_vehicle_rows(db: Session, customer: Customer) -> list[VehicleModel]:
    return get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None))


def _get_user_owned_vehicle(db: Session, customer: Customer, vehicle_id: int) -> Optional[VehicleModel]:
    return get_owned_vehicle(db, customer, int(vehicle_id), tenant_id=getattr(customer, "tenant_id", None))


def _enforce_free_manual_reminder_limit(
    db: Session,
    *,
    tenant_id: int,
    customer_id: int,
    user_email: Optional[str],
    requested_new_count: int = 1,
) -> None:
    license_status = get_license_status(db, tenant_id, user_email)
    if str(license_status.get("plan") or "").strip().lower() != "free":
        return

    manual_active_count = int(
        db.query(func.count(ReminderModel.id)).filter(
            ReminderModel.customer_id == customer_id,
            ReminderModel.tenant_id == tenant_id,
            ReminderModel.is_manual == True,
            ReminderModel.is_completed == False,
        ).scalar() or 0
    )
    if manual_active_count + max(0, int(requested_new_count or 0)) > FREE_ACTIVE_MANUAL_REMINDERS_LIMIT:
        raise HTTPException(
            status_code=403,
            detail=(
                "Ve verzi Free můžete mít pouze 1 aktivní ruční připomínku. "
                "Pro více připomínek a opakování přejděte na licenci Basic."
            ),
        )


def _already_sent_today(
    db: Session,
    *,
    notification_type: str,
    entity_id: Optional[int],
    customer_id: Optional[int],
    tenant_id: Optional[int],
    today: date,
) -> bool:
    """today = kalendářní den v Europe/Prague (ne UTC datum serveru)."""
    start_utc, end_utc = prague_day_bounds_naive_utc(today)
    query = db.query(EmailNotificationLog).filter(
        EmailNotificationLog.notification_type == notification_type,
        EmailNotificationLog.entity_id == entity_id,
        EmailNotificationLog.customer_id == customer_id,
        EmailNotificationLog.sent_at >= start_utc,
        EmailNotificationLog.sent_at < end_utc,
    )
    if tenant_id is not None:
        query = query.filter(EmailNotificationLog.tenant_id == tenant_id)
    return query.first() is not None


def _notification_channels(notification_method: Optional[str]) -> tuple[bool, bool]:
    """Vrátí (email, push) kanály podle nastavení."""
    method = (notification_method or "app").strip().lower()
    send_email = method in {"email", "both", "all"}
    send_push = method in {"app", "both", "push", "all"}
    return send_email, send_push


def _has_active_push_subscription(db: Session, *, tenant_id: int, customer_id: int) -> bool:
    """Vrátí True, pokud má zákazník aktivní push subskripci."""
    try:
        row = db.query(PushSubscription.id).filter(
            PushSubscription.tenant_id == tenant_id,
            PushSubscription.customer_id == customer_id,
            PushSubscription.is_active == True,
        ).first()
        return row is not None
    except Exception:
        return False


def _normalize_notification_method(notification_method: Optional[str], *, strict: bool = True) -> Optional[str]:
    """
    Normalizuje per-reminder kanál notifikace.
    Vrací None pro "inherit/default" => použije se globální nastavení uživatele.
    """
    if notification_method is None:
        return None

    method = str(notification_method).strip().lower()
    if method in {"", "inherit", "default", "global", "none", "null"}:
        return None

    if method not in {"app", "email", "both"}:
        if strict:
            raise HTTPException(
                status_code=422,
                detail="Neplatná hodnota notification_method. Povolené: app, email, both.",
            )
        return None

    return method


def is_recurring_reminder(reminder: ReminderModel) -> bool:
    return bool(getattr(reminder, "recurrence_group_id", None))


def ensure_completion_update_allowed(reminder: ReminderModel, requested_is_completed: Optional[bool]) -> None:
    if requested_is_completed is None:
        return
    if not bool(getattr(reminder, "is_manual", False)) or is_recurring_reminder(reminder):
        raise HTTPException(status_code=422, detail=REMINDER_COMPLETION_BLOCK_MESSAGE)


def apply_reminder_completion_update(reminder: ReminderModel, requested_is_completed: Optional[bool]) -> None:
    if requested_is_completed is None:
        return
    ensure_completion_update_allowed(reminder, requested_is_completed)
    reminder.is_completed = bool(requested_is_completed)
    reminder.last_notified_at = None


def _log_push_notification(
    db: Session,
    *,
    tenant_id: int,
    customer: Customer,
    notification_type: str,
    entity_id: Optional[int],
    subject: str,
    status: str = "sent",
    error_message: Optional[str] = None,
) -> None:
    """Zapíše push událost do email_notification_logs (pro audit + deduplikaci)."""
    db.add(
        EmailNotificationLog(
            tenant_id=tenant_id,
            customer_id=customer.id,
            email=customer.email,
            subject=subject,
            notification_type=notification_type,
            entity_id=entity_id,
            status=status,
            error_message=error_message,
        )
    )


@router.get("", response_model=List[ReminderOutV1])
def get_reminders(
    include_completed: bool = Query(
        False,
        description="Zahrnout dokončené ruční připomínky (pro filtr Dokončené / úplný přehled na webu).",
    ),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vrací připomínky pro aktuálního uživatele (automatické i ruční)"""
    from fastapi import HTTPException
    from ...licensing.service import assert_feature
    
    # KROK 1: Zkontrolovat feature flag
    tenant_id = getattr(current_user, 'tenant_id', None)
    if tenant_id:
        try:
            assert_feature(db, tenant_id, "reminders")
        except HTTPException as e:
            raise
    
    try:
        _ensure_reminders_schema(db)
        reminders = []
        
        # Načíst všechna vozidla uživatele
        vehicles = _get_user_owned_vehicle_rows(db, current_user)
        
        today = prague_today()
        thirty_days_later = today + timedelta(days=30)
        
        for vehicle in vehicles:
            vehicle_name = vehicle.nickname or f"{vehicle.brand} {vehicle.model}" or "Bez názvu"
            
            # 1. STK připomínka
            if vehicle.stk_valid_until:
                if vehicle.stk_valid_until <= thirty_days_later:
                    days_until = (vehicle.stk_valid_until - today).days
                    if days_until < 0:
                        text = f"STK vypršela před {abs(days_until)} dny"
                    elif days_until == 0:
                        text = "STK vyprší dnes"
                    else:
                        text = f"STK vyprší za {days_until} dní"
                    
                    reminders.append(ReminderOutV1(
                        id=None,
                        type="STK",
                        vehicle_id=vehicle.id,
                        vehicle_name=vehicle_name,
                        text=text,
                        due_date=vehicle.stk_valid_until,
                        notify_at=None,
                        is_manual=False,
                        is_completed=False
                    ))
            
            # 2. Výměna oleje připomínka
            from sqlalchemy import desc, nullslast
            last_oil_service = db.query(ServiceRecordModel).filter(
                ServiceRecordModel.vehicle_id == vehicle.id,
                ServiceRecordModel.category.isnot(None),
                ServiceRecordModel.category == "OLEJ"
            ).order_by(nullslast(desc(ServiceRecordModel.performed_at))).first()
            
            if last_oil_service and last_oil_service.mileage:
                current_mileage = last_oil_service.mileage
                next_oil_km = current_mileage + 15000
                
                # Najít nejnovější záznam s mileage
                latest_record = db.query(ServiceRecordModel).filter(
                    ServiceRecordModel.vehicle_id == vehicle.id,
                    ServiceRecordModel.mileage.isnot(None)
                ).order_by(nullslast(desc(ServiceRecordModel.performed_at))).first()
                
                if latest_record and latest_record.mileage:
                    current_km = latest_record.mileage
                    km_until_oil = next_oil_km - current_km
                    
                    if km_until_oil <= 5000:
                        reminders.append(ReminderOutV1(
                            id=None,
                            type="OLEJ",
                            vehicle_id=vehicle.id,
                            vehicle_name=vehicle_name,
                            text=f"Výměna oleje za cca {km_until_oil} km (při {current_km} km)",
                            due_date=None,
                            notify_at=None,
                            is_manual=False,
                            is_completed=False
                        ))
                
                # Kontrola času (1 rok od poslední výměny)
                if last_oil_service.performed_at:
                    try:
                        if isinstance(last_oil_service.performed_at, datetime):
                            one_year_later = last_oil_service.performed_at.date() + timedelta(days=365)
                        elif isinstance(last_oil_service.performed_at, date):
                            one_year_later = last_oil_service.performed_at + timedelta(days=365)
                        else:
                            continue
                    except (AttributeError, TypeError):
                        continue
                    if one_year_later <= thirty_days_later:
                        days_until = (one_year_later - today).days
                        if days_until < 0:
                            text = f"Výměna oleje byla před {abs(days_until)} dny"
                        else:
                            text = f"Výměna oleje za {days_until} dní (1 rok od poslední)"
                        
                        reminders.append(ReminderOutV1(
                            id=None,
                            type="OLEJ",
                            vehicle_id=vehicle.id,
                            vehicle_name=vehicle_name,
                            text=text,
                            due_date=one_year_later,
                            notify_at=None,
                            is_manual=False,
                            is_completed=False
                        ))
            
            # 3. Obecné připomínky (next_service_due_date z servisních záznamů)
            upcoming_services = db.query(ServiceRecordModel).filter(
                ServiceRecordModel.vehicle_id == vehicle.id,
                ServiceRecordModel.next_service_due_date.isnot(None),
                ServiceRecordModel.next_service_due_date <= thirty_days_later
            ).order_by(ServiceRecordModel.next_service_due_date.asc()).all()
            
            for service in upcoming_services:
                days_until = (service.next_service_due_date - today).days
                if days_until < 0:
                    text = f"Plánovaný servis: {service.description} (byl před {abs(days_until)} dny)"
                elif days_until == 0:
                    text = f"Plánovaný servis dnes: {service.description}"
                else:
                    text = f"Plánovaný servis za {days_until} dní: {service.description}"
                
                reminders.append(ReminderOutV1(
                    id=None,
                    type="GENERAL",
                    vehicle_id=vehicle.id,
                    vehicle_name=vehicle_name,
                    text=text,
                    due_date=service.next_service_due_date,
                    notify_at=None,
                    is_manual=False,
                    is_completed=False
                ))
        
        # Načíst ruční připomínky uživatele (neukončené)
        manual_reminders = []
        try:
            # Zkontrolovat, zda tabulka Reminder existuje
            try:
                inspector_obj = inspect(db.bind)
                table_names = set(inspector_obj.get_table_names())
                if 'reminders' in table_names:
                    # Filtrovat podle customer_id a tenant_id (pokud existuje)
                    query = db.query(ReminderModel).filter(
                        ReminderModel.customer_id == current_user.id,
                        ReminderModel.is_completed == False
                    )
                    # Přidat filtr podle tenant_id pokud uživatel má tenant_id
                    if hasattr(current_user, 'tenant_id') and current_user.tenant_id is not None:
                        query = query.filter(ReminderModel.tenant_id == current_user.tenant_id)
                    manual_reminders = query.all()
            except (AttributeError, TypeError):
                # Pokud inspect selže, zkusit přímo dotaz
                try:
                    query = db.query(ReminderModel).filter(
                        ReminderModel.customer_id == current_user.id,
                        ReminderModel.is_completed == False
                    )
                    # Přidat filtr podle tenant_id pokud uživatel má tenant_id
                    if hasattr(current_user, 'tenant_id') and current_user.tenant_id is not None:
                        query = query.filter(ReminderModel.tenant_id == current_user.tenant_id)
                    manual_reminders = query.all()
                except Exception:
                    manual_reminders = []
        except Exception as e:
            print(f"[REMINDERS] Warning: Chyba při načítání ručních připomínek: {e}")
            import traceback
            traceback.print_exc()
            manual_reminders = []
        
        # Přidat ruční připomínky do seznamu
        for reminder in manual_reminders:
            vehicle_name = "Obecná připomínka"
            if reminder.vehicle_id:
                vehicle = _get_user_owned_vehicle(db, current_user, int(reminder.vehicle_id))
                if vehicle:
                    vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"
            
            reminders.append(ReminderOutV1(
                id=reminder.id,
                type=reminder.type,
                vehicle_id=reminder.vehicle_id,
                vehicle_name=vehicle_name,
                text=reminder.text,
                due_date=reminder.due_date,
                notify_at=reminder.notify_at,
                notification_method=_normalize_notification_method(reminder.notification_method, strict=False),
                is_manual=True,
                is_completed=reminder.is_completed
            ))
        
        completed_manual_reminders: list = []
        if include_completed:
            try:
                inspector_obj = inspect(db.bind)
                table_names = set(inspector_obj.get_table_names())
                if "reminders" in table_names:
                    cq = db.query(ReminderModel).filter(
                        ReminderModel.customer_id == current_user.id,
                        ReminderModel.is_completed == True,
                    )
                    if hasattr(current_user, "tenant_id") and current_user.tenant_id is not None:
                        cq = cq.filter(ReminderModel.tenant_id == current_user.tenant_id)
                    completed_manual_reminders = cq.order_by(desc(ReminderModel.id)).limit(80).all()
            except Exception as exc:
                print(f"[REMINDERS] Warning: dokončené připomínky nelze načíst: {exc}")
                completed_manual_reminders = []

        for reminder in completed_manual_reminders:
            vehicle_name = "Obecná připomínka"
            if reminder.vehicle_id:
                vehicle = _get_user_owned_vehicle(db, current_user, int(reminder.vehicle_id))
                if vehicle:
                    vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"

            reminders.append(
                ReminderOutV1(
                    id=reminder.id,
                    type=reminder.type,
                    vehicle_id=reminder.vehicle_id,
                    vehicle_name=vehicle_name,
                    text=reminder.text,
                    due_date=reminder.due_date,
                    notify_at=reminder.notify_at,
                    notification_method=_normalize_notification_method(reminder.notification_method, strict=False),
                    is_manual=True,
                    is_completed=True,
                )
            )

        def _effective_dt_for_sort(r: ReminderOutV1) -> datetime:
            if r.notify_at is not None:
                na = r.notify_at
                if getattr(na, "tzinfo", None) is not None:
                    conv = _to_naive_utc(na)
                    return conv if conv is not None else datetime.max
                return na
            if r.due_date is not None:
                return datetime.combine(r.due_date, datetime.min.time())
            return datetime.max

        try:
            incomplete_items = [r for r in reminders if not r.is_completed]
            complete_items = [r for r in reminders if r.is_completed]
            incomplete_items.sort(
                key=lambda r: (_effective_dt_for_sort(r), (r.type or "").lower(), r.text or "")
            )
            complete_items.sort(
                key=lambda r: (-(_effective_dt_for_sort(r).timestamp()), -(r.id or 0))
            )
            reminders.clear()
            reminders.extend(incomplete_items + complete_items)
        except Exception as e:
            print(f"[REMINDERS] Warning: Nepodařilo se seřadit připomínky: {e}")
        
        return reminders
    except HTTPException:
        raise
    except Exception as e:
        print(f"[REMINDERS] Error getting reminders: {e}")
        import traceback
        traceback.print_exc()
        # Vrátit prázdný seznam místo 500 chyby, pokud je to možné
        try:
            return []
        except:
            raise HTTPException(status_code=500, detail=f"Chyba při načítání připomínek: {str(e)}")


@router.post("", response_model=ReminderOutV1)
def create_reminder(
    reminder_data: ReminderCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří novou ruční připomínku, volitelně včetně opakování."""
    try:
        _ensure_reminders_schema(db)

        # Ověřit, že vozidlo patří uživateli (pokud je zadáno)
        if reminder_data.vehicle_id:
            vehicle = _get_user_owned_vehicle(db, current_user, int(reminder_data.vehicle_id))
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno nebo nemáte oprávnění")
        
        # Vytvořit připomínku
        # DŮLEŽITÉ: tenant_id je povinné pole v modelu - musí být nastaveno při registraci/autentizaci
        tenant_id = getattr(current_user, 'tenant_id', None)
        if tenant_id is None:
            # V multi-tenant systému musí mít každý uživatel tenant_id
            # Silent fallback na tenant_id = 1 by porušil data integrity
            # Místo toho vrátíme chybu, která upozorní na problém v konfiguraci uživatele
            raise HTTPException(
                status_code=403,
                detail=f"Uživatel {current_user.email} nemá přiřazený tenant. Kontaktujte administrátora pro opravu účtu."
            )

        # Podpora opakování: repeat_count + repeat_interval_days
        reminders_created = []
        repeat_count = reminder_data.repeat_count or 0
        repeat_interval = reminder_data.repeat_interval_days or 0
        requested_new_count = 1 + (repeat_count if repeat_count > 0 and repeat_interval > 0 else 0)
        _enforce_free_manual_reminder_limit(
            db,
            tenant_id=tenant_id,
            customer_id=current_user.id,
            user_email=current_user.email,
            requested_new_count=requested_new_count,
        )
        notify_at_base = _to_naive_utc(reminder_data.notify_at)
        notification_method = _normalize_notification_method(reminder_data.notification_method)

        def add_reminder(due_date_val, notify_at_val):
            r = ReminderModel(
                tenant_id=tenant_id,
                customer_id=current_user.id,
                vehicle_id=reminder_data.vehicle_id,
                type=reminder_data.type,
                text=reminder_data.text,
                due_date=due_date_val,
                notify_at=notify_at_val,
                notification_method=notification_method,
                last_notified_at=None,
                is_completed=False,
                is_manual=True
            )
            db.add(r)
            db.commit()
            db.refresh(r)
            reminders_created.append(r)
            return r

        # Vždy vytvořit základní připomínku
        first = add_reminder(reminder_data.due_date, notify_at_base)

        # Pokud je nastaveno opakování, vytvořit další
        if repeat_count > 0 and repeat_interval > 0 and (reminder_data.due_date or notify_at_base):
            base_due = reminder_data.due_date
            for i in range(1, repeat_count + 1):
                next_due = base_due + timedelta(days=repeat_interval * i) if base_due else None
                next_notify_at = notify_at_base + timedelta(days=repeat_interval * i) if notify_at_base else None
                add_reminder(next_due, next_notify_at)

        # Odeslat email notifikaci při vytvoření připomínky (pokud je to povoleno)
        try:
            settings = get_reminder_settings(current_user)
            notification_settings = settings.get("notification", {})
            notification_method_effective = notification_method or notification_settings.get("notification_method", "app")
            
            # Odeslat email, pokud je nastaveno "email" nebo "both"
            if notification_method_effective in ["email", "both"]:
                send_reminder_created_email(db, first)
        except Exception as e:
            # Nechceme, aby selhalo vytvoření připomínky kvůli chybě při odesílání emailu
            print(f"[REMINDERS] Warning: Nepodařilo se odeslat email při vytvoření připomínky: {e}")
        
        # Kontrola jen když je logicky „čas doručit“ hned — jinak worker / heartbeat stačí a neexpedujeme hromadu e-mailů.
        now_utc = datetime.utcnow()
        sweep_now = False
        if notify_at_base:
            if now_utc >= notify_at_base:
                sweep_now = True
        elif reminder_data.due_date is not None and reminder_data.due_date <= prague_today():
            sweep_now = True

        if sweep_now:
            try:
                check_and_send_reminder_notifications(db)
            except Exception as sweep_exc:
                print(f"[REMINDERS] Post-create notification sweep failed (non-fatal): {sweep_exc}")
        
        # Vytvořit odpověď
        vehicle_name = "Obecná připomínka"
        if first.vehicle_id:
            vehicle = db.query(VehicleModel).filter(VehicleModel.id == first.vehicle_id).first()
            if vehicle:
                vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"
        
        return ReminderOutV1(
            id=first.id,
            type=first.type,
            vehicle_id=first.vehicle_id,
            vehicle_name=vehicle_name,
            text=first.text,
            due_date=first.due_date,
            notify_at=first.notify_at,
            notification_method=_normalize_notification_method(first.notification_method, strict=False),
            is_manual=True,
            is_completed=first.is_completed
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Chyba při vytváření připomínky: {str(e)}"
        print(f"[REMINDERS] Error in create_reminder: {error_detail}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=error_detail)


@router.put("/{reminder_id}", response_model=ReminderOutV1)
def update_reminder(
    reminder_id: int,
    reminder_update: ReminderUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje ruční připomínku"""
    try:
        _ensure_reminders_schema(db)

        # Načíst připomínku
        reminder = db.query(ReminderModel).filter(
            ReminderModel.id == reminder_id,
            ReminderModel.customer_id == current_user.id
        ).first()
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena nebo nemáte oprávnění")

        update_payload = reminder_update.model_dump(exclude_unset=True)
        reset_last_notified = False

        # Aktualizovat pouze poskytnutá pole
        if "type" in update_payload:
            reminder.type = reminder_update.type
        if "vehicle_id" in update_payload:
            if reminder_update.vehicle_id:
                vehicle = _get_user_owned_vehicle(db, current_user, int(reminder_update.vehicle_id))
                if not vehicle:
                    raise HTTPException(status_code=404, detail="Vozidlo nenalezeno nebo nemáte oprávnění")
                reminder.vehicle_id = reminder_update.vehicle_id
            else:
                reminder.vehicle_id = None
        if "text" in update_payload:
            reminder.text = reminder_update.text
        if "due_date" in update_payload:
            reminder.due_date = reminder_update.due_date
            reset_last_notified = True
        if "notify_at" in update_payload:
            reminder.notify_at = _to_naive_utc(reminder_update.notify_at)
            reset_last_notified = True
        if "notification_method" in update_payload:
            reminder.notification_method = _normalize_notification_method(reminder_update.notification_method)

        if reset_last_notified:
            reminder.last_notified_at = None

        if "is_completed" in update_payload:
            apply_reminder_completion_update(reminder, reminder_update.is_completed)

        db.commit()
        db.refresh(reminder)
        
        if reset_last_notified:
            try:
                now_utc = datetime.utcnow()
                today = prague_today()
                should_sweep = False
                if reminder.notify_at and now_utc >= _to_naive_utc(reminder.notify_at):
                    should_sweep = True
                elif reminder.due_date is not None and reminder.due_date <= today:
                    should_sweep = True
                if should_sweep:
                    check_and_send_reminder_notifications(db)
            except Exception as sweep_exc:
                print(f"[REMINDERS] Post-update notification sweep failed (non-fatal): {sweep_exc}")
        
        # Vytvořit odpověď
        vehicle_name = "Obecná připomínka"
        if reminder.vehicle_id:
            vehicle = db.query(VehicleModel).filter(VehicleModel.id == reminder.vehicle_id).first()
            if vehicle:
                vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"
        
        return ReminderOutV1(
            id=reminder.id,
            type=reminder.type,
            vehicle_id=reminder.vehicle_id,
            vehicle_name=vehicle_name,
            text=reminder.text,
            due_date=reminder.due_date,
            notify_at=reminder.notify_at,
            notification_method=_normalize_notification_method(reminder.notification_method, strict=False),
            is_manual=True,
            is_completed=reminder.is_completed
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Chyba při aktualizaci připomínky: {str(e)}"
        print(f"[REMINDERS] Error in update_reminder: {error_detail}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=error_detail)


@router.delete("/{reminder_id}")
def delete_reminder(
    reminder_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Smaže ruční připomínku"""
    try:
        _ensure_reminders_schema(db)

        # Načíst připomínku
        reminder = db.query(ReminderModel).filter(
            ReminderModel.id == reminder_id,
            ReminderModel.customer_id == current_user.id
        ).first()
        
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena nebo nemáte oprávnění")
        
        db.delete(reminder)
        db.commit()
        
        return {"message": "Připomínka byla smazána"}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_detail = f"Chyba při mazání připomínky: {str(e)}"
        print(f"[REMINDERS] Error in delete_reminder: {error_detail}")
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=error_detail)


@router.post("/check-and-send-notifications")
def check_and_send_reminder_notifications(
    db: Session = Depends(get_db)
):
    """
    Kontroluje připomínky a odesílá upozornění předem podle nastavení uživatelů.
    Tento endpoint by měl být volán pravidelně (např. jednou denně z cron jobu nebo Task Scheduleru).
    """
    try:
        _ensure_reminders_schema(db)
        today = prague_today()
        now_utc = datetime.utcnow()
        sent_count = 0
        error_count = 0
        email_sent_count = 0
        push_sent_count = 0

        checked_manual = 0
        checked_auto_stk = 0

        # Načíst všechny aktivní ruční připomínky s due_date nebo notify_at
        reminders = db.query(ReminderModel).filter(
            ReminderModel.is_completed == False,
            or_(
                ReminderModel.due_date.isnot(None),
                ReminderModel.notify_at.isnot(None)
            )
        ).all()

        for reminder in reminders:
            checked_manual += 1
            try:
                # Načíst uživatele a jeho nastavení
                customer = db.query(Customer).filter(Customer.id == reminder.customer_id).first()
                if not customer:
                    continue

                settings = get_reminder_settings(customer)
                if not settings.get("enabled", True):
                    continue

                notification_settings = settings.get("notification", {})
                reminder_method = _normalize_notification_method(reminder.notification_method, strict=False)
                notification_method = reminder_method or notification_settings.get("notification_method", "app")
                send_email, send_push = _notification_channels(notification_method)
                if send_email and not customer.notify_email:
                    send_email = False
                # Pokud je zvolen kanál "aplikace" ale uživatel nemá aktivní push zařízení,
                # fallbackneme na e-mail (pokud je povolený), aby upozornění nezaniklo.
                if send_push and not send_email:
                    if not _has_active_push_subscription(
                        db,
                        tenant_id=(reminder.tenant_id or getattr(customer, "tenant_id", None) or 1),
                        customer_id=customer.id,
                    ) and customer.notify_email:
                        send_email = True
                if not send_email and not send_push:
                    continue

                try:
                    notify_days_before = int(notification_settings.get("notify_days_before", 7))
                except (TypeError, ValueError):
                    notify_days_before = 7

                tenant_id = reminder.tenant_id or getattr(customer, "tenant_id", None) or 1
                should_send = False
                notification_type = "REMINDER_DUE_DATE"
                debug_reason = None

                # Priorita: explicitní notify_at na konkrétní datum+čas
                if reminder.notify_at is not None:
                    notify_at = _to_naive_utc(reminder.notify_at)
                    if notify_at and now_utc >= notify_at:
                        if reminder.last_notified_at is None or reminder.last_notified_at < notify_at:
                            if not send_email or not _already_sent_today(
                                db,
                                notification_type="REMINDER_NOTIFY_AT",
                                entity_id=reminder.id,
                                customer_id=customer.id,
                                tenant_id=tenant_id,
                                today=today,
                            ):
                                should_send = True
                                notification_type = "REMINDER_NOTIFY_AT"
                                debug_reason = f"notify_at reached ({notify_at.isoformat()})"
                elif reminder.due_date is not None:
                    # Fallback: globální nastavení předstihu
                    days_until = (reminder.due_date - today).days
                    # Odešli notifikaci, jakmile jsme v okně předstihu (<=),
                    # ale pouze jednou pro aktuální due_date.
                    anchor_date = reminder.due_date - timedelta(days=notify_days_before)
                    threshold_anchor = prague_day_start_as_naive_utc(anchor_date)
                    last_notified_at = _to_naive_utc(reminder.last_notified_at)
                    if days_until <= notify_days_before:
                        if last_notified_at is None or last_notified_at < threshold_anchor:
                            if not send_email or not _already_sent_today(
                                db,
                                notification_type="REMINDER_DUE_DATE",
                                entity_id=reminder.id,
                                customer_id=customer.id,
                                tenant_id=tenant_id,
                                today=today,
                            ):
                                should_send = True
                                notification_type = "REMINDER_DUE_DATE"
                                debug_reason = f"due_date in {days_until} days"

                if not should_send:
                    continue

                sent_channels = []

                vehicle_name = "Obecná připomínka"
                if reminder.vehicle_id:
                    _vrow = db.query(VehicleModel).filter(VehicleModel.id == reminder.vehicle_id).first()
                    if _vrow:
                        vehicle_name = (
                            _vrow.nickname
                            or _vrow.plate
                            or f"{_vrow.brand} {_vrow.model}".strip()
                            or "Vozidlo"
                        )
                bell_title = "Připomínka"
                if reminder.type == "STK":
                    bell_title = "STK — připomínka"
                elif reminder.type == "OLEJ":
                    bell_title = "Výměna oleje — připomínka"
                elif reminder.type == "SERVIS":
                    bell_title = "Servis — připomínka"
                bell_body = (
                    f"{vehicle_name}: {reminder.text}\n\n"
                    f"Detaily najdete v záložce Připomínky."
                )

                if send_email and send_reminder_email(
                    db,
                    reminder,
                    notification_type=notification_type,
                    entity_id=reminder.id
                ):
                    sent_channels.append("email")
                    email_sent_count += 1
                elif send_email:
                    error_count += 1
                    print(f"[REMINDERS] Chyba při odesílání email notifikace pro připomínku ID {reminder.id}")

                if send_push:
                    push_title = f"📅 Připomínka · {APP_DISPLAY_NAME}"
                    if reminder.type == "STK":
                        push_title = "🚗 STK připomínka"
                    elif reminder.type == "OLEJ":
                        push_title = "🛢️ Připomínka výměny oleje"

                    push_body = f"{vehicle_name}: {reminder.text}".strip()
                    if len(push_body) > 220:
                        push_body = push_body[:217] + "..."

                    push_result = send_push_to_customer(
                        db,
                        tenant_id=tenant_id,
                        customer_id=customer.id,
                        title=push_title,
                        body=push_body,
                        url="/web/index.html?tab=reminders",
                        tag=f"reminder-{reminder.id}",
                    )

                    if push_result.get("sent", 0) > 0:
                        _log_push_notification(
                            db,
                            tenant_id=tenant_id,
                            customer=customer,
                            notification_type=f"PUSH_{notification_type}",
                            entity_id=reminder.id,
                            subject=push_title,
                            status="sent",
                        )
                        sent_channels.append("push")
                        push_sent_count += 1
                    elif push_result.get("reason") not in {"no_active_subscriptions"}:
                        _log_push_notification(
                            db,
                            tenant_id=tenant_id,
                            customer=customer,
                            notification_type=f"PUSH_{notification_type}",
                            entity_id=reminder.id,
                            subject=push_title,
                            status="failed",
                            error_message=str(push_result),
                        )
                        error_count += 1

                if sent_channels:
                    try:
                        create_user_in_app_notification(
                            db,
                            customer_id=int(customer.id),
                            title=bell_title,
                            message=bell_body,
                            severity="warning" if reminder.type == "STK" else "info",
                        )
                    except Exception as bell_exc:
                        print(f"[REMINDERS] In-app zvonek pro připomínku {reminder.id}: {bell_exc}")
                    reminder.last_notified_at = now_utc
                    db.commit()
                    sent_count += len(sent_channels)
                    print(
                        f"[REMINDERS] Odeslána notifikace {notification_type} pro připomínku "
                        f"ID {reminder.id} ({customer.email}); reason={debug_reason}; channels={','.join(sent_channels)}"
                    )

            except Exception as e:
                error_count += 1
                print(f"[REMINDERS] Chyba při zpracování připomínky ID {reminder.id}: {e}")
                import traceback
                traceback.print_exc()

        # Automatické STK notifikace dle nastavení zákazníka
        customers = db.query(Customer).filter(Customer.notify_stk == True).all()
        for customer in customers:
            try:
                settings = get_reminder_settings(customer)
                if not settings.get("enabled", True):
                    continue

                stk_settings = settings.get("stk", {})
                if not stk_settings.get("enabled", True):
                    continue

                notification_settings = settings.get("notification", {})
                notification_method = notification_settings.get("notification_method", "app")
                send_email, send_push = _notification_channels(notification_method)
                if send_email and not customer.notify_email:
                    send_email = False
                if send_push and not send_email:
                    tenant_id_for_push = getattr(customer, "tenant_id", None) or 1
                    if not _has_active_push_subscription(
                        db,
                        tenant_id=tenant_id_for_push,
                        customer_id=customer.id,
                    ) and customer.notify_email:
                        send_email = True
                if not send_email and not send_push:
                    continue

                try:
                    stk_days_before = int(stk_settings.get("days_before", 30))
                except (TypeError, ValueError):
                    stk_days_before = 30

                user_vehicles = [
                    vehicle
                    for vehicle in _get_user_owned_vehicle_rows(db, customer)
                    if getattr(vehicle, "stk_valid_until", None) is not None
                ]

                for vehicle in user_vehicles:
                    checked_auto_stk += 1
                    vehicle_send_email = send_email
                    vehicle_send_push = send_push

                    stk_due = vehicle.stk_valid_until
                    if isinstance(stk_due, datetime):
                        stk_due = stk_due.date()
                    elif isinstance(stk_due, str):
                        try:
                            stk_due = datetime.fromisoformat(stk_due).date()
                        except ValueError:
                            continue

                    if not isinstance(stk_due, date):
                        continue

                    days_until = (stk_due - today).days
                    if days_until != stk_days_before:
                        continue

                    tenant_id = getattr(customer, "tenant_id", None) or getattr(vehicle, "tenant_id", None) or 1
                    email_already_sent = vehicle_send_email and _already_sent_today(
                        db,
                        notification_type="AUTO_STK",
                        entity_id=vehicle.id,
                        customer_id=customer.id,
                        tenant_id=tenant_id,
                        today=today,
                    )
                    push_already_sent = vehicle_send_push and _already_sent_today(
                        db,
                        notification_type="PUSH_AUTO_STK",
                        entity_id=vehicle.id,
                        customer_id=customer.id,
                        tenant_id=tenant_id,
                        today=today,
                    )
                    if email_already_sent:
                        vehicle_send_email = False
                    if push_already_sent:
                        vehicle_send_push = False
                    if not vehicle_send_email and not vehicle_send_push:
                        continue

                    if days_until < 0:
                        text = f"STK vypršela před {abs(days_until)} dny"
                    elif days_until == 0:
                        text = "STK vyprší dnes"
                    elif days_until == 1:
                        text = "STK vyprší zítra"
                    else:
                        text = f"STK vyprší za {days_until} dní"

                    synthetic_reminder = SimpleNamespace(
                        id=vehicle.id,  # pro log entity_id používáme vehicle.id
                        tenant_id=tenant_id,
                        customer_id=customer.id,
                        vehicle_id=vehicle.id,
                        type="STK",
                        text=text,
                        due_date=stk_due,
                    )

                    sent_channels = []

                    if vehicle_send_email and send_reminder_email(
                        db,
                        synthetic_reminder,
                        notification_type="AUTO_STK",
                        entity_id=vehicle.id
                    ):
                        sent_channels.append("email")
                        email_sent_count += 1
                    elif vehicle_send_email:
                        error_count += 1
                        print(f"[REMINDERS] Chyba při AUTO_STK email notifikaci pro vehicle {vehicle.id}")

                    if vehicle_send_push:
                        vehicle_name = vehicle.nickname or vehicle.plate or f"{vehicle.brand} {vehicle.model}" or "Vozidlo"
                        push_title = f"🚗 STK brzy: {vehicle_name}"
                        push_result = send_push_to_customer(
                            db,
                            tenant_id=tenant_id,
                            customer_id=customer.id,
                            title=push_title,
                            body=text,
                            url="/web/index.html?tab=vehicles",
                            tag=f"stk-{vehicle.id}",
                        )
                        if push_result.get("sent", 0) > 0:
                            _log_push_notification(
                                db,
                                tenant_id=tenant_id,
                                customer=customer,
                                notification_type="PUSH_AUTO_STK",
                                entity_id=vehicle.id,
                                subject=push_title,
                                status="sent",
                            )
                            sent_channels.append("push")
                            push_sent_count += 1
                        elif push_result.get("reason") not in {"no_active_subscriptions"}:
                            _log_push_notification(
                                db,
                                tenant_id=tenant_id,
                                customer=customer,
                                notification_type="PUSH_AUTO_STK",
                                entity_id=vehicle.id,
                                subject=push_title,
                                status="failed",
                                error_message=str(push_result),
                            )
                            error_count += 1
                            print(f"[REMINDERS] Chyba při AUTO_STK push notifikaci pro vehicle {vehicle.id}: {push_result}")

                    if sent_channels:
                        try:
                            vn = (
                                vehicle.nickname
                                or vehicle.plate
                                or f"{vehicle.brand} {vehicle.model}".strip()
                                or "Vozidlo"
                            )
                            create_user_in_app_notification(
                                db,
                                customer_id=int(customer.id),
                                title="STK — blíží se termín",
                                message=f"{vn}: {text}\n\nZkontrolujte vozidlo v aplikaci (záložka Vozidla / Připomínky).",
                                severity="warning" if days_until <= 14 else "info",
                            )
                        except Exception as bell_exc:
                            print(f"[REMINDERS] In-app zvonek AUTO_STK vehicle {vehicle.id}: {bell_exc}")
                        sent_count += len(sent_channels)
                        db.commit()
                        print(
                            f"[REMINDERS] Odeslána AUTO_STK notifikace pro vehicle {vehicle.id} "
                            f"({customer.email}), dní do STK: {days_until}; channels={','.join(sent_channels)}"
                        )

            except Exception as e:
                error_count += 1
                print(f"[REMINDERS] Chyba při AUTO_STK pro uživatele {customer.id}: {e}")
                import traceback
                traceback.print_exc()

        return {
            "status": "ok",
            "checked_reminders": checked_manual,
            "checked_auto_stk": checked_auto_stk,
            "notifications_sent": sent_count,
            "email_notifications_sent": email_sent_count,
            "push_notifications_sent": push_sent_count,
            "errors": error_count
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při kontrole připomínek: {str(e)}")
