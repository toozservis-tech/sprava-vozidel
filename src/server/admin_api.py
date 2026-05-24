"""
Admin API router pro Správa vozidel
Přístupné pouze pro developer_admin/admin role

Struktura (datový tok, ne UI):
- Sekce Uživatelé: /admin-api/users, /admin-api/users/{id}, /admin-api/users/{id}/vehicles,
  /admin-api/users/{id}/detail, control-center akce nad uživateli.
- Sekce Servisy: /admin-api/services, /admin-api/services/{id}, /admin-api/service-registration-requests.
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request as FastAPIRequest
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect, func
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone, timedelta
from pydantic import BaseModel, Field, EmailStr, field_validator
from pathlib import Path
from copy import deepcopy
import gzip
import hashlib
import os
import re
import time
import json
import sqlite3
import shutil
import zipfile
import ipaddress
import secrets
import string
import csv
import io
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET


from src.core.auth import get_current_user_email, security
from src.core.rbac import is_admin, is_developer_admin
from src.core.security import hash_password
from src.core.config import (
    DATA_DIR,
    ENVIRONMENT,
    HOST,
    PORT,
    JWT_EXPIRE_MINUTES,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_FROM,
    ALLOWED_ORIGINS,
)
from src.modules.vehicle_hub.database import get_db, DB_URL, engine
from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.service_record_snapshot import (
    service_record_audit_snapshot,
    snapshot_json_and_hash,
)
from src.modules.vehicle_hub.customer_ordinal import (
    assign_admin_ordinal_if_missing,
    deletion_mark_display,
)
from src.modules.vehicle_hub.models import (
    Customer,
    CustomerDeletionLabel,
    Tenant,
    Vehicle,
    VehicleOwnership,
    ServiceRecord,
    ServiceRecordAuditLog,
    Reservation,
    Reminder,
    ServiceRegistrationRequest,
    License,
    LicenseSubscription,
    LicensePaymentTransaction,
    EmailNotificationLog,
    SecurityAccessLog,
    PushSubscription,
    DeveloperActionAuditLog,
    AdminCustomerChangeEvent,
    GlobalAuditLog,
    SecurityBlockedIp,
    SystemNotification,
    DemoAccessToken,
    VehicleInspectionHistory,
    VehicleMileage,
    VehicleStkImportAuditLog,
    VehicleTachometerHistoryEntry,
    ServiceCustomerLink,
    ServiceVehicleAccess,
    VehicleServiceLink,
    ServiceAccessRequest,
    ServiceCustomerInvite,
    ServiceInvoice,
)
from src.server.admin_customer_change_notify import (
    admin_change_table_exists,
    record_admin_customer_change,
    record_user_profile_license_changes_from_admin,
    send_customer_change_notification_email,
    mark_events_notified,
)
from src.modules.vehicle_hub.account_state import (
    ensure_customer_account_state_schema,
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
    increment_customer_session_version,
)
from src.server.customer_soft_delete import (
    soft_delete_customer,
    sync_vehicle_user_email_display_for_customer,
)
from src.modules.vehicle_hub.ownership import (
    ensure_vehicle_owner_assignment,
    get_primary_vehicle_owner,
)
from src.modules.vehicle_hub.tenant_provisioning import (
    create_dedicated_tenant,
    ensure_default_license_for_tenant,
)
from src.modules.vehicle_hub.workspace_entitlements import (
    effective_workspace_kinds,
    normalize_workspace_entitlements_for_storage,
    normalize_workspace_ui_default_for_storage,
)
from src.server.main_helpers import delete_customer_account


def _effective_workspace_entitlements_for_admin_summary(role: Optional[str], raw_column: Any) -> List[str]:
    """Stejné výsledky jako effective_workspace_kinds(Customer) — pro SQL seznam uživatelů."""
    class _MiniCustomer:
        __slots__ = ("role", "workspace_entitlements")

        def __init__(self, r: Optional[str], raw: Any):
            self.role = r
            self.workspace_entitlements = raw

    return sorted(effective_workspace_kinds(_MiniCustomer(role, raw_column)))
from src.modules.vehicle_hub.routers_v1.reminders import apply_reminder_completion_update
from src.modules.vehicle_hub.schema_management import assert_module_ready
from src.server.maintenance_runtime_notice import build_maintenance_runtime_notification_item
from src.server.runtime_settings import ADMIN_SETTINGS_FILE, invalidate_runtime_settings_cache, load_runtime_settings
from src.server.system_notification_markup import (
    NOTIFICATION_HTML_MARKER,
    notification_message_kind,
    notification_visible_text_len,
    sanitize_notification_rich_html,
)
from src.server.control_center_jobs import (
    is_job_paused,
    set_job_paused,
    get_job_pause_metadata,
)
try:
    from src.modules.licensing.service import (
        upgrade_license_plan,
        get_license_status as get_tenant_license_status,
        get_allowed_license_plans_for_role,
        get_license_plan_base,
        get_license_plan_public_label,
        get_license_workspace_kind_for_role,
        get_license_plan_workspace_kind,
        normalize_license_plan_key as normalize_license_plan_for_role,
        pairing_role_for_tenant_license,
        effective_service_license_storage_plan,
    )
    LICENSE_MANAGEMENT_AVAILABLE = True
except Exception:
    upgrade_license_plan = None
    get_tenant_license_status = None
    get_allowed_license_plans_for_role = None
    get_license_plan_base = None
    get_license_plan_public_label = None
    get_license_workspace_kind_for_role = None
    get_license_plan_workspace_kind = None
    normalize_license_plan_for_role = None
    pairing_role_for_tenant_license = None
    effective_service_license_storage_plan = None
    LICENSE_MANAGEMENT_AVAILABLE = False

router = APIRouter(prefix="/admin-api", tags=["admin"])
ADMIN_ROLES = {"developer_admin", "admin"}
EDITABLE_ROLES = {"user", "service", "admin", "developer_admin"}
ONLINE_WINDOW_SECONDS = max(30, int(os.getenv("ADMIN_USER_ONLINE_WINDOW_SEC", "300")))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTROL_CENTER_BACKUP_DIR = PROJECT_ROOT / "backups" / "control_center"
CONTROL_CENTER_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
CONTROL_CENTER_LOG_DIR = PROJECT_ROOT / "logs"
CONTROL_CENTER_DANGEROUS_CONFIRM = "PROCEED_RESTORE"
CONTROL_CENTER_CLEANUP_CONFIRM = "PROCEED_CLEANUP"
JOB_NAME_ALIASES = {
    "license.subscription.cycle": "license.subscription.cycle",
    "payments.resync": "license.subscription.cycle",
    "reminders.notification.check": "reminders.notification.check",
    "reminders.check": "reminders.notification.check",
}

# Import pro admin tenants endpoints
try:
    from src.modules.vehicle_hub.models import Instance
    TENANTS_AVAILABLE = True
except ImportError:
    TENANTS_AVAILABLE = False
    Instance = None

try:
    from src.modules.ai_features.models import UsageAnalytics
    USAGE_ANALYTICS_AVAILABLE = True
except ImportError:
    UsageAnalytics = None
    USAGE_ANALYTICS_AVAILABLE = False


def get_db_file_path() -> Optional[Path]:
    raw = str(DB_URL or "")
    if raw.startswith("sqlite:///"):
        return Path(raw.replace("sqlite:///", ""))
    return None


def _primary_owner_join_sql(
    *,
    vehicle_alias: str = "v",
    selector_alias: str = "vo_primary",
    ownership_alias: str = "vo",
    owner_alias: str = "owner_customer",
) -> str:
    return f"""
        LEFT JOIN (
            SELECT vehicle_id, MIN(id) AS ownership_id
            FROM vehicle_ownerships
            WHERE is_active = 1 AND is_primary = 1
            GROUP BY vehicle_id
        ) {selector_alias} ON {selector_alias}.vehicle_id = {vehicle_alias}.id
        LEFT JOIN vehicle_ownerships {ownership_alias} ON {ownership_alias}.id = {selector_alias}.ownership_id
        LEFT JOIN customers {owner_alias} ON {owner_alias}.id = {ownership_alias}.customer_id
    """


def _customer_vehicle_count_join_sql(*, customer_alias: str = "c", join_alias: str = "vehicle_counts") -> str:
    return f"""
        LEFT JOIN (
            SELECT customer_id, COUNT(DISTINCT vehicle_id) AS vehicles_count
            FROM vehicle_ownerships
            WHERE is_active = 1
            GROUP BY customer_id
        ) {join_alias} ON {join_alias}.customer_id = {customer_alias}.id
    """


def _delete_vehicle_dependencies_for_admin(db: Session, vehicle_id: int) -> Dict[str, int]:
    """Hard-delete data that blocks developer-admin vehicle deletion."""
    statements = [
        ("vehicles_primary_photo", "UPDATE vehicles SET primary_photo_asset_id = NULL WHERE id = :vehicle_id"),
        ("service_quote_access_logs", "DELETE FROM service_quote_access_logs WHERE quote_id IN (SELECT id FROM service_quotes WHERE vehicle_id = :vehicle_id)"),
        ("service_quote_access_tokens", "DELETE FROM service_quote_access_tokens WHERE quote_id IN (SELECT id FROM service_quotes WHERE vehicle_id = :vehicle_id)"),
        ("service_quote_audit_logs", "DELETE FROM service_quote_audit_logs WHERE vehicle_id = :vehicle_id OR quote_id IN (SELECT id FROM service_quotes WHERE vehicle_id = :vehicle_id)"),
        ("service_quotes", "DELETE FROM service_quotes WHERE vehicle_id = :vehicle_id"),
        ("service_invoice_lines", "DELETE FROM service_invoice_lines WHERE invoice_id IN (SELECT id FROM service_invoices WHERE vehicle_id = :vehicle_id)"),
        ("service_invoices", "DELETE FROM service_invoices WHERE vehicle_id = :vehicle_id"),
        ("service_work_orders_unlink_docs", "UPDATE service_work_orders SET source_document_id = NULL, source_intake_id = NULL WHERE vehicle_id = :vehicle_id"),
        ("service_record_audit_logs", "DELETE FROM service_record_audit_logs WHERE vehicle_id = :vehicle_id OR service_record_id IN (SELECT id FROM service_records WHERE vehicle_id = :vehicle_id)"),
        ("service_document_ingestions", "DELETE FROM service_document_ingestions WHERE vehicle_id = :vehicle_id OR auto_created_service_record_id IN (SELECT id FROM service_records WHERE vehicle_id = :vehicle_id)"),
        ("service_records", "DELETE FROM service_records WHERE vehicle_id = :vehicle_id"),
        ("service_work_order_audit_logs", "DELETE FROM service_work_order_audit_logs WHERE vehicle_id = :vehicle_id OR work_order_id IN (SELECT id FROM service_work_orders WHERE vehicle_id = :vehicle_id)"),
        ("service_work_orders", "DELETE FROM service_work_orders WHERE vehicle_id = :vehicle_id"),
        ("service_labor_sessions", "DELETE FROM service_labor_sessions WHERE vehicle_id = :vehicle_id OR service_case_id IN (SELECT id FROM service_intakes WHERE vehicle_id = :vehicle_id)"),
        ("service_intakes", "DELETE FROM service_intakes WHERE vehicle_id = :vehicle_id"),
        ("vehicle_qr_access_logs", "DELETE FROM vehicle_qr_access_logs WHERE vehicle_id = :vehicle_id OR qr_token_id IN (SELECT id FROM vehicle_qr_tokens WHERE vehicle_id = :vehicle_id)"),
        ("vehicle_qr_tokens", "DELETE FROM vehicle_qr_tokens WHERE vehicle_id = :vehicle_id"),
        ("vehicle_removal_events", "DELETE FROM vehicle_removal_events WHERE vehicle_id = :vehicle_id OR transfer_token_id IN (SELECT id FROM vehicle_transfer_tokens WHERE vehicle_id = :vehicle_id)"),
        ("vehicle_ownerships", "DELETE FROM vehicle_ownerships WHERE vehicle_id = :vehicle_id OR transfer_token_id IN (SELECT id FROM vehicle_transfer_tokens WHERE vehicle_id = :vehicle_id)"),
        ("vehicle_transfer_tokens", "DELETE FROM vehicle_transfer_tokens WHERE vehicle_id = :vehicle_id"),
        ("vehicle_service_links", "DELETE FROM vehicle_service_links WHERE vehicle_id = :vehicle_id"),
        ("service_vehicle_access", "DELETE FROM service_vehicle_access WHERE vehicle_id = :vehicle_id"),
        ("service_access_requests", "DELETE FROM service_access_requests WHERE vehicle_id = :vehicle_id"),
        ("service_vehicle_lookup_audit", "DELETE FROM service_vehicle_lookup_audit WHERE matched_vehicle_id = :vehicle_id"),
        ("customer_commands", "DELETE FROM customer_commands WHERE vehicle_id = :vehicle_id"),
        ("reminders", "DELETE FROM reminders WHERE vehicle_id = :vehicle_id"),
        ("reservations", "DELETE FROM reservations WHERE vehicle_id = :vehicle_id"),
        ("vehicle_inspection_histories", "DELETE FROM vehicle_inspection_histories WHERE vehicle_id = :vehicle_id"),
        ("vehicle_mileage", "DELETE FROM vehicle_mileage WHERE vehicle_id = :vehicle_id"),
        ("vehicle_orv_scans", "DELETE FROM vehicle_orv_scans WHERE vehicle_id = :vehicle_id"),
        ("vehicle_photos", "DELETE FROM vehicle_photos WHERE vehicle_id = :vehicle_id"),
        ("vehicle_photo_assets", "DELETE FROM vehicle_photo_assets WHERE vehicle_id = :vehicle_id"),
        ("vehicle_report_documents", "DELETE FROM vehicle_report_documents WHERE vehicle_id = :vehicle_id"),
        ("vehicle_stk_import_audit_logs", "DELETE FROM vehicle_stk_import_audit_logs WHERE vehicle_id = :vehicle_id"),
        ("vehicle_tachometer_history_entries", "DELETE FROM vehicle_tachometer_history_entries WHERE vehicle_id = :vehicle_id"),
        ("audit_log", "DELETE FROM audit_log WHERE vehicle_id = :vehicle_id"),
    ]
    deleted_counts: Dict[str, int] = {}
    for label, sql in statements:
        result = db.execute(text(sql), {"vehicle_id": vehicle_id})
        if result.rowcount and result.rowcount > 0:
            deleted_counts[label] = int(result.rowcount)
    return deleted_counts


def _reassign_vehicle_primary_owner(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
    assigned_by_customer_id: Optional[int],
) -> None:
    now = datetime.utcnow()
    (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.is_active.is_(True),
            VehicleOwnership.is_primary.is_(True),
            VehicleOwnership.customer_id != owner.id,
        )
        .update(
            {
                VehicleOwnership.is_active: False,
                VehicleOwnership.is_primary: False,
                VehicleOwnership.revoked_at: now,
                VehicleOwnership.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=assigned_by_customer_id,
    )
    vehicle.tenant_id = owner.tenant_id
    vehicle.user_email = owner.email


def _json_serialize_for_audit(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"raw": str(value)}, ensure_ascii=False)


def log_developer_action(
    db: Session,
    *,
    developer_email: str,
    request: Optional[FastAPIRequest],
    action_type: str,
    target_resource: str,
    parameters: Optional[Dict[str, Any]] = None,
    result: str = "success",
    status_code: Optional[int] = None,
) -> None:
    """
    Zápis immutable audit logu vývojářských akcí.
    Nikdy nevyhazuje výjimku ven.
    """
    try:
        actor = get_customer_by_email(db, developer_email)
        if not actor:
            return
        entry = DeveloperActionAuditLog(
            developer_id=actor.id,
            developer_email=(developer_email or "").strip().lower() or None,
            action_type=action_type,
            target_resource=target_resource,
            parameters_json=_json_serialize_for_audit(parameters or {}),
            result=result,
            status_code=status_code,
            request_ip=get_client_ip(request) if request else None,
            created_at=datetime.utcnow(),
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[ADMIN_AUDIT] Failed to persist audit action '{action_type}': {exc}")


def _safe_json_load(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _admin_vehicle_short_label(vehicle: Vehicle) -> str:
    nick = (vehicle.nickname or "").strip()
    if nick:
        return nick
    bm = f"{vehicle.brand or ''} {vehicle.model or ''}".strip()
    if bm:
        return bm
    if vehicle.plate:
        return str(vehicle.plate)
    return f"Vozidlo #{vehicle.id}"


def _notify_customer_id_for_record(db: Session, record: ServiceRecord) -> Optional[int]:
    if record.user_id:
        return int(record.user_id)
    vehicle = db.query(Vehicle).filter(Vehicle.id == record.vehicle_id).first()
    if not vehicle:
        return None
    owner = get_primary_vehicle_owner(db, vehicle)
    return int(owner.id) if owner else None


PAYMENT_SUCCESS_PROVIDER_STATUSES = {"PAID", "CONFIRMED"}
PAYMENT_SUCCESS_EVENT_TYPES = {
    "payment_paid",
    "payment_confirmed",
    "subscription_renewal_paid",
    "paid_confirmed",
    "renewal_paid",
}
PAYMENT_FAILURE_MARKERS = ("fail", "error", "declin", "cancel", "denied", "timeout")
COUNT_TEST_PAYMENTS_AS_PAID = ENVIRONMENT != "production"


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _extract_payment_test_flag(payload: Dict[str, Any]) -> Optional[bool]:
    if not payload:
        return None

    stack: List[tuple[Dict[str, Any], int]] = [(payload, 0)]
    while stack:
        current, depth = stack.pop()
        for raw_key, raw_value in current.items():
            key = str(raw_key or "").strip().lower()
            if key in {"test", "is_test", "test_mode", "sandbox", "sandbox_mode"}:
                coerced = _coerce_bool(raw_value)
                if coerced is not None:
                    return coerced
            if key in {"environment", "env", "mode"}:
                normalized = str(raw_value or "").strip().lower()
                if any(marker in normalized for marker in ("test", "sandbox")):
                    return True
                if any(marker in normalized for marker in ("live", "prod", "production")):
                    return False
            if depth < 2 and isinstance(raw_value, dict):
                stack.append((raw_value, depth + 1))
    return None


def _infer_payment_environment(
    *,
    payload_json: Any,
    provider_status: Any,
    event_type: Any,
) -> str:
    payload = _safe_json_load(payload_json)
    test_flag = _extract_payment_test_flag(payload)
    if test_flag is not None:
        return "TEST" if test_flag else "LIVE"

    combined = " ".join(
        [
            str(provider_status or "").strip().lower(),
            str(event_type or "").strip().lower(),
        ]
    )
    if "test" in combined or "sandbox" in combined:
        return "TEST"
    return "LIVE"


def _is_payment_successful(provider_status: Any, event_type: Any) -> bool:
    status = str(provider_status or "").strip().upper()
    event = str(event_type or "").strip().lower()
    return status in PAYMENT_SUCCESS_PROVIDER_STATUSES or event in PAYMENT_SUCCESS_EVENT_TYPES


def _is_payment_failed(provider_status: Any, event_type: Any) -> bool:
    status = str(provider_status or "").strip().lower()
    event = str(event_type or "").strip().lower()
    return any(marker in status for marker in PAYMENT_FAILURE_MARKERS) or any(
        marker in event for marker in PAYMENT_FAILURE_MARKERS
    )


def _payment_refund_status(provider_status: Any, event_type: Any) -> str:
    status = str(provider_status or "").strip().lower()
    event = str(event_type or "").strip().lower()
    return "refunded" if ("refund" in status or "refund" in event) else "none"


def _payment_needs_attention(provider_status: Any, event_type: Any) -> bool:
    status = str(provider_status or "").strip().lower()
    if _payment_refund_status(provider_status, event_type) == "refunded":
        return True
    return _is_payment_failed(provider_status, event_type) or "pending" in status or "created" in status


def _payment_counts_as_paid(*, environment: str, is_successful: bool) -> bool:
    if not is_successful:
        return False
    return environment == "LIVE" or COUNT_TEST_PAYMENTS_AS_PAID


def _collect_paid_state_by_tenant(db: Session, tenant_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    normalized_tenant_ids = [int(tid) for tid in tenant_ids if tid is not None]
    if not normalized_tenant_ids:
        return {}

    state: Dict[int, Dict[str, Any]] = {
        tenant_id: {
            "has_paid": False,
            "last_paid_at": None,
            "live_paid_count": 0,
            "test_paid_count": 0,
        }
        for tenant_id in normalized_tenant_ids
    }

    rows = (
        db.query(
            LicensePaymentTransaction.tenant_id,
            LicensePaymentTransaction.provider_status,
            LicensePaymentTransaction.event_type,
            LicensePaymentTransaction.payload_json,
            LicensePaymentTransaction.created_at,
        )
        .filter(LicensePaymentTransaction.tenant_id.in_(normalized_tenant_ids))
        .order_by(LicensePaymentTransaction.created_at.desc(), LicensePaymentTransaction.id.desc())
        .all()
    )

    for tenant_id, provider_status, event_type, payload_json, created_at in rows:
        if tenant_id not in state:
            continue
        environment = _infer_payment_environment(
            payload_json=payload_json,
            provider_status=provider_status,
            event_type=event_type,
        )
        is_successful = _is_payment_successful(provider_status, event_type)
        if is_successful:
            if environment == "LIVE":
                state[tenant_id]["live_paid_count"] += 1
            else:
                state[tenant_id]["test_paid_count"] += 1
        if _payment_counts_as_paid(environment=environment, is_successful=is_successful):
            state[tenant_id]["has_paid"] = True
            if state[tenant_id]["last_paid_at"] is None and created_at is not None:
                state[tenant_id]["last_paid_at"] = created_at

    return state


def _format_bytes(value: int) -> str:
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _directory_usage(path: Path) -> Dict[str, Any]:
    total_bytes = 0
    file_count = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                file_count += 1
                try:
                    total_bytes += item.stat().st_size
                except OSError:
                    continue
    return {
        "path": str(path),
        "exists": path.exists(),
        "file_count": file_count,
        "total_bytes": total_bytes,
        "total_human": _format_bytes(total_bytes),
    }


_VEHICLE_REPORT_ARCHIVE_RE = re.compile(r"^vehicle-(\d+)-")
_TENANT_DISK_USAGE_CACHE: Dict[str, Any] = {"ts": 0.0, "map": {}}


def _tenant_disk_cache_ttl_sec() -> float:
    try:
        return max(15.0, float(os.getenv("ADMIN_TENANT_DISK_CACHE_SEC", "90")))
    except ValueError:
        return 90.0


def _get_tenant_disk_usage_map(db: Session) -> Dict[int, int]:
    """Součet velikostí souborů v data/ podle tenant_id (sdílené mezi účty se stejným tenantem)."""
    now = time.monotonic()
    ttl = _tenant_disk_cache_ttl_sec()
    cached_map = _TENANT_DISK_USAGE_CACHE.get("map") or {}
    cached_ts = float(_TENANT_DISK_USAGE_CACHE.get("ts") or 0.0)
    if cached_map and (now - cached_ts) < ttl:
        return cached_map  # type: ignore[return-value]
    computed = _compute_tenant_disk_usage_bytes(db)
    _TENANT_DISK_USAGE_CACHE["ts"] = now
    _TENANT_DISK_USAGE_CACHE["map"] = computed
    return computed


def _compute_tenant_disk_usage_bytes(db: Session) -> Dict[int, int]:
    totals: Dict[int, int] = {}

    def add_bytes(tenant_id: int, nbytes: int) -> None:
        if tenant_id <= 0 or nbytes <= 0:
            return
        totals[tenant_id] = totals.get(tenant_id, 0) + nbytes

    vp_root = DATA_DIR / "vehicle_photos" / "tenants"
    if vp_root.is_dir():
        for item in vp_root.rglob("*"):
            if not item.is_file():
                continue
            try:
                rel = item.relative_to(vp_root)
            except ValueError:
                continue
            parts = rel.parts
            if not parts:
                continue
            head = parts[0]
            if not str(head).isdigit():
                continue
            try:
                tid = int(head)
            except ValueError:
                continue
            try:
                add_bytes(tid, item.stat().st_size)
            except OSError:
                pass

    def add_tenant_prefixed_subtree(root: Path, prefix: str) -> None:
        if not root.is_dir():
            return
        for child in root.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if not name.startswith(prefix):
                continue
            rest = name[len(prefix) :]
            if not rest.isdigit():
                continue
            tid = int(rest)
            for item in child.rglob("*"):
                if item.is_file():
                    try:
                        add_bytes(tid, item.stat().st_size)
                    except OSError:
                        pass

    add_tenant_prefixed_subtree(DATA_DIR / "service_record_attachments", "tenant_")
    add_tenant_prefixed_subtree(DATA_DIR / "vehicle_orv_scans", "tenant_")

    vid_to_tid: Dict[int, int] = {}
    for vid, tid in db.query(Vehicle.id, Vehicle.tenant_id).all():
        if tid is not None:
            vid_to_tid[int(vid)] = int(tid)

    uploads_root = DATA_DIR / "uploads" / "vehicles"
    if uploads_root.is_dir():
        for child in uploads_root.iterdir():
            if not child.is_dir():
                continue
            if not child.name.isdigit():
                continue
            vid = int(child.name)
            tid = vid_to_tid.get(vid)
            if tid is None:
                continue
            for item in child.rglob("*"):
                if item.is_file():
                    try:
                        add_bytes(tid, item.stat().st_size)
                    except OSError:
                        pass

    for folder in (DATA_DIR / "vehicle_reports", DATA_DIR / "vehicle_archives"):
        if not folder.is_dir():
            continue
        for item in folder.iterdir():
            if not item.is_file():
                continue
            match = _VEHICLE_REPORT_ARCHIVE_RE.match(item.name)
            if not match:
                continue
            vid = int(match.group(1))
            tid = vid_to_tid.get(vid)
            if tid is None:
                continue
            try:
                add_bytes(tid, item.stat().st_size)
            except OSError:
                pass

    vin_to_tid: Dict[str, int] = {}
    for vin, tid in db.query(Vehicle.vin, Vehicle.tenant_id).filter(Vehicle.tenant_id.isnot(None)).all():
        if tid is None:
            continue
        tid_int = int(tid)
        raw_vin = str(vin or "").strip()
        if raw_vin:
            vk = re.sub(r"[^A-Z0-9_-]", "_", raw_vin.upper())
            if vk:
                vin_to_tid[vk] = tid_int
    for vid, tid_int in vid_to_tid.items():
        vin_to_tid[f"VEHICLE-{vid}"] = tid_int

    case_root = DATA_DIR / "vehicle_case_photos"
    if case_root.is_dir():
        for child in case_root.iterdir():
            if not child.is_dir():
                continue
            tid = vin_to_tid.get(child.name)
            if tid is None:
                continue
            for item in child.rglob("*"):
                if item.is_file():
                    try:
                        add_bytes(tid, item.stat().st_size)
                    except OSError:
                        pass

    return totals


def _backup_entry_sort_ts(created_at: Optional[str], backup_dir: Path) -> float:
    """Čas pro řazení snapshotů — manifest created_at, jinak mtime složky."""
    if created_at:
        try:
            raw = str(created_at).strip()
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return datetime.fromisoformat(raw).timestamp()
        except Exception:
            pass
    try:
        return backup_dir.stat().st_mtime
    except OSError:
        return 0.0


def _list_backup_entries() -> List[Dict[str, Any]]:
    rows: List[tuple[float, str, Dict[str, Any]]] = []
    if not CONTROL_CENTER_BACKUP_DIR.exists():
        return []
    for backup_dir in CONTROL_CENTER_BACKUP_DIR.iterdir():
        if not backup_dir.is_dir():
            continue
        manifest_path = backup_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = _safe_json_load(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        else:
            manifest = {}
        db_file = backup_dir / "vehicles.db"
        entry = {
            "backup_id": backup_dir.name,
            "created_at": manifest.get("created_at"),
            "created_by": manifest.get("created_by"),
            "db_exists": db_file.exists(),
            "db_size_bytes": db_file.stat().st_size if db_file.exists() else 0,
            "db_size_human": _format_bytes(db_file.stat().st_size if db_file.exists() else 0),
            "include_data_dir": bool(manifest.get("include_data_dir", False)),
            "manifest": manifest,
        }
        ts = _backup_entry_sort_ts(entry.get("created_at"), backup_dir)
        rows.append((ts, backup_dir.name, entry))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return [r[2] for r in rows]


def _create_sqlite_backup(source_db: Path, target_db: Path) -> None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as src_conn:
        with sqlite3.connect(str(target_db)) as dst_conn:
            src_conn.backup(dst_conn)


def _restore_sqlite_backup(source_db: Path, target_db: Path) -> None:
    engine.dispose()
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as src_conn:
        with sqlite3.connect(str(target_db)) as dst_conn:
            src_conn.backup(dst_conn)


def _tail_file_lines(path: Path, limit: int = 120) -> List[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
        return [line.rstrip("\n") for line in lines[-max(1, limit):]]
    except Exception:
        return []


def _collect_old_log_files(days: int) -> List[Path]:
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    candidates: List[Path] = []
    if not CONTROL_CENTER_LOG_DIR.exists():
        return candidates
    for file_path in CONTROL_CENTER_LOG_DIR.glob("*"):
        if not file_path.is_file():
            continue
        try:
            mtime = datetime.utcfromtimestamp(file_path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            candidates.append(file_path)
    return sorted(candidates, key=lambda item: item.stat().st_mtime if item.exists() else 0)


def _collect_old_backup_dirs(days: int) -> List[Path]:
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    candidates: List[Path] = []
    if not CONTROL_CENTER_BACKUP_DIR.exists():
        return candidates
    for backup_dir in CONTROL_CENTER_BACKUP_DIR.iterdir():
        if not backup_dir.is_dir():
            continue
        try:
            mtime = datetime.utcfromtimestamp(backup_dir.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            candidates.append(backup_dir)
    return sorted(candidates, key=lambda item: item.stat().st_mtime if item.exists() else 0)


def _common_table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    main_cols = [row[1] for row in conn.execute(f"PRAGMA main.table_info({table_name})").fetchall()]
    backup_cols = {row[1] for row in conn.execute(f"PRAGMA backupdb.table_info({table_name})").fetchall()}
    return [col for col in main_cols if col in backup_cols]


def _upsert_rows_from_backup(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    where_sql: str,
    params: tuple[Any, ...],
) -> int:
    columns = _common_table_columns(conn, table_name)
    if not columns:
        return 0

    col_csv = ", ".join(columns)
    rows = conn.execute(
        f"SELECT {col_csv} FROM backupdb.{table_name} WHERE {where_sql}",
        params,
    ).fetchall()
    if not rows:
        return 0

    placeholders = ", ".join(["?"] * len(columns))
    updatable_columns = [col for col in columns if col != "id"]
    if updatable_columns:
        update_sql = ", ".join([f"{col}=excluded.{col}" for col in updatable_columns])
        sql = (
            f"INSERT INTO {table_name} ({col_csv}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_sql}"
        )
    else:
        sql = f"INSERT OR IGNORE INTO {table_name} ({col_csv}) VALUES ({placeholders})"

    conn.executemany(sql, rows)
    return len(rows)


def _attached_sqlite_has_table(conn: sqlite3.Connection, schema_name: str, table_name: str) -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema_name}.sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _legacy_backup_vehicle_ids_by_email(conn: sqlite3.Connection, *, owner_email: str) -> List[int]:
    normalized_email = str(owner_email or "").strip().lower()
    if not normalized_email:
        return []
    vehicle_rows = conn.execute(
        "SELECT id FROM backupdb.vehicles WHERE lower(user_email) = lower(?)",
        (normalized_email,),
    ).fetchall()
    return [int(row["id"]) for row in vehicle_rows if row["id"] is not None]


def _backup_vehicle_ids_for_customer_scope(
    conn: sqlite3.Connection,
    *,
    customer_id: int,
    owner_email: str,
) -> List[int]:
    """
    Ownership-first restore helper.

    Primárně používá explicitní vehicle_ownerships ze snapshotu. Pokud jsou
    ownership tabulky v záloze chybějící nebo prázdné, použije legacy emailový
    bridge jen jako compat fallback pro staré / napůl migrované snapshoty.
    """
    if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
        ownership_rows = conn.execute(
            """
            SELECT DISTINCT vehicle_id
            FROM backupdb.vehicle_ownerships
            WHERE customer_id = ?
              AND COALESCE(is_active, 1) = 1
            """,
            (customer_id,),
        ).fetchall()
        vehicle_ids = [int(row["vehicle_id"]) for row in ownership_rows if row["vehicle_id"] is not None]
        if vehicle_ids:
            return vehicle_ids
    return _legacy_backup_vehicle_ids_by_email(conn, owner_email=owner_email)


def _backup_owner_ids_for_vehicle_scope(
    conn: sqlite3.Connection,
    *,
    vehicle_id: int,
    owner_email: str,
) -> List[int]:
    """
    Ownership-first restore helper for vehicle scope.

    Pokud snapshot obsahuje ownership rows, bere je jako autoritu. Legacy email
    bridge použije jen jako fallback pro staré snapshoty nebo snapshoty bez
    backfillnutých ownership vazeb.
    """
    if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
        owner_rows = conn.execute(
            """
            SELECT DISTINCT customer_id
            FROM backupdb.vehicle_ownerships
            WHERE vehicle_id = ?
            """,
            (vehicle_id,),
        ).fetchall()
        owner_ids = [int(row["customer_id"]) for row in owner_rows if row["customer_id"] is not None]
        if owner_ids:
            return owner_ids

    normalized_email = str(owner_email or "").strip().lower()
    if not normalized_email:
        return []
    customer_rows = conn.execute(
        "SELECT id FROM backupdb.customers WHERE lower(email) = lower(?)",
        (normalized_email,),
    ).fetchall()
    return [int(row["id"]) for row in customer_rows if row["id"] is not None]


def _restore_user_scope_from_backup(
    *,
    backup_db_file: Path,
    target_db_file: Path,
    user_id: int,
) -> Dict[str, int]:
    restored: Dict[str, int] = {}
    with sqlite3.connect(str(target_db_file)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH DATABASE ? AS backupdb", (str(backup_db_file),))
        try:
            user_row = conn.execute(
                "SELECT id, email FROM backupdb.customers WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not user_row:
                raise ValueError(f"Uživatel {user_id} v záloze neexistuje")

            user_email = str(user_row["email"] or "").strip().lower()
            restored["customers"] = _upsert_rows_from_backup(
                conn,
                table_name="customers",
                where_sql="id = ?",
                params=(user_id,),
            )

            vehicle_ids: List[int] = []
            if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
                vehicle_ids = _backup_vehicle_ids_for_customer_scope(
                    conn,
                    customer_id=user_id,
                    owner_email=user_email,
                )
                restored["vehicle_ownerships"] = _upsert_rows_from_backup(
                    conn,
                    table_name="vehicle_ownerships",
                    where_sql="customer_id = ?",
                    params=(user_id,),
                )
            else:
                # Deprecated fallback for snapshots from legacy user_email ownership era.
                vehicle_ids = _legacy_backup_vehicle_ids_by_email(conn, owner_email=user_email)
                restored["vehicle_ownerships"] = 0

            if vehicle_ids:
                placeholders = ", ".join(["?"] * len(vehicle_ids))
                restored["vehicles"] = _upsert_rows_from_backup(
                    conn,
                    table_name="vehicles",
                    where_sql=f"id IN ({placeholders})",
                    params=tuple(vehicle_ids),
                )
            else:
                restored["vehicles"] = 0
            restored["reminders"] = _upsert_rows_from_backup(
                conn,
                table_name="reminders",
                where_sql="customer_id = ?",
                params=(user_id,),
            )
            restored["reservations"] = _upsert_rows_from_backup(
                conn,
                table_name="reservations",
                where_sql="customer_id = ?",
                params=(user_id,),
            )
            restored["push_subscriptions"] = _upsert_rows_from_backup(
                conn,
                table_name="push_subscriptions",
                where_sql="customer_id = ?",
                params=(user_id,),
            )
            restored["security_access_logs"] = _upsert_rows_from_backup(
                conn,
                table_name="security_access_logs",
                where_sql="customer_id = ? OR lower(user_email) = lower(?)",
                params=(user_id, user_email),
            )
            restored["email_notification_logs"] = _upsert_rows_from_backup(
                conn,
                table_name="email_notification_logs",
                where_sql="customer_id = ? OR lower(email) = lower(?)",
                params=(user_id, user_email),
            )

            if vehicle_ids:
                placeholders = ", ".join(["?"] * len(vehicle_ids))
                restored["service_records"] = _upsert_rows_from_backup(
                    conn,
                    table_name="service_records",
                    where_sql=f"vehicle_id IN ({placeholders})",
                    params=tuple(vehicle_ids),
                )
            else:
                restored["service_records"] = 0

            conn.commit()
            return restored
        finally:
            conn.execute("DETACH DATABASE backupdb")


def _restore_vehicle_scope_from_backup(
    *,
    backup_db_file: Path,
    target_db_file: Path,
    vehicle_id: int,
) -> Dict[str, int]:
    restored: Dict[str, int] = {}
    with sqlite3.connect(str(target_db_file)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH DATABASE ? AS backupdb", (str(backup_db_file),))
        try:
            vehicle_row = conn.execute(
                "SELECT id, user_email FROM backupdb.vehicles WHERE id = ?",
                (vehicle_id,),
            ).fetchone()
            if not vehicle_row:
                raise ValueError(f"Vozidlo {vehicle_id} v záloze neexistuje")

            if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
                owner_ids = _backup_owner_ids_for_vehicle_scope(
                    conn,
                    vehicle_id=vehicle_id,
                    owner_email=str(vehicle_row["user_email"] or ""),
                )
                if owner_ids:
                    placeholders = ", ".join(["?"] * len(owner_ids))
                    restored["customers"] = _upsert_rows_from_backup(
                        conn,
                        table_name="customers",
                        where_sql=f"id IN ({placeholders})",
                        params=tuple(owner_ids),
                    )
                else:
                    restored["customers"] = 0
                restored["vehicle_ownerships"] = _upsert_rows_from_backup(
                    conn,
                    table_name="vehicle_ownerships",
                    where_sql="vehicle_id = ?",
                    params=(vehicle_id,),
                )
            else:
                # Deprecated fallback for snapshots from legacy user_email ownership era.
                owner_email = str(vehicle_row["user_email"] or "").strip().lower()
                if owner_email:
                    owner_ids = _backup_owner_ids_for_vehicle_scope(
                        conn,
                        vehicle_id=vehicle_id,
                        owner_email=owner_email,
                    )
                    if owner_ids:
                        placeholders = ", ".join(["?"] * len(owner_ids))
                        restored["customers"] = _upsert_rows_from_backup(
                            conn,
                            table_name="customers",
                            where_sql=f"id IN ({placeholders})",
                            params=tuple(owner_ids),
                        )
                    else:
                        restored["customers"] = 0
                else:
                    restored["customers"] = 0
                restored["vehicle_ownerships"] = 0

            restored["vehicles"] = _upsert_rows_from_backup(
                conn,
                table_name="vehicles",
                where_sql="id = ?",
                params=(vehicle_id,),
            )
            restored["service_records"] = _upsert_rows_from_backup(
                conn,
                table_name="service_records",
                where_sql="vehicle_id = ?",
                params=(vehicle_id,),
            )
            restored["reminders"] = _upsert_rows_from_backup(
                conn,
                table_name="reminders",
                where_sql="vehicle_id = ?",
                params=(vehicle_id,),
            )
            restored["reservations"] = _upsert_rows_from_backup(
                conn,
                table_name="reservations",
                where_sql="vehicle_id = ?",
                params=(vehicle_id,),
            )
            conn.commit()
            return restored
        finally:
            conn.execute("DETACH DATABASE backupdb")


# ============= DEPENDENCIES =============

def require_developer_admin(
    email: str = Depends(get_current_user_email),
    request: FastAPIRequest = None,
    db: Session = Depends(get_db)
):
    """Ověří, že uživatel má roli developer_admin nebo admin."""
    ensure_customer_account_state_schema(db)
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if customer_is_deleted(customer) or customer_is_disabled(customer):
        raise HTTPException(status_code=403, detail="Účet je neaktivní")
    
    if not is_admin(customer.role):
        raise HTTPException(
            status_code=403,
            detail="Přístup odepřen. Vyžadována role developer_admin nebo admin."
        )

    if request and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            log_developer_action(
                db,
                developer_email=email,
                request=request,
                action_type=f"http.{request.method.lower()}",
                target_resource=str(request.url.path),
                parameters={
                    "query": str(request.url.query or ""),
                },
                result="requested",
                status_code=None,
            )
        except Exception:
            # Audit selhání nesmí zablokovat funkční flow.
            pass
    
    return email


def require_control_center_admin(
    email: str = Depends(get_current_user_email),
    request: FastAPIRequest = None,
    db: Session = Depends(get_db)
):
    """
    Přísný přístup pouze pro roli developer_admin (infra Control Center: zálohy, konzole, monitory).

    Pozn.: Účetní zásahy u uživatele (disable / licence / reset hesla) pod `/control-center/users/…`
    používají `require_developer_admin`, aby je mohl provádět i běžný admin (`admin`).
    """
    ensure_customer_account_state_schema(db)
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if customer_is_deleted(customer) or customer_is_disabled(customer):
        raise HTTPException(status_code=403, detail="Účet je neaktivní")

    if not is_developer_admin(customer.role):
        raise HTTPException(
            status_code=403,
            detail="Přístup odepřen. Tato sekce je dostupná pouze pro roli developer_admin."
        )

    if request and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            log_developer_action(
                db,
                developer_email=email,
                request=request,
                action_type=f"http.{request.method.lower()}",
                target_resource=str(request.url.path),
                parameters={"query": str(request.url.query or "")},
                result="requested",
                status_code=None,
            )
        except Exception:
            pass

    return email


def get_customer_by_email(db: Session, email: str, *, include_deleted: bool = False) -> Optional[Customer]:
    """Najde uživatele case-insensitive podle emailu."""
    ensure_customer_account_state_schema(db)
    normalized = email.strip().lower()
    query = db.query(Customer).filter(func.lower(Customer.email) == normalized)
    if not include_deleted:
        query = query.filter(func.coalesce(Customer.is_deleted, False) == False)  # noqa: E712
    return query.first()


def resolve_tenant_id_for_create(
    db: Session,
    acting_admin: Customer,
    explicit_tenant_id: Optional[int],
) -> int:
    """
    Určí tenant pro nově vytvářený záznam.
    Priorita:
    1) explicitní tenant_id z requestu
    2) tenant přihlášeného admina
    3) první tenant v databázi (fallback)
    """
    if explicit_tenant_id is not None:
        if explicit_tenant_id <= 0:
            raise HTTPException(status_code=400, detail="tenant_id musí být kladné číslo")
        if TENANTS_AVAILABLE:
            tenant = db.query(Tenant).filter(Tenant.id == explicit_tenant_id).first()
            if not tenant:
                raise HTTPException(status_code=404, detail=f"Tenant {explicit_tenant_id} neexistuje")
        return explicit_tenant_id

    if acting_admin.tenant_id:
        return acting_admin.tenant_id

    if TENANTS_AVAILABLE:
        tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
        if tenant:
            return tenant.id

    raise HTTPException(
        status_code=400,
        detail="Nelze určit tenant_id pro nový záznam. Zadejte tenant_id explicitně."
    )


def validate_role_value(role: str) -> str:
    normalized_role = role.strip().lower()
    if normalized_role not in EDITABLE_ROLES:
        allowed = ", ".join(sorted(EDITABLE_ROLES))
        raise HTTPException(status_code=400, detail=f"Neplatná role '{role}'. Povolené role: {allowed}")
    return normalized_role


def normalize_license_plan(plan: Optional[str], role: Optional[str] = None) -> Optional[str]:
    if plan is None:
        return None
    normalized_plan_raw = str(plan).strip().lower()
    if not normalized_plan_raw:
        return None

    if role is None:
        normalized_plan = normalized_plan_raw
        allowed_plans = (
            set(get_allowed_license_plans_for_role("user") + get_allowed_license_plans_for_role("service"))
            if get_allowed_license_plans_for_role
            else {"free", "basic", "premium", "lifetime"}
        )
    else:
        normalized_plan = (
            normalize_license_plan_for_role(normalized_plan_raw, role)
            if normalize_license_plan_for_role
            else normalized_plan_raw
        )
        allowed_plans = (
            set(get_allowed_license_plans_for_role(role))
            if get_allowed_license_plans_for_role
            else {"free", "basic", "premium", "lifetime"}
        )
    if normalized_plan not in allowed_plans:
        allowed = ", ".join(sorted(allowed_plans))
        raise HTTPException(status_code=400, detail=f"Neplatný plán licence '{plan}'. Povolené plány: {allowed}")
    return normalized_plan


def _customer_presensed_as_service_operator(*, role: str, tenant_workspace_route_kind: str) -> bool:
    r = str(role or "").strip().lower()
    if r == "service":
        return True
    if r == "developer_admin" and str(tenant_workspace_route_kind or "").strip().lower() == "service":
        return True
    return False


def _revoke_service_operator_graph(
    db: Session,
    *,
    service_customer_id: int,
    admin_email: str,
) -> Dict[str, int]:
    """
    Po přechodu účtu ze servisního operátora na běžného uživatele zruší veškeré aktivní vazby,
    které jiným účtům způsobovaly zobrazení tohoto ID jako „servisu“.
    """
    now = datetime.utcnow()
    counts: Dict[str, int] = {
        "customer_links_archived": 0,
        "vehicle_access_revoked": 0,
        "vehicle_service_links_revoked": 0,
        "access_requests_revoked": 0,
        "invites_cancelled": 0,
        "reservations_cancelled": 0,
    }
    bind = db.bind
    reason = f"admin_demotion:{admin_email}"

    if inspect(bind).has_table("service_customer_links"):
        for link in (
            db.query(ServiceCustomerLink)
            .filter(ServiceCustomerLink.service_customer_id == int(service_customer_id))
            .filter(ServiceCustomerLink.status != "archived")
            .all()
        ):
            link.status = "archived"
            link.revoked_at = now
            link.updated_at = now
            counts["customer_links_archived"] += 1

    if inspect(bind).has_table("service_vehicle_access"):
        for row in (
            db.query(ServiceVehicleAccess)
            .filter(ServiceVehicleAccess.service_customer_id == int(service_customer_id))
            .filter(ServiceVehicleAccess.status == "active")
            .all()
        ):
            row.status = "revoked"
            row.revoked_at = now
            row.updated_at = now
            row.revoke_reason = reason
            counts["vehicle_access_revoked"] += 1

    if inspect(bind).has_table("vehicle_service_links"):
        for row in (
            db.query(VehicleServiceLink)
            .filter(VehicleServiceLink.service_customer_id == int(service_customer_id))
            .filter(VehicleServiceLink.status == "approved")
            .all()
        ):
            row.status = "revoked"
            row.revoked_at = now
            row.updated_at = now
            row.revoked_reason = "admin_role_demotion"
            counts["vehicle_service_links_revoked"] += 1

    if inspect(bind).has_table("service_access_requests"):
        for req in (
            db.query(ServiceAccessRequest)
            .filter(ServiceAccessRequest.service_customer_id == int(service_customer_id))
            .filter(ServiceAccessRequest.status == "pending")
            .all()
        ):
            req.status = "revoked"
            req.decided_at = now
            req.decision_note = reason
            req.updated_at = now
            counts["access_requests_revoked"] += 1

    if inspect(bind).has_table("service_customer_invites"):
        for inv in (
            db.query(ServiceCustomerInvite)
            .filter(ServiceCustomerInvite.service_customer_id == int(service_customer_id))
            .filter(ServiceCustomerInvite.status == "pending")
            .all()
        ):
            inv.status = "cancelled"
            inv.updated_at = now
            counts["invites_cancelled"] += 1

    if inspect(bind).has_table("reservations"):
        rc = (
            db.query(Reservation)
            .filter(Reservation.service_id == int(service_customer_id))
            .filter(Reservation.status.in_(["PENDING", "CONFIRMED"]))
            .update({Reservation.status: "CANCELLED"}, synchronize_session=False)
        )
        counts["reservations_cancelled"] += int(rc or 0)

    return counts


def _map_service_license_storage_to_user_plan(plan_raw: Optional[str]) -> str:
    """Po převodu účtu ze servisu na uživatele — ekvivalent uživatelského tarifu v DB."""
    if not LICENSE_MANAGEMENT_AVAILABLE or not effective_service_license_storage_plan:
        return "free"
    eff = effective_service_license_storage_plan(str(plan_raw or "").strip().lower())
    return {
        "service_free": "free",
        "service_full": "premium",
        "service_lifetime": "lifetime",
    }.get(eff, "free")


def normalize_license_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = str(status).strip().lower()
    if not normalized:
        return None
    allowed = {"active", "inactive", "expired", "suspended"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Neplatný status licence '{status}'. Povolené: {', '.join(sorted(allowed))}",
        )
    return normalized


def normalize_broadcast_severity(value: Optional[str]) -> str:
    normalized = str(value or "info").strip().lower()
    allowed = {"info", "warning", "critical"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Neplatná severity '{value}'. Povolené: {', '.join(sorted(allowed))}",
        )
    return normalized


def normalize_notification_target(
    target_type: Optional[str],
    target_value: Optional[str],
) -> tuple[str, Optional[str]]:
    normalized_type = str(target_type or "all").strip().lower()
    allowed = {"all", "tenant", "plan", "user"}
    if normalized_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Neplatný target_type '{target_type}'. Povolené: {', '.join(sorted(allowed))}",
        )

    normalized_value = str(target_value or "").strip()
    if normalized_type == "all":
        return "all", None
    if not normalized_value:
        raise HTTPException(status_code=400, detail="target_value je povinný pro zvolený target_type")
    if normalized_type == "plan":
        normalized_value = normalize_license_plan(normalized_value) or "free"
    if normalized_type in {"tenant", "user"}:
        try:
            normalized_value = str(int(normalized_value))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="target_value musí být číselné ID")
    return normalized_type, normalized_value


def generate_temporary_password(length: int = 14) -> str:
    safe_length = max(10, min(length, 40))
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(safe_length))


def resolve_job_name(job_name_raw: str) -> str:
    normalized = str(job_name_raw or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="job_name je povinný")
    resolved = JOB_NAME_ALIASES.get(normalized)
    if not resolved:
        raise HTTPException(status_code=400, detail="Nepodporovaný job_name")
    return resolved


def safe_count_query(db: Session, query_str: str, params: Dict[str, Any] = None) -> int:
    """Bezpečné provedení COUNT dotazu - vrací 0 při chybě"""
    try:
        result = db.execute(text(query_str), params or {})
        return result.scalar() or 0
    except Exception as e:
        print(f"⚠️ Warning: Query failed: {query_str}, Error: {e}")
        return 0


def get_user_id_from_email(email: str, db: Session) -> Optional[int]:
    """Získá ID uživatele podle emailu"""
    user = db.query(Customer).filter(Customer.email == email).first()
    return user.id if user else None


def get_client_ip(request: FastAPIRequest) -> Optional[str]:
    """Získá IP adresu klienta"""
    if request.client:
        return request.client.host
    return None


def to_iso_datetime(value: Any) -> Optional[str]:
    """Bezpečný převod datetime/date/string hodnot na ISO string.

    Časové údaje z DB jsou v UTC (naivní datetime); do JSON posíláme vždy s příponou Z,
    aby je prohlížeč neinterpretoval jako lokální čas (posun oproti Praze).
    Čisté kalendářní datum (YYYY-MM-DD) vracíme beze změny.
    """
    if value is None:
        return None
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        # SQLite často vrací datetime jako "YYYY-MM-DD HH:MM:SS(.ms)".
        candidate = text_value
        if " " in candidate and "T" not in candidate:
            candidate = candidate.replace(" ", "T", 1)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", candidate):
            return candidate
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return text_value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def is_online_by_last_seen(last_seen_at: Optional[str]) -> bool:
    """
    Urci online stav z casu posledni aktivity.
    """
    if not last_seen_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
    except ValueError:
        return False

    if parsed.tzinfo is not None:
        parsed_utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        parsed_utc = parsed

    return (datetime.utcnow() - parsed_utc).total_seconds() <= ONLINE_WINDOW_SECONDS


def build_vehicle_label(nickname: Optional[str], brand: Optional[str], model: Optional[str], plate: Optional[str], fallback_id: Optional[int] = None) -> str:
    if nickname:
        return nickname
    brand_model = " ".join([part for part in [brand, model] if part]).strip()
    if brand_model:
        return brand_model
    if plate:
        return plate
    if fallback_id:
        return f"Vozidlo #{fallback_id}"
    return "Neznámé vozidlo"


def build_location_line(city: Optional[str], region: Optional[str], country: Optional[str]) -> Optional[str]:
    parts = [part for part in [city, region, country] if part]
    return ", ".join(parts) if parts else None


def infer_setting_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"


def normalize_setting_value(value: Any, value_type: str) -> Any:
    normalized_type = (value_type or "").strip().lower()
    if normalized_type == "boolean":
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if normalized_type == "number":
        if isinstance(value, str):
            text_value = value.strip()
            if text_value == "":
                return 0
            if "." in text_value:
                try:
                    return float(text_value)
                except ValueError:
                    return 0
            try:
                return int(text_value)
            except ValueError:
                try:
                    return float(text_value)
                except ValueError:
                    return 0
        return value
    if normalized_type == "json" and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _default_env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_env_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def get_default_admin_settings() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Výchozí konfigurace administrace (uložená jako JSON)."""
    comgate_basic_monthly = max(0, _default_env_int("COMGATE_PRICE_BASIC_HALERS", 9900))
    comgate_premium_monthly = max(0, _default_env_int("COMGATE_PRICE_PREMIUM_HALERS", 29900))
    comgate_basic_yearly = max(0, _default_env_int("COMGATE_PRICE_BASIC_YEARLY_HALERS", comgate_basic_monthly * 10))
    comgate_premium_yearly = max(0, _default_env_int("COMGATE_PRICE_PREMIUM_YEARLY_HALERS", comgate_premium_monthly * 10))

    return {
        "general": {
            "app_name": {"value": "Správa vozidel", "value_type": "string", "description": "Název aplikace"},
            "app_version": {"value": "2.2.0", "value_type": "string", "description": "Verze aplikace"},
            "app_description": {"value": "Správa vozidel a servisních záznamů", "value_type": "string", "description": "Popis aplikace"},
            "maintenance_notice_enabled": {
                "value": False,
                "value_type": "boolean",
                "description": "Zobrazit plánovanou údržbu v Oznamování v aplikaci",
            },
            "maintenance_notice_title": {"value": "Oznámení", "value_type": "string", "description": "Nadpis v seznamu oznámení"},
            "maintenance_notice_message": {
                "value": "",
                "value_type": "string",
                "description": "Text pro uživatele (např. plánovaná odstávka, žádost o zálohu)",
            },
            "maintenance_notice_period_start": {
                "value": "",
                "value_type": "string",
                "description": "Od kdy platí připomenutí – prázdné = vždy, formát data RRRR-MM-DD",
            },
            "maintenance_notice_period_end": {
                "value": "",
                "value_type": "string",
                "description": "Do kdy platí připomenutí – volitelně, formát data RRRR-MM-DD",
            },
            "maintenance_mode": {
                "value": False,
                "value_type": "boolean",
                "description": "Úplný režim údržby: ukončení přístupu pro uživatele (chyba 503). Admin panel dál funguje.",
            },
        },
        "security": {
            "jwt_expiration_hours": {"value": max(1, int(JWT_EXPIRE_MINUTES / 60)), "value_type": "number", "description": "Jak dlouho je token platný"},
            "session_timeout_minutes": {"value": 60, "value_type": "number", "description": "Automatické odhlášení po nečinnosti"},
            "max_login_attempts": {"value": 5, "value_type": "number", "description": "Počet pokusů před zablokováním"},
            "password_min_length": {"value": 6, "value_type": "number", "description": "Minimální počet znaků"},
            "password_require_uppercase": {"value": False, "value_type": "boolean", "description": "Heslo musí obsahovat velká písmena"},
            "password_require_numbers": {"value": True, "value_type": "boolean", "description": "Heslo musí obsahovat čísla"},
        },
        "database": {
            "backup_enabled": {"value": True, "value_type": "boolean", "description": "Povolit automatické zálohování"},
            "backup_frequency_hours": {"value": 24, "value_type": "number", "description": "Jak často se má zálohovat"},
            "backup_retention_days": {"value": 30, "value_type": "number", "description": "Kolik dní uchovávat zálohy"},
            "backup_path": {"value": str(DATA_DIR / "backups"), "value_type": "string", "description": "Složka pro ukládání záloh"},
        },
        "server": {
            "host": {"value": HOST, "value_type": "string", "description": "IP adresa nebo hostname"},
            "port": {"value": PORT, "value_type": "number", "description": "Port serveru"},
            "cors_enabled": {"value": True, "value_type": "boolean", "description": "Povolit Cross-Origin Resource Sharing"},
            "cors_origins": {"value": ALLOWED_ORIGINS, "value_type": "json", "description": "JSON pole povolených originů"},
            "rate_limit_enabled": {"value": True, "value_type": "boolean", "description": "Omezit počet požadavků"},
            "rate_limit_per_minute": {"value": 100, "value_type": "number", "description": "Maximální počet požadavků za minutu"},
        },
        "email": {
            "smtp_enabled": {"value": bool(SMTP_HOST), "value_type": "boolean", "description": "Zapnout odesílání e-mailů"},
            "smtp_host": {"value": SMTP_HOST, "value_type": "string", "description": "Adresa SMTP serveru"},
            "smtp_port": {"value": SMTP_PORT, "value_type": "number", "description": "Port SMTP serveru"},
            "smtp_user": {"value": SMTP_USER, "value_type": "string", "description": "Uživatelské jméno"},
            "smtp_from": {"value": SMTP_FROM, "value_type": "string", "description": "E-mailová adresa odesílatele"},
        },
        "logging": {
            "log_level": {"value": "INFO", "value_type": "string", "description": "Minimální úroveň logů"},
            "log_file_enabled": {"value": True, "value_type": "boolean", "description": "Ukládat logy do souboru"},
            "log_file_path": {"value": str(Path(__file__).parent.parent.parent / "logs"), "value_type": "string", "description": "Složka pro ukládání logů"},
            "log_rotation_days": {"value": 7, "value_type": "number", "description": "Po kolika dnech rotovat logy"},
        },
        "ui": {
            "theme": {"value": "light", "value_type": "string", "description": "Vzhled aplikace"},
            "primary_color": {"value": "#6366f1", "value_type": "string", "description": "Hex kód primární barvy"},
            "items_per_page": {"value": 24, "value_type": "number", "description": "Výchozí počet položek v seznamech"},
        },
        "api": {
            "api_docs_enabled": {"value": ENVIRONMENT != "production", "value_type": "boolean", "description": "Zobrazit Swagger dokumentaci"},
            "api_rate_limit": {"value": 120, "value_type": "number", "description": "Maximální počet API požadavků za minutu"},
        },
        "comgate": {
            "enabled": {"value": _default_env_bool("COMGATE_ENABLED", False), "value_type": "boolean", "description": "Aktivovat Comgate platby"},
            "merchant": {"value": os.getenv("COMGATE_MERCHANT", ""), "value_type": "string", "description": "Comgate Merchant ID"},
            "secret": {"value": os.getenv("COMGATE_SECRET", ""), "value_type": "string", "description": "Comgate Secret"},
            "test_mode": {"value": _default_env_bool("COMGATE_TEST_MODE", True), "value_type": "boolean", "description": "Testovací režim Comgate"},
            "currency": {"value": (os.getenv("COMGATE_CURRENCY", "CZK") or "CZK").strip().upper(), "value_type": "string", "description": "Měna plateb"},
            "method": {"value": (os.getenv("COMGATE_METHOD", "ALL") or "ALL").strip().upper(), "value_type": "string", "description": "Platební metoda (ALL/CARD/BANK)"},
            "subscription_method": {"value": (os.getenv("COMGATE_SUBSCRIPTION_METHOD", "CARD") or "CARD").strip().upper(), "value_type": "string", "description": "Metoda pro předplatné (doporučeno CARD)"},
            "test_one_time_fallback": {"value": _default_env_bool("COMGATE_TEST_ONE_TIME_FALLBACK", True), "value_type": "boolean", "description": "V testu povolit fallback bez recurring"},
            "lang": {"value": (os.getenv("COMGATE_LANG", "cs") or "cs").strip().lower(), "value_type": "string", "description": "Jazyk platební brány"},
            "country": {"value": (os.getenv("COMGATE_COUNTRY", "CZ") or "CZ").strip().upper(), "value_type": "string", "description": "Země platební brány"},
            "create_url": {"value": (os.getenv("COMGATE_CREATE_URL", "https://payments.comgate.cz/v1.0/create") or "https://payments.comgate.cz/v1.0/create").strip(), "value_type": "string", "description": "Comgate create endpoint"},
            "status_url": {"value": (os.getenv("COMGATE_STATUS_URL", "https://payments.comgate.cz/v1.0/status") or "https://payments.comgate.cz/v1.0/status").strip(), "value_type": "string", "description": "Comgate status endpoint"},
            "recurring_url": {"value": (os.getenv("COMGATE_RECURRING_URL", "https://payments.comgate.cz/v1.0/recurring") or "https://payments.comgate.cz/v1.0/recurring").strip(), "value_type": "string", "description": "Comgate recurring endpoint"},
            "recurring_enabled": {"value": _default_env_bool("COMGATE_RECURRING_ENABLED", True), "value_type": "boolean", "description": "Povolit backend recurring flow"},
            "price_basic_monthly_halers": {"value": comgate_basic_monthly, "value_type": "number", "description": "BASIC měsíčně (v haléřích)"},
            "price_basic_yearly_halers": {"value": comgate_basic_yearly, "value_type": "number", "description": "BASIC ročně (v haléřích)"},
            "price_premium_monthly_halers": {"value": comgate_premium_monthly, "value_type": "number", "description": "PREMIUM měsíčně (v haléřích)"},
            "price_premium_yearly_halers": {"value": comgate_premium_yearly, "value_type": "number", "description": "PREMIUM ročně (v haléřích)"},
            "subscription_grace_days": {"value": max(1, _default_env_int("COMGATE_SUBSCRIPTION_GRACE_DAYS", 7)), "value_type": "number", "description": "Délka grace periody po neúspěšné obnově"},
            "subscription_notify_days": {"value": str(os.getenv("COMGATE_SUBSCRIPTION_NOTIFY_DAYS", "14,7,1") or "14,7,1").strip(), "value_type": "string", "description": "Dny upozornění před expirací (CSV)"},
        },
        "system": {
            "autostart_enabled": {"value": False, "value_type": "boolean", "description": "Spustit aplikaci při startu PC"},
        },
    }


def load_admin_settings() -> Dict[str, Dict[str, Dict[str, Any]]]:
    defaults = get_default_admin_settings()
    if not ADMIN_SETTINGS_FILE.exists():
        return defaults

    try:
        with open(ADMIN_SETTINGS_FILE, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except Exception:
        return defaults

    if not isinstance(stored, dict):
        return defaults

    merged = deepcopy(defaults)
    for category, entries in stored.items():
        if not isinstance(entries, dict):
            continue
        merged.setdefault(category, {})
        for key, payload in entries.items():
            if not isinstance(payload, dict):
                continue
            value = payload.get("value")
            default_payload = merged.get(category, {}).get(key, {})
            value_type = payload.get("value_type") or default_payload.get("value_type") or infer_setting_value_type(value)
            description = payload.get("description", default_payload.get("description"))
            merged[category][key] = {
                "value": value,
                "value_type": value_type,
                "description": description,
            }

    return merged


def save_admin_settings(settings: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    ADMIN_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ADMIN_SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)
    invalidate_runtime_settings_cache()


# ============= SCHEMAS =============

class StatsOverview(BaseModel):
    total_users: int
    total_vehicles: int
    total_services: int
    total_records: int
    total_reservations: int = 0
    total_reminders: int = 0


class DeletedUserArchiveRow(BaseModel):
    customer_id: int
    deletion_mark: str
    email_before: str
    deleted_at: Optional[str] = None
    current_email: str


class UserSummary(BaseModel):
    id: int
    admin_ordinal: Optional[int] = None
    email: str
    name: Optional[str] = None
    role: str
    tenant_id: Optional[int] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    vehicles_count: int = 0
    last_ip_address: Optional[str] = None
    last_location: Optional[str] = None
    last_seen_at: Optional[str] = None
    is_online: bool = False
    license_plan: Optional[str] = None
    license_status: Optional[str] = None
    has_paid: bool = False
    last_paid_at: Optional[str] = None
    is_disabled: bool = False
    is_deleted: bool = False
    session_version: int = 0
    workspace_entitlements: Optional[List[str]] = None
    workspace_ui_default: Optional[str] = None
    pending_admin_notify_count: int = 0
    # Soubory v data/ přiřazené k tenantovi (stejná hodnota u účtů se stejným tenant_id).
    disk_usage_bytes: int = 0
    disk_usage_human: str = "0.0 B"


class AdminNotifySendRequest(BaseModel):
    change_ids: List[int]


class VehicleSummary(BaseModel):
    id: int
    user_email: str
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None
    created_at: Optional[datetime] = None
    service_count: int = 0


# ============= CRUD SCHEMAS =============

class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    role: str = "user"
    tenant_id: Optional[int] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    license_plan: Optional[str] = None
    workspace_entitlements: Optional[List[str]] = None
    workspace_ui_default: Optional[str] = None

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = Field(None, max_length=200)
    password: Optional[str] = None
    role: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    license_plan: Optional[str] = None
    # JSON pole ["user","service"] — rozšíření pracovních režimů (None = beze změny)
    workspace_entitlements: Optional[List[str]] = None
    workspace_ui_default: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name_optional(cls, value):
        if value is None or value == "":
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) < 2:
            raise ValueError("Jméno musí mít alespoň 2 znaky.")
        return text

    @field_validator(
        "phone",
        "ico",
        "dic",
        "street",
        "street_number",
        "city",
        "zip",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value):
        if value is None or value == "":
            return None
        text = str(value).strip()
        return text or None

class VehicleCreate(BaseModel):
    user_email: EmailStr
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None
    tenant_id: Optional[int] = None

class VehicleUpdate(BaseModel):
    user_email: Optional[EmailStr] = None
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None

class ServiceCreate(BaseModel):
    email: EmailStr
    name: str
    city: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    password: str
    tenant_id: Optional[int] = None

class ServiceUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    password: Optional[str] = None
    partner_catalog_approved: Optional[bool] = None


class ServiceRegistrationDecision(BaseModel):
    review_note: Optional[str] = None


class ServiceRegistrationRequestItem(BaseModel):
    id: int
    status: str
    email: str
    ico: str
    service_name: str
    responsible_person: str
    phone: str
    dic: Optional[str] = None
    street: str
    street_number: Optional[str] = None
    city: str
    zip: str
    registration_purpose: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_customer_id: Optional[int] = None
    review_note: Optional[str] = None
    approved_customer_id: Optional[int] = None
    approved_tenant_id: Optional[int] = None

class RecordCreate(BaseModel):
    vehicle_id: int
    user_id: Optional[int] = None
    performed_at: datetime
    mileage: Optional[int] = None
    description: str
    price: Optional[float] = None
    category: Optional[str] = None
    note: Optional[str] = None

class RecordUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    user_id: Optional[int] = None
    performed_at: Optional[datetime] = None
    mileage: Optional[int] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    note: Optional[str] = None


class ReminderUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    type: Optional[str] = None
    text: Optional[str] = None
    due_date: Optional[date] = None
    is_manual: Optional[bool] = None
    is_completed: Optional[bool] = None


class ReservationUpdate(BaseModel):
    service_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    service_type: Optional[str] = None
    note: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    status: Optional[str] = None


class SettingUpdateItem(BaseModel):
    category: str
    key: str
    value: Any
    value_type: Optional[str] = None
    description: Optional[str] = None


class SettingsUpdatePayload(BaseModel):
    settings: List[SettingUpdateItem]


def _json_loads_safe(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _audit_severity(action: Any, details: Any = None) -> str:
    haystack = f"{action or ''} {details or ''}".lower()
    if any(token in haystack for token in ("delete", "restore", "failed", "blocked", "disable", "force", "suspended", "error")):
        return "critical"
    if any(token in haystack for token in ("update", "change", "warning", "expired", "reject", "cleanup")):
        return "warning"
    return "info"


def _client_ip_from_request(request: Optional[FastAPIRequest]) -> Optional[str]:
    if request is None:
        return None
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    return forwarded or real_ip or (request.client.host if request.client else None)


def _license_is_expired(row: License) -> bool:
    status = str(getattr(row, "status", "") or "").strip().lower()
    valid_to = getattr(row, "valid_to", None)
    return status == "expired" or (valid_to is not None and valid_to < datetime.utcnow())


def _serialize_payment_attention_row(tx: LicensePaymentTransaction, customer: Optional[Customer] = None) -> Dict[str, Any]:
    environment = _infer_payment_environment(
        payload_json=tx.payload_json,
        provider_status=tx.provider_status,
        event_type=tx.event_type,
    )
    return {
        "id": tx.id,
        "tenant_id": tx.tenant_id,
        "email": customer.email if customer else None,
        "user_id": customer.id if customer else None,
        "trans_id": tx.trans_id,
        "ref_id": tx.ref_id,
        "plan": tx.plan,
        "amount_halers": tx.amount_halers,
        "currency": tx.currency or "CZK",
        "provider_status": tx.provider_status,
        "event_type": tx.event_type,
        "payment_environment": environment,
        "is_failed": _is_payment_failed(tx.provider_status, tx.event_type),
        "needs_attention": _payment_needs_attention(tx.provider_status, tx.event_type),
        "created_at": to_iso_datetime(tx.created_at),
    }


def _table_ready(db: Session, name: str) -> bool:
    try:
        return bool(inspect(db.bind).has_table(name))
    except Exception:
        return False


def _module_status(*checks: bool) -> str:
    if not checks:
        return "unknown"
    return "ok" if all(checks) else "warning"


def _app_center_module(
    *,
    key: str,
    label: str,
    group: str,
    status: str,
    description: str,
    admin_section: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "group": group,
        "status": status,
        "description": description,
        "admin_section": admin_section,
        "metrics": metrics or {},
        "actions": actions or [],
        "notes": notes or [],
    }


class DbInfoResponse(BaseModel):
    db_path: str
    table_count: int
    tables: List[str]
    total_size_kb: Optional[float] = None


class TenantListItem(BaseModel):
    id: int
    name: str
    license_key: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class InstanceListItem(BaseModel):
    id: int
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    last_seen_at: datetime
    
    class Config:
        from_attributes = True


class SecurityBlockIpRequest(BaseModel):
    ip_address: str
    reason: Optional[str] = None
    expires_in_minutes: Optional[int] = None


class SecurityUnblockIpRequest(BaseModel):
    ip_address: str
    reason: Optional[str] = None


class MdcrOpenDataImportRequest(BaseModel):
    source_url: Optional[str] = None
    use_latest_source: bool = True
    dry_run: bool = True
    limit: Optional[int] = 500
    update_vehicle_profile: bool = True


class MdcrVinLookupRequest(BaseModel):
    vin: str
    source_url: Optional[str] = None
    use_latest_source: bool = True
    limit: Optional[int] = 50000
    max_matches: Optional[int] = 20


class BackupCreateRequest(BaseModel):
    include_data_dir: bool = True


class BackupRestoreRequest(BaseModel):
    backup_id: str
    scope: str = "full"  # full | user | vehicle
    user_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    confirm_text: str


class InternalCommandRequest(BaseModel):
    command: str


class UserStateActionRequest(BaseModel):
    reason: Optional[str] = None


class UserSoftRestoreRequest(BaseModel):
    customer_id: int = Field(..., ge=1)
    reason: Optional[str] = Field(default=None, max_length=2000)


class UserArchivePurgeRequest(BaseModel):
    customer_ids: List[int] = Field(default_factory=list)
    purge_all: bool = False
    confirm_phrase: str = Field(..., min_length=1, max_length=100)


class UserPasswordResetRequest(BaseModel):
    new_password: Optional[str] = None
    generate_random: bool = True
    reason: Optional[str] = None


class UserLicenseUpdateRequest(BaseModel):
    plan: Optional[str] = None
    status: Optional[str] = None
    valid_to: Optional[datetime] = None
    source: Optional[str] = None
    reason: Optional[str] = None

def prepare_broadcast_notification_storage_message(message: str, *, rich: bool) -> str:
    raw_plain = str(message or "").strip()
    if rich:
        clean_html = sanitize_notification_rich_html(raw_plain)
        if notification_visible_text_len(clean_html) < 3:
            raise HTTPException(
                status_code=400,
                detail="Formátovaná zpráva musí obsahovat alespoň 3 viditelné znaky.",
            )
        return NOTIFICATION_HTML_MARKER + clean_html
    if len(raw_plain) < 3:
        raise HTTPException(status_code=400, detail="Zpráva musí mít alespoň 3 znaky.")
    return raw_plain


class BroadcastNotificationRequest(BaseModel):
    message: str
    rich: bool = False
    title: Optional[str] = None
    severity: Optional[str] = "info"  # info | warning | critical
    target_type: Optional[str] = "all"  # all | tenant | plan | user
    target_value: Optional[str] = None
    expires_in_hours: Optional[int] = None


class JobStateRequest(BaseModel):
    job_name: str
    reason: Optional[str] = None


class StorageCleanupRequest(BaseModel):
    confirm_text: str
    delete_old_logs_days: Optional[int] = 30
    delete_old_backups_days: Optional[int] = 30


# ============= ENDPOINTS =============

@router.get("/overview", response_model=StatsOverview)
def get_overview(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí přehled statistik celé databáze - pouze pro developer_admin"""
    try:
        # Stejná logika jako GET /admin-api/users: bez soft-smazaných účtů (is_deleted).
        total_users = safe_count_query(
            db, "SELECT COUNT(*) FROM customers WHERE COALESCE(is_deleted, 0) = 0"
        )
        total_vehicles = safe_count_query(db, "SELECT COUNT(*) FROM vehicles")
        total_services = safe_count_query(
            db,
            """
            SELECT COUNT(*) FROM customers c
            LEFT JOIN tenants t ON t.id = c.tenant_id
            WHERE COALESCE(c.is_deleted, 0) = 0
              AND (
                c.role = 'service'
                OR (c.role = 'developer_admin' AND COALESCE(t.workspace_route_kind, '') = 'service')
              )
            """,
        )
        total_records = safe_count_query(db, "SELECT COUNT(*) FROM service_records")
        total_reservations = safe_count_query(db, "SELECT COUNT(*) FROM reservations")
        total_reminders = safe_count_query(db, "SELECT COUNT(*) FROM reminders")
        
        return StatsOverview(
            total_users=total_users,
            total_vehicles=total_vehicles,
            total_services=total_services,
            total_records=total_records,
            total_reservations=total_reservations,
            total_reminders=total_reminders
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání statistik: {str(e)}")


@router.get("/admin-home")
def get_admin_home(
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Pracovní přehled pro běžného admina: co dnes vyžaduje pozornost."""
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)
    since_14d = now - timedelta(days=14)

    pending_service_requests: List[ServiceRegistrationRequest] = []
    if inspect(db.bind).has_table("service_registration_requests"):
        pending_service_requests = (
            db.query(ServiceRegistrationRequest)
            .filter(ServiceRegistrationRequest.status == "pending")
            .order_by(ServiceRegistrationRequest.created_at.asc())
            .limit(10)
            .all()
        )

    payment_attention: List[Dict[str, Any]] = []
    if inspect(db.bind).has_table("license_payment_transactions"):
        tx_rows = (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.created_at >= since_14d)
            .order_by(LicensePaymentTransaction.created_at.desc(), LicensePaymentTransaction.id.desc())
            .limit(200)
            .all()
        )
        tenant_ids = sorted({tx.tenant_id for tx in tx_rows if tx.tenant_id is not None})
        customers_by_tenant = {
            row.tenant_id: row
            for row in db.query(Customer)
            .filter(Customer.tenant_id.in_(tenant_ids), Customer.role.in_(["user", "service"]))
            .order_by(Customer.id.asc())
            .all()
        } if tenant_ids else {}
        for tx in tx_rows:
            if _payment_needs_attention(tx.provider_status, tx.event_type):
                payment_attention.append(_serialize_payment_attention_row(tx, customers_by_tenant.get(tx.tenant_id)))
            if len(payment_attention) >= 10:
                break

    expired_licenses: List[Dict[str, Any]] = []
    if inspect(db.bind).has_table("licenses"):
        license_rows = (
            db.query(License)
            .filter((License.status == "expired") | (License.valid_to < now))
            .order_by(License.valid_to.asc().nullsfirst(), License.id.asc())
            .limit(20)
            .all()
        )
        tenant_ids = sorted({lic.tenant_id for lic in license_rows if lic.tenant_id is not None})
        customers_by_tenant = {
            row.tenant_id: row
            for row in db.query(Customer)
            .filter(Customer.tenant_id.in_(tenant_ids), Customer.role.in_(["user", "service"]))
            .order_by(Customer.id.asc())
            .all()
        } if tenant_ids else {}
        for lic in license_rows:
            user = customers_by_tenant.get(lic.tenant_id)
            expired_licenses.append({
                "license_id": lic.id,
                "tenant_id": lic.tenant_id,
                "user_id": user.id if user else None,
                "email": user.email if user else None,
                "plan": lic.plan,
                "status": lic.status,
                "valid_to": to_iso_datetime(lic.valid_to),
            })

    security_summary = {
        "failed_logins_24h": 0,
        "rate_limited_24h": 0,
        "source_probes_24h": 0,
        "blocked_ips_active": 0,
        "admin_allowlist_configured": bool(str(os.getenv("ADMIN_NETWORK_ALLOWLIST", "")).strip()),
        "current_ip": _client_ip_from_request(request),
    }
    if inspect(db.bind).has_table("security_access_logs"):
        security_summary["failed_logins_24h"] = int(db.query(func.count(SecurityAccessLog.id)).filter(SecurityAccessLog.event_type == "login_failed", SecurityAccessLog.created_at >= since_24h).scalar() or 0)
        security_summary["rate_limited_24h"] = int(db.query(func.count(SecurityAccessLog.id)).filter(SecurityAccessLog.event_type == "login_rate_limited", SecurityAccessLog.created_at >= since_24h).scalar() or 0)
        security_summary["source_probes_24h"] = int(db.query(func.count(SecurityAccessLog.id)).filter(SecurityAccessLog.event_type == "source_probe_blocked", SecurityAccessLog.created_at >= since_24h).scalar() or 0)
    if inspect(db.bind).has_table("security_blocked_ips"):
        security_summary["blocked_ips_active"] = int(db.query(func.count(SecurityBlockedIp.id)).filter(SecurityBlockedIp.is_active.is_(True)).scalar() or 0)

    backup_entries = _list_backup_entries() if CONTROL_CENTER_BACKUP_DIR.exists() else []
    latest_backup = backup_entries[0] if backup_entries else None
    backup_created = latest_backup.get("created_at") if latest_backup else None
    backup_warning = True
    if backup_created:
        try:
            backup_dt = datetime.fromisoformat(str(backup_created).replace("Z", "+00:00")).replace(tzinfo=None)
            backup_warning = backup_dt < (now - timedelta(hours=72))
        except Exception:
            backup_warning = True

    recent_errors: List[Dict[str, Any]] = []
    if inspect(db.bind).has_table("developer_action_audit_logs"):
        for row in (
            db.query(DeveloperActionAuditLog)
            .filter(DeveloperActionAuditLog.created_at >= since_7d, DeveloperActionAuditLog.result != "success")
            .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
            .limit(10)
            .all()
        ):
            recent_errors.append({
                "id": row.id,
                "source": "developer_action",
                "action": row.action_type,
                "actor": row.developer_email,
                "target": row.target_resource,
                "result": row.result,
                "created_at": to_iso_datetime(row.created_at),
            })
    if inspect(db.bind).has_table("security_access_logs"):
        for row in (
            db.query(SecurityAccessLog)
            .filter(SecurityAccessLog.created_at >= since_7d, SecurityAccessLog.event_type.in_(["login_rate_limited", "source_probe_blocked"]))
            .order_by(SecurityAccessLog.created_at.desc(), SecurityAccessLog.id.desc())
            .limit(10)
            .all()
        ):
            recent_errors.append({
                "id": row.id,
                "source": "security",
                "action": row.event_type,
                "actor": row.user_email,
                "target": row.endpoint,
                "result": row.ip_address,
                "created_at": to_iso_datetime(row.created_at),
            })
    recent_errors = sorted(recent_errors, key=lambda item: item.get("created_at") or "", reverse=True)[:10]

    priorities = []
    def add_priority(key: str, label: str, count: int, severity: str, section: str, hint: str) -> None:
        priorities.append({"key": key, "label": label, "count": count, "severity": severity, "section": section, "hint": hint})

    add_priority("service_requests", "Čekající servisní registrace", len(pending_service_requests), "warning" if pending_service_requests else "ok", "services", "Schválit nebo zamítnout nové servisní účty.")
    add_priority("payments", "Problémové platby", len(payment_attention), "critical" if payment_attention else "ok", "control-center", "Zkontrolovat failed/pending/refund transakce.")
    add_priority("licenses", "Expirované licence", len(expired_licenses), "warning" if expired_licenses else "ok", "users", "Vyřešit obnovu licence nebo ruční stav účtu.")
    add_priority("security", "Bezpečnostní upozornění", int(security_summary["failed_logins_24h"]) + int(security_summary["rate_limited_24h"]) + int(security_summary["source_probes_24h"]) + int(security_summary["blocked_ips_active"]), "critical" if (security_summary["rate_limited_24h"] or security_summary["source_probes_24h"]) else "warning" if security_summary["failed_logins_24h"] else "ok", "security", "Zkontrolovat IP, rate limit a allowlist.")
    add_priority("backup", "Backup stav", 1 if backup_warning else 0, "warning" if backup_warning else "ok", "system", "Backup je starší než 72 h nebo chybí.")

    return {
        "timestamp": to_iso_datetime(now),
        "priorities": priorities,
        "pending_service_requests": [
            {
                "id": r.id,
                "service_name": r.service_name,
                "email": r.email,
                "ico": r.ico,
                "city": r.city,
                "created_at": to_iso_datetime(r.created_at),
            }
            for r in pending_service_requests
        ],
        "payment_attention": payment_attention,
        "expired_licenses": expired_licenses[:10],
        "recent_errors": recent_errors,
        "backup": {
            "latest": latest_backup,
            "count": len(backup_entries),
            "warning": backup_warning,
        },
        "security": security_summary,
    }


@router.get("/app-center/modules")
def get_admin_app_center_modules(
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Mapa celé aplikace pro admina: co existuje, v jakém je stavu a kde to ovládat."""
    now = datetime.utcnow()
    customers_ready = _table_ready(db, "customers")
    vehicles_ready = _table_ready(db, "vehicles")
    records_ready = _table_ready(db, "service_records")
    reminders_ready = _table_ready(db, "reminders")
    reservations_ready = _table_ready(db, "reservations")
    services_ready = _table_ready(db, "service_registration_requests")
    payments_ready = _table_ready(db, "license_payment_transactions")
    licenses_ready = _table_ready(db, "licenses")
    security_ready = _table_ready(db, "security_access_logs")
    invoices_ready = _table_ready(db, "service_invoices")
    audit_ready = _table_ready(db, "audit_log")
    notifications_ready = _table_ready(db, "system_notifications")

    runtime_settings = load_admin_settings()
    comgate_settings = runtime_settings.get("comgate", {})
    email_settings = runtime_settings.get("email", {})
    payment_enabled = bool(comgate_settings.get("enabled", {}).get("value", False))
    payment_merchant = bool(str(comgate_settings.get("merchant", {}).get("value", "")).strip())
    smtp_ready = bool(str(email_settings.get("smtp_host", {}).get("value", SMTP_HOST or "")).strip()) and bool(
        str(email_settings.get("smtp_from", {}).get("value", SMTP_FROM or "")).strip()
    )

    total_users = safe_count_query(db, "SELECT COUNT(*) FROM customers WHERE COALESCE(is_deleted, 0) = 0") if customers_ready else 0
    total_services = (
        safe_count_query(
            db,
            """
            SELECT COUNT(*) FROM customers c
            LEFT JOIN tenants t ON t.id = c.tenant_id
            WHERE COALESCE(c.is_deleted, 0) = 0
              AND (
                c.role = 'service'
                OR (c.role = 'developer_admin' AND COALESCE(t.workspace_route_kind, '') = 'service')
              )
            """,
        )
        if customers_ready
        else 0
    )
    total_vehicles = safe_count_query(db, "SELECT COUNT(*) FROM vehicles") if vehicles_ready else 0
    total_records = safe_count_query(db, "SELECT COUNT(*) FROM service_records") if records_ready else 0
    pending_service_requests = safe_count_query(db, "SELECT COUNT(*) FROM service_registration_requests WHERE status = 'pending'") if services_ready else 0
    support_count = safe_count_query(db, "SELECT COUNT(*) FROM security_access_logs WHERE event_type = 'support_contact_submitted'") if security_ready else 0
    failed_login_24h = 0
    if security_ready:
        failed_login_24h = int(
            db.query(func.count(SecurityAccessLog.id))
            .filter(SecurityAccessLog.event_type == "login_failed", SecurityAccessLog.created_at >= now - timedelta(hours=24))
            .scalar()
            or 0
        )
    payment_attention = 0
    if payments_ready:
        recent_payments = (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.created_at >= now - timedelta(days=14))
            .order_by(LicensePaymentTransaction.created_at.desc())
            .limit(200)
            .all()
        )
        payment_attention = sum(1 for tx in recent_payments if _payment_needs_attention(tx.provider_status, tx.event_type))

    backup_entries = _list_backup_entries()
    latest_backup = backup_entries[0] if backup_entries else None
    backup_status = "warning"
    if latest_backup and latest_backup.get("created_at"):
        try:
            created = datetime.fromisoformat(str(latest_backup["created_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
            backup_status = "ok" if created >= now - timedelta(hours=72) else "warning"
        except Exception:
            backup_status = "warning"

    modules = [
        _app_center_module(
            key="today",
            label="Co řešit dnes",
            group="Denní práce",
            status="ok",
            description="Prioritní pracovní fronta pro admina.",
            admin_section="overview",
            metrics={"priority_view": "ready"},
            actions=[{"label": "Otevřít přehled", "type": "section", "target": "overview"}],
        ),
        _app_center_module(
            key="users",
            label="Uživatelé a účty",
            group="Denní práce",
            status=_module_status(customers_ready, licenses_ready),
            description="Správa účtů, rolí, licencí, detailu účtu a historie.",
            admin_section="users",
            metrics={"active_users": total_users},
            actions=[
                {"label": "Správa uživatelů", "type": "section", "target": "users"},
                {"label": "Globální hledání", "type": "section", "target": "global-admin"},
            ],
        ),
        _app_center_module(
            key="vehicles",
            label="Vozidla",
            group="Denní práce",
            status=_module_status(vehicles_ready),
            description="Vozidla, vlastnictví, převody, archiv a servisní vazby.",
            admin_section="vehicles",
            metrics={"vehicles": total_vehicles},
            actions=[
                {"label": "Správa vozidel", "type": "section", "target": "vehicles"},
                {"label": "Převody a archiv", "type": "section", "target": "vehicle-lifecycle"},
            ],
        ),
        _app_center_module(
            key="service_records",
            label="Záznamy, připomínky, rezervace",
            group="Denní práce",
            status=_module_status(records_ready, reminders_ready, reservations_ready),
            description="Servisní historie, připomínky, rezervace a zásahy do záznamů.",
            admin_section="records",
            metrics={"records": total_records},
            actions=[{"label": "Servisní záznamy", "type": "section", "target": "records"}],
        ),
        _app_center_module(
            key="services",
            label="Servisy",
            group="Servisní provoz",
            status=_module_status(customers_ready, services_ready),
            description="Servisní účty, žádosti o registraci, propojení s vozidly.",
            admin_section="services",
            metrics={"services": total_services, "pending_requests": pending_service_requests},
            actions=[{"label": "Správa servisů", "type": "section", "target": "services"}],
        ),
        _app_center_module(
            key="invoices",
            label="Faktury a servisní doklady",
            group="Servisní provoz",
            status=_module_status(invoices_ready),
            description="Servisní faktury, PDF, FakturyWeb export a jednotná historie dokladů.",
            admin_section="global-admin",
            metrics={"table_ready": invoices_ready},
            actions=[
                {"label": "Najít faktury", "type": "global_filter", "target": "payment"},
                {"label": "Servisní účty", "type": "section", "target": "services"},
            ],
            notes=["Detailní tvorba faktur je v servisním účtu; admin má dohled přes servis a audit."],
        ),
        _app_center_module(
            key="payments",
            label="Platby a licence",
            group="Finance",
            status=_module_status(payments_ready, licenses_ready, payment_enabled, payment_merchant),
            description="Comgate platby, licence, subscription stav a resync.",
            admin_section="control-center",
            metrics={"attention": payment_attention, "comgate_enabled": payment_enabled, "merchant_configured": payment_merchant},
            actions=[
                {"label": "Platební panel", "type": "control_center", "target": "payments"},
                {"label": "Spustit resync plateb", "type": "command", "target": "payments.resync"},
            ],
        ),
        _app_center_module(
            key="support",
            label="Podpora",
            group="Komunikace",
            status=_module_status(security_ready, smtp_ready),
            description="Požadavky podpory z aplikace a komunikace s uživateli.",
            admin_section="support",
            metrics={"support_events": support_count, "smtp_ready": smtp_ready},
            actions=[{"label": "Support inbox", "type": "section", "target": "support"}],
        ),
        _app_center_module(
            key="notifications",
            label="Notifikace",
            group="Komunikace",
            status=_module_status(notifications_ready, smtp_ready),
            description="Systémová oznámení, broadcast a e-mail delivery.",
            admin_section="control-center",
            metrics={"smtp_ready": smtp_ready},
            actions=[
                {"label": "Broadcast", "type": "control_center", "target": "notifications"},
                {"label": "Email monitor", "type": "command", "target": "logs.tail"},
            ],
        ),
        _app_center_module(
            key="security",
            label="Bezpečnost",
            group="Provoz",
            status="warning" if failed_login_24h else _module_status(security_ready),
            description="Admin allowlist, blokace IP, failed loginy a security události.",
            admin_section="security",
            metrics={
                "failed_login_24h": failed_login_24h,
                "allowlist_configured": bool(str(os.getenv("ADMIN_NETWORK_ALLOWLIST", "")).strip()),
                "current_ip": _client_ip_from_request(request),
            },
            actions=[
                {"label": "Bezpečnostní panel", "type": "section", "target": "security"},
                {"label": "Security monitor", "type": "control_center", "target": "security"},
            ],
        ),
        _app_center_module(
            key="system",
            label="Systém, backup, nastavení",
            group="Provoz",
            status=backup_status,
            description="Health, DB nástroje, backup/restore, runtime settings a env přehled.",
            admin_section="system",
            metrics={"backups": len(backup_entries), "latest_backup": latest_backup.get("created_at") if latest_backup else None},
            actions=[
                {"label": "Systémové nástroje", "type": "section", "target": "system"},
                {"label": "Nastavení", "type": "section", "target": "settings"},
                {"label": "Vytvořit backup", "type": "command", "target": "backup.create"},
            ],
        ),
        _app_center_module(
            key="audit",
            label="Audit a historie",
            group="Provoz",
            status=_module_status(audit_ready),
            description="Append-only audit, developer akce, timeline entit a CSV export.",
            admin_section="audit",
            metrics={"audit_ready": audit_ready},
            actions=[{"label": "Audit log", "type": "section", "target": "audit"}],
        ),
        _app_center_module(
            key="mdcr_open_data",
            label="MDČR otevřená data",
            group="Integrace",
            status=_module_status(vehicles_ready, _table_ready(db, "vehicle_inspection_histories"), _table_ready(db, "vehicle_tachometer_history_entries")),
            description="Import STK/SME údajů z otevřených dat podle VIN: platnost STK, výsledek prohlídky, tachometr a technický přehled.",
            admin_section="mdcr-open-data",
            metrics={
                "vehicles_with_vin": safe_count_query(db, "SELECT COUNT(*) FROM vehicles WHERE vin IS NOT NULL AND TRIM(vin) <> ''") if vehicles_ready else 0,
                "source": "data.gov.cz",
            },
            actions=[{"label": "Import MDČR dat", "type": "section", "target": "mdcr-open-data"}],
            notes=["KontrolaTachometru.cz nemá veřejné API; používáme otevřená data MDČR."],
        ),
        _app_center_module(
            key="public",
            label="Veřejné části a demo",
            group="Veřejná aplikace",
            status="ok",
            description="Public web, demo přístupy, veřejná historie vozidla a transfer tokeny.",
            admin_section="demo-access",
            metrics={"demo_leads": safe_count_query(db, "SELECT COUNT(*) FROM demo_access_tokens") if _table_ready(db, "demo_access_tokens") else 0},
            actions=[
                {"label": "Demo žádosti", "type": "section", "target": "demo-access"},
                {"label": "Public web", "type": "url", "target": "/"},
            ],
        ),
        _app_center_module(
            key="integrations",
            label="Integrace a API",
            group="Integrace",
            status="ok" if smtp_ready else "warning",
            description="SMTP, Comgate, ARES, VIN/ORV, FakturyWeb a interní API dostupnost.",
            admin_section="settings",
            metrics={
                "smtp_ready": smtp_ready,
                "comgate_enabled": payment_enabled,
                "fakturyweb_configured": bool(os.getenv("FAKTURYWEB_EMAIL") and os.getenv("FAKTURYWEB_API_KEY")),
            },
            actions=[
                {"label": "Nastavení API", "type": "section", "target": "settings"},
                {"label": "MDČR open data", "type": "section", "target": "mdcr-open-data"},
                {"label": "Health", "type": "command", "target": "system.health"},
            ],
        ),
    ]

    status_counts: Dict[str, int] = {}
    for module in modules:
        status_counts[module["status"]] = status_counts.get(module["status"], 0) + 1

    return {
        "timestamp": to_iso_datetime(now),
        "groups": sorted({module["group"] for module in modules}),
        "status_counts": status_counts,
        "modules": modules,
    }


@router.post("/app-center/actions/{action_key}")
def run_admin_app_center_action(
    action_key: str,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Bezpečné rychlé akce z Centra aplikace."""
    normalized = (action_key or "").strip().lower()
    if normalized == "system.health":
        return get_control_center_health(email=email, db=db)
    if normalized == "payments.resync":
        return resync_control_center_payments(request=request, email=email, db=db)
    if normalized == "backup.create":
        return create_control_center_backup(
            payload=BackupCreateRequest(include_data_dir=True),
            request=request,
            email=email,
            db=db,
        )
    if normalized == "logs.tail":
        return get_control_center_system_logs(lines=80, email=email, db=db)
    raise HTTPException(status_code=400, detail="Nepodporovaná rychlá akce")


MDCR_OPEN_DATA_DEFAULT_URL = os.getenv(
    "MDCR_STK_OPEN_DATA_URL",
    "https://istp.data.md.gov.cz/api/data/2c90870f-8991-475d-b527-e78fa436d546",
)
MDCR_OPEN_DATA_SOURCE_LABEL = "data.gov.cz/MDČR otevřená data STK/SME"
MDCR_OPEN_DATA_SPARQL_URL = "https://data.gov.cz/sparql"
_MDCR_LATEST_SOURCE_CACHE: Dict[str, Any] = {}


def _mdcr_legal_notice() -> Dict[str, Any]:
    return {
        "status": "official_open_data",
        "provider": "Ministerstvo dopravy ČR",
        "catalog": "Národní katalog otevřených dat / data.gov.cz",
        "source_label": MDCR_OPEN_DATA_SOURCE_LABEL,
        "not_official_app_notice": "Aplikace není oficiální službou Ministerstva dopravy ČR a nezobrazuje online výpis z registru.",
        "freshness_notice": "Aktuálnost odpovídá nejnovější datové sadě zveřejněné poskytovatelem v NKOD/data.gov.cz, nikoliv okamžitému stavu registru.",
        "attribution": "Zdroj dat: Ministerstvo dopravy ČR, Národní katalog otevřených dat (data.gov.cz).",
        "usage_rules": [
            "U každého importovaného údaje uchovávat zdroj, datum datasetu, URL distribuce a čas importu.",
            "Neoznačovat data jako živé online ověření ani jako oficiální výpis MDČR.",
            "Při zobrazení uživateli vždy uvádět datum datasetu a zdroj dat.",
            "Nezpracovávat neveřejné služby typu Kontrola tachometru scrapingem ani obcházením ochrany.",
            "Před přidáním nové datové sady ověřit její katalogový záznam, podmínky užití a dokumentaci.",
        ],
        "links": [
            {
                "label": "NKOD / data.gov.cz",
                "url": "https://data.gov.cz",
            },
            {
                "label": "Otevřená data v eGovernmentu ČR",
                "url": "https://archi.gov.cz/nap:otevrena_data",
            },
            {
                "label": "Dokumentace schématu Prohlídky STK/SME",
                "url": "https://istp.data.md.gov.cz/resources/istp/opendata/documentation/istp-opendata-schemas-ProhlidkaSeznam-v1.pdf",
            },
        ],
        "supported_datasets": [
            {
                "key": "stk_sme_inspections",
                "label": "Prohlídky vozidel STK a SME",
                "status": "implemented",
                "purpose": "VIN, datum prohlídky, typ prohlídky, výsledek, stav tachometru, platnost příští STK, značka/model, protokol.",
            },
            {
                "key": "stations_stk_sme",
                "label": "Stanice STK/SME a číselníky",
                "status": "planned_review",
                "purpose": "Doplnění názvů stanic, kódů, číselníků a lepší čitelnosti importovaných výsledků.",
            },
            {
                "key": "emissions",
                "label": "Data měření emisí",
                "status": "planned_review",
                "purpose": "Doplnění emisních údajů, pokud katalogový záznam a schéma potvrdí vhodné použití.",
            },
        ],
    }


def _xml_local_name(tag: Any) -> str:
    raw = str(tag or "")
    return raw.rsplit("}", 1)[-1] if "}" in raw else raw


def _mdcr_child_text(elem: ET.Element, path: str) -> Optional[str]:
    current = elem
    for part in path.split("/"):
        next_child = None
        for child in list(current):
            if _xml_local_name(child.tag) == part:
                next_child = child
                break
        if next_child is None:
            return None
        current = next_child
    text_value = current.text
    if text_value is None:
        return None
    cleaned = str(text_value).strip()
    return cleaned or None


def _parse_mdcr_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _parse_mdcr_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    normalized = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return None


def _parse_mdcr_date(value: Optional[str]) -> Optional[date]:
    parsed = _parse_mdcr_datetime(value)
    return parsed.date() if parsed else None


def _normalize_mdcr_vin(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return normalized or None


def _mdcr_record_from_element(elem: ET.Element) -> Dict[str, Any]:
    vin = _normalize_mdcr_vin(_mdcr_child_text(elem, "Vozidlo/Vin"))
    inspection_date_raw = _mdcr_child_text(elem, "DatumProhlidky")
    next_inspection_raw = _mdcr_child_text(elem, "Vysledek/DatumPristiProhlidky")
    brand = _mdcr_child_text(elem, "Vozidlo/Znacka")
    model = _mdcr_child_text(elem, "Vozidlo/ObchodniOznaceni")
    protocol = _mdcr_child_text(elem, "CisloProtokolu")
    odometer = _parse_mdcr_int(_mdcr_child_text(elem, "Vysledek/Odometr"))
    inspection_type = _mdcr_child_text(elem, "DruhProhlidky")
    result = _mdcr_child_text(elem, "Vysledek/VysledekCelkovy")
    station_name = _mdcr_child_text(elem, "Stanice/Nazev")
    station_code = _mdcr_child_text(elem, "Stanice/CisloStanice")
    record = {
        "vin": vin,
        "protocol_number": protocol,
        "inspection_date": _parse_mdcr_datetime(inspection_date_raw),
        "inspection_date_raw": inspection_date_raw,
        "next_inspection_date": _parse_mdcr_date(next_inspection_raw),
        "next_inspection_date_raw": next_inspection_raw,
        "inspection_type": inspection_type,
        "result_label": result,
        "odometer_km": odometer,
        "brand": brand,
        "model": model,
        "station_name": station_name,
        "station_code": station_code,
    }
    record["source_hash"] = hashlib.sha256(
        "|".join(
            str(record.get(key) or "")
            for key in ("vin", "protocol_number", "inspection_date_raw", "odometer_km", "result_label")
        ).encode("utf-8")
    ).hexdigest()
    return record


def _serialize_mdcr_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "vin": record.get("vin"),
        "protocol_number": record.get("protocol_number"),
        "inspection_date": to_iso_datetime(record.get("inspection_date")),
        "inspection_date_raw": record.get("inspection_date_raw"),
        "next_inspection_date": record.get("next_inspection_date").isoformat() if record.get("next_inspection_date") else None,
        "next_inspection_date_raw": record.get("next_inspection_date_raw"),
        "inspection_type": record.get("inspection_type"),
        "result_label": record.get("result_label"),
        "odometer_km": record.get("odometer_km"),
        "brand": record.get("brand"),
        "model": record.get("model"),
        "station_name": record.get("station_name"),
        "station_code": record.get("station_code"),
        "source_hash": record.get("source_hash"),
    }


def _mdcr_source_url_from_payload(value: Optional[str]) -> str:
    source_url = (value or MDCR_OPEN_DATA_DEFAULT_URL).strip()
    if not source_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Zdroj MDČR musí být HTTPS URL")
    return source_url


def _fetch_latest_mdcr_open_data_source(force: bool = False) -> Dict[str, Any]:
    now = datetime.utcnow()
    cached_at = _MDCR_LATEST_SOURCE_CACHE.get("cached_at")
    if (
        not force
        and cached_at
        and isinstance(cached_at, datetime)
        and cached_at >= now - timedelta(minutes=15)
        and _MDCR_LATEST_SOURCE_CACHE.get("source_url")
    ):
        return dict(_MDCR_LATEST_SOURCE_CACHE)

    query = """
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX dcat: <http://www.w3.org/ns/dcat#>
SELECT ?dataset ?title ?download WHERE {
  ?dataset dct:title ?title ; dcat:distribution ?dist .
  ?dist dcat:downloadURL ?download .
  FILTER(CONTAINS(STR(?title), "Prohlídky vozidel STK a SME za"))
}
LIMIT 10000
"""
    url = MDCR_OPEN_DATA_SPARQL_URL + "?" + urllib.parse.urlencode(
        {"query": query, "format": "application/sparql-results+json"}
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if _MDCR_LATEST_SOURCE_CACHE.get("source_url"):
            cached = dict(_MDCR_LATEST_SOURCE_CACHE)
            cached["warning"] = f"Nepodařilo se obnovit katalog data.gov.cz, používám poslední známý zdroj: {exc}"
            return cached
        return {
            "source_url": MDCR_OPEN_DATA_DEFAULT_URL,
            "title": "Výchozí MDČR distribuční soubor",
            "dataset_date": None,
            "warning": f"Nepodařilo se načíst katalog data.gov.cz, používám výchozí zdroj: {exc}",
            "cached_at": now,
        }

    latest: Optional[Dict[str, Any]] = None
    for binding in payload.get("results", {}).get("bindings", []):
        title = binding.get("title", {}).get("value") or ""
        match = re.search(r"(\d{2})-(\d{2})-(\d{4})", title)
        if not match:
            continue
        try:
            dataset_date = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except Exception:
            continue
        download = binding.get("download", {}).get("value") or ""
        if not download.startswith("https://"):
            continue
        dataset_iri = binding.get("dataset", {}).get("value") or ""
        item = {
            "source_url": download,
            "title": title,
            "dataset_date": dataset_date.isoformat(),
            "dataset_iri": dataset_iri,
            "catalog_url": "https://data.gov.cz/datov%C3%A1-sada?iri=" + urllib.parse.quote(dataset_iri, safe=""),
            "cached_at": now,
        }
        if latest is None or dataset_date > date.fromisoformat(str(latest["dataset_date"])):
            latest = item
    if not latest:
        latest = {
            "source_url": MDCR_OPEN_DATA_DEFAULT_URL,
            "title": "Výchozí MDČR distribuční soubor",
            "dataset_date": None,
            "warning": "Katalog data.gov.cz nevrátil žádný denní dataset STK/SME.",
            "cached_at": now,
        }
    _MDCR_LATEST_SOURCE_CACHE.clear()
    _MDCR_LATEST_SOURCE_CACHE.update(latest)
    return dict(latest)


def _resolve_mdcr_source(value: Optional[str], use_latest: bool = True) -> Dict[str, Any]:
    if use_latest:
        latest = _fetch_latest_mdcr_open_data_source(force=True)
        latest["resolved_by"] = "data.gov.cz latest at click"
        return latest
    return {
        "source_url": _mdcr_source_url_from_payload(value),
        "title": "Ručně zadaný distribuční soubor",
        "dataset_date": None,
        "resolved_by": "manual",
    }


def _iter_mdcr_open_data_records(xml_stream):
    for event, elem in ET.iterparse(xml_stream, events=("end",)):
        if _xml_local_name(elem.tag) != "Prohlidka":
            continue
        yield _mdcr_record_from_element(elem)
        elem.clear()


def _mdcr_existing_vin_map(db: Session) -> Dict[str, List[Vehicle]]:
    vehicles = db.query(Vehicle).filter(Vehicle.vin.isnot(None)).all()
    result: Dict[str, List[Vehicle]] = {}
    for vehicle in vehicles:
        vin = _normalize_mdcr_vin(vehicle.vin)
        if not vin:
            continue
        result.setdefault(vin, []).append(vehicle)
    return result


def _mdcr_upsert_inspection(db: Session, vehicle: Vehicle, record: Dict[str, Any], now: datetime) -> str:
    existing = (
        db.query(VehicleInspectionHistory)
        .filter(
            VehicleInspectionHistory.vehicle_id == vehicle.id,
            VehicleInspectionHistory.source_hash == record["source_hash"],
        )
        .first()
    )
    raw_payload = json.dumps(record, ensure_ascii=False, default=str)
    if existing:
        existing.imported_at = now
        existing.raw_payload_json = raw_payload
        return "updated"
    inspection = VehicleInspectionHistory(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        vin=record.get("vin") or vehicle.vin or "",
        inspection_date=record.get("inspection_date"),
        inspection_type=record.get("inspection_type"),
        inspection_kind=record.get("inspection_type"),
        odometer_km=record.get("odometer_km"),
        protocol_number=record.get("protocol_number"),
        result_label=record.get("result_label"),
        note_text=f"Import z otevřených dat MDČR; stanice: {record.get('station_name') or record.get('station_code') or '-'}",
        source=MDCR_OPEN_DATA_SOURCE_LABEL,
        source_hash=record["source_hash"],
        imported_at=now,
        raw_payload_json=raw_payload,
    )
    db.add(inspection)
    return "inserted"


def _mdcr_upsert_tachometer_entry(db: Session, vehicle: Vehicle, record: Dict[str, Any], now: datetime) -> str:
    if record.get("odometer_km") is None and record.get("inspection_date") is None:
        return "skipped"
    query = db.query(VehicleTachometerHistoryEntry).filter(
        VehicleTachometerHistoryEntry.vehicle_id == vehicle.id,
        VehicleTachometerHistoryEntry.check_date == record.get("inspection_date"),
        VehicleTachometerHistoryEntry.mileage_km == record.get("odometer_km"),
    )
    protocol = record.get("protocol_number")
    if protocol:
        query = query.filter(VehicleTachometerHistoryEntry.protocol_number == protocol)
    else:
        query = query.filter(VehicleTachometerHistoryEntry.protocol_number.is_(None))
    existing = query.first()
    raw_payload = json.dumps(record, ensure_ascii=False, default=str)
    summary = (
        f"{record.get('inspection_type') or 'STK/SME'} · "
        f"{record.get('result_label') or 'bez výsledku'} · "
        f"{record.get('odometer_km') or '?'} km"
    )
    if existing:
        existing.last_seen_at = now
        existing.raw_payload_json = raw_payload
        existing.summary = summary
        return "updated"
    db.add(
        VehicleTachometerHistoryEntry(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=record.get("inspection_date"),
            mileage_km=record.get("odometer_km"),
            protocol_number=protocol,
            inspection_type=record.get("inspection_type"),
            source=MDCR_OPEN_DATA_SOURCE_LABEL,
            status="imported",
            read_only=True,
            summary=summary,
            findings_summary=record.get("result_label"),
            detail_snapshot_json=raw_payload,
            source_detail_reference=record.get("protocol_number"),
            raw_payload_json=raw_payload,
            imported_at=now,
            last_seen_at=now,
        )
    )
    return "inserted"


def _mdcr_update_vehicle_profile(db: Session, vehicle: Vehicle, record: Dict[str, Any], now: datetime) -> bool:
    changed = False
    inspection_date = record.get("inspection_date")
    odometer = record.get("odometer_km")
    next_inspection = record.get("next_inspection_date")
    current_overview = vehicle.vehicle_technical_overview if isinstance(vehicle.vehicle_technical_overview, dict) else {}
    overview = dict(current_overview)
    overview["mdcr_open_data"] = {
        "source": MDCR_OPEN_DATA_SOURCE_LABEL,
        "last_imported_at": to_iso_datetime(now),
        "protocol_number": record.get("protocol_number"),
        "inspection_date": to_iso_datetime(inspection_date),
        "inspection_type": record.get("inspection_type"),
        "result_label": record.get("result_label"),
        "odometer_km": odometer,
        "next_inspection_date": next_inspection.isoformat() if next_inspection else None,
        "brand": record.get("brand"),
        "model": record.get("model"),
        "station_name": record.get("station_name"),
        "station_code": record.get("station_code"),
    }
    vehicle.vehicle_technical_overview = overview
    changed = True
    if next_inspection and vehicle.stk_valid_until != next_inspection:
        vehicle.stk_valid_until = next_inspection
        changed = True
    if odometer is not None:
        latest_date = vehicle.latest_stk_odometer_date
        should_update_latest = not latest_date or (inspection_date and inspection_date >= latest_date)
        if should_update_latest:
            vehicle.latest_stk_odometer_km = odometer
            vehicle.latest_stk_odometer_date = inspection_date
            vehicle.last_stk_mileage_km = odometer
            vehicle.mileage_checked_at = now
            vehicle.latest_stk_sync_at = now
            vehicle.latest_stk_source = MDCR_OPEN_DATA_SOURCE_LABEL
            vehicle.latest_stk_import_status = "imported"
            if vehicle.current_mileage_km is None or odometer > vehicle.current_mileage_km:
                vehicle.current_mileage_km = odometer
            changed = True
        mileage_exists = (
            db.query(VehicleMileage)
            .filter(
                VehicleMileage.vehicle_id == vehicle.id,
                VehicleMileage.source == "stk",
                VehicleMileage.mileage_km == odometer,
            )
            .first()
        )
        if not mileage_exists:
            db.add(
                VehicleMileage(
                    tenant_id=vehicle.tenant_id,
                    vehicle_id=vehicle.id,
                    mileage_km=odometer,
                    source="stk",
                    note=f"MDČR otevřená data, protokol {record.get('protocol_number') or '-'}",
                    created_at=now,
                )
            )
            changed = True
    return changed


def _run_mdcr_open_data_import(
    db: Session,
    payload: MdcrOpenDataImportRequest,
    admin_email: str,
    request: Optional[FastAPIRequest] = None,
) -> Dict[str, Any]:
    source_info = _resolve_mdcr_source(payload.source_url, payload.use_latest_source)
    source_url = _mdcr_source_url_from_payload(source_info.get("source_url"))
    if payload.limit is not None and payload.limit < 1:
        raise HTTPException(status_code=400, detail="Limit musí být prázdný nebo větší než 0")

    vin_map = _mdcr_existing_vin_map(db)
    now = datetime.utcnow()
    summary = {
        "source_url": source_url,
        "source_info": {k: to_iso_datetime(v) if isinstance(v, datetime) else v for k, v in source_info.items()},
        "dry_run": bool(payload.dry_run),
        "limit": payload.limit,
        "known_vehicle_vins": len(vin_map),
        "scanned_records": 0,
        "records_with_vin": 0,
        "matched_records": 0,
        "matched_vehicles": 0,
        "inspection_inserted": 0,
        "inspection_updated": 0,
        "tachometer_inserted": 0,
        "tachometer_updated": 0,
        "vehicle_profile_updated": 0,
        "sample_matches": [],
        "started_at": to_iso_datetime(now),
    }
    touched_vehicle_ids = set()
    req = urllib.request.Request(source_url, headers={"User-Agent": "ToozHub2 admin MDCR open-data importer"})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            buffered = io.BufferedReader(response)
            head = buffered.peek(2)[:2]
            stream = gzip.GzipFile(fileobj=buffered) if head == b"\x1f\x8b" else buffered
            for record in _iter_mdcr_open_data_records(stream):
                summary["scanned_records"] += 1
                vin = record.get("vin")
                if vin:
                    summary["records_with_vin"] += 1
                vehicles = vin_map.get(vin or "", [])
                if vehicles:
                    summary["matched_records"] += 1
                    for vehicle in vehicles:
                        touched_vehicle_ids.add(vehicle.id)
                        if len(summary["sample_matches"]) < 8:
                            summary["sample_matches"].append(
                                {
                                    "vehicle_id": vehicle.id,
                                    "vin": vin,
                                    "plate": vehicle.plate,
                                    "inspection_date": to_iso_datetime(record.get("inspection_date")),
                                    "odometer_km": record.get("odometer_km"),
                                    "result": record.get("result_label"),
                                }
                            )
                        if payload.dry_run:
                            continue
                        inspection_status = _mdcr_upsert_inspection(db, vehicle, record, now)
                        if inspection_status == "inserted":
                            summary["inspection_inserted"] += 1
                        elif inspection_status == "updated":
                            summary["inspection_updated"] += 1
                        tachometer_status = _mdcr_upsert_tachometer_entry(db, vehicle, record, now)
                        if tachometer_status == "inserted":
                            summary["tachometer_inserted"] += 1
                        elif tachometer_status == "updated":
                            summary["tachometer_updated"] += 1
                        if payload.update_vehicle_profile and _mdcr_update_vehicle_profile(db, vehicle, record, now):
                            summary["vehicle_profile_updated"] += 1
                    if not payload.dry_run and len(touched_vehicle_ids) % 100 == 0:
                        db.flush()
                if payload.limit and summary["scanned_records"] >= payload.limit:
                    break
    except HTTPException:
        raise
    except Exception as exc:
        if not payload.dry_run:
            db.rollback()
        raise HTTPException(status_code=502, detail=f"Import MDČR dat selhal: {exc}") from exc

    summary["matched_vehicles"] = len(touched_vehicle_ids)
    summary["finished_at"] = to_iso_datetime(datetime.utcnow())
    if not payload.dry_run:
        for vehicle_id in list(touched_vehicle_ids)[:50]:
            vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
            if not vehicle:
                continue
            db.add(
                VehicleStkImportAuditLog(
                    tenant_id=vehicle.tenant_id,
                    vehicle_id=vehicle.id,
                    vin=vehicle.vin,
                    action="mdcr_open_data_import",
                    status="success",
                    message="Import otevřených dat MDČR dokončen pro vozidlo",
                    metadata_json=json.dumps(summary, ensure_ascii=False, default=str),
                    created_at=datetime.utcnow(),
                )
            )
        db.commit()
        audit_email = (admin_email or "").strip()
        if audit_email:
            log_developer_action(
                db,
                developer_email=audit_email,
                request=request,
                action_type="MDCR_OPEN_DATA_IMPORT",
                target_resource="mdcr_open_data",
                parameters={
                    "source_url": source_url,
                    "scanned_records": summary["scanned_records"],
                    "matched_vehicles": summary["matched_vehicles"],
                    "inspection_inserted": summary["inspection_inserted"],
                    "trigger": "schedule" if request is None else "admin_api",
                },
                result="success",
            )
    return summary


@router.get("/mdcr-open-data/status")
def get_mdcr_open_data_status(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    vin_count = safe_count_query(db, "SELECT COUNT(*) FROM vehicles WHERE vin IS NOT NULL AND TRIM(vin) <> ''")
    latest_audit = (
        db.query(VehicleStkImportAuditLog)
        .filter(VehicleStkImportAuditLog.action == "mdcr_open_data_import")
        .order_by(VehicleStkImportAuditLog.created_at.desc())
        .first()
        if _table_ready(db, "vehicle_stk_import_audit_logs")
        else None
    )
    latest_source = _fetch_latest_mdcr_open_data_source(force=False)
    return {
        "default_source_url": MDCR_OPEN_DATA_DEFAULT_URL,
        "latest_source": {k: to_iso_datetime(v) if isinstance(v, datetime) else v for k, v in latest_source.items()},
        "source_label": MDCR_OPEN_DATA_SOURCE_LABEL,
        "legal_notice": _mdcr_legal_notice(),
        "tables": {
            "vehicles": _table_ready(db, "vehicles"),
            "vehicle_inspection_histories": _table_ready(db, "vehicle_inspection_histories"),
            "vehicle_tachometer_history_entries": _table_ready(db, "vehicle_tachometer_history_entries"),
            "vehicle_mileage": _table_ready(db, "vehicle_mileage"),
            "vehicle_stk_import_audit_logs": _table_ready(db, "vehicle_stk_import_audit_logs"),
        },
        "vehicles_with_vin": vin_count,
        "latest_import": {
            "created_at": to_iso_datetime(latest_audit.created_at),
            "status": latest_audit.status,
            "message": latest_audit.message,
        }
        if latest_audit
        else None,
        "what_is_imported": [
            "VIN a párování na vozidlo",
            "datum a druh STK/SME prohlídky",
            "výsledek prohlídky",
            "stav tachometru",
            "datum příští prohlídky / platnost STK",
            "značka, model a stanice ze zdrojového záznamu",
            "číslo protokolu a raw záznam pro audit",
        ],
    }


@router.post("/mdcr-open-data/import")
def import_mdcr_open_data(
    payload: MdcrOpenDataImportRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    return _run_mdcr_open_data_import(db, payload, email, request)


@router.get("/mdcr-open-data/latest-source")
def get_mdcr_open_data_latest_source(
    email: str = Depends(require_developer_admin),
):
    latest = _fetch_latest_mdcr_open_data_source(force=True)
    return {k: to_iso_datetime(v) if isinstance(v, datetime) else v for k, v in latest.items()}


@router.post("/mdcr-open-data/lookup-vin")
def lookup_mdcr_open_data_by_vin(
    payload: MdcrVinLookupRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    source_info = _resolve_mdcr_source(payload.source_url, payload.use_latest_source)
    source_url = _mdcr_source_url_from_payload(source_info.get("source_url"))
    normalized_vin = _normalize_mdcr_vin(payload.vin)
    if not normalized_vin or len(normalized_vin) < 5:
        raise HTTPException(status_code=400, detail="Zadejte platný VIN nebo jeho dostatečně dlouhou část")
    if payload.limit is not None and payload.limit < 1:
        raise HTTPException(status_code=400, detail="Limit musí být prázdný nebo větší než 0")
    max_matches = max(1, min(int(payload.max_matches or 20), 100))
    local_vehicles = (
        db.query(Vehicle)
        .filter(func.upper(Vehicle.vin) == normalized_vin)
        .order_by(Vehicle.id.asc())
        .limit(20)
        .all()
    )
    summary = {
        "source_url": source_url,
        "source_info": {k: to_iso_datetime(v) if isinstance(v, datetime) else v for k, v in source_info.items()},
        "legal_notice": _mdcr_legal_notice(),
        "vin": payload.vin,
        "normalized_vin": normalized_vin,
        "limit": payload.limit,
        "scanned_records": 0,
        "records_with_vin": 0,
        "matches_count": 0,
        "matches": [],
        "source_sample_records": [],
        "source_metadata": {},
        "source_opened": False,
        "source_opened_note": None,
        "local_vehicles": [
            {
                "id": vehicle.id,
                "plate": vehicle.plate,
                "brand": vehicle.brand,
                "model": vehicle.model,
                "user_email": vehicle.user_email,
                "stk_valid_until": vehicle.stk_valid_until.isoformat() if vehicle.stk_valid_until else None,
                "latest_stk_odometer_km": vehicle.latest_stk_odometer_km,
                "latest_stk_odometer_date": to_iso_datetime(vehicle.latest_stk_odometer_date),
            }
            for vehicle in local_vehicles
        ],
    }
    req = urllib.request.Request(source_url, headers={"User-Agent": "ToozHub2 admin MDCR VIN lookup"})
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            buffered = io.BufferedReader(response)
            head = buffered.peek(2)[:2]
            summary["source_metadata"] = {
                "status_code": getattr(response, "status", None),
                "content_type": response.headers.get("content-type"),
                "content_encoding": response.headers.get("content-encoding"),
                "content_length": response.headers.get("content-length"),
                "detected_format": "gzip/xml" if head == b"\x1f\x8b" else "xml",
                "final_url": response.geturl(),
            }
            summary["source_opened"] = True
            summary["source_opened_note"] = (
                "Soubor MDČR je komprimovaný GZIP/XML. Aplikace jej úspěšně otevřela, rozbalila a níže zobrazuje konkrétní řádky."
                if head == b"\x1f\x8b"
                else "Soubor MDČR je XML. Aplikace jej úspěšně otevřela a níže zobrazuje konkrétní řádky."
            )
            stream = gzip.GzipFile(fileobj=buffered) if head == b"\x1f\x8b" else buffered
            for record in _iter_mdcr_open_data_records(stream):
                summary["scanned_records"] += 1
                if len(summary["source_sample_records"]) < 5:
                    summary["source_sample_records"].append(_serialize_mdcr_record(record))
                vin = record.get("vin")
                if vin:
                    summary["records_with_vin"] += 1
                if vin == normalized_vin:
                    summary["matches"].append(_serialize_mdcr_record(record))
                    summary["matches_count"] += 1
                    if summary["matches_count"] >= max_matches:
                        break
                if payload.limit and summary["scanned_records"] >= payload.limit:
                    break
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Kontrola VIN v MDČR datech selhala: {exc}") from exc
    if summary["matches_count"]:
        summary["verification_note"] = "Zadaný VIN byl nalezen přímo ve staženém MDČR datasetu."
    else:
        limit_text = "celém načteném souboru" if payload.limit is None else f"prvních {payload.limit} záznamech"
        summary["verification_note"] = (
            f"Zadaný VIN nebyl nalezen v {limit_text} tohoto konkrétního distribučního souboru. "
            "Neznamená to, že MDČR k vozidlu nikdy nic nemá; může být potřeba jiný denní soubor nebo hledání bez limitu."
        )
    return summary


@router.get("/mdcr-open-data/imports")
def list_mdcr_open_data_imports(
    limit: int = 30,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    limit = max(1, min(int(limit or 30), 100))
    rows = (
        db.query(VehicleStkImportAuditLog)
        .filter(VehicleStkImportAuditLog.action == "mdcr_open_data_import")
        .order_by(VehicleStkImportAuditLog.created_at.desc())
        .limit(limit)
        .all()
        if _table_ready(db, "vehicle_stk_import_audit_logs")
        else []
    )
    return {
        "items": [
            {
                "id": row.id,
                "vehicle_id": row.vehicle_id,
                "vin": row.vin,
                "status": row.status,
                "message": row.message,
                "created_at": to_iso_datetime(row.created_at),
            }
            for row in rows
        ]
    }


@router.get("/workspace-sections")
def get_admin_workspace_sections(
    email: str = Depends(require_developer_admin),
):
    """Oddělení přehledu admin API: Uživatelé vs. Servisy (pro klienty / nástroje)."""
    return {
        "sections": [
            {
                "id": "users",
                "label": "Uživatelé",
                "description": "Účty, licence, vozidla vázaná na uživatele",
                "paths": [
                    "/admin-api/users",
                    "/admin-api/users/{user_id}",
                    "/admin-api/users/{user_id}/vehicles",
                    "/admin-api/users/{user_id}/detail",
                    "/admin-api/users/{user_id}/admin-notify-history",
                    "/admin-api/users/{user_id}/admin-notify-send",
                    "/admin-api/control-center/users/{user_id}/license",
                ],
            },
            {
                "id": "services",
                "label": "Servisy",
                "description": "Servisní účty, žádosti o registraci",
                "paths": [
                    "/admin-api/services",
                    "/admin-api/services/{service_id}",
                    "/admin-api/service-registration-requests",
                ],
            },
            {
                "id": "demo_leads",
                "label": "Ukázkový přístup",
                "description": "E-maily, na které byl odeslán odkaz do veřejné ukázky (Developer Admin → Ukázka)",
                "paths": [
                    "/admin-api/demo-access-leads",
                ],
            },
        ]
    }


@router.get("/global-audit-log")
def list_global_audit_log_entries(
    limit: int = 100,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Čtení append-only tabulky audit_log (globální audit aplikace)."""
    if not inspect(db.bind).has_table("audit_log"):
        return {"items": [], "limit": limit, "offset": offset, "note": "audit_log table missing — run alembic upgrade"}
    rows = (
        db.query(GlobalAuditLog)
        .order_by(GlobalAuditLog.created_at.desc(), GlobalAuditLog.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "tenant_id": r.tenant_id,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "action": r.action,
                "actor_user_id": r.actor_user_id,
                "actor_role": r.actor_role,
                "metadata_json": r.metadata_json,
                "created_at": to_iso_datetime(r.created_at),
            }
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/security-status")
def get_admin_security_status(
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Zjednodušený bezpečnostní panel pro běžný admin režim."""
    now = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    allowlist_raw = str(os.getenv("ADMIN_NETWORK_ALLOWLIST", "")).strip()
    latest_failed = []
    active_blocks = []

    if inspect(db.bind).has_table("security_access_logs"):
        failed_rows = (
            db.query(SecurityAccessLog)
            .filter(SecurityAccessLog.event_type.in_(["login_failed", "login_rate_limited", "source_probe_blocked"]))
            .order_by(SecurityAccessLog.created_at.desc(), SecurityAccessLog.id.desc())
            .limit(50)
            .all()
        )
        latest_failed = [
            {
                "id": row.id,
                "event_type": row.event_type,
                "user_email": row.user_email,
                "ip_address": row.ip_address,
                "endpoint": row.endpoint,
                "location": ", ".join([part for part in [row.city, row.region, row.country] if part]) or None,
                "details": row.details,
                "created_at": to_iso_datetime(row.created_at),
            }
            for row in failed_rows
        ]

    if inspect(db.bind).has_table("security_blocked_ips"):
        active_blocks = [
            {
                "id": row.id,
                "ip_address": row.ip_address,
                "reason": row.reason,
                "blocked_by_email": row.blocked_by_email,
                "blocked_at": to_iso_datetime(row.blocked_at),
                "expires_at": to_iso_datetime(row.expires_at),
                "is_active": bool(row.is_active),
            }
            for row in (
                db.query(SecurityBlockedIp)
                .filter(SecurityBlockedIp.is_active.is_(True))
                .order_by(SecurityBlockedIp.blocked_at.desc())
                .limit(100)
                .all()
            )
        ]

    counters = {
        "failed_logins_24h": 0,
        "rate_limited_24h": 0,
        "source_probes_24h": 0,
        "blocked_ips_active": len(active_blocks),
    }
    if inspect(db.bind).has_table("security_access_logs"):
        counters["failed_logins_24h"] = int(db.query(func.count(SecurityAccessLog.id)).filter(SecurityAccessLog.event_type == "login_failed", SecurityAccessLog.created_at >= since_24h).scalar() or 0)
        counters["rate_limited_24h"] = int(db.query(func.count(SecurityAccessLog.id)).filter(SecurityAccessLog.event_type == "login_rate_limited", SecurityAccessLog.created_at >= since_24h).scalar() or 0)
        counters["source_probes_24h"] = int(db.query(func.count(SecurityAccessLog.id)).filter(SecurityAccessLog.event_type == "source_probe_blocked", SecurityAccessLog.created_at >= since_24h).scalar() or 0)

    return {
        "current_ip": _client_ip_from_request(request),
        "allowlist": {
            "configured": bool(allowlist_raw),
            "raw": allowlist_raw,
            "entries": [part.strip() for part in allowlist_raw.split(",") if part.strip()],
            "source": ".env / process environment",
            "requires_restart": True,
        },
        "counters": counters,
        "active_blocks": active_blocks,
        "latest_security_events": latest_failed,
        "timestamp": to_iso_datetime(now),
    }


@router.get("/settings/effective")
def get_admin_effective_settings(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Vrátí praktický přehled zdrojů nastavení: env vs. runtime admin settings."""
    runtime_settings = load_admin_settings()
    env_rows = [
        ("ENVIRONMENT", ENVIRONMENT, "env", True, False),
        ("HOST", HOST, "env", True, False),
        ("PORT", PORT, "env", True, False),
        ("ALLOWED_ORIGINS", ",".join(ALLOWED_ORIGINS or []), "env", True, False),
        ("ADMIN_NETWORK_ALLOWLIST", os.getenv("ADMIN_NETWORK_ALLOWLIST", ""), "env", True, False),
        ("ENFORCE_HTTPS", os.getenv("ENFORCE_HTTPS", ""), "env", True, False),
        ("SMTP_HOST", SMTP_HOST or "", "env", True, False),
        ("SMTP_PORT", SMTP_PORT or "", "env", True, False),
        ("SMTP_FROM", SMTP_FROM or "", "env", True, False),
        ("SMTP_USER", SMTP_USER or "", "env", True, True),
        ("JWT_EXPIRE_MINUTES", JWT_EXPIRE_MINUTES, "env", True, False),
        ("DATA_DIR", str(DATA_DIR), "env", True, False),
    ]
    runtime_rows = []
    for category, values in runtime_settings.items():
        if not isinstance(values, dict):
            continue
        for key, payload in values.items():
            payload = payload if isinstance(payload, dict) else {"value": payload}
            runtime_rows.append({
                "key": f"{category}.{key}",
                "value": payload.get("value"),
                "source": "runtime_settings",
                "requires_restart": False,
                "editable_in_admin": True,
                "description": payload.get("description"),
                "value_type": payload.get("value_type"),
            })
    return {
        "env": [
            {
                "key": key,
                "value": "***" if secret and value else value,
                "source": source,
                "requires_restart": restart,
                "editable_in_admin": False,
            }
            for key, value, source, restart, secret in env_rows
        ],
        "runtime": runtime_rows,
        "settings_file": str(ADMIN_SETTINGS_FILE),
        "settings_file_exists": ADMIN_SETTINGS_FILE.exists(),
    }


@router.get("/support-inbox")
def get_admin_support_inbox(
    limit: int = 100,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Inbox požadavků podpory složený z existujících security/support událostí."""
    if not inspect(db.bind).has_table("security_access_logs"):
        return {"items": [], "limit": limit, "offset": offset, "note": "security_access_logs missing"}
    rows = (
        db.query(SecurityAccessLog)
        .filter(SecurityAccessLog.event_type == "support_contact_submitted")
        .order_by(SecurityAccessLog.created_at.desc(), SecurityAccessLog.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 500))
        .all()
    )
    items = []
    for row in rows:
        details = _json_loads_safe(row.details)
        items.append({
            "id": row.id,
            "customer_id": row.customer_id,
            "tenant_id": row.tenant_id,
            "email": row.user_email,
            "category": details.get("category"),
            "subject": details.get("subject"),
            "has_phone": details.get("has_phone"),
            "include_diagnostics": details.get("include_diagnostics"),
            "ip_address": row.ip_address,
            "endpoint": row.endpoint,
            "created_at": to_iso_datetime(row.created_at),
        })
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/entity-history/{entity_type}/{entity_id}")
def get_admin_entity_history(
    entity_type: str,
    entity_id: int,
    limit: int = 100,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Jednotná timeline pro uživatele, vozidlo nebo servis."""
    normalized_type = (entity_type or "").strip().lower()
    if normalized_type not in {"user", "service", "vehicle"}:
        raise HTTPException(status_code=400, detail="entity_type musí být user, service nebo vehicle")

    items: List[Dict[str, Any]] = []
    target_user: Optional[Customer] = None
    tenant_id: Optional[int] = None
    if normalized_type in {"user", "service"}:
        target_user = db.query(Customer).filter(Customer.id == entity_id).first()
        if target_user:
            tenant_id = target_user.tenant_id

    if inspect(db.bind).has_table("audit_log"):
        q = db.query(GlobalAuditLog)
        if normalized_type == "vehicle":
            q = q.filter((GlobalAuditLog.vehicle_id == entity_id) | ((GlobalAuditLog.entity_type == "vehicle") & (GlobalAuditLog.entity_id == entity_id)))
        else:
            q = q.filter((GlobalAuditLog.actor_user_id == entity_id) | ((GlobalAuditLog.entity_type.in_(["user", "service", "customer"])) & (GlobalAuditLog.entity_id == entity_id)))
        for row in q.order_by(GlobalAuditLog.created_at.desc(), GlobalAuditLog.id.desc()).limit(limit).all():
            items.append({
                "source": "audit_log",
                "severity": _audit_severity(row.action, row.metadata_json),
                "title": row.action,
                "details": row.metadata_json,
                "actor": row.actor_role or row.actor_user_id,
                "created_at": to_iso_datetime(row.created_at),
            })

    if target_user and inspect(db.bind).has_table("security_access_logs"):
        for row in (
            db.query(SecurityAccessLog)
            .filter((SecurityAccessLog.customer_id == entity_id) | (func.lower(SecurityAccessLog.user_email) == func.lower(target_user.email)))
            .order_by(SecurityAccessLog.created_at.desc(), SecurityAccessLog.id.desc())
            .limit(30)
            .all()
        ):
            items.append({
                "source": "security",
                "severity": _audit_severity(row.event_type, row.details),
                "title": row.event_type,
                "details": row.details,
                "actor": row.user_email,
                "ip_address": row.ip_address,
                "created_at": to_iso_datetime(row.created_at),
            })

    if tenant_id and inspect(db.bind).has_table("license_payment_transactions"):
        for tx in (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.tenant_id == tenant_id)
            .order_by(LicensePaymentTransaction.created_at.desc(), LicensePaymentTransaction.id.desc())
            .limit(30)
            .all()
        ):
            items.append({
                "source": "payment",
                "severity": "critical" if _payment_needs_attention(tx.provider_status, tx.event_type) else "info",
                "title": tx.provider_status or tx.event_type or "payment",
                "details": tx.trans_id or tx.ref_id,
                "actor": tx.provider,
                "created_at": to_iso_datetime(tx.created_at),
            })

    if target_user and inspect(db.bind).has_table("admin_customer_change_events"):
        for row in (
            db.query(AdminCustomerChangeEvent)
            .filter(AdminCustomerChangeEvent.customer_id == entity_id)
            .order_by(AdminCustomerChangeEvent.created_at.desc(), AdminCustomerChangeEvent.id.desc())
            .limit(30)
            .all()
        ):
            items.append({
                "source": "admin_change",
                "severity": "warning" if row.notified_at is None else "info",
                "title": row.summary_line,
                "details": row.detail_text,
                "actor": row.admin_email,
                "created_at": to_iso_datetime(row.created_at),
            })

    if inspect(db.bind).has_table("developer_action_audit_logs"):
        targets = [f"{normalized_type}:{entity_id}"]
        if tenant_id:
            targets.append(f"tenant:{tenant_id}")
        for row in (
            db.query(DeveloperActionAuditLog)
            .filter(DeveloperActionAuditLog.target_resource.in_(targets))
            .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
            .limit(30)
            .all()
        ):
            items.append({
                "source": "developer_action",
                "severity": _audit_severity(row.action_type, row.result),
                "title": row.action_type,
                "details": row.parameters_json,
                "actor": row.developer_email,
                "created_at": to_iso_datetime(row.created_at),
            })

    items = sorted(items, key=lambda item: item.get("created_at") or "", reverse=True)[: min(max(limit, 1), 300)]
    return {"items": items, "entity_type": normalized_type, "entity_id": entity_id}


@router.get("/demo-access-leads")
def list_demo_access_leads(
    limit: int = 100,
    offset: int = 0,
    search: Optional[str] = None,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Přehled žádostí o ukázkový přístup (e-mail, na který byl odeslán odkaz, IP při žádosti, uplatnění odkazu).
    developer_admin / admin — obsahuje osobní údaje zájemců.
    Volitelný query param ``search`` filtruje řádky podle části e-mailu (case-insensitive).
    """
    if not inspect(db.bind).has_table("demo_access_tokens"):
        return {
            "items": [],
            "summary": {
                "total_requests": 0,
                "unique_visitor_emails": 0,
                "last_24h_requests": 0,
                "consumed_total": 0,
                "filtered_total": 0,
            },
            "limit": limit,
            "offset": offset,
            "note": "demo_access_tokens missing — run alembic upgrade",
            "search": None,
        }

    lim = min(max(int(limit), 1), 500)
    off = max(int(offset), 0)
    needle = (search or "").strip()
    list_q = db.query(DemoAccessToken)
    count_q = db.query(func.count(DemoAccessToken.id))
    if needle:
        like = f"%{needle}%"
        list_q = list_q.filter(DemoAccessToken.visitor_email.ilike(like))
        count_q = count_q.filter(DemoAccessToken.visitor_email.ilike(like))
    filtered_total = int(count_q.scalar() or 0)
    rows = (
        list_q.order_by(DemoAccessToken.created_at.desc(), DemoAccessToken.id.desc())
        .offset(off)
        .limit(lim)
        .all()
    )
    total_requests = int(db.query(func.count(DemoAccessToken.id)).scalar() or 0)
    unique_visitor_emails = int(
        db.query(func.count(func.distinct(DemoAccessToken.visitor_email))).scalar() or 0
    )
    consumed_total = int(
        db.query(func.count(DemoAccessToken.id)).filter(DemoAccessToken.consumed_at.isnot(None)).scalar() or 0
    )
    since = datetime.utcnow() - timedelta(hours=24)
    last_24h = int(
        db.query(func.count(DemoAccessToken.id))
        .filter(DemoAccessToken.created_at >= since)
        .scalar()
        or 0
    )

    return {
        "items": [
            {
                "id": r.id,
                "visitor_email": r.visitor_email,
                "client_ip": r.request_ip,
                "user_agent": r.user_agent,
                "contact_consent": bool(r.contact_consent),
                "created_at": to_iso_datetime(r.created_at),
                "expires_at": to_iso_datetime(r.expires_at),
                "consumed_at": to_iso_datetime(r.consumed_at) if r.consumed_at else None,
            }
            for r in rows
        ],
        "summary": {
            "total_requests": total_requests,
            "unique_visitor_emails": unique_visitor_emails,
            "last_24h_requests": last_24h,
            "consumed_total": consumed_total,
            "filtered_total": filtered_total,
        },
        "limit": lim,
        "offset": off,
        "search": needle or None,
    }


@router.get("/users", response_model=List[UserSummary])
def get_all_users(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech uživatelů s počtem vozidel - pouze pro developer_admin"""
    try:
        ensure_customer_account_state_schema(db)
        security_logs_available = inspect(db.bind).has_table("security_access_logs")
        licenses_available = inspect(db.bind).has_table("licenses")
        payments_available = inspect(db.bind).has_table("license_payment_transactions")
        notify_table = inspect(db.bind).has_table("admin_customer_change_events")
        pending_notify_sql = (
            "(SELECT COUNT(*) FROM admin_customer_change_events accne "
            "WHERE accne.customer_id = c.id AND accne.notified_at IS NULL)"
            if notify_table
            else "0"
        )
        license_plan_sql = (
            "(SELECT l.plan FROM licenses l WHERE l.tenant_id = c.tenant_id LIMIT 1)"
            if licenses_available
            else "NULL"
        )
        license_status_sql = (
            "(SELECT l.status FROM licenses l WHERE l.tenant_id = c.tenant_id LIMIT 1)"
            if licenses_available
            else "NULL"
        )
        has_paid_sql = (
            """
            (
                SELECT CASE WHEN EXISTS (
                    SELECT 1
                    FROM license_payment_transactions tx
                    WHERE tx.tenant_id = c.tenant_id
                      AND (
                        UPPER(COALESCE(tx.provider_status, '')) IN ('PAID', 'CONFIRMED')
                        OR LOWER(COALESCE(tx.event_type, '')) IN ('payment_paid', 'payment_confirmed', 'subscription_renewal_paid')
                      )
                ) THEN 1 ELSE 0 END
            )
            """
            if payments_available
            else "0"
        )
        last_paid_at_sql = (
            """
            (
                SELECT MAX(tx.created_at)
                FROM license_payment_transactions tx
                WHERE tx.tenant_id = c.tenant_id
                  AND (
                    UPPER(COALESCE(tx.provider_status, '')) IN ('PAID', 'CONFIRMED')
                    OR LOWER(COALESCE(tx.event_type, '')) IN ('payment_paid', 'payment_confirmed', 'subscription_renewal_paid')
                  )
            )
            """
            if payments_available
            else "NULL"
        )

        if security_logs_available:
            result = db.execute(text(f"""
                WITH page_customers AS (
                    SELECT
                        c.id as id,
                        c.email as email,
                        c.name as name,
                        c.role as role,
                        c.tenant_id as tenant_id,
                        c.city as city,
                        c.phone as phone,
                        c.created_at as created_at,
                        COALESCE(c.is_disabled, 0) as is_disabled,
                        COALESCE(c.is_deleted, 0) as is_deleted,
                        COALESCE(c.session_version, 0) as session_version,
                        c.admin_ordinal as admin_ordinal,
                        c.workspace_entitlements as workspace_entitlements,
                        c.workspace_ui_default as workspace_ui_default,
                        COALESCE(vehicle_counts.vehicles_count, 0) as vehicles_count,
                        {license_plan_sql} as license_plan,
                        {license_status_sql} as license_status,
                        {has_paid_sql} as has_paid,
                        {last_paid_at_sql} as last_paid_at,
                        {pending_notify_sql} as pending_admin_notify_count
                    FROM customers c
                    {_customer_vehicle_count_join_sql(customer_alias="c", join_alias="vehicle_counts")}
                    WHERE COALESCE(c.is_deleted, 0) = 0
                    GROUP BY c.id, c.email, c.name, c.role, c.tenant_id, c.city, c.phone, c.created_at, c.is_disabled, c.is_deleted, c.session_version, c.admin_ordinal, c.workspace_entitlements, c.workspace_ui_default, vehicle_counts.vehicles_count
                    ORDER BY c.created_at DESC
                    LIMIT :limit OFFSET :offset
                ),
                latest_security AS (
                    SELECT *
                    FROM (
                        SELECT
                            lower(sal.user_email) as user_email_norm,
                            sal.ip_address as last_ip_address,
                            sal.city as last_city,
                            sal.region as last_region,
                            sal.country as last_country,
                            sal.created_at as last_seen_at,
                            ROW_NUMBER() OVER (
                                PARTITION BY lower(sal.user_email)
                                ORDER BY sal.created_at DESC, sal.id DESC
                            ) as rn
                        FROM security_access_logs sal
                        WHERE sal.event_type IN ('login_success', 'api_activity', 'support_contact_submitted')
                          AND lower(sal.user_email) IN (SELECT lower(email) FROM page_customers)
                    )
                    WHERE rn = 1
                )
                SELECT
                    pc.*,
                    ls.last_ip_address,
                    ls.last_city,
                    ls.last_region,
                    ls.last_country,
                    ls.last_seen_at
                FROM page_customers pc
                LEFT JOIN latest_security ls ON ls.user_email_norm = lower(pc.email)
                ORDER BY pc.created_at DESC
            """), {"limit": limit, "offset": offset})
        else:
            result = db.execute(text(f"""
                WITH page_customers AS (
                    SELECT
                        c.id as id,
                        c.email as email,
                        c.name as name,
                        c.role as role,
                        c.tenant_id as tenant_id,
                        c.city as city,
                        c.phone as phone,
                        c.created_at as created_at,
                        COALESCE(c.is_disabled, 0) as is_disabled,
                        COALESCE(c.is_deleted, 0) as is_deleted,
                        COALESCE(c.session_version, 0) as session_version,
                        c.admin_ordinal as admin_ordinal,
                        c.workspace_entitlements as workspace_entitlements,
                        c.workspace_ui_default as workspace_ui_default,
                        COALESCE(vehicle_counts.vehicles_count, 0) as vehicles_count,
                        {license_plan_sql} as license_plan,
                        {license_status_sql} as license_status,
                        {has_paid_sql} as has_paid,
                        {last_paid_at_sql} as last_paid_at,
                        {pending_notify_sql} as pending_admin_notify_count
                    FROM customers c
                    {_customer_vehicle_count_join_sql(customer_alias="c", join_alias="vehicle_counts")}
                    WHERE COALESCE(c.is_deleted, 0) = 0
                    GROUP BY c.id, c.email, c.name, c.role, c.tenant_id, c.city, c.phone, c.created_at, c.is_disabled, c.is_deleted, c.session_version, c.admin_ordinal, c.workspace_entitlements, c.workspace_ui_default, vehicle_counts.vehicles_count
                    ORDER BY c.created_at DESC
                    LIMIT :limit OFFSET :offset
                )
                SELECT *
                FROM page_customers
                ORDER BY created_at DESC
            """), {"limit": limit, "offset": offset})

        rows = result.fetchall()
        payment_state_by_tenant: Dict[int, Dict[str, Any]] = {}
        if payments_available:
            tenant_ids = []
            for row in rows:
                row_map = dict(row._mapping) if hasattr(row, "_mapping") else {}
                tenant_id = row_map.get("tenant_id")
                if tenant_id is not None:
                    tenant_ids.append(int(tenant_id))
            payment_state_by_tenant = _collect_paid_state_by_tenant(db, tenant_ids)

        tenant_disk_map = _get_tenant_disk_usage_map(db)

        users = []
        for row in rows:
            data = dict(row._mapping) if hasattr(row, "_mapping") else {}
            created_at = data.get("created_at")
            if security_logs_available:
                last_ip_address = data.get("last_ip_address")
                last_location = build_location_line(data.get("last_city"), data.get("last_region"), data.get("last_country"))
                last_seen_at = to_iso_datetime(data.get("last_seen_at"))
                license_plan = (data.get("license_plan") or "free")
                license_status = (data.get("license_status") or "active")
            else:
                last_ip_address = None
                last_location = None
                last_seen_at = None
                license_plan = (data.get("license_plan") or "free")
                license_status = (data.get("license_status") or "active")

            is_online = is_online_by_last_seen(last_seen_at)
            tenant_id = data.get("tenant_id")
            tenant_payment_state = payment_state_by_tenant.get(int(tenant_id)) if tenant_id is not None else None
            has_paid_value = bool(data.get("has_paid"))
            last_paid_at_value = data.get("last_paid_at")
            if tenant_payment_state:
                has_paid_value = bool(tenant_payment_state.get("has_paid", has_paid_value))
                if has_paid_value:
                    last_paid_at_value = tenant_payment_state.get("last_paid_at") or last_paid_at_value
                else:
                    last_paid_at_value = None

            ws_eff = _effective_workspace_entitlements_for_admin_summary(
                str(data.get("role") or "") or None,
                data.get("workspace_entitlements"),
            )
            tid_for_disk = data.get("tenant_id")
            disk_b = int(tenant_disk_map.get(int(tid_for_disk), 0)) if tid_for_disk is not None else 0
            users.append(UserSummary(
                id=data.get("id"),
                admin_ordinal=data.get("admin_ordinal"),
                email=data.get("email"),
                name=data.get("name"),
                role=data.get("role"),
                tenant_id=data.get("tenant_id"),
                city=data.get("city"),
                phone=data.get("phone"),
                created_at=created_at,
                vehicles_count=data.get("vehicles_count") or 0,
                last_ip_address=last_ip_address,
                last_location=last_location,
                last_seen_at=last_seen_at,
                is_online=is_online,
                license_plan=license_plan,
                license_status=license_status,
                has_paid=has_paid_value,
                last_paid_at=to_iso_datetime(last_paid_at_value),
                is_disabled=bool(data.get("is_disabled")),
                is_deleted=bool(data.get("is_deleted")),
                session_version=int(data.get("session_version") or 0),
                workspace_entitlements=ws_eff,
                workspace_ui_default=data.get("workspace_ui_default"),
                pending_admin_notify_count=int(data.get("pending_admin_notify_count") or 0),
                disk_usage_bytes=disk_b,
                disk_usage_human=_format_bytes(disk_b),
            ))
        
        return users
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání uživatelů: {str(e)}")


def _fetch_deleted_user_archive_rows(db: Session) -> List[DeletedUserArchiveRow]:
    rows = (
        db.query(Customer, CustomerDeletionLabel)
        .join(CustomerDeletionLabel, CustomerDeletionLabel.customer_id == Customer.id)
        .filter(Customer.is_deleted.is_(True))
        .order_by(CustomerDeletionLabel.created_at.desc(), CustomerDeletionLabel.id.desc())
        .all()
    )
    out: List[DeletedUserArchiveRow] = []
    for cust, label in rows:
        out.append(
            DeletedUserArchiveRow(
                customer_id=int(cust.id),
                deletion_mark=deletion_mark_display(label.hash_depth, label.ordinal_at_delete),
                email_before=label.email_before or "",
                deleted_at=to_iso_datetime(cust.deleted_at),
                current_email=cust.email or "",
            )
        )
    return out


ARCHIVED_USERS_PURGE_CONFIRM_PHRASE = "VYMAZAT ARCHIV"


def _normalize_archive_purge_confirm_phrase(value: Optional[str]) -> str:
    without_punctuation = re.sub(r"[.,;:!?\"'`´]+", "", str(value or "").strip())
    return re.sub(r"\s+", " ", without_punctuation).upper()


def _merge_deleted_counts(target: Dict[str, int], source: Dict[str, Any]) -> None:
    for key, value in (source or {}).items():
        try:
            target[key] = int(target.get(key, 0)) + int(value or 0)
        except (TypeError, ValueError):
            continue


def _restore_archived_service_records_for_vehicle_ids(
    db: Session,
    *,
    vehicle_ids: List[int],
    admin_email: str,
) -> int:
    """Obnoví všechny archivované servisní záznamy na daných vozidlech (jedna transakce před volajícím commitem)."""
    if not vehicle_ids:
        return 0
    records = (
        db.query(ServiceRecord)
        .filter(
            ServiceRecord.vehicle_id.in_(vehicle_ids),
            ServiceRecord.is_deleted.is_(True),
        )
        .all()
    )
    restored = 0
    for record in records:
        before_snapshot = service_record_audit_snapshot(record)
        record.is_deleted = False
        record.deleted_at = None
        record.deleted_by_user_id = None
        record.deletion_reason = None
        after_snapshot = service_record_audit_snapshot(record)
        prev_json, _ = snapshot_json_and_hash(before_snapshot)
        new_json, snap_hash = snapshot_json_and_hash(after_snapshot)
        record.snapshot_hash = snap_hash
        db.add(
            ServiceRecordAuditLog(
                tenant_id=record.tenant_id,
                service_record_id=record.id,
                vehicle_id=record.vehicle_id,
                changed_by_user_id=None,
                action="restore",
                previous_snapshot_json=prev_json,
                new_snapshot_json=new_json,
                snapshot_hash=snap_hash,
                change_reason="customer_soft_restore",
            )
        )
        write_global_audit_log(
            db,
            entity_type="service_record",
            entity_id=int(record.id),
            action="service_record_restore_admin",
            actor_user_id=None,
            actor_role="developer_admin",
            tenant_id=int(record.tenant_id),
            metadata={
                "vehicle_id": int(record.vehicle_id),
                "cause": "user_soft_restore",
                "admin_email": admin_email,
            },
        )
        restored += 1
    return restored


@router.get("/user-deletion-archive", response_model=List[DeletedUserArchiveRow])
def get_deleted_users_archive(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Smazané účty s přehledovým označením (#N, ##N) a původním e-mailem.

    Pozn.: Cesta záměrně není pod /users/… — některé reverse proxy vrací 405 Method Not Allowed
    na vnořené cesty pod /admin-api/users/.
    """
    try:
        return _fetch_deleted_user_archive_rows(db)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání archivu smazaných: {str(e)}")


@router.post("/user-archive-purge")
def purge_deleted_users_archive(
    payload: UserArchivePurgeRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Trvale odstraní uživatele z archivu soft-delete.

    Cesta odpovídá existujícímu admin UI. Smazání je povoleno pouze pro účty,
    které už jsou označené jako smazané, a vyžaduje potvrzovací frázi.
    """
    try:
        if _normalize_archive_purge_confirm_phrase(payload.confirm_phrase) != ARCHIVED_USERS_PURGE_CONFIRM_PHRASE:
            raise HTTPException(status_code=400, detail="Potvrzovací fráze nesouhlasí.")

        actor = get_customer_by_email(db, email)
        actor_id = int(actor.id) if actor and actor.id is not None else None

        requested_ids = sorted({int(raw_id) for raw_id in (payload.customer_ids or []) if int(raw_id) > 0})
        if not payload.purge_all and not requested_ids:
            raise HTTPException(status_code=400, detail="Vyberte alespoň jeden účet z archivu.")

        query = db.query(Customer).filter(Customer.is_deleted.is_(True))
        if payload.purge_all:
            users = query.order_by(Customer.id.asc()).all()
        else:
            users = query.filter(Customer.id.in_(requested_ids)).order_by(Customer.id.asc()).all()

        if actor_id is not None:
            users = [user for user in users if int(user.id) != actor_id]

        if not users:
            return {
                "message": "V archivu nebyl nalezen žádný účet k trvalému odstranění.",
                "purged": 0,
                "customer_ids": [],
                "skipped_ids": requested_ids,
                "deleted_counts": {},
            }

        purged_ids = [int(user.id) for user in users if user.id is not None]
        skipped_ids = sorted(set(requested_ids) - set(purged_ids)) if not payload.purge_all else []
        deleted_counts: Dict[str, int] = {}

        labels_deleted = (
            db.query(CustomerDeletionLabel)
            .filter(CustomerDeletionLabel.customer_id.in_(purged_ids))
            .delete(synchronize_session=False)
        )
        deleted_counts["customer_deletion_labels"] = int(labels_deleted or 0)

        for user in users:
            counts = delete_customer_account(user, email=user.email or "", db=db)
            _merge_deleted_counts(deleted_counts, counts)

        db.commit()

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="user.archive_purge",
            target_resource="user_deletion_archive",
            parameters={
                "purge_all": bool(payload.purge_all),
                "requested_customer_ids": requested_ids,
                "purged_customer_ids": purged_ids,
                "skipped_customer_ids": skipped_ids,
                "deleted_counts": deleted_counts,
            },
            result="success",
            status_code=200,
        )

        return {
            "message": f"Trvale odstraněno z archivu: {len(purged_ids)}.",
            "purged": len(purged_ids),
            "customer_ids": purged_ids,
            "skipped_ids": skipped_ids,
            "deleted_counts": deleted_counts,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při trvalém mazání z archivu: {str(e)}")


@router.post("/user-soft-restore")
def soft_restore_deleted_customer(
    payload: UserSoftRestoreRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Obnoví účet po soft-delete: původní e-mail z archivu, aktivace účtu,
    synchronizace zobrazovaného e-mailu u vozidel vlastníka a obnovení
    archivovaných servisních záznamů na těchto vozidlech.
    """
    try:
        actor = get_customer_by_email(db, email)
        user = db.query(Customer).filter(Customer.id == int(payload.customer_id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        if actor and actor.id == user.id:
            raise HTTPException(status_code=400, detail="Nelze obnovit účet, pod kterým jste přihlášeni.")

        if not customer_is_deleted(user):
            raise HTTPException(status_code=400, detail="Účet není ve stavu soft-delete — obnova není potřeba.")

        label = (
            db.query(CustomerDeletionLabel)
            .filter(CustomerDeletionLabel.customer_id == user.id)
            .order_by(CustomerDeletionLabel.created_at.desc(), CustomerDeletionLabel.id.desc())
            .first()
        )
        if not label or not (label.email_before or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Nelze zjistit původní e-mail z archivu smazání (chybí záznam customer_deletion_labels).",
            )

        restored_email = (label.email_before or "").strip().lower()
        conflict = (
            db.query(Customer)
            .filter(
                func.lower(Customer.email) == restored_email,
                Customer.id != user.id,
                Customer.is_deleted.is_(False),
            )
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"E-mail {restored_email} je již použit jiným aktivním účtem (ID {conflict.id}).",
            )

        own_rows = (
            db.query(VehicleOwnership.vehicle_id)
            .filter(
                VehicleOwnership.customer_id == user.id,
                VehicleOwnership.is_active.is_(True),
            )
            .all()
        )
        vehicle_ids = [int(v[0]) for v in own_rows if v[0] is not None]

        user.email = restored_email
        user.is_deleted = False
        user.is_disabled = False
        user.deleted_at = None
        user.disabled_at = None
        assign_admin_ordinal_if_missing(db, user)
        sync_vehicle_user_email_display_for_customer(db, user.id, restored_email)
        increment_customer_session_version(user)

        records_restored = _restore_archived_service_records_for_vehicle_ids(
            db, vehicle_ids=vehicle_ids, admin_email=email
        )

        db.commit()

        if admin_change_table_exists(db):
            record_admin_customer_change(
                db,
                customer_id=user.id,
                admin_email=email,
                change_key="account.restored_after_soft_delete",
                summary_line=f"Účet byl obnoven z archivu (e-mail {restored_email})",
                detail_text=(payload.reason or "").strip() or None,
                payload={
                    "vehicles_considered": len(vehicle_ids),
                    "service_records_restored": records_restored,
                },
            )
            db.commit()

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="user.soft_restore",
            target_resource=f"user:{user.id}",
            parameters={
                "restored_email": restored_email,
                "vehicles_count": len(vehicle_ids),
                "service_records_restored": records_restored,
                "reason": (payload.reason or "").strip() or None,
            },
            result="success",
            status_code=200,
        )

        return {
            "message": f"Účet byl obnoven. Přihlašovací e-mail: {restored_email}",
            "user_id": user.id,
            "restored_email": restored_email,
            "vehicles_count": len(vehicle_ids),
            "service_records_restored": records_restored,
            "session_version": customer_session_version(user),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při obnově účtu: {str(e)}")


@router.post("/users")
def create_user(
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
    payload: Dict[str, Any] = Body(...),
):
    """Vytvoření nového uživatele"""
    try:
        user_data = UserCreate.model_validate(payload)
        acting_admin = get_customer_by_email(db, email)
        if not acting_admin:
            raise HTTPException(status_code=404, detail="Admin účet nenalezen")

        target_email = str(user_data.email).strip().lower()
        target_role = validate_role_value(user_data.role)
        selected_plan = normalize_license_plan(user_data.license_plan, target_role)
        can_manage_license = bool(LICENSE_MANAGEMENT_AVAILABLE and upgrade_license_plan)
        plan_for_upgrade = selected_plan if can_manage_license else None
        if user_data.tenant_id is not None:
            tenant_id = resolve_tenant_id_for_create(db, acting_admin, user_data.tenant_id)
        else:
            tenant_kind = "service" if target_role == "service" else "user"
            tenant_id = create_dedicated_tenant(
                db,
                owner_email=target_email,
                owner_name=user_data.name,
                workspace_route_kind=tenant_kind,
            ).id

        # Zkontrolovat, zda email již existuje
        existing = get_customer_by_email(db, target_email)
        if existing:
            raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
        
        # Hash hesla
        password_hash_value = hash_password(user_data.password)

        now_admin = datetime.utcnow()
        phone_e164_create = None
        if user_data.phone:
            from src.modules.vehicle_hub.registration_security import normalize_validate_phone_e164

            try:
                phone_e164_create = normalize_validate_phone_e164(str(user_data.phone))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

        # Vytvořit uživatele
        new_user = Customer(
            tenant_id=tenant_id,
            email=target_email,
            name=user_data.name,
            password_hash=password_hash_value,
            role=target_role,
            ico=user_data.ico,
            dic=user_data.dic,
            phone=user_data.phone,
            phone_e164=phone_e164_create,
            street=user_data.street,
            street_number=user_data.street_number,
            city=user_data.city,
            zip=user_data.zip,
            created_at=now_admin,
            account_status="active",
            email_verified_at=now_admin,
        )
        db.add(new_user)
        db.flush()
        assign_admin_ordinal_if_missing(db, new_user)

        if "workspace_entitlements" in payload:
            raw_ent_c = payload.get("workspace_entitlements")
            if raw_ent_c is None:
                new_user.workspace_entitlements = None
            else:
                try:
                    new_user.workspace_entitlements = normalize_workspace_entitlements_for_storage(raw_ent_c)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
        if "workspace_ui_default" in payload:
            raw_ui_c = payload.get("workspace_ui_default")
            if raw_ui_c is None or str(raw_ui_c).strip() == "":
                new_user.workspace_ui_default = None
            else:
                try:
                    new_user.workspace_ui_default = normalize_workspace_ui_default_for_storage(
                        raw_ui_c,
                        effective_workspace_kinds(new_user),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        db.commit()
        db.refresh(new_user)

        ensure_default_license_for_tenant(db, new_user.tenant_id)
        if plan_for_upgrade:
            upgrade_license_plan(db, new_user.tenant_id, plan_for_upgrade)
        db.refresh(new_user)

        return {
            "id": new_user.id,
            "email": new_user.email,
            "tenant_id": new_user.tenant_id,
            "role": new_user.role,
            "license_plan": selected_plan or normalize_license_plan("free", target_role) or "free",
            "workspace_entitlements": sorted(effective_workspace_kinds(new_user)),
            "workspace_ui_default": getattr(new_user, "workspace_ui_default", None),
            "message": "Uživatel byl vytvořen",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření uživatele: {str(e)}")


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
    payload: Dict[str, Any] = Body(...),
):
    """Úprava uživatele"""
    try:
        user_data = UserUpdate.model_validate(payload)
        ensure_customer_account_state_schema(db)
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        if customer_is_deleted(user):
            raise HTTPException(status_code=400, detail="Smazaný účet nelze upravovat")

        target_role = validate_role_value(user_data.role) if user_data.role is not None else str(user.role or "user")

        old_role_l = str(user.role or "").strip().lower()
        tenant_row = db.query(Tenant).filter(Tenant.id == user.tenant_id).first() if user.tenant_id else None
        old_tenant_kind = str(tenant_row.workspace_route_kind or "").strip().lower() if tenant_row else ""

        if tenant_row:
            nr = str(target_role or "").strip().lower()
            if nr == "service":
                tenant_row.workspace_route_kind = "service"
            elif old_tenant_kind == "service" and nr not in ("service", "developer_admin"):
                tenant_row.workspace_route_kind = "user"

        tenant_kind_after = str(tenant_row.workspace_route_kind or "").strip().lower() if tenant_row else ""
        demotion_counts: Optional[Dict[str, int]] = None
        old_svc_operator = _customer_presensed_as_service_operator(
            role=old_role_l,
            tenant_workspace_route_kind=old_tenant_kind,
        )
        new_svc_operator = _customer_presensed_as_service_operator(
            role=str(target_role or "").strip().lower(),
            tenant_workspace_route_kind=tenant_kind_after,
        )
        service_operator_demotion = old_svc_operator and not new_svc_operator
        if service_operator_demotion:
            demotion_counts = _revoke_service_operator_graph(
                db,
                service_customer_id=int(user.id),
                admin_email=email,
            )
            if hasattr(user, "partner_catalog_approved"):
                user.partner_catalog_approved = False
            increment_customer_session_version(user)

        db.flush()

        plan_role_for_license = target_role
        if LICENSE_MANAGEMENT_AVAILABLE and pairing_role_for_tenant_license and user.tenant_id:
            plan_role_for_license = pairing_role_for_tenant_license(db, int(user.tenant_id))

        lic_row_for_plan = None
        if inspect(db.bind).has_table("licenses") and user.tenant_id:
            lic_row_for_plan = db.query(License).filter(License.tenant_id == user.tenant_id).first()

        if service_operator_demotion:
            fallback_user_plan = _map_service_license_storage_to_user_plan(
                lic_row_for_plan.plan if lic_row_for_plan else None
            )
            try:
                selected_plan = normalize_license_plan(user_data.license_plan, "user")
            except HTTPException:
                selected_plan = fallback_user_plan
        else:
            selected_plan = normalize_license_plan(user_data.license_plan, plan_role_for_license)
        can_manage_license = bool(LICENSE_MANAGEMENT_AVAILABLE and upgrade_license_plan)
        plan_for_upgrade = selected_plan if can_manage_license else None

        license_before = (None, None)
        if inspect(db.bind).has_table("licenses"):
            lic_row0 = db.query(License).filter(License.tenant_id == user.tenant_id).first()
            if lic_row0:
                license_before = (lic_row0.plan, lic_row0.status)
        before_prof = {
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "ico": user.ico,
            "dic": user.dic,
            "phone": user.phone,
            "street": user.street,
            "street_number": user.street_number,
            "city": user.city,
            "zip": user.zip,
            "workspace_entitlements": user.workspace_entitlements,
            "workspace_ui_default": user.workspace_ui_default,
        }
        pwd_will_update = user_data.password is not None
        
        # Aktualizovat pole
        if user_data.email is not None:
            new_email = str(user_data.email).strip().lower()
            # Zkontrolovat, zda nový email neexistuje
            existing = db.query(Customer).filter(
                func.lower(Customer.email) == new_email,
                Customer.id != user_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
            user.email = new_email
            sync_vehicle_user_email_display_for_customer(db, user.id, new_email)
        
        if user_data.name is not None:
            user.name = user_data.name
        
        if user_data.role is not None:
            user.role = target_role

        if user_data.ico is not None:
            user.ico = user_data.ico
        if user_data.dic is not None:
            user.dic = user_data.dic
        if user_data.phone is not None:
            user.phone = user_data.phone
            phone_e164_val = None
            if user_data.phone:
                from src.modules.vehicle_hub.registration_security import normalize_validate_phone_e164

                try:
                    phone_e164_val = normalize_validate_phone_e164(str(user_data.phone))
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            user.phone_e164 = phone_e164_val
        if user_data.street is not None:
            user.street = user_data.street
        if user_data.street_number is not None:
            user.street_number = user_data.street_number
        if user_data.city is not None:
            user.city = user_data.city
        if user_data.zip is not None:
            user.zip = user_data.zip
        
        if user_data.password is not None:
            user.password_hash = hash_password(user_data.password)
            increment_customer_session_version(user)

        if "workspace_entitlements" in payload:
            raw_ent = payload.get("workspace_entitlements")
            if raw_ent is None:
                user.workspace_entitlements = None
            else:
                try:
                    user.workspace_entitlements = normalize_workspace_entitlements_for_storage(raw_ent)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        if "workspace_ui_default" in payload:
            raw_ui = payload.get("workspace_ui_default")
            if raw_ui is None or str(raw_ui).strip() == "":
                user.workspace_ui_default = None
            else:
                try:
                    user.workspace_ui_default = normalize_workspace_ui_default_for_storage(
                        raw_ui,
                        effective_workspace_kinds(user),
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

        if service_operator_demotion and str(target_role or "").strip().lower() == "user":
            if "workspace_entitlements" not in payload:
                user.workspace_entitlements = None
            if "workspace_ui_default" not in payload:
                user.workspace_ui_default = None

        db.commit()

        updated_license = None
        if plan_for_upgrade:
            updated_license = upgrade_license_plan(db, user.tenant_id, plan_for_upgrade)

        db.refresh(user)

        license_after = (None, None)
        if inspect(db.bind).has_table("licenses"):
            lic_row1 = db.query(License).filter(License.tenant_id == user.tenant_id).first()
            if lic_row1:
                license_after = (lic_row1.plan, lic_row1.status)
        after_prof = {
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "ico": user.ico,
            "dic": user.dic,
            "phone": user.phone,
            "street": user.street,
            "street_number": user.street_number,
            "city": user.city,
            "zip": user.zip,
            "workspace_entitlements": user.workspace_entitlements,
            "workspace_ui_default": user.workspace_ui_default,
        }
        if admin_change_table_exists(db):
            record_user_profile_license_changes_from_admin(
                db,
                customer_id=user.id,
                admin_email=email,
                before=before_prof,
                after=after_prof,
                license_before=license_before,
                license_after=license_after,
                password_updated=pwd_will_update,
            )
            db.commit()

        acting = get_customer_by_email(db, email)
        write_global_audit_log(
            db,
            entity_type="admin_customer",
            entity_id=int(user.id),
            action="admin_user_patch",
            actor_user_id=int(acting.id) if acting else None,
            actor_role=str(getattr(acting, "role", None) or "") if acting else None,
            tenant_id=int(user.tenant_id) if user.tenant_id else None,
            before_json=before_prof,
            after_json=after_prof,
            metadata={
                "admin_email": email,
                "target_user_id": int(user.id),
                "password_updated": bool(pwd_will_update),
            },
            ip=(str(request.client.host)[:128] if request.client and request.client.host else None),
        )
        db.commit()

        resp_license_plan = (updated_license or {}).get("plan")
        resp_license_status = (updated_license or {}).get("status")
        if (
            (resp_license_plan is None or resp_license_status is None)
            and LICENSE_MANAGEMENT_AVAILABLE
            and get_tenant_license_status
        ):
            try:
                lic_snap = get_tenant_license_status(db, int(user.tenant_id), user_email=user.email)
                if isinstance(lic_snap, dict):
                    if resp_license_plan is None:
                        resp_license_plan = lic_snap.get("plan") or resp_license_plan
                    if resp_license_status is None:
                        resp_license_status = lic_snap.get("status") or resp_license_status
            except Exception:
                pass
        if resp_license_plan is None:
            resp_license_plan = selected_plan

        return {
            "message": "Uživatel byl upraven",
            "license_plan": resp_license_plan,
            "license_status": resp_license_status,
            "workspace_entitlements": sorted(effective_workspace_kinds(user)),
            "workspace_ui_default": getattr(user, "workspace_ui_default", None),
            "service_binding_cleanup": demotion_counts,
            "service_operator_demotion": {
                "applied": bool(service_operator_demotion),
                "license_plan_applied": selected_plan if service_operator_demotion else None,
            },
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě uživatele: {str(e)}")


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Bezpečné smazání uživatele (soft-delete + invalidace session)."""
    try:
        actor = get_customer_by_email(db, email)
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")

        if actor and actor.id == user.id:
            raise HTTPException(status_code=400, detail="Nelze smazat aktuálně přihlášený admin účet.")

        result = soft_delete_customer(db, user)
        if result.get("already"):
            return {"message": f"Účet {result.get('email')} je již smazaný.", "soft_deleted": True}

        previous_email = result["previous_email"]
        deleted_alias = result["deleted_alias"]
        db.commit()

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="user.delete",
            target_resource=f"user:{user_id}",
            parameters={
                "previous_email": previous_email,
                "deleted_alias": deleted_alias,
                "by": email.lower(),
            },
            result="success",
            status_code=200,
        )

        return {
            "message": f"Uživatel {previous_email} byl bezpečně smazán",
            "soft_deleted": True,
            "deleted_alias_email": deleted_alias,
            "session_version": result.get("session_version"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání uživatele: {str(e)}")


@router.get("/users/{user_id}/vehicles", response_model=List[VehicleSummary])
def get_user_vehicles(
    user_id: int,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí všechna vozidla daného uživatele - pouze pro developer_admin"""
    try:
        # Získat email uživatele podle ID
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        
        
        # Načíst vozidla uživatele podle explicitního ownership source-of-truth.
        vehicles_result = db.execute(text(f"""
            SELECT 
                v.id,
                COALESCE(owner_customer.email, v.user_email) as user_email,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.created_at,
                COUNT(sr.id) as service_count
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            {_primary_owner_join_sql(vehicle_alias="v", selector_alias="uvo_primary", ownership_alias="uvo", owner_alias="owner_customer")}
            WHERE uvo.customer_id = :user_id
              AND uvo.is_active = 1
              AND v.status != 'archived'
            GROUP BY v.id, owner_customer.email, v.user_email, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.created_at
            ORDER BY v.created_at DESC
        """), {"user_id": user_id})
        
        vehicles = []
        for row in vehicles_result:
            created_at = row[8]
            vehicles.append(VehicleSummary(
                id=row[0],
                user_email=row[1],
                nickname=row[2],
                brand=row[3],
                model=row[4],
                year=row[5],
                plate=row[6],
                vin=row[7],
                created_at=created_at,
                service_count=row[9] or 0
            ))
        
        return vehicles
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {str(e)}")


@router.get("/users/{user_id}/detail")
def get_user_detail(
    user_id: int,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """
    Detail uživatele pro admin dashboard.
    Vrací kompletní profil + navazující seznamy (vozidla, připomínky, rezervace, záznamy).
    """
    try:
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        normalized_email = (user.email or "").strip().lower()

        vehicle_rows = db.execute(text(f"""
            SELECT
                v.id,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.engine,
                v.notes,
                v.stk_valid_until,
                v.insurance_provider,
                v.insurance_valid_until,
                v.created_at,
                COUNT(sr.id) as service_count
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            {_primary_owner_join_sql(vehicle_alias="v", selector_alias="udv_primary", ownership_alias="udv_ownership", owner_alias="udv_owner")}
            WHERE udv_ownership.customer_id = :customer_id
              AND udv_ownership.is_active = 1
              AND v.status != 'archived'
            GROUP BY
                v.id, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.engine, v.notes,
                v.stk_valid_until, v.insurance_provider, v.insurance_valid_until, v.created_at
            ORDER BY v.created_at DESC
        """), {"customer_id": user_id})

        vehicles: List[Dict[str, Any]] = []
        for row in vehicle_rows:
            vehicle_id = row[0]
            vehicle_label = build_vehicle_label(row[1], row[2], row[3], row[5], vehicle_id)
            vehicles.append({
                "id": vehicle_id,
                "nickname": row[1],
                "brand": row[2],
                "model": row[3],
                "year": row[4],
                "plate": row[5],
                "vin": row[6],
                "engine": row[7],
                "notes": row[8],
                "stk_valid_until": to_iso_datetime(row[9]),
                "insurance_provider": row[10],
                "insurance_valid_until": to_iso_datetime(row[11]),
                "created_at": to_iso_datetime(row[12]),
                "service_count": row[13] or 0,
                "label": vehicle_label,
            })

        reminder_rows = db.execute(text("""
            SELECT
                r.id,
                r.vehicle_id,
                r.type,
                r.text,
                r.due_date,
                r.is_manual,
                r.is_completed,
                r.created_at,
                v.nickname,
                v.brand,
                v.model,
                v.plate
            FROM reminders r
            LEFT JOIN vehicles v ON v.id = r.vehicle_id
            WHERE r.customer_id = :customer_id
            ORDER BY
                CASE WHEN r.due_date IS NULL THEN 1 ELSE 0 END,
                r.due_date ASC,
                r.created_at DESC
        """), {"customer_id": user_id})

        reminders: List[Dict[str, Any]] = []
        for row in reminder_rows:
            vehicle_id = row[1]
            reminders.append({
                "id": row[0],
                "vehicle_id": vehicle_id,
                "type": row[2],
                "text": row[3],
                "due_date": to_iso_datetime(row[4]),
                "is_manual": bool(row[5]) if row[5] is not None else False,
                "is_completed": bool(row[6]) if row[6] is not None else False,
                "created_at": to_iso_datetime(row[7]),
                "vehicle_label": build_vehicle_label(row[8], row[9], row[10], row[11], vehicle_id),
            })

        reservation_rows = db.execute(text("""
            SELECT
                rs.id,
                rs.service_id,
                rs.vehicle_id,
                rs.service_type,
                rs.note,
                rs.start_datetime,
                rs.end_datetime,
                rs.status,
                rs.created_at,
                svc.name as service_name,
                svc.email as service_email,
                v.nickname,
                v.brand,
                v.model,
                v.plate
            FROM reservations rs
            LEFT JOIN customers svc ON svc.id = rs.service_id
            LEFT JOIN vehicles v ON v.id = rs.vehicle_id
            WHERE rs.customer_id = :customer_id
            ORDER BY rs.start_datetime DESC, rs.created_at DESC
        """), {"customer_id": user_id})

        reservations: List[Dict[str, Any]] = []
        for row in reservation_rows:
            vehicle_id = row[2]
            reservations.append({
                "id": row[0],
                "service_id": row[1],
                "vehicle_id": vehicle_id,
                "service_type": row[3],
                "note": row[4],
                "start_datetime": to_iso_datetime(row[5]),
                "end_datetime": to_iso_datetime(row[6]),
                "status": row[7],
                "created_at": to_iso_datetime(row[8]),
                "service_name": row[9],
                "service_email": row[10],
                "vehicle_label": build_vehicle_label(row[11], row[12], row[13], row[14], vehicle_id),
            })

        record_rows = db.execute(text("""
            SELECT
                sr.id,
                sr.vehicle_id,
                sr.user_id,
                sr.performed_at,
                sr.mileage,
                sr.description,
                sr.price,
                sr.note,
                sr.category,
                sr.created_by_ai,
                v.nickname,
                v.brand,
                v.model,
                v.plate
            FROM service_records sr
            JOIN vehicles v ON v.id = sr.vehicle_id
            JOIN vehicle_ownerships vo
              ON vo.vehicle_id = v.id
             AND vo.customer_id = :customer_id
             AND vo.is_active = 1
            ORDER BY sr.performed_at DESC
        """), {"customer_id": user_id})

        records: List[Dict[str, Any]] = []
        for row in record_rows:
            vehicle_id = row[1]
            records.append({
                "id": row[0],
                "vehicle_id": vehicle_id,
                "user_id": row[2],
                "performed_at": to_iso_datetime(row[3]),
                "mileage": row[4],
                "description": row[5],
                "price": row[6],
                "note": row[7],
                "category": row[8],
                "created_by_ai": bool(row[9]) if row[9] is not None else False,
                "vehicle_label": build_vehicle_label(row[10], row[11], row[12], row[13], vehicle_id),
            })

        ip_history: List[Dict[str, Any]] = []

        security_logs_available = inspect(db.bind).has_table("security_access_logs")
        if security_logs_available:
            try:
                ip_rows = db.execute(text("""
                    SELECT
                        ip_address,
                        user_agent,
                        created_at,
                        event_type,
                        city,
                        region,
                        country,
                        timezone,
                        isp,
                        source,
                        latitude,
                        longitude,
                        details
                    FROM security_access_logs
                    WHERE (customer_id = :customer_id OR lower(user_email) = :user_email)
                      AND ip_address IS NOT NULL
                      AND TRIM(ip_address) != ''
                    ORDER BY created_at DESC
                    LIMIT 20
                """), {"customer_id": user_id, "user_email": (user.email or "").strip().lower()})

                for row in ip_rows:
                    location_label = build_location_line(row[4], row[5], row[6])
                    details_payload: Dict[str, Any] = {}
                    if row[12]:
                        try:
                            parsed = json.loads(row[12])
                            if isinstance(parsed, dict):
                                details_payload = parsed
                        except Exception:
                            details_payload = {}

                    latitude = row[10]
                    longitude = row[11]
                    geo_accuracy = details_payload.get("geo_accuracy_m")
                    geo_source = details_payload.get("geo_source") or row[9]
                    if not location_label and latitude is not None and longitude is not None:
                        location_label = f"GPS {float(latitude):.5f}, {float(longitude):.5f}"

                    maps_url = None
                    if latitude is not None and longitude is not None:
                        maps_url = f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=16/{latitude}/{longitude}"
                    ip_history.append({
                        "ip_address": row[0],
                        "user_agent": row[1],
                        "timestamp": to_iso_datetime(row[2]),
                        "event_type": row[3],
                        "city": row[4],
                        "region": row[5],
                        "country": row[6],
                        "timezone": row[7],
                        "isp": row[8],
                        "source": row[9],
                        "geo_source": geo_source,
                        "latitude": latitude,
                        "longitude": longitude,
                        "geo_accuracy_m": geo_accuracy,
                        "maps_url": maps_url,
                        "location_label": location_label,
                    })
            except Exception:
                ip_history = []

        # Fallback na starsi usage_analytics tabulku, pokud nejsou security logy.
        if not ip_history and USAGE_ANALYTICS_AVAILABLE:
            try:
                ip_rows = db.execute(text("""
                    SELECT ip_address, user_agent, timestamp
                    FROM usage_analytics
                    WHERE lower(user_email) = :user_email
                      AND ip_address IS NOT NULL
                      AND TRIM(ip_address) != ''
                    ORDER BY timestamp DESC
                    LIMIT 10
                """), {"user_email": (user.email or "").strip().lower()})

                for row in ip_rows:
                    ip_history.append({
                        "ip_address": row[0],
                        "user_agent": row[1],
                        "timestamp": to_iso_datetime(row[2]),
                        "event_type": "legacy_activity",
                        "city": None,
                        "region": None,
                        "country": None,
                        "timezone": None,
                        "isp": None,
                        "source": "usage_analytics",
                        "location_label": None,
                    })
            except Exception:
                ip_history = []

        address_parts = [part for part in [user.street, user.street_number] if part]
        address_line = " ".join(address_parts) if address_parts else None
        city_line_parts = [part for part in [user.zip, user.city] if part]
        city_line = " ".join(city_line_parts) if city_line_parts else None

        last_activity_at = None
        if ip_history:
            last_activity_at = ip_history[0].get("timestamp")
        elif records:
            last_activity_at = records[0].get("performed_at")
        elif reminders:
            last_activity_at = reminders[0].get("created_at")
        elif reservations:
            last_activity_at = reservations[0].get("created_at")

        license_plan = "free"
        license_status = "active"
        license_limit = None
        license_vehicle_count = None
        licenses_table_available = inspect(db.bind).has_table("licenses")
        subscriptions_table_available = inspect(db.bind).has_table("license_subscriptions")
        payments_table_available = inspect(db.bind).has_table("license_payment_transactions")
        license_row = (
            db.query(License).filter(License.tenant_id == user.tenant_id).first()
            if licenses_table_available
            else None
        )
        subscription_row = (
            db.query(LicenseSubscription)
            .filter(LicenseSubscription.tenant_id == user.tenant_id)
            .first()
            if subscriptions_table_available
            else None
        )
        if LICENSE_MANAGEMENT_AVAILABLE and get_tenant_license_status:
            try:
                license_payload = get_tenant_license_status(db, user.tenant_id, user.email)
                license_plan = license_payload.get("plan") or "free"
                license_status = license_payload.get("status") or "active"
                license_limit = license_payload.get("vehicles_limit")
                license_vehicle_count = license_payload.get("vehicles_current")
            except Exception:
                pass

        payment_rows = (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.tenant_id == user.tenant_id)
            .order_by(LicensePaymentTransaction.created_at.desc(), LicensePaymentTransaction.id.desc())
            .limit(10)
            .all()
            if payments_table_available
            else []
        )

        has_paid = False
        first_paid_at = None
        latest_paid_at = None
        live_payments_count = 0
        test_payments_count = 0
        live_paid_count = 0
        test_paid_count = 0
        failed_payments_count = 0
        refunded_payments_count = 0
        recent_payments: List[Dict[str, Any]] = []
        for tx in payment_rows:
            provider_status = str(tx.provider_status or "").strip().upper()
            event_type = str(tx.event_type or "").strip().lower()
            payment_environment = _infer_payment_environment(
                payload_json=tx.payload_json,
                provider_status=provider_status,
                event_type=event_type,
            )
            is_successful = _is_payment_successful(provider_status, event_type)
            is_failed = _is_payment_failed(provider_status, event_type)
            refund_status = _payment_refund_status(provider_status, event_type)
            is_counted_paid = _payment_counts_as_paid(
                environment=payment_environment,
                is_successful=is_successful,
            )
            tx_created = to_iso_datetime(tx.created_at)
            if payment_environment == "LIVE":
                live_payments_count += 1
            else:
                test_payments_count += 1
            if is_successful:
                if payment_environment == "LIVE":
                    live_paid_count += 1
                else:
                    test_paid_count += 1
            if is_failed:
                failed_payments_count += 1
            if refund_status == "refunded":
                refunded_payments_count += 1

            if is_counted_paid:
                has_paid = True
                if tx_created:
                    latest_paid_at = latest_paid_at or tx_created
                    first_paid_at = tx_created

            recent_payments.append(
                {
                    "id": tx.id,
                    "provider": tx.provider,
                    "trans_id": tx.trans_id,
                    "ref_id": tx.ref_id,
                    "provider_status": tx.provider_status,
                    "event_type": tx.event_type,
                    "payment_environment": payment_environment,
                    "is_successful": is_successful,
                    "is_failed": is_failed,
                    "amount_halers": tx.amount_halers,
                    "currency": tx.currency,
                    "payment_timestamp": tx_created,
                    "refund_status": refund_status,
                }
            )

        latest_license_admin_action = (
            db.query(DeveloperActionAuditLog)
            .filter(
                DeveloperActionAuditLog.target_resource.in_(
                    [f"user:{user_id}", f"tenant:{user.tenant_id}"]
                ),
                DeveloperActionAuditLog.action_type.in_(
                    ["license.change", "license.override", "user.create"]
                ),
            )
            .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
            .first()
        )

        source_of_activation = "manual"
        if has_paid:
            source_of_activation = "payment"
        if latest_license_admin_action:
            action = str(latest_license_admin_action.action_type or "").strip().lower()
            if action in {"license.change", "license.override"}:
                source_of_activation = "developer_override"
            elif action == "user.create":
                source_of_activation = "trial_or_manual"

        presence_row = None
        if security_logs_available:
            presence_row = db.execute(
                text(
                    """
                    SELECT
                        (
                            SELECT MAX(s1.created_at)
                            FROM security_access_logs s1
                            WHERE lower(s1.user_email) = :user_email
                              AND s1.event_type IN ('api_activity', 'login_success', 'support_contact_submitted')
                        ) AS last_seen_at,
                        (
                            SELECT MAX(s2.created_at)
                            FROM security_access_logs s2
                            WHERE lower(s2.user_email) = :user_email
                              AND s2.event_type = 'login_success'
                        ) AS last_login_at,
                        (
                            SELECT COUNT(DISTINCT COALESCE(s3.ip_address, '') || '|' || COALESCE(s3.user_agent, ''))
                            FROM security_access_logs s3
                            WHERE lower(s3.user_email) = :user_email
                              AND s3.created_at >= :window_start
                              AND s3.event_type IN ('api_activity', 'login_success')
                        ) AS active_session_count
                    """
                ),
                {
                    "window_start": datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS),
                    "user_email": normalized_email,
                },
            ).fetchone()

        presence_last_seen = to_iso_datetime(presence_row[0] if presence_row else None)
        presence_last_login = to_iso_datetime(presence_row[1] if presence_row else None)
        active_session_count = int(presence_row[2] or 0) if presence_row else 0
        is_online = is_online_by_last_seen(presence_last_seen)

        activation_date = to_iso_datetime(license_row.valid_from if license_row else None)
        expiration_date = to_iso_datetime(license_row.valid_to if license_row else None)
        if not expiration_date:
            expiration_date = to_iso_datetime(subscription_row.current_period_end if subscription_row else None)
        next_renewal_date = to_iso_datetime(subscription_row.next_charge_at if subscription_row else None)
        purchase_date = first_paid_at or activation_date

        deletion_archive_mark = None
        deletion_email_before = None
        label_row = (
            db.query(CustomerDeletionLabel)
            .filter(CustomerDeletionLabel.customer_id == user_id)
            .order_by(CustomerDeletionLabel.id.desc())
            .first()
        )
        if label_row:
            deletion_archive_mark = deletion_mark_display(label_row.hash_depth, label_row.ordinal_at_delete)
            raw_prev = (label_row.email_before or "").strip().lower()
            deletion_email_before = raw_prev or None

        admin_notify_pending = 0
        if admin_change_table_exists(db):
            admin_notify_pending = int(
                db.query(func.count())
                .select_from(AdminCustomerChangeEvent)
                .filter(
                    AdminCustomerChangeEvent.customer_id == user_id,
                    AdminCustomerChangeEvent.notified_at.is_(None),
                )
                .scalar()
                or 0
            )

        tenant_disk_map = _get_tenant_disk_usage_map(db)
        tid_u = user.tenant_id
        disk_u = int(tenant_disk_map.get(int(tid_u), 0)) if tid_u is not None else 0

        tenant_license_pair_role = str(user.role or "user")
        if LICENSE_MANAGEMENT_AVAILABLE and pairing_role_for_tenant_license and tid_u is not None:
            tenant_license_pair_role = pairing_role_for_tenant_license(db, int(tid_u))

        return {
            "admin_notify_pending_count": admin_notify_pending,
            "user": {
                "id": user.id,
                "admin_ordinal": getattr(user, "admin_ordinal", None),
                "deletion_archive_mark": deletion_archive_mark,
                "deletion_email_before": deletion_email_before,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "workspace_entitlements": sorted(effective_workspace_kinds(user)),
                "workspace_ui_default": getattr(user, "workspace_ui_default", None),
                "tenant_id": user.tenant_id,
                "disk_usage_bytes": disk_u,
                "disk_usage_human": _format_bytes(disk_u),
                "disk_usage_note": (
                    "Součet souborů ve složce data/ přiřazených k tenantovi tohoto účtu (fotky vozidel, přílohy záznamů, "
                    "ORV skeny, PDF reporty/archivy, fotky servisních případů). Účty se stejným tenant_id mají stejnou "
                    "hodnotu. Nezahrnuje databázi ani sdílené dočasné soubory mimo tyto cesty."
                ),
                "ico": user.ico,
                "dic": user.dic,
                "phone": user.phone,
                "street": user.street,
                "street_number": user.street_number,
                "city": user.city,
                "zip": user.zip,
                "address_line": address_line,
                "city_line": city_line,
                "notify_email": bool(user.notify_email) if user.notify_email is not None else False,
                "notify_sms": bool(user.notify_sms) if user.notify_sms is not None else False,
                "notify_stk": bool(user.notify_stk) if user.notify_stk is not None else False,
                "notify_oil": bool(user.notify_oil) if user.notify_oil is not None else False,
                "notify_general": bool(user.notify_general) if user.notify_general is not None else False,
                "license_plan": license_plan,
                "license_plan_base": get_license_plan_base(license_plan) if get_license_plan_base else license_plan,
                "license_workspace_kind": (
                    get_license_plan_workspace_kind(license_plan)
                    if LICENSE_MANAGEMENT_AVAILABLE and get_license_plan_workspace_kind
                    else (
                        get_license_workspace_kind_for_role(user.role)
                        if get_license_workspace_kind_for_role
                        else ("service" if str(user.role or "").lower() == "service" else "user")
                    )
                ),
                "license_allowed_plans": (
                    get_allowed_license_plans_for_role(tenant_license_pair_role)
                    if get_allowed_license_plans_for_role
                    else ["free", "basic", "premium", "lifetime"]
                ),
                "license_status": license_status,
                "is_disabled": bool(getattr(user, "is_disabled", False)),
                "is_deleted": bool(getattr(user, "is_deleted", False)),
                "session_version": customer_session_version(user),
                "last_login_at": to_iso_datetime(getattr(user, "last_login_at", None)),
                "last_seen_at": to_iso_datetime(getattr(user, "last_seen_at", None)),
                "created_at": to_iso_datetime(user.created_at),
                "account_status": getattr(user, "account_status", None) or "active",
                "email_verified_at": to_iso_datetime(getattr(user, "email_verified_at", None)),
                "email_verification_label": ("verified" if getattr(user, "email_verified_at", None) else "pending"),
                "phone_e164": getattr(user, "phone_e164", None),
                "phone_verified_at": to_iso_datetime(getattr(user, "phone_verified_at", None)),
                "phone_status_label": (
                    "verified"
                    if getattr(user, "phone_verified_at", None)
                    else ("unverified" if getattr(user, "phone_e164", None) else "invalid")
                ),
                "registration_ip": getattr(user, "registration_ip", None),
                "registration_user_agent": getattr(user, "registration_user_agent", None),
                "registration_risk_flags": getattr(user, "registration_risk_flags", None),
            },
            "stats": {
                "vehicles_count": len(vehicles),
                "reminders_count": len(reminders),
                "reservations_count": len(reservations),
                "records_count": len(records),
                "license_limit": license_limit,
                "license_vehicle_count": license_vehicle_count,
            },
            "meta": {
                "last_ip_address": ip_history[0]["ip_address"] if ip_history else None,
                "last_location": ip_history[0].get("location_label") if ip_history else None,
                "last_activity_at": last_activity_at,
                "ip_history": ip_history,
            },
            "insight": {
                "license": {
                    "current_plan": (license_row.plan if license_row else license_plan) or "free",
                    "current_plan_base": (
                        get_license_plan_base((license_row.plan if license_row else license_plan) or "free")
                        if get_license_plan_base
                        else ((license_row.plan if license_row else license_plan) or "free")
                    ),
                    "workspace_kind": (
                        get_license_plan_workspace_kind((license_row.plan if license_row else license_plan) or "free")
                        if LICENSE_MANAGEMENT_AVAILABLE and get_license_plan_workspace_kind
                        else (
                            get_license_workspace_kind_for_role(user.role)
                            if get_license_workspace_kind_for_role
                            else ("service" if str(user.role or "").lower() == "service" else "user")
                        )
                    ),
                    "allowed_plans": (
                        get_allowed_license_plans_for_role(tenant_license_pair_role)
                        if get_allowed_license_plans_for_role
                        else ["free", "basic", "premium", "lifetime"]
                    ),
                    "status": (license_row.status if license_row else license_status) or "active",
                    "purchase_date": purchase_date,
                    "activation_date": activation_date,
                    "expiration_date": expiration_date,
                    "next_renewal_date": next_renewal_date,
                    "source_of_activation": source_of_activation,
                    "vehicles_limit": license_row.vehicles_limit if license_row else license_limit,
                },
                "payments_summary": {
                    "has_paid": has_paid,
                    "count": len(recent_payments),
                    "first_paid_at": first_paid_at,
                    "last_paid_at": latest_paid_at,
                    "count_live": live_payments_count,
                    "count_test": test_payments_count,
                    "live_paid_count": live_paid_count,
                    "test_paid_count": test_paid_count,
                    "failed_count": failed_payments_count,
                    "refund_count": refunded_payments_count,
                    "has_live_paid": live_paid_count > 0,
                    "has_test_paid": test_paid_count > 0,
                    "paid_counting_mode": "live_only" if not COUNT_TEST_PAYMENTS_AS_PAID else "live_and_test",
                    "provider": subscription_row.provider if subscription_row else None,
                },
                "payments": recent_payments,
                "presence": {
                    "online_status": "ONLINE" if is_online else "OFFLINE",
                    "last_seen_at": presence_last_seen or to_iso_datetime(getattr(user, "last_seen_at", None)),
                    "last_login_at": presence_last_login or to_iso_datetime(getattr(user, "last_login_at", None)),
                    "active_session_count": active_session_count,
                },
            },
            "panels": {
                "vehicles": vehicles,
                "reminders": reminders,
                "reservations": reservations,
                "records": records,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání detailu uživatele: {str(e)}")


@router.get("/users/{user_id}/admin-notify-history")
def get_user_admin_notify_history(
    user_id: int,
    limit: int = 200,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Historie změn účtu z adminu + stav odeslání e-mailem uživateli."""
    user = db.query(Customer).filter(Customer.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if not admin_change_table_exists(db):
        return {"items": [], "pending_count": 0, "user_email": user.email}
    lim = min(max(limit, 1), 500)
    rows = (
        db.query(AdminCustomerChangeEvent)
        .filter(AdminCustomerChangeEvent.customer_id == user_id)
        .order_by(AdminCustomerChangeEvent.created_at.desc(), AdminCustomerChangeEvent.id.desc())
        .limit(lim)
        .all()
    )
    pending_count = int(
        db.query(func.count())
        .select_from(AdminCustomerChangeEvent)
        .filter(
            AdminCustomerChangeEvent.customer_id == user_id,
            AdminCustomerChangeEvent.notified_at.is_(None),
        )
        .scalar()
        or 0
    )
    return {
        "items": [
            {
                "id": r.id,
                "change_key": r.change_key,
                "summary_line": r.summary_line,
                "detail_text": r.detail_text,
                "admin_email": r.admin_email,
                "created_at": to_iso_datetime(r.created_at),
                "notified_at": to_iso_datetime(r.notified_at) if r.notified_at else None,
                "notified_to_email": r.notified_to_email,
            }
            for r in rows
        ],
        "pending_count": pending_count,
        "user_email": user.email,
    }


@router.post("/users/{user_id}/admin-notify-send")
def post_user_admin_notify_send(
    user_id: int,
    payload: AdminNotifySendRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Odešle uživateli e-mail se souhrnem vybraných (dosud neodeslaných) změn."""
    if not admin_change_table_exists(db):
        raise HTTPException(status_code=503, detail="Tabulka historie změn neexistuje — spusťte migrace.")
    user = db.query(Customer).filter(Customer.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if customer_is_deleted(user):
        raise HTTPException(status_code=400, detail="Smazaný účet")
    ids = list(dict.fromkeys(int(x) for x in (payload.change_ids or [])))
    if not ids:
        raise HTTPException(status_code=400, detail="Vyberte alespoň jednu změnu")
    rows = (
        db.query(AdminCustomerChangeEvent)
        .filter(
            AdminCustomerChangeEvent.customer_id == user_id,
            AdminCustomerChangeEvent.id.in_(ids),
        )
        .all()
    )
    if len(rows) != len(ids):
        raise HTTPException(status_code=400, detail="Neplatné nebo cizí ID změny")
    if any(r.notified_at is not None for r in rows):
        raise HTTPException(status_code=400, detail="Některé položky již byly e-mailem odeslány")
    to_email = (user.email or "").strip().lower()
    if not to_email:
        raise HTTPException(status_code=400, detail="Uživatel nemá e-mail")
    lines = [r.summary_line for r in sorted(rows, key=lambda r: (r.created_at or datetime.min, r.id))]
    try:
        send_customer_change_notification_email(
            to_email=to_email,
            user_name=user.name,
            admin_email=email,
            lines=lines,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    mark_events_notified(db, rows=rows, to_email=to_email)
    db.commit()
    return {"message": f"E-mail byl odeslán na {to_email}", "sent_count": len(rows)}


def _customer_qualifies_for_admin_service_directory(db: Session, service: Customer) -> bool:
    """
    Účty v sekci „Servisy“: role=service, nebo developer_admin nad tenantem s workspace_route_kind=service
    (typicky stejní lidé jako v servisním režimu v aplikaci).
    """
    if customer_is_deleted(service):
        return False
    if service.role == "service":
        return True
    if service.role != "developer_admin":
        return False
    tenant = db.query(Tenant).filter(Tenant.id == service.tenant_id).first()
    return bool(tenant and str(tenant.workspace_route_kind or "").strip() == "service")


@router.get("/services", response_model=List[UserSummary])
def get_all_services(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí servisní účty evidované v aplikaci — role=service i developer_admin se servisním tenantem."""
    try:
        ensure_customer_account_state_schema(db)
        result = db.execute(text(f"""
            SELECT 
                c.id,
                c.email,
                c.name,
                c.role,
                c.tenant_id,
                c.city,
                c.phone,
                c.created_at,
                COALESCE(c.is_disabled, 0) as is_disabled,
                COALESCE(c.is_deleted, 0) as is_deleted,
                COALESCE(c.session_version, 0) as session_version,
                COALESCE(vehicle_counts.vehicles_count, 0) as vehicles_count
            FROM customers c
            LEFT JOIN tenants t ON t.id = c.tenant_id
            {_customer_vehicle_count_join_sql(customer_alias="c", join_alias="vehicle_counts")}
            WHERE COALESCE(c.is_deleted, 0) = 0
              AND (
                c.role = 'service'
                OR (c.role = 'developer_admin' AND COALESCE(t.workspace_route_kind, '') = 'service')
              )
            ORDER BY c.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})
        
        tenant_disk_map = _get_tenant_disk_usage_map(db)
        services = []
        for row in result:
            created_at = row[7]
            tid_sv = row[4]
            disk_sv = int(tenant_disk_map.get(int(tid_sv), 0)) if tid_sv is not None else 0
            services.append(UserSummary(
                id=row[0],
                email=row[1],
                name=row[2],
                role=row[3],
                tenant_id=row[4],
                city=row[5],
                phone=row[6],
                created_at=created_at,
                vehicles_count=int(row[11] or 0),
                is_disabled=bool(row[8]),
                is_deleted=bool(row[9]),
                session_version=int(row[10] or 0),
                disk_usage_bytes=disk_sv,
                disk_usage_human=_format_bytes(disk_sv),
            ))
        
        return services
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisů: {str(e)}")


@router.post("/services")
def create_service(
    service_data: ServiceCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového servisu"""
    try:
        acting_admin = get_customer_by_email(db, email)
        if not acting_admin:
            raise HTTPException(status_code=404, detail="Admin účet nenalezen")

        target_email = str(service_data.email).strip().lower()
        if service_data.tenant_id is not None:
            tenant_id = resolve_tenant_id_for_create(db, acting_admin, service_data.tenant_id)
        else:
            tenant_id = create_dedicated_tenant(
                db,
                owner_email=target_email,
                owner_name=service_data.name,
            ).id

        # Zkontrolovat, zda email již existuje
        existing = get_customer_by_email(db, target_email)
        if existing:
            raise HTTPException(status_code=400, detail="Servis s tímto emailem již existuje")
        
        # Hash hesla
        password_hash_value = hash_password(service_data.password)
        
        # Vytvořit servis
        new_service = Customer(
            tenant_id=tenant_id,
            email=target_email,
            name=service_data.name,
            password_hash=password_hash_value,
            role="service",
            city=service_data.city,
            phone=service_data.phone,
            ico=service_data.ico,
            partner_catalog_approved=True,
            created_at=datetime.utcnow()
        )
        db.add(new_service)
        db.flush()
        assign_admin_ordinal_if_missing(db, new_service)
        db.commit()
        db.refresh(new_service)

        ensure_default_license_for_tenant(db, new_service.tenant_id)
        
        return {
            "id": new_service.id,
            "email": new_service.email,
            "tenant_id": new_service.tenant_id,
            "message": "Servis byl vytvořen",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření servisu: {str(e)}")


@router.patch("/services/{service_id}")
def update_service(
    service_id: int,
    service_data: ServiceUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava servisu"""
    try:
        service = db.query(Customer).filter(Customer.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Servis nenalezen")
        
        if not _customer_qualifies_for_admin_service_directory(db, service):
            raise HTTPException(status_code=400, detail="Zadaný uživatel není servis v této evidenci.")
        
        # Aktualizovat pole
        if service_data.email is not None:
            new_email = str(service_data.email).strip().lower()
            existing = db.query(Customer).filter(
                func.lower(Customer.email) == new_email,
                Customer.id != service_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Servis s tímto emailem již existuje")
            service.email = new_email
            sync_vehicle_user_email_display_for_customer(db, service.id, new_email)
        
        if service_data.name is not None:
            service.name = service_data.name
        
        if service_data.city is not None:
            service.city = service_data.city
        
        if service_data.phone is not None:
            service.phone = service_data.phone
        
        if service_data.ico is not None:
            service.ico = service_data.ico
        
        if service_data.password is not None:
            service.password_hash = hash_password(service_data.password)
            increment_customer_session_version(service)

        if service_data.partner_catalog_approved is not None:
            service.partner_catalog_approved = bool(service_data.partner_catalog_approved)

        db.commit()
        return {"message": "Servis byl upraven"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě servisu: {str(e)}")


@router.delete("/services/{service_id}")
def delete_service(
    service_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Odstranění servisního účtu ze seznamu (soft-delete kvůli FK vazbám v aplikaci)."""
    try:
        actor = get_customer_by_email(db, email)
        service = db.query(Customer).filter(Customer.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Servis nenalezen")

        if actor and actor.id == service.id:
            raise HTTPException(status_code=400, detail="Nelze smazat účet, pod kterým jste přihlášeni.")

        if customer_is_deleted(service):
            return {"message": "Servis je již odstraněn ze seznamu.", "soft_deleted": True}

        if not _customer_qualifies_for_admin_service_directory(db, service):
            raise HTTPException(status_code=400, detail="Zadaný uživatel není servis v této evidenci.")

        vehicles_count = (
            db.query(func.count(func.distinct(VehicleOwnership.vehicle_id)))
            .filter(
                VehicleOwnership.customer_id == service.id,
                VehicleOwnership.is_active.is_(True),
            )
            .scalar()
            or 0
        )
        if vehicles_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Servis má přiřazeno {vehicles_count} vozidel. Nejprve změňte vlastníka nebo vozidla smažte.",
            )

        previous_email = (service.email or "").strip().lower()
        result = soft_delete_customer(db, service)
        if result.get("already"):
            return {"message": f"Servis {result.get('email')} je již odstraněný.", "soft_deleted": True}

        deleted_alias = result["deleted_alias"]
        db.commit()

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="service.delete",
            target_resource=f"service:{service_id}",
            parameters={
                "previous_email": previous_email,
                "deleted_alias": deleted_alias,
                "soft_deleted": True,
            },
            result="success",
            status_code=200,
        )

        return {
            "message": f"Servis {previous_email} byl odstraněn ze seznamu (soft-delete)",
            "soft_deleted": True,
            "deleted_alias_email": deleted_alias,
            "session_version": result.get("session_version"),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání servisu: {str(e)}")


@router.get("/service-registration-requests", response_model=List[ServiceRegistrationRequestItem])
def list_service_registration_requests(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Seznam žádostí o registraci servisního účtu.
    """
    try:
        query = db.query(ServiceRegistrationRequest)
        normalized_status = (status or "").strip().lower()
        if normalized_status:
            if normalized_status not in {"pending", "approved", "rejected"}:
                raise HTTPException(status_code=400, detail="Neplatný status. Použijte pending/approved/rejected.")
            query = query.filter(ServiceRegistrationRequest.status == normalized_status)

        requests = (
            query.order_by(ServiceRegistrationRequest.created_at.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
            .all()
        )

        return [
            ServiceRegistrationRequestItem(
                id=row.id,
                status=row.status,
                email=row.email,
                ico=row.ico,
                service_name=row.service_name,
                responsible_person=row.responsible_person,
                phone=row.phone,
                dic=row.dic,
                street=row.street,
                street_number=row.street_number,
                city=row.city,
                zip=row.zip,
                registration_purpose=row.registration_purpose,
                created_at=row.created_at,
                reviewed_at=row.reviewed_at,
                reviewed_by_customer_id=row.reviewed_by_customer_id,
                review_note=row.review_note,
                approved_customer_id=row.approved_customer_id,
                approved_tenant_id=row.approved_tenant_id,
            )
            for row in requests
        ]
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání žádostí: {str(e)}")


@router.post("/service-registration-requests/{request_id}/approve")
def approve_service_registration_request(
    request_id: int,
    payload: ServiceRegistrationDecision,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Schválí žádost o servisní registraci a vytvoří aktivní servisní účet.
    """
    try:
        reviewer = get_customer_by_email(db, email)
        if not reviewer:
            raise HTTPException(status_code=404, detail="Developer/Admin účet nebyl nalezen")

        req = db.query(ServiceRegistrationRequest).filter(ServiceRegistrationRequest.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Žádost nebyla nalezena")
        if req.status != "pending":
            raise HTTPException(status_code=400, detail=f"Žádost není ve stavu pending (aktuálně: {req.status})")

        existing_customer = get_customer_by_email(db, req.email)
        if existing_customer:
            raise HTTPException(status_code=400, detail="Účet s tímto emailem už existuje. Žádost nelze schválit.")

        normalized_ico = "".join(ch for ch in str(req.ico or "") if ch.isdigit())
        if normalized_ico:
            existing_service_same_ico = (
                db.query(Customer)
                .filter(
                    Customer.role == "service",
                    Customer.ico == normalized_ico,
                    func.lower(Customer.email) != req.email.strip().lower(),
                )
                .first()
            )
            if existing_service_same_ico:
                raise HTTPException(
                    status_code=400,
                    detail="Toto IČO je už použito u jiného servisního účtu. Schválení bylo zablokováno.",
                )

        dedicated_tenant = create_dedicated_tenant(
            db,
            owner_email=req.email,
            owner_name=req.service_name,
            workspace_route_kind="service",
        )

        from src.modules.vehicle_hub.registration_security import normalize_validate_phone_e164

        try:
            approved_phone_e164 = normalize_validate_phone_e164(str(req.phone or ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        approved_at = datetime.utcnow()
        new_service = Customer(
            tenant_id=dedicated_tenant.id,
            email=req.email.strip().lower(),
            password_hash=req.password_hash,
            name=req.service_name,
            ico=normalized_ico or req.ico,
            dic=req.dic,
            street=req.street,
            street_number=req.street_number,
            city=req.city,
            zip=req.zip,
            phone=req.phone,
            phone_e164=approved_phone_e164,
            role="service",
            partner_catalog_approved=True,
            created_at=approved_at,
            account_status="active",
            email_verified_at=approved_at,
        )
        db.add(new_service)
        db.flush()
        assign_admin_ordinal_if_missing(db, new_service)

        ensure_default_license_for_tenant(db, dedicated_tenant.id)

        req.status = "approved"
        req.reviewed_by_customer_id = reviewer.id
        req.reviewed_at = datetime.utcnow()
        req.review_note = (payload.review_note or "").strip() or "Schváleno developerem."
        req.approved_customer_id = new_service.id
        req.approved_tenant_id = dedicated_tenant.id

        db.commit()
        db.refresh(new_service)
        db.refresh(req)

        return {
            "message": "Žádost byla schválena a servisní účet vytvořen.",
            "request_id": req.id,
            "service_customer_id": new_service.id,
            "tenant_id": dedicated_tenant.id,
            "email": new_service.email,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při schvalování žádosti: {str(e)}")


@router.post("/service-registration-requests/{request_id}/reject")
def reject_service_registration_request(
    request_id: int,
    payload: ServiceRegistrationDecision,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Zamítne žádost o servisní registraci.
    """
    try:
        reviewer = get_customer_by_email(db, email)
        if not reviewer:
            raise HTTPException(status_code=404, detail="Developer/Admin účet nebyl nalezen")

        req = db.query(ServiceRegistrationRequest).filter(ServiceRegistrationRequest.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Žádost nebyla nalezena")
        if req.status != "pending":
            raise HTTPException(status_code=400, detail=f"Žádost není ve stavu pending (aktuálně: {req.status})")

        req.status = "rejected"
        req.reviewed_by_customer_id = reviewer.id
        req.reviewed_at = datetime.utcnow()
        req.review_note = (payload.review_note or "").strip() or "Žádost byla zamítnuta."
        req.approved_customer_id = None
        req.approved_tenant_id = None

        db.commit()
        db.refresh(req)

        return {
            "message": "Žádost byla zamítnuta.",
            "request_id": req.id,
            "status": req.status,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při zamítání žádosti: {str(e)}")


@router.get("/vehicles")
def get_all_vehicles(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech vozidel - pouze pro developer_admin"""
    try:
        result = db.execute(text(f"""
            SELECT 
                v.id,
                COALESCE(owner_customer.email, v.user_email) as user_email,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.created_at,
                COUNT(sr.id) as service_count,
                owner_customer.name as owner_name,
                owner_customer.id as owner_id,
                v.tenant_id
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            {_primary_owner_join_sql(vehicle_alias="v", selector_alias="gav_primary", ownership_alias="gav_ownership", owner_alias="owner_customer")}
            WHERE v.status != 'archived'
            GROUP BY v.id, owner_customer.email, v.user_email, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.created_at, owner_customer.name, owner_customer.id, v.tenant_id
            ORDER BY v.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})
        
        vehicles = []
        for row in result:
            created_at = row[8]
            vehicles.append({
                "id": row[0],
                "user_email": row[1],
                "nickname": row[2],
                "brand": row[3],
                "model": row[4],
                "year": row[5],
                "plate": row[6],
                "vin": row[7],
                "created_at": to_iso_datetime(created_at),
                "service_count": row[9] or 0,
                "owner_name": row[10],
                "owner_id": row[11],
                "tenant_id": row[12],
            })
        
        return vehicles
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {str(e)}")


@router.post("/vehicles")
def create_vehicle(
    vehicle_data: VehicleCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového vozidla"""
    try:
        actor = get_customer_by_email(db, email)
        target_email = str(vehicle_data.user_email).strip().lower()
        # Zkontrolovat, zda uživatel existuje
        user = get_customer_by_email(db, target_email)
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")

        if vehicle_data.tenant_id is not None and vehicle_data.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=400,
                detail=f"tenant_id vozidla ({vehicle_data.tenant_id}) neodpovídá tenantu vlastníka ({user.tenant_id})",
            )
        
        # Vytvořit vozidlo
        new_vehicle = Vehicle(
            tenant_id=user.tenant_id,
            user_email=user.email,
            nickname=vehicle_data.nickname,
            brand=vehicle_data.brand,
            model=vehicle_data.model,
            year=vehicle_data.year,
            plate=vehicle_data.plate,
            vin=vehicle_data.vin,
            created_at=datetime.utcnow()
        )
        db.add(new_vehicle)
        db.flush()
        _reassign_vehicle_primary_owner(
            db,
            vehicle=new_vehicle,
            owner=user,
            assigned_by_customer_id=actor.id if actor else user.id,
        )
        db.commit()
        db.refresh(new_vehicle)
        if admin_change_table_exists(db):
            lbl = _admin_vehicle_short_label(new_vehicle)
            record_admin_customer_change(
                db,
                customer_id=user.id,
                admin_email=email,
                change_key="vehicle.created",
                summary_line=f"Přidáno vozidlo „{lbl}“",
                detail_text=f"ID vozidla v systému: {new_vehicle.id}",
            )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="vehicle.create",
            target_resource=f"vehicle:{new_vehicle.id}",
            parameters={
                "vehicle_id": new_vehicle.id,
                "tenant_id": new_vehicle.tenant_id,
                "owner_customer_id": user.id,
                "owner_email": user.email,
            },
            result="success",
            status_code=200,
        )
        
        return {"id": new_vehicle.id, "tenant_id": new_vehicle.tenant_id, "message": "Vozidlo bylo vytvořeno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření vozidla: {str(e)}")


@router.patch("/vehicles/{vehicle_id}")
def update_vehicle(
    vehicle_id: int,
    vehicle_data: VehicleUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava vozidla"""
    try:
        actor = get_customer_by_email(db, email)
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

        old_owner = get_primary_vehicle_owner(db, vehicle)
        old_owner_id = int(old_owner.id) if old_owner else None
        old_snapshot = (
            vehicle.nickname,
            vehicle.brand,
            vehicle.model,
            vehicle.year,
            vehicle.plate,
            vehicle.vin,
        )
        
        # Aktualizovat pole
        if vehicle_data.user_email is not None:
            target_email = str(vehicle_data.user_email).strip().lower()
            user = get_customer_by_email(db, target_email)
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            _reassign_vehicle_primary_owner(
                db,
                vehicle=vehicle,
                owner=user,
                assigned_by_customer_id=actor.id if actor else user.id,
            )
        
        if vehicle_data.nickname is not None:
            vehicle.nickname = vehicle_data.nickname
        
        if vehicle_data.brand is not None:
            vehicle.brand = vehicle_data.brand
        
        if vehicle_data.model is not None:
            vehicle.model = vehicle_data.model
        
        if vehicle_data.year is not None:
            vehicle.year = vehicle_data.year
        
        if vehicle_data.plate is not None:
            vehicle.plate = vehicle_data.plate
        
        if vehicle_data.vin is not None:
            vehicle.vin = vehicle_data.vin
        
        db.commit()
        db.refresh(vehicle)
        primary_owner = get_primary_vehicle_owner(db, vehicle)
        new_owner_id = int(primary_owner.id) if primary_owner else None
        new_snapshot = (
            vehicle.nickname,
            vehicle.brand,
            vehicle.model,
            vehicle.year,
            vehicle.plate,
            vehicle.vin,
        )
        if admin_change_table_exists(db):
            lbl = _admin_vehicle_short_label(vehicle)
            if vehicle_data.user_email is not None and old_owner_id != new_owner_id:
                if old_owner_id:
                    record_admin_customer_change(
                        db,
                        customer_id=old_owner_id,
                        admin_email=email,
                        change_key="vehicle.transferred_from",
                        summary_line=f"Vozidlo „{lbl}“ bylo převedeno na jiného uživatele",
                    )
                if new_owner_id:
                    record_admin_customer_change(
                        db,
                        customer_id=new_owner_id,
                        admin_email=email,
                        change_key="vehicle.transferred_to",
                        summary_line=f"Bylo vám přiřazeno vozidlo „{lbl}“",
                    )
            elif new_owner_id and old_snapshot != new_snapshot:
                record_admin_customer_change(
                    db,
                    customer_id=new_owner_id,
                    admin_email=email,
                    change_key="vehicle.updated",
                    summary_line=f"Upraveno vozidlo „{lbl}“",
                    detail_text="Administrátor změnil údaje vozidla (název, značka, model, rok, SPZ nebo VIN).",
                )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="vehicle.update",
            target_resource=f"vehicle:{vehicle.id}",
            parameters={
                "vehicle_id": vehicle.id,
                "tenant_id": vehicle.tenant_id,
                "owner_customer_id": primary_owner.id if primary_owner else None,
                "owner_email": primary_owner.email if primary_owner else None,
            },
            result="success",
            status_code=200,
        )
        return {"message": "Vozidlo bylo upraveno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě vozidla: {str(e)}")


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání vozidla"""
    try:
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        primary_owner = get_primary_vehicle_owner(db, vehicle)
        owner_id = int(primary_owner.id) if primary_owner else None
        vlabel = _admin_vehicle_short_label(vehicle)
        tenant_id = vehicle.tenant_id
        vehicle_audit = {
            "vehicle_id": vehicle_id,
            "label": vlabel,
            "vin": vehicle.vin,
            "plate": vehicle.plate,
            "nickname": vehicle.nickname,
            "brand": vehicle.brand,
            "model": vehicle.model,
            "owner_email": primary_owner.email if primary_owner else None,
            "recoverable_via_app": False,
            "note": "Tvrdé mazání včetně závislostí — obnova pouze ze zálohy databáze.",
        }
        dependency_counts = _delete_vehicle_dependencies_for_admin(db, vehicle_id)
        db.delete(vehicle)
        db.commit()
        if admin_change_table_exists(db) and owner_id:
            record_admin_customer_change(
                db,
                customer_id=owner_id,
                admin_email=email,
                change_key="vehicle.deleted",
                summary_line=f"Smazáno vozidlo „{vlabel}“",
                detail_text=f"ID vozidla: {vehicle_id}",
            )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="vehicle.delete",
            target_resource=f"vehicle:{vehicle_id}",
            parameters={
                "vehicle_id": vehicle_id,
                "tenant_id": tenant_id,
                "owner_customer_id": primary_owner.id if primary_owner else None,
                "owner_email": primary_owner.email if primary_owner else None,
                "deleted_dependencies": dependency_counts,
                "vehicle_snapshot": vehicle_audit,
            },
            result="success",
            status_code=200,
        )
        
        return {"message": "Vozidlo bylo smazáno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání vozidla: {str(e)}")


def _admin_deleted_service_records_response(db: Session, *, limit: int, offset: int) -> dict[str, Any]:
    """Společná datová část pro archivované servisní záznamy (obnova)."""
    lim = min(max(limit, 1), 300)
    off = max(0, offset)
    pairs = (
        db.query(ServiceRecord, Vehicle)
        .outerjoin(Vehicle, Vehicle.id == ServiceRecord.vehicle_id)
        .filter(ServiceRecord.is_deleted.is_(True))
        .order_by(ServiceRecord.deleted_at.desc(), ServiceRecord.id.desc())
        .offset(off)
        .limit(lim)
        .all()
    )
    customer_ids = {int(r.user_id) for r, _v in pairs if r.user_id}
    customers_by_id: dict[int, Customer] = {}
    if customer_ids:
        rows = db.query(Customer).filter(Customer.id.in_(customer_ids)).all()
        customers_by_id = {int(c.id): c for c in rows}

    items = []
    for r, v in pairs:
        uid = int(r.user_id) if r.user_id else None
        cust = customers_by_id.get(uid) if uid else None
        vl = _admin_vehicle_short_label(v) if v else f"ID {r.vehicle_id}"
        snap = service_record_audit_snapshot(r)
        items.append(
            {
                "record_id": r.id,
                "tenant_id": r.tenant_id,
                "vehicle_id": r.vehicle_id,
                "vehicle_label": vl,
                "user_id": r.user_id,
                "user_email": (cust.email if cust else None),
                "performed_at": to_iso_datetime(r.performed_at),
                "deleted_at": to_iso_datetime(r.deleted_at),
                "deletion_reason": r.deletion_reason,
                "description_preview": ((r.description or "")[:280] + "…")
                if len(r.description or "") > 280
                else (r.description or ""),
                "mileage": r.mileage,
                "category": r.category,
                "record_snapshot": snap,
            }
        )

    total = db.query(func.count(ServiceRecord.id)).filter(ServiceRecord.is_deleted.is_(True)).scalar() or 0
    return {"items": items, "total": int(total), "limit": lim, "offset": off}


@router.get("/archived-service-records")
def list_archived_service_records_for_restore(
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Archivované (soft-smazané) servisní záznamy pro obnovu v adminu.
    Dedikovaná URL mimo ``/records`` kvůli proxy/cache a starším workerům bez query ``deleted_only``.
    """
    return _admin_deleted_service_records_response(db, limit=limit, offset=offset)


@router.get("/service-invoices")
def admin_service_invoices_list(
    vehicle_id: Optional[int] = Query(None),
    vin: Optional[str] = Query(None, max_length=32),
    service_id: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="draft | issued | cancelled"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Read-only přehled servisních faktur (JOIN vozidlo kvůli VIN / filtrům)."""
    if not inspect(db.bind).has_table("service_invoices"):
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    def _apply_filters(qs):
        if vehicle_id is not None:
            qs = qs.filter(ServiceInvoice.vehicle_id == int(vehicle_id))
        if vin:
            qs = qs.filter(Vehicle.vin == str(vin).strip().upper())
        if service_id is not None:
            qs = qs.filter(ServiceInvoice.service_id == int(service_id))
        if customer_id is not None:
            qs = qs.filter(ServiceInvoice.customer_id == int(customer_id))
        if status:
            qs = qs.filter(ServiceInvoice.status == str(status).strip().lower())
        ref_ts = func.coalesce(ServiceInvoice.issued_at, ServiceInvoice.created_at)
        if date_from is not None:
            qs = qs.filter(ref_ts >= date_from)
        if date_to is not None:
            qs = qs.filter(ref_ts <= date_to)
        return qs

    cq = (
        db.query(func.count(func.distinct(ServiceInvoice.id)))
        .select_from(ServiceInvoice)
        .outerjoin(Vehicle, Vehicle.id == ServiceInvoice.vehicle_id)
    )
    total = int(_apply_filters(cq).scalar() or 0)

    q = db.query(ServiceInvoice, Vehicle).outerjoin(Vehicle, Vehicle.id == ServiceInvoice.vehicle_id)
    q = _apply_filters(q)
    rows = (
        q.order_by(ServiceInvoice.id.desc())
        .offset(int(offset))
        .limit(int(limit))
        .all()
    )
    items: List[Dict[str, Any]] = []
    for inv, veh in rows:
        items.append(
            {
                "invoice_id": int(inv.id),
                "invoice_number": inv.invoice_number,
                "status": inv.status,
                "vehicle_id": int(inv.vehicle_id) if inv.vehicle_id is not None else None,
                "vin": getattr(veh, "vin", None) if veh else None,
                "service_id": int(inv.service_id),
                "customer_id": int(inv.customer_id),
                "total": float(inv.total) if inv.total is not None else 0.0,
                "issued_at": to_iso_datetime(inv.issued_at),
                "service_record_id": int(inv.service_record_id) if inv.service_record_id is not None else None,
                "work_order_id": int(inv.work_order_id) if inv.work_order_id is not None else None,
                "created_at": to_iso_datetime(inv.created_at),
            }
        )

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/records")
def get_all_records(
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[int] = None,
    vehicle_id: Optional[int] = None,
    deleted_only: bool = Query(
        False,
        description="Vrátí archivované (soft-deleted) záznamy určené k obnově. Použijte místo /records/deleted pokud proxy vrací 405.",
    ),
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Vrátí kompletní seznam všech servisních záznamů
    Dostupné jen pro developer_admin
    """
    try:
        if deleted_only:
            try:
                return _admin_deleted_service_records_response(db, limit=limit, offset=offset)
            except Exception as inner_exc:
                import traceback
                traceback.print_exc()
                return {
                    "items": [],
                    "total": 0,
                    "limit": limit,
                    "offset": offset,
                    "error": f"Chyba při načítání archivovaných záznamů: {str(inner_exc)}",
                }

        query = """
            SELECT 
                sr.id,
                sr.vehicle_id,
                sr.user_id,
                sr.performed_at,
                sr.mileage,
                sr.description,
                sr.price,
                sr.note,
                sr.category,
                sr.performed_at as created_at,
                v.nickname as vehicle_nickname,
                v.brand as vehicle_brand,
                v.model as vehicle_model,
                v.plate as vehicle_plate,
                c.email as user_email,
                c.name as user_name
            FROM service_records sr
            LEFT JOIN vehicles v ON v.id = sr.vehicle_id
            LEFT JOIN customers c ON c.id = sr.user_id
            WHERE COALESCE(sr.is_deleted, 0) = 0
        """
        params = {}
        
        if user_id:
            query += " AND sr.user_id = :user_id"
            params["user_id"] = user_id
        
        if vehicle_id:
            query += " AND sr.vehicle_id = :vehicle_id"
            params["vehicle_id"] = vehicle_id
        
        query += " ORDER BY sr.performed_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        result = db.execute(text(query), params)
        
        records = []
        for row in result:
            performed_at = row[3]
            created_at = row[9]
            records.append({
                "id": row[0],
                "vehicle_id": row[1],
                "user_id": row[2],
                "performed_at": to_iso_datetime(performed_at),
                "mileage": row[4],
                "description": row[5],
                "price": row[6],
                "note": row[7],
                "category": row[8],
                "created_at": to_iso_datetime(created_at),
                "vehicle_nickname": row[10],
                "vehicle_brand": row[11],
                "vehicle_model": row[12],
                "vehicle_plate": row[13],
                "user_email": row[14],
                "user_name": row[15]
            })
        
        # Celkový počet (bez archivovaných záznamů — ty jsou v GET /records/deleted)
        count_query = "SELECT COUNT(*) FROM service_records WHERE COALESCE(is_deleted, 0) = 0"
        count_params = {}
        if user_id:
            count_query += " AND user_id = :user_id"
            count_params["user_id"] = user_id
        if vehicle_id:
            count_query += " AND vehicle_id = :vehicle_id"
            count_params["vehicle_id"] = vehicle_id
        
        total_count = safe_count_query(db, count_query, count_params)
        
        return {
            "records": records,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "records": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Chyba při načítání záznamů: {str(e)}"
        }


@router.get("/records/deleted")
def list_deleted_service_records(
    limit: int = 100,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Archivované (soft-deleted) servisní záznamy — alias; preferujte GET /records?deleted_only=true kvůli proxy."""
    return _admin_deleted_service_records_response(db, limit=limit, offset=offset)


@router.get("/audit")
def get_audit_log(
    limit: int = 50,
    offset: int = 0,
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    actor: Optional[str] = None,
    entity_id: Optional[int] = None,
    severity: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    export: Optional[str] = None,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """
    Vrátí audit log pro admin UI.
    Primárně čte append-only audit_log, fallback je starší syntetický přehled.
    Dostupné jen pro developer_admin
    """
    try:
        if inspect(db.bind).has_table("audit_log"):
            global_query = db.query(GlobalAuditLog)

            if entity_type:
                global_query = global_query.filter(GlobalAuditLog.entity_type == entity_type)
            if action:
                global_query = global_query.filter(GlobalAuditLog.action == action)
            if entity_id is not None:
                global_query = global_query.filter(GlobalAuditLog.entity_id == entity_id)
            if actor:
                like = f"%{actor.strip()}%"
                global_query = global_query.filter(
                    (GlobalAuditLog.actor_role.ilike(like))
                    | (GlobalAuditLog.actor_type.ilike(like))
                    | (GlobalAuditLog.ip.ilike(like))
                )
            if date_from:
                global_query = global_query.filter(GlobalAuditLog.created_at >= date_from)
            if date_to:
                global_query = global_query.filter(GlobalAuditLog.created_at <= date_to)

            rows = (
                global_query
                .order_by(GlobalAuditLog.created_at.desc(), GlobalAuditLog.id.desc())
                .offset(max(offset, 0))
                .limit(min(max(limit, 1), 500))
                .all()
            )
            logs = []
            for row in rows:
                metadata_text = ""
                if getattr(row, "metadata_json", None):
                    metadata_text = str(row.metadata_json)
                    if len(metadata_text) > 240:
                        metadata_text = metadata_text[:237] + "..."
                row_severity = _audit_severity(row.action, row.metadata_json)
                if severity and row_severity != severity:
                    continue
                logs.append({
                    "id": row.id,
                    "timestamp": to_iso_datetime(row.created_at),
                    "actor_email": None,
                    "actor_user_id": row.actor_user_id,
                    "actor_role": row.actor_role,
                    "actor_type": row.actor_type,
                    "ip": row.ip,
                    "action": row.action,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "details": metadata_text,
                    "severity": row_severity,
                    "source_project": "audit_log",
                    "tenant_id": row.tenant_id,
                    "metadata_json": row.metadata_json,
                })

            if str(export or "").lower() == "csv":
                output = io.StringIO()
                writer = csv.DictWriter(
                    output,
                    fieldnames=["id", "timestamp", "severity", "actor_email", "actor_user_id", "actor_role", "action", "entity_type", "entity_id", "tenant_id", "ip", "details"],
                )
                writer.writeheader()
                for item in logs:
                    writer.writerow({key: item.get(key) for key in writer.fieldnames})
                return Response(
                    content=output.getvalue(),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=admin-audit-log.csv"},
                )

            return {
                "logs": logs,
                "total": len(logs),
                "limit": limit,
                "offset": offset,
                "source": "audit_log",
            }

        # Kombinace reservations a reminders jako "audit log"
        # SQLite nepodporuje CONCAT, použít || pro concatenaci
        query = """
            SELECT 
                'reservation' as type,
                r.id,
                r.created_at as timestamp,
                c.email as actor_email,
                'CREATE_RESERVATION' as action,
                r.vehicle_id as entity_id,
                r.service_id as related_id,
                ('Rezervace pro vozidlo ' || COALESCE(v.nickname, '?')) as details
            FROM reservations r
            LEFT JOIN vehicles v ON v.id = r.vehicle_id
            LEFT JOIN customers c ON c.id = r.customer_id
            WHERE 1=1
            
            UNION ALL
            
            SELECT 
                'reminder' as type,
                rem.id,
                rem.created_at as timestamp,
                c.email as actor_email,
                'CREATE_REMINDER' as action,
                rem.vehicle_id as entity_id,
                NULL as related_id,
                rem.text as details
            FROM reminders rem
            LEFT JOIN customers c ON c.id = rem.customer_id
            WHERE 1=1
            
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """
        
        result = db.execute(text(query), {"limit": limit, "offset": offset})
        
        logs = []
        for row in result:
            timestamp = row[2]
            logs.append({
                "id": row[1],
                "timestamp": to_iso_datetime(timestamp),
                "actor_email": row[3],
                "action": row[4],
                "entity_type": row[0],
                "entity_id": row[5],
                "details": row[7],
                "source_project": "legacy_union",
            })
        
        return {
            "logs": logs,
            "total": len(logs),
            "limit": limit,
            "offset": offset,
            "source": "legacy_union",
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "logs": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Chyba při načítání audit logu: {str(e)}"
        }


@router.post("/records")
def create_record(
    record_data: RecordCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového servisního záznamu"""
    try:
        # Zkontrolovat, zda vozidlo existuje
        vehicle = db.query(Vehicle).filter(Vehicle.id == record_data.vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        resolved_user_id = record_data.user_id

        # Pokud je zadán user_id, zkontrolovat, zda existuje
        if resolved_user_id:
            user = db.query(Customer).filter(Customer.id == resolved_user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            if user.tenant_id != vehicle.tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail="Uživatel záznamu musí být ze stejného tenantu jako vozidlo",
                )
        else:
            # Pokud není zadán user_id, použít aktuálního admina
            current_user = get_customer_by_email(db, email)
            if current_user and current_user.tenant_id == vehicle.tenant_id:
                resolved_user_id = current_user.id
            else:
                resolved_user_id = None
        
        # Vytvořit záznam
        new_record = ServiceRecord(
            tenant_id=vehicle.tenant_id,
            vehicle_id=record_data.vehicle_id,
            user_id=resolved_user_id,
            performed_at=record_data.performed_at,
            mileage=record_data.mileage,
            description=record_data.description,
            price=record_data.price,
            category=record_data.category,
            note=record_data.note
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        nid = _notify_customer_id_for_record(db, new_record)
        if admin_change_table_exists(db) and nid:
            v = db.query(Vehicle).filter(Vehicle.id == new_record.vehicle_id).first()
            vl = _admin_vehicle_short_label(v) if v else f"ID {new_record.vehicle_id}"
            record_admin_customer_change(
                db,
                customer_id=nid,
                admin_email=email,
                change_key="service_record.created",
                summary_line=f"Přidán servisní záznam k vozidlu „{vl}“",
                detail_text=(record_data.description or "")[:800],
                payload={"record_id": new_record.id, "mileage": record_data.mileage},
            )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="record.create",
            target_resource=f"record:{new_record.id}",
            parameters={
                "record_id": new_record.id,
                "tenant_id": new_record.tenant_id,
                "vehicle_id": new_record.vehicle_id,
                "user_id": new_record.user_id,
            },
            status_code=201,
        )
        
        return {"id": new_record.id, "tenant_id": new_record.tenant_id, "message": "Servisní záznam byl vytvořen"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření záznamu: {str(e)}")


@router.patch("/records/{record_id}")
def update_record(
    record_id: int,
    record_data: RecordUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava servisního záznamu"""
    try:
        record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Záznam nenalezen")
        if bool(getattr(record, "is_deleted", False)):
            raise HTTPException(
                status_code=409,
                detail="Archivovaný servisní záznam nelze upravit — použijte nejdříve obnovu v sekci Záznamy.",
            )

        snap_b = {
            "vehicle_id": record.vehicle_id,
            "user_id": record.user_id,
            "performed_at": record.performed_at,
            "mileage": record.mileage,
            "description": record.description,
            "price": record.price,
            "category": record.category,
            "note": record.note,
        }
        
        # Aktualizovat pole
        if record_data.vehicle_id is not None:
            vehicle = db.query(Vehicle).filter(Vehicle.id == record_data.vehicle_id).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            record.vehicle_id = record_data.vehicle_id
            record.tenant_id = vehicle.tenant_id
        
        if record_data.user_id is not None:
            user = db.query(Customer).filter(Customer.id == record_data.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            vehicle_scope = db.query(Vehicle).filter(Vehicle.id == record.vehicle_id).first()
            if not vehicle_scope:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            if int(user.tenant_id or 0) != int(vehicle_scope.tenant_id or 0):
                raise HTTPException(
                    status_code=400,
                    detail="Uživatel záznamu musí patřit ke stejnému tenantu jako vozidlo záznamu",
                )
            record.user_id = record_data.user_id
            record.tenant_id = vehicle_scope.tenant_id
        
        if record_data.performed_at is not None:
            record.performed_at = record_data.performed_at
        
        if record_data.mileage is not None:
            record.mileage = record_data.mileage
        
        if record_data.description is not None:
            record.description = record_data.description
        
        if record_data.price is not None:
            record.price = record_data.price
        
        if record_data.category is not None:
            record.category = record_data.category
        
        if record_data.note is not None:
            record.note = record_data.note
        
        db.commit()
        db.refresh(record)
        snap_a = {
            "vehicle_id": record.vehicle_id,
            "user_id": record.user_id,
            "performed_at": record.performed_at,
            "mileage": record.mileage,
            "description": record.description,
            "price": record.price,
            "category": record.category,
            "note": record.note,
        }
        if admin_change_table_exists(db) and snap_b != snap_a:
            nid = _notify_customer_id_for_record(db, record)
            if nid:
                parts: List[str] = []
                if snap_b.get("mileage") != snap_a.get("mileage"):
                    parts.append(
                        f"Nájezd (km): {snap_b.get('mileage')} → {snap_a.get('mileage')}"
                    )
                if snap_b.get("description") != snap_a.get("description"):
                    parts.append("Popis záznamu byl upraven.")
                if snap_b.get("performed_at") != snap_a.get("performed_at"):
                    parts.append("Datum provedení bylo změněno.")
                if snap_b.get("price") != snap_a.get("price"):
                    parts.append(f"Cena: {snap_b.get('price')} → {snap_a.get('price')}")
                if snap_b.get("category") != snap_a.get("category"):
                    parts.append(f"Kategorie: {snap_b.get('category')} → {snap_a.get('category')}")
                if snap_b.get("note") != snap_a.get("note"):
                    parts.append("Poznámka k záznamu byla upravena.")
                if snap_b.get("vehicle_id") != snap_a.get("vehicle_id"):
                    parts.append("Záznam byl přeřazen na jiné vozidlo.")
                if snap_b.get("user_id") != snap_a.get("user_id"):
                    parts.append("U vazby záznamu na uživatele došlo ke změně.")
                if parts:
                    v = db.query(Vehicle).filter(Vehicle.id == record.vehicle_id).first()
                    vl = _admin_vehicle_short_label(v) if v else f"ID {record.vehicle_id}"
                    record_admin_customer_change(
                        db,
                        customer_id=nid,
                        admin_email=email,
                        change_key="service_record.updated",
                        summary_line=f"Úprava servisního záznamu u vozidla „{vl}“",
                        detail_text="\n".join(parts),
                        payload={"record_id": record.id},
                    )
                    db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="record.update",
            target_resource=f"record:{record.id}",
            parameters={
                "record_id": record.id,
                "tenant_id": record.tenant_id,
                "vehicle_id": record.vehicle_id,
                "user_id": record.user_id,
            },
            status_code=200,
        )
        return {"message": "Záznam byl upraven"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě záznamu: {str(e)}")


@router.delete("/records/{record_id}")
def delete_record(
    record_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Archivuje servisní záznam (soft-delete). Obnova přes POST /records/{record_id}/restore."""
    try:
        record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Záznam nenalezen")
        if bool(getattr(record, "is_deleted", False)):
            return {"message": "Záznam je již archivovaný", "recoverable": True}

        nid = _notify_customer_id_for_record(db, record)
        v = db.query(Vehicle).filter(Vehicle.id == record.vehicle_id).first()
        vl = _admin_vehicle_short_label(v) if v else f"ID {record.vehicle_id}"
        desc_snip = (record.description or "")[:400] or None

        before_snapshot = service_record_audit_snapshot(record)
        record.is_deleted = True
        record.deleted_at = datetime.utcnow()
        record.deleted_by_user_id = None
        record.deletion_reason = "admin_developer_delete"
        after_snapshot = service_record_audit_snapshot(record)
        prev_json, _ = snapshot_json_and_hash(before_snapshot)
        new_json, snap_hash = snapshot_json_and_hash(after_snapshot)
        record.snapshot_hash = snap_hash

        db.add(
            ServiceRecordAuditLog(
                tenant_id=record.tenant_id,
                service_record_id=record.id,
                vehicle_id=record.vehicle_id,
                changed_by_user_id=None,
                action="delete",
                previous_snapshot_json=prev_json,
                new_snapshot_json=new_json,
                snapshot_hash=snap_hash,
                change_reason="admin_developer_delete",
            )
        )
        write_global_audit_log(
            db,
            entity_type="service_record",
            entity_id=int(record_id),
            action="service_record_archive_admin",
            actor_user_id=None,
            actor_role="developer_admin",
            tenant_id=int(record.tenant_id),
            metadata={
                "vehicle_id": int(record.vehicle_id),
                "admin_email": email,
                "cause": "admin_api_archive",
                "recoverable": True,
            },
        )
        db.commit()

        if admin_change_table_exists(db) and nid:
            record_admin_customer_change(
                db,
                customer_id=nid,
                admin_email=email,
                change_key="service_record.archived",
                summary_line=f"Archivován servisní záznam u vozidla „{vl}“",
                detail_text=desc_snip,
                payload={"record_id": record_id},
            )
            db.commit()

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="record.delete",
            target_resource=f"record:{record_id}",
            parameters={
                "record_id": record.id,
                "tenant_id": record.tenant_id,
                "vehicle_id": record.vehicle_id,
                "user_id": record.user_id,
                "cause": "developer_admin_soft_archive",
                "recoverable": True,
                "record_snapshot_before": before_snapshot,
            },
            status_code=200,
        )

        return {
            "message": "Servisní záznam byl archivován (lze obnovit v sekci Záznamy / archivované záznamy).",
            "recoverable": True,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při archivaci záznamu: {str(e)}")


@router.post("/records/{record_id}/restore")
def restore_deleted_service_record(
    record_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Obnoví archivovaný servisní záznam."""
    try:
        record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Záznam nenalezen")
        if not bool(getattr(record, "is_deleted", False)):
            return {"message": "Záznam není archivovaný"}

        nid = _notify_customer_id_for_record(db, record)
        v = db.query(Vehicle).filter(Vehicle.id == record.vehicle_id).first()
        vl = _admin_vehicle_short_label(v) if v else f"ID {record.vehicle_id}"

        before_snapshot = service_record_audit_snapshot(record)
        record.is_deleted = False
        record.deleted_at = None
        record.deleted_by_user_id = None
        record.deletion_reason = None
        after_snapshot = service_record_audit_snapshot(record)
        prev_json, _ = snapshot_json_and_hash(before_snapshot)
        new_json, snap_hash = snapshot_json_and_hash(after_snapshot)
        record.snapshot_hash = snap_hash

        db.add(
            ServiceRecordAuditLog(
                tenant_id=record.tenant_id,
                service_record_id=record.id,
                vehicle_id=record.vehicle_id,
                changed_by_user_id=None,
                action="restore",
                previous_snapshot_json=prev_json,
                new_snapshot_json=new_json,
                snapshot_hash=snap_hash,
                change_reason="admin_developer_restore",
            )
        )
        write_global_audit_log(
            db,
            entity_type="service_record",
            entity_id=int(record_id),
            action="service_record_restore_admin",
            actor_user_id=None,
            actor_role="developer_admin",
            tenant_id=int(record.tenant_id),
            metadata={"vehicle_id": int(record.vehicle_id), "admin_email": email},
        )
        db.commit()

        if admin_change_table_exists(db) and nid:
            record_admin_customer_change(
                db,
                customer_id=nid,
                admin_email=email,
                change_key="service_record.restored",
                summary_line=f"Obnoven servisní záznam u vozidla „{vl}“",
                payload={"record_id": record_id},
            )
            db.commit()

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="record.restore",
            target_resource=f"record:{record_id}",
            parameters={
                "record_id": record.id,
                "tenant_id": record.tenant_id,
                "vehicle_id": record.vehicle_id,
                "cause": "developer_admin_restore",
            },
            status_code=200,
        )

        return {"message": "Servisní záznam byl obnoven"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při obnově záznamu: {str(e)}")


# ============= REMINDERS CRUD (ADMIN) =============

@router.patch("/reminders/{reminder_id}")
def update_reminder_admin(
    reminder_id: int,
    reminder_data: ReminderUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava připomínky administrátorem."""
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena")

        cust_id = int(reminder.customer_id)
        snap_b = {
            "vehicle_id": reminder.vehicle_id,
            "type": reminder.type,
            "text": reminder.text,
            "due_date": reminder.due_date,
            "is_manual": reminder.is_manual,
            "is_completed": reminder.is_completed,
        }

        if reminder_data.vehicle_id is not None:
            if reminder_data.vehicle_id <= 0:
                raise HTTPException(status_code=400, detail="vehicle_id musí být kladné číslo")
            vehicle = db.query(Vehicle).filter(Vehicle.id == reminder_data.vehicle_id).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            reminder.vehicle_id = reminder_data.vehicle_id

        if reminder_data.type is not None:
            reminder.type = reminder_data.type.strip().upper() if reminder_data.type else reminder.type
        if reminder_data.text is not None:
            reminder.text = reminder_data.text
        if reminder_data.due_date is not None:
            reminder.due_date = reminder_data.due_date
        if reminder_data.is_manual is not None:
            reminder.is_manual = reminder_data.is_manual
        if reminder_data.is_completed is not None:
            apply_reminder_completion_update(reminder, reminder_data.is_completed)

        db.commit()
        db.refresh(reminder)
        snap_a = {
            "vehicle_id": reminder.vehicle_id,
            "type": reminder.type,
            "text": reminder.text,
            "due_date": reminder.due_date,
            "is_manual": reminder.is_manual,
            "is_completed": reminder.is_completed,
        }
        if admin_change_table_exists(db) and snap_b != snap_a:
            record_admin_customer_change(
                db,
                customer_id=cust_id,
                admin_email=email,
                change_key="reminder.updated",
                summary_line="Připomínka byla upravena administrátorem",
                detail_text=f"ID připomínky: {reminder.id}",
                payload={"before": snap_b, "after": snap_a},
            )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="reminder.update",
            target_resource=f"reminder:{reminder.id}",
            parameters={
                "reminder_id": reminder.id,
                "tenant_id": reminder.tenant_id,
                "customer_id": reminder.customer_id,
                "vehicle_id": reminder.vehicle_id,
                "is_completed": reminder.is_completed,
            },
            status_code=200,
        )
        return {"message": "Připomínka byla upravena adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě připomínky: {str(e)}")


@router.delete("/reminders/{reminder_id}")
def delete_reminder_admin(
    reminder_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání připomínky administrátorem."""
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena")
        cust_id = int(reminder.customer_id)
        audit_payload = {
            "reminder_id": reminder.id,
            "tenant_id": reminder.tenant_id,
            "customer_id": reminder.customer_id,
            "vehicle_id": reminder.vehicle_id,
        }

        db.delete(reminder)
        db.commit()
        if admin_change_table_exists(db):
            record_admin_customer_change(
                db,
                customer_id=cust_id,
                admin_email=email,
                change_key="reminder.deleted",
                summary_line="Připomínka byla smazána administrátorem",
                detail_text=f"ID připomínky: {reminder_id}",
            )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="reminder.delete",
            target_resource=f"reminder:{reminder_id}",
            parameters=audit_payload,
            status_code=200,
        )
        return {"message": "Připomínka byla smazána adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání připomínky: {str(e)}")


# ============= RESERVATIONS CRUD (ADMIN) =============

@router.patch("/reservations/{reservation_id}")
def update_reservation_admin(
    reservation_id: int,
    reservation_data: ReservationUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava rezervace administrátorem."""
    try:
        reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervace nenalezena")

        cust_id = int(reservation.customer_id)
        snap_b = {
            "service_id": reservation.service_id,
            "vehicle_id": reservation.vehicle_id,
            "service_type": reservation.service_type,
            "note": reservation.note,
            "start_datetime": reservation.start_datetime,
            "end_datetime": reservation.end_datetime,
            "status": reservation.status,
        }

        if reservation_data.service_id is not None:
            service = db.query(Customer).filter(Customer.id == reservation_data.service_id).first()
            if not service:
                raise HTTPException(status_code=404, detail="Servis nenalezen")
            reservation.service_id = reservation_data.service_id

        if reservation_data.vehicle_id is not None:
            vehicle = db.query(Vehicle).filter(Vehicle.id == reservation_data.vehicle_id).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            reservation.vehicle_id = reservation_data.vehicle_id

        if reservation_data.service_type is not None:
            reservation.service_type = reservation_data.service_type
        if reservation_data.note is not None:
            reservation.note = reservation_data.note
        if reservation_data.start_datetime is not None:
            reservation.start_datetime = reservation_data.start_datetime
        if reservation_data.end_datetime is not None:
            reservation.end_datetime = reservation_data.end_datetime
        if reservation_data.status is not None:
            normalized_status = reservation_data.status.strip().upper()
            allowed_statuses = {"PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"}
            if normalized_status not in allowed_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Neplatný status '{reservation_data.status}'. Povolené: {', '.join(sorted(allowed_statuses))}"
                )
            reservation.status = normalized_status

        db.commit()
        db.refresh(reservation)
        snap_a = {
            "service_id": reservation.service_id,
            "vehicle_id": reservation.vehicle_id,
            "service_type": reservation.service_type,
            "note": reservation.note,
            "start_datetime": reservation.start_datetime,
            "end_datetime": reservation.end_datetime,
            "status": reservation.status,
        }
        if admin_change_table_exists(db) and snap_b != snap_a:
            record_admin_customer_change(
                db,
                customer_id=cust_id,
                admin_email=email,
                change_key="reservation.updated",
                summary_line="Rezervace byla upravena administrátorem",
                detail_text=f"ID rezervace: {reservation.id}",
                payload={"before": snap_b, "after": snap_a},
            )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="reservation.update",
            target_resource=f"reservation:{reservation.id}",
            parameters={
                "reservation_id": reservation.id,
                "tenant_id": reservation.tenant_id,
                "service_id": reservation.service_id,
                "customer_id": reservation.customer_id,
                "vehicle_id": reservation.vehicle_id,
                "status": reservation.status,
            },
            status_code=200,
        )
        return {"message": "Rezervace byla upravena adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě rezervace: {str(e)}")


@router.delete("/reservations/{reservation_id}")
def delete_reservation_admin(
    reservation_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání rezervace administrátorem."""
    try:
        reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervace nenalezena")
        cust_id = int(reservation.customer_id)
        audit_payload = {
            "reservation_id": reservation.id,
            "tenant_id": reservation.tenant_id,
            "service_id": reservation.service_id,
            "customer_id": reservation.customer_id,
            "vehicle_id": reservation.vehicle_id,
            "status": reservation.status,
        }

        db.delete(reservation)
        db.commit()
        if admin_change_table_exists(db):
            record_admin_customer_change(
                db,
                customer_id=cust_id,
                admin_email=email,
                change_key="reservation.deleted",
                summary_line="Rezervace byla smazána administrátorem",
                detail_text=f"ID rezervace: {reservation_id}",
            )
            db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="reservation.delete",
            target_resource=f"reservation:{reservation_id}",
            parameters=audit_payload,
            status_code=200,
        )
        return {"message": "Rezervace byla smazána adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání rezervace: {str(e)}")


GLOBAL_ADMIN_ENTITY_TYPES = {
    "user",
    "service",
    "vehicle",
    "record",
    "reservation",
    "reminder",
    "payment",
    "audit",
}


def _global_admin_like(query: Optional[str]) -> tuple[str, str]:
    normalized = (query or "").strip().lower()
    return normalized, f"%{normalized}%"


def _append_global_admin_rows(
    db: Session,
    *,
    rows: List[Dict[str, Any]],
    sql: str,
    params: Dict[str, Any],
    per_type_limit: int,
) -> None:
    result = db.execute(text(sql), {**params, "per_type_limit": per_type_limit})
    for row in result.fetchall():
        data = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        rows.append({
            "type": data.get("type"),
            "id": data.get("id"),
            "title": data.get("title") or "-",
            "subtitle": data.get("subtitle") or "-",
            "status": data.get("status") or "-",
            "tenant_id": data.get("tenant_id"),
            "user_id": data.get("user_id"),
            "vehicle_id": data.get("vehicle_id"),
            "timestamp": to_iso_datetime(data.get("timestamp")),
            "meta": data.get("meta") or "",
            "action_hint": data.get("action_hint") or "",
        })


@router.get("/global-admin/search")
def global_admin_search(
    q: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = 120,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Jednotné admin hledání napříč hlavními entitami aplikace."""
    normalized_q, like = _global_admin_like(q)
    selected_type = (entity_type or "").strip().lower()
    if selected_type and selected_type not in GLOBAL_ADMIN_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail="Neznámý typ entity pro globální dohled")

    per_type_limit = min(max(limit, 1), 250) if selected_type else max(8, min(max(limit, 1), 160) // 8)
    params = {
        "like": like,
        "exact_id": int(normalized_q) if normalized_q.isdigit() else -1,
    }
    inspector = inspect(db.bind)
    tables = set(inspector.get_table_names())
    rows: List[Dict[str, Any]] = []

    include_all = not selected_type

    if include_all or selected_type == "user":
        _append_global_admin_rows(
            db,
            rows=rows,
            sql="""
                SELECT
                    'user' AS type,
                    c.id AS id,
                    COALESCE(c.name, c.email) AS title,
                    c.email || ' · role=' || COALESCE(c.role, '-') AS subtitle,
                    CASE
                        WHEN COALESCE(c.is_deleted, 0) = 1 THEN 'deleted'
                        WHEN COALESCE(c.is_disabled, 0) = 1 THEN 'disabled'
                        ELSE 'active'
                    END AS status,
                    c.tenant_id AS tenant_id,
                    c.id AS user_id,
                    NULL AS vehicle_id,
                    c.created_at AS timestamp,
                    'city=' || COALESCE(c.city, '-') || ' · phone=' || COALESCE(c.phone, '-') AS meta,
                    'open_user_detail' AS action_hint
                FROM customers c
                WHERE COALESCE(c.is_deleted, 0) = 0
                  AND (
                    :exact_id = c.id
                    OR lower(COALESCE(c.email, '')) LIKE :like
                    OR lower(COALESCE(c.name, '')) LIKE :like
                    OR lower(COALESCE(c.city, '')) LIKE :like
                    OR lower(COALESCE(c.phone, '')) LIKE :like
                  )
                ORDER BY c.created_at DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    if include_all or selected_type == "service":
        _append_global_admin_rows(
            db,
            rows=rows,
            sql="""
                SELECT
                    'service' AS type,
                    c.id AS id,
                    COALESCE(c.name, c.email) AS title,
                    c.email || ' · ' || COALESCE(c.city, '-') AS subtitle,
                    CASE
                        WHEN COALESCE(c.is_deleted, 0) = 1 THEN 'deleted'
                        WHEN COALESCE(c.is_disabled, 0) = 1 THEN 'disabled'
                        ELSE 'active'
                    END AS status,
                    c.tenant_id AS tenant_id,
                    c.id AS user_id,
                    NULL AS vehicle_id,
                    c.created_at AS timestamp,
                    'ico=' || COALESCE(c.ico, '-') || ' · phone=' || COALESCE(c.phone, '-') AS meta,
                    'edit_service' AS action_hint
                FROM customers c
                WHERE COALESCE(c.is_deleted, 0) = 0
                  AND lower(COALESCE(c.role, '')) = 'service'
                  AND (
                    :exact_id = c.id
                    OR lower(COALESCE(c.email, '')) LIKE :like
                    OR lower(COALESCE(c.name, '')) LIKE :like
                    OR lower(COALESCE(c.ico, '')) LIKE :like
                    OR lower(COALESCE(c.city, '')) LIKE :like
                    OR lower(COALESCE(c.phone, '')) LIKE :like
                  )
                ORDER BY c.created_at DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    if include_all or selected_type == "vehicle":
        _append_global_admin_rows(
            db,
            rows=rows,
            sql=f"""
                SELECT
                    'vehicle' AS type,
                    v.id AS id,
                    COALESCE(v.nickname, TRIM(COALESCE(v.brand, '') || ' ' || COALESCE(v.model, '')), 'Vozidlo #' || v.id) AS title,
                    'SPZ=' || COALESCE(v.plate, '-') || ' · VIN=' || COALESCE(v.vin, '-') AS subtitle,
                    COALESCE(v.status, 'active') AS status,
                    v.tenant_id AS tenant_id,
                    owner_customer.id AS user_id,
                    v.id AS vehicle_id,
                    v.created_at AS timestamp,
                    'owner=' || COALESCE(owner_customer.email, v.user_email, '-') || ' · year=' || COALESCE(CAST(v.year AS TEXT), '-') AS meta,
                    'edit_vehicle' AS action_hint
                FROM vehicles v
                {_primary_owner_join_sql(vehicle_alias="v")}
                WHERE
                  :exact_id = v.id
                  OR lower(COALESCE(v.nickname, '')) LIKE :like
                  OR lower(COALESCE(v.brand, '')) LIKE :like
                  OR lower(COALESCE(v.model, '')) LIKE :like
                  OR lower(COALESCE(v.plate, '')) LIKE :like
                  OR lower(COALESCE(v.vin, '')) LIKE :like
                  OR lower(COALESCE(v.user_email, '')) LIKE :like
                  OR lower(COALESCE(owner_customer.email, '')) LIKE :like
                  OR lower(COALESCE(owner_customer.name, '')) LIKE :like
                ORDER BY v.created_at DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    if include_all or selected_type == "record":
        _append_global_admin_rows(
            db,
            rows=rows,
            sql="""
                SELECT
                    'record' AS type,
                    sr.id AS id,
                    COALESCE(sr.description, 'Servisní záznam #' || sr.id) AS title,
                    COALESCE(v.nickname, TRIM(COALESCE(v.brand, '') || ' ' || COALESCE(v.model, '')), 'Vozidlo #' || sr.vehicle_id) AS subtitle,
                    COALESCE(sr.record_status, CASE WHEN COALESCE(sr.is_deleted, 0) = 1 THEN 'deleted' ELSE 'active' END) AS status,
                    sr.tenant_id AS tenant_id,
                    sr.user_id AS user_id,
                    sr.vehicle_id AS vehicle_id,
                    COALESCE(sr.performed_at, sr.updated_at) AS timestamp,
                    'category=' || COALESCE(sr.category, '-') || ' · price=' || COALESCE(CAST(sr.price AS TEXT), '-') AS meta,
                    'edit_record' AS action_hint
                FROM service_records sr
                LEFT JOIN vehicles v ON v.id = sr.vehicle_id
                LEFT JOIN customers c ON c.id = sr.user_id
                WHERE COALESCE(sr.is_deleted, 0) = 0
                  AND (
                    :exact_id = sr.id
                    OR :exact_id = sr.vehicle_id
                    OR lower(COALESCE(sr.description, '')) LIKE :like
                    OR lower(COALESCE(sr.note, '')) LIKE :like
                    OR lower(COALESCE(sr.category, '')) LIKE :like
                    OR lower(COALESCE(v.nickname, '')) LIKE :like
                    OR lower(COALESCE(v.plate, '')) LIKE :like
                    OR lower(COALESCE(c.email, '')) LIKE :like
                  )
                ORDER BY COALESCE(sr.performed_at, sr.updated_at) DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    if include_all or selected_type == "reservation":
        _append_global_admin_rows(
            db,
            rows=rows,
            sql="""
                SELECT
                    'reservation' AS type,
                    r.id AS id,
                    COALESCE(r.service_type, 'Rezervace #' || r.id) AS title,
                    COALESCE(v.nickname, v.plate, 'Vozidlo #' || r.vehicle_id) AS subtitle,
                    COALESCE(r.status, '-') AS status,
                    r.tenant_id AS tenant_id,
                    r.customer_id AS user_id,
                    r.vehicle_id AS vehicle_id,
                    r.start_datetime AS timestamp,
                    'customer=' || COALESCE(c.email, '-') || ' · service=' || COALESCE(s.email, '-') AS meta,
                    'open_user_detail' AS action_hint
                FROM reservations r
                LEFT JOIN vehicles v ON v.id = r.vehicle_id
                LEFT JOIN customers c ON c.id = r.customer_id
                LEFT JOIN customers s ON s.id = r.service_id
                WHERE
                    :exact_id = r.id
                    OR :exact_id = r.vehicle_id
                    OR lower(COALESCE(r.service_type, '')) LIKE :like
                    OR lower(COALESCE(r.note, '')) LIKE :like
                    OR lower(COALESCE(r.status, '')) LIKE :like
                    OR lower(COALESCE(c.email, '')) LIKE :like
                    OR lower(COALESCE(s.email, '')) LIKE :like
                    OR lower(COALESCE(v.plate, '')) LIKE :like
                ORDER BY r.start_datetime DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    if include_all or selected_type == "reminder":
        _append_global_admin_rows(
            db,
            rows=rows,
            sql="""
                SELECT
                    'reminder' AS type,
                    rem.id AS id,
                    COALESCE(rem.text, 'Připomínka #' || rem.id) AS title,
                    COALESCE(v.nickname, v.plate, 'Bez vozidla') AS subtitle,
                    CASE WHEN COALESCE(rem.is_completed, 0) = 1 THEN 'completed' ELSE 'active' END AS status,
                    rem.tenant_id AS tenant_id,
                    rem.customer_id AS user_id,
                    rem.vehicle_id AS vehicle_id,
                    COALESCE(rem.notify_at, rem.due_date, rem.created_at) AS timestamp,
                    'type=' || COALESCE(rem.type, '-') || ' · customer=' || COALESCE(c.email, '-') AS meta,
                    'open_user_detail' AS action_hint
                FROM reminders rem
                LEFT JOIN vehicles v ON v.id = rem.vehicle_id
                LEFT JOIN customers c ON c.id = rem.customer_id
                WHERE
                    :exact_id = rem.id
                    OR :exact_id = rem.vehicle_id
                    OR lower(COALESCE(rem.text, '')) LIKE :like
                    OR lower(COALESCE(rem.type, '')) LIKE :like
                    OR lower(COALESCE(c.email, '')) LIKE :like
                    OR lower(COALESCE(v.plate, '')) LIKE :like
                ORDER BY COALESCE(rem.notify_at, rem.due_date, rem.created_at) DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    if (include_all or selected_type == "payment") and "license_payment_transactions" in tables:
        _append_global_admin_rows(
            db,
            rows=rows,
            sql="""
                SELECT
                    'payment' AS type,
                    tx.id AS id,
                    COALESCE(tx.trans_id, tx.ref_id, 'Platba #' || tx.id) AS title,
                    COALESCE(tx.plan, '-') || ' · ' || COALESCE(tx.provider_status, tx.event_type, '-') AS subtitle,
                    COALESCE(tx.provider_status, tx.event_type, '-') AS status,
                    tx.tenant_id AS tenant_id,
                    c.id AS user_id,
                    NULL AS vehicle_id,
                    tx.created_at AS timestamp,
                    'amount=' || COALESCE(CAST(tx.amount_halers AS TEXT), '-') || ' ' || COALESCE(tx.currency, 'CZK') || ' · user=' || COALESCE(c.email, '-') AS meta,
                    'open_user_detail' AS action_hint
                FROM license_payment_transactions tx
                LEFT JOIN customers c ON c.tenant_id = tx.tenant_id
                WHERE
                    :exact_id = tx.id
                    OR :exact_id = tx.tenant_id
                    OR lower(COALESCE(tx.trans_id, '')) LIKE :like
                    OR lower(COALESCE(tx.ref_id, '')) LIKE :like
                    OR lower(COALESCE(tx.plan, '')) LIKE :like
                    OR lower(COALESCE(tx.provider_status, '')) LIKE :like
                    OR lower(COALESCE(tx.event_type, '')) LIKE :like
                    OR lower(COALESCE(c.email, '')) LIKE :like
                ORDER BY tx.created_at DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    if (include_all or selected_type == "audit") and "audit_log" in tables:
        _append_global_admin_rows(
            db,
            rows=rows,
            sql="""
                SELECT
                    'audit' AS type,
                    a.id AS id,
                    COALESCE(a.action, 'audit #' || a.id) AS title,
                    COALESCE(a.entity_type, '-') || CASE WHEN a.entity_id IS NOT NULL THEN ' #' || a.entity_id ELSE '' END AS subtitle,
                    COALESCE(a.actor_role, '-') AS status,
                    a.tenant_id AS tenant_id,
                    a.actor_user_id AS user_id,
                    a.vehicle_id AS vehicle_id,
                    a.created_at AS timestamp,
                    SUBSTR(COALESCE(a.metadata_json, ''), 1, 180) AS meta,
                    'open_audit' AS action_hint
                FROM audit_log a
                WHERE
                    :exact_id = a.id
                    OR :exact_id = a.entity_id
                    OR :exact_id = a.vehicle_id
                    OR lower(COALESCE(a.entity_type, '')) LIKE :like
                    OR lower(COALESCE(a.action, '')) LIKE :like
                    OR lower(COALESCE(a.actor_role, '')) LIKE :like
                    OR lower(COALESCE(a.metadata_json, '')) LIKE :like
                ORDER BY a.created_at DESC
                LIMIT :per_type_limit
            """,
            params=params,
            per_type_limit=per_type_limit,
        )

    summary = {kind: 0 for kind in sorted(GLOBAL_ADMIN_ENTITY_TYPES)}
    for item in rows:
        kind = str(item.get("type") or "")
        if kind in summary:
            summary[kind] += 1

    rows.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    rows = rows[: min(max(limit, 1), 250)]
    return {
        "query": normalized_q,
        "entity_type": selected_type or "all",
        "items": rows,
        "summary": summary,
        "count": len(rows),
        "limit": limit,
    }


# ============= SYSTEM TOOLS =============

@router.post("/reindex")
def reindex_database(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Přeindexování databáze - pro SQLite není potřeba, vrací úspěch"""
    try:
        # SQLite automaticky udržuje indexy, takže tato operace není nutná
        # Pro kompatibilitu s TOOZ_SERVICE_HUB vracíme úspěch
        return {"message": "Databáze je již indexovaná (SQLite)", "success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při indexování: {str(e)}")


@router.post("/repair")
def repair_database(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Oprava databáze - pro SQLite není potřeba, vrací úspěch"""
    try:
        # SQLite automaticky udržuje integritu, takže tato operace není nutná
        # Pro kompatibilitu s TOOZ_SERVICE_HUB vracíme úspěch
        return {"message": "Databáze je v pořádku (SQLite)", "success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při opravě: {str(e)}")


@router.get("/db-info", response_model=DbInfoResponse)
def get_db_info(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Informace o databázi"""
    try:
        from src.modules.vehicle_hub.database import DB_URL
        
        # Získat seznam tabulek
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        
        # Získat cestu k databázi
        db_path = str(DB_URL).replace("sqlite:///", "")
        if os.path.exists(db_path):
            size_bytes = os.path.getsize(db_path)
            size_kb = round(size_bytes / 1024, 2)
        else:
            size_kb = None
        
        return DbInfoResponse(
            db_path=db_path,
            table_count=len(tables),
            tables=tables,
            total_size_kb=size_kb
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při získávání informací: {str(e)}")


@router.get("/settings")
def get_admin_settings(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Vrátí uložená nastavení administrace."""
    try:
        settings = load_admin_settings()
        return {"settings": settings}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání nastavení: {str(e)}")


@router.put("/settings")
def update_admin_settings(
    payload: SettingsUpdatePayload,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Uloží dávku nastavení administrace."""
    try:
        settings = load_admin_settings()
        updated_count = 0

        for item in payload.settings:
            category = (item.category or "").strip()
            key = (item.key or "").strip()
            if not category or not key:
                continue

            settings.setdefault(category, {})
            current = settings[category].get(key, {})
            value_type = (item.value_type or current.get("value_type") or infer_setting_value_type(item.value)).strip().lower()
            value = normalize_setting_value(item.value, value_type)
            description = item.description if item.description is not None else current.get("description")

            settings[category][key] = {
                "value": value,
                "value_type": value_type,
                "description": description,
            }
            updated_count += 1

        save_admin_settings(settings)
        return {"message": f"Nastavení uloženo ({updated_count} položek)", "settings": settings}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při ukládání nastavení: {str(e)}")


@router.post("/settings/init-defaults")
def init_default_admin_settings(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Inicializuje výchozí nastavení administrace."""
    try:
        defaults = get_default_admin_settings()
        save_admin_settings(defaults)
        return {"message": "Výchozí nastavení byla vytvořena", "settings": defaults}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při inicializaci výchozích nastavení: {str(e)}")


@router.get("/settings/system-notifications-overview")
def settings_system_notifications_overview(
    limit: int = 50,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Přehled oznámení pro administraci Nastavení: řádky v DB + náhled aktivního oznámení z konfigurace údržby.
    Dostupné pro admin i developer_admin (na rozdíl od samostatného broadcastu v Control Center).
    """
    assert_module_ready(db, "system_notifications", detail_prefix="Systémová oznámení nejsou připravená")

    safe_limit = max(1, min(limit, 100))
    rows = (
        db.query(SystemNotification)
        .order_by(SystemNotification.created_at.desc(), SystemNotification.id.desc())
        .limit(safe_limit)
        .all()
    )
    database_items = [
        {
            "id": row.id,
            "target_type": row.target_type,
            "target_value": row.target_value,
            "title": row.title,
            "message": row.message,
            "message_kind": notification_message_kind(row.message),
            "severity": row.severity,
            "starts_at": to_iso_datetime(row.starts_at),
            "expires_at": to_iso_datetime(row.expires_at),
            "is_active": bool(row.is_active),
            "created_by_email": row.created_by_email,
            "created_at": to_iso_datetime(row.created_at),
        }
        for row in rows
    ]

    rt_settings = load_runtime_settings()
    runtime_preview = build_maintenance_runtime_notification_item(rt_settings)

    return {
        "database_items": database_items,
        "database_count": len(database_items),
        "runtime_maintenance_preview": runtime_preview,
        "runtime_maintenance_active": runtime_preview is not None,
    }


@router.post("/settings/system-notifications/{notification_id}/deactivate")
def deactivate_settings_system_notification(
    notification_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Skryje systémové oznámení z aplikace (is_active=false). Pouze řádky z databáze (kladné ID).
    """
    if notification_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Virtuální oznámení z konfigurace údržby nelze takto vypnout – použijte výše přepínač „Oznámení o údržbě“.",
        )
    assert_module_ready(db, "system_notifications", detail_prefix="Systémová oznámení nejsou připravená")

    row = db.query(SystemNotification).filter(SystemNotification.id == notification_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Oznámení nenalezeno")

    if not row.is_active:
        return {"message": "Oznámení již bylo vypnuto", "id": notification_id, "already_inactive": True}

    row.is_active = False
    db.commit()
    db.refresh(row)

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="notifications.deactivate",
        target_resource=f"system_notifications:{notification_id}",
        parameters={
            "title": row.title,
            "message_snippet": (row.message or "")[:240],
            "target_type": row.target_type,
            "target_value": row.target_value,
        },
        result="success",
        status_code=200,
    )
    return {"message": "Oznámení bylo vypnuto", "id": notification_id}


# ============= DEVELOPER CONTROL CENTER =============

@router.get("/control-center/capabilities")
def get_control_center_capabilities(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Mapa dostupných modulů Developer Control Center."""
    return {
        "modules": [
            "system_health",
            "user_management",
            "user_account_actions",
            "vehicle_management",
            "license_management",
            "payment_management",
            "user_license_payment_insight",
            "user_presence",
            "database_tools",
            "backup_restore",
            "system_logs",
            "security_monitor",
            "api_monitor",
            "webhook_monitor",
            "storage_manager",
            "storage_cleanup",
            "email_monitor",
            "background_jobs",
            "background_jobs_pause_resume",
            "system_notifications",
            "command_console",
            "debug_tools",
        ]
    }


@router.get("/control-center/health")
def get_control_center_health(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Komplexní health panel pro Developer Control Center."""
    try:
        db_status = "ok"
        db_error = None
        try:
            db.execute(text("SELECT 1")).scalar()
        except Exception as exc:
            db_status = "error"
            db_error = str(exc)

        settings = load_admin_settings()
        comgate_settings = settings.get("comgate", {})
        smtp_settings = settings.get("email", {})

        payment_enabled = bool(comgate_settings.get("enabled", {}).get("value", False))
        payment_merchant = bool(str(comgate_settings.get("merchant", {}).get("value", "")).strip())

        smtp_host_configured = bool(str(smtp_settings.get("smtp_host", {}).get("value", SMTP_HOST or "")).strip())
        smtp_from_configured = bool(str(smtp_settings.get("smtp_from", {}).get("value", SMTP_FROM or "")).strip())
        email_status = "ok" if (smtp_host_configured and smtp_from_configured) else "warning"

        api_threshold = datetime.utcnow() - timedelta(minutes=15)
        recent_api_activity = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.event_type == "api_activity",
                SecurityAccessLog.created_at >= api_threshold,
            )
            .count()
        )

        webhook_log_file = CONTROL_CENTER_LOG_DIR / "licensing_webhook.log"
        webhook_log_exists = webhook_log_file.exists()
        # Soubor se vytvoří až při prvním licenčním webhooku — chybějící log není porucha.
        webhook_recent_count = len(_tail_file_lines(webhook_log_file, 200))

        hardening_hints: List[str] = []
        hardening_status = "ok"
        if ENVIRONMENT == "production":
            if ALLOWED_ORIGINS == ["*"]:
                hardening_hints.append("CORS: nastavte explicitní ALLOWED_ORIGINS (ne *).")
                hardening_status = "warning"
            if not str(os.getenv("ADMIN_NETWORK_ALLOWLIST", "")).strip():
                hardening_hints.append("Admin: zvažte ADMIN_NETWORK_ALLOWLIST (VPN / pevná IP).")
                hardening_status = "warning"
            if os.getenv("ENFORCE_HTTPS", "").strip().lower() not in {"1", "true", "yes", "on"}:
                hardening_hints.append("HTTPS: zapněte ENFORCE_HTTPS=1 za TLS proxy (X-Forwarded-Proto).")
                hardening_status = "warning"

        data_usage = _directory_usage(DATA_DIR)
        logs_usage = _directory_usage(CONTROL_CENTER_LOG_DIR)
        backups_usage = _directory_usage(CONTROL_CENTER_BACKUP_DIR)

        db_path = get_db_file_path()
        db_file_size = 0
        if db_path and db_path.exists():
            db_file_size = db_path.stat().st_size

        from src.modules.vehicle_hub.routers_v1.license_status import (
            _detect_recurring_url_version,
            _load_comgate_config,
            _load_subscription_runtime_config,
        )

        billing_cfg = _load_comgate_config()
        billing_runtime_cfg = _load_subscription_runtime_config()
        recurring_url = str(billing_runtime_cfg.get("recurring_url") or "")
        recurring_url_version = _detect_recurring_url_version(recurring_url)
        recurring_warning = None
        if recurring_url_version == "v2.0":
            recurring_warning = (
                "Aktivní recurring URL míří na v2.0 endpoint. Současná implementace používá Merchant API "
                "form-urlencoded flow, kde oficiální dokumentace očekává v1.0/recurring."
            )

        subscriptions_with_auto_renew = (
            db.query(func.count(LicenseSubscription.id))
            .filter(LicenseSubscription.auto_renew_enabled.is_(True))
            .scalar()
            or 0
        )
        recurring_ready_count = (
            db.query(func.count(LicenseSubscription.id))
            .filter(LicenseSubscription.recurring_ready.is_(True))
            .scalar()
            or 0
        )
        subscriptions_missing_init_recurring_id = (
            db.query(func.count(LicenseSubscription.id))
            .filter(
                LicenseSubscription.auto_renew_enabled.is_(True),
                (LicenseSubscription.init_recurring_id.is_(None) | (LicenseSubscription.init_recurring_id == "")),
            )
            .scalar()
            or 0
        )
        last_recurring_row = (
            db.query(LicenseSubscription.last_recurring_attempt_at, LicenseSubscription.last_recurring_result)
            .filter(LicenseSubscription.last_recurring_attempt_at.isnot(None))
            .order_by(LicenseSubscription.last_recurring_attempt_at.desc(), LicenseSubscription.id.desc())
            .first()
        )

        return {
            "components": {
                "api": {"status": "ok"},
                "database": {"status": db_status, "error": db_error},
                "payment_gateway": {
                    "status": "ok" if (payment_enabled and payment_merchant) else "warning",
                    "enabled": payment_enabled,
                    "merchant_configured": payment_merchant,
                    "billing_diagnostics": {
                        "COMGATE_ENABLED": bool(billing_cfg.get("enabled")),
                        "COMGATE_TEST_MODE": bool(billing_cfg.get("test_mode")),
                        "COMGATE_CREATE_URL": str(billing_cfg.get("create_url") or ""),
                        "COMGATE_STATUS_URL": str(billing_cfg.get("status_url") or ""),
                        "COMGATE_RECURRING_URL": recurring_url,
                        "recurring_url_version_detected": recurring_url_version,
                        "recurring_enabled_by_config": bool(billing_runtime_cfg.get("recurring_enabled", True)),
                        "recurring_ready_count": int(recurring_ready_count),
                        "subscriptions_with_auto_renew": int(subscriptions_with_auto_renew),
                        "subscriptions_missing_init_recurring_id": int(subscriptions_missing_init_recurring_id),
                        "last_recurring_attempt_at": (
                            last_recurring_row[0].isoformat() if last_recurring_row and last_recurring_row[0] else None
                        ),
                        "last_recurring_result": last_recurring_row[1] if last_recurring_row else None,
                        "warning": recurring_warning,
                    },
                },
                "email_service": {
                    "status": email_status,
                    "smtp_host_configured": smtp_host_configured,
                    "smtp_from_configured": smtp_from_configured,
                },
                "background_jobs": {
                    "status": "ok",
                    "reminders_worker_enabled": os.getenv("ENABLE_REMINDER_NOTIFICATION_WORKER", "1") in {"1", "true", "True"},
                    "license_worker_enabled": os.getenv("ENABLE_LICENSE_SUBSCRIPTION_WORKER", "1") in {"1", "true", "True"},
                    "reminders_worker_paused": is_job_paused("reminders.notification.check"),
                    "license_worker_paused": is_job_paused("license.subscription.cycle"),
                },
                "api_monitor": {
                    "status": "ok",
                    "recent_api_activity_15m": recent_api_activity,
                },
                "webhook_monitor": {
                    "status": "ok",
                    "log_file_exists": webhook_log_exists,
                    "recent_events_tail_count": webhook_recent_count,
                },
                "security_hardening": {
                    "status": hardening_status,
                    "hardening_hints": hardening_hints,
                    "admin_allowlist_configured": bool(str(os.getenv("ADMIN_NETWORK_ALLOWLIST", "")).strip()),
                    "enforce_https": os.getenv("ENFORCE_HTTPS", "").strip().lower() in {"1", "true", "yes", "on"},
                    "cors_restricted": ALLOWED_ORIGINS != ["*"],
                },
            },
            "storage": {
                "database_bytes": db_file_size,
                "database_human": _format_bytes(db_file_size),
                "data_dir": data_usage,
                "logs_dir": logs_usage,
                "backups_dir": backups_usage,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání health panelu: {str(e)}")


@router.get("/control-center/payments")
def get_control_center_payments(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    user_email: Optional[str] = None,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Payment management feed (Comgate + interní transakce)."""
    try:
        query = """
            SELECT
                tx.id,
                tx.tenant_id,
                tx.provider,
                tx.trans_id,
                tx.ref_id,
                tx.plan,
                tx.billing_period,
                tx.amount_halers,
                tx.currency,
                tx.event_type,
                tx.provider_status,
                tx.payload_json,
                tx.created_at,
                tx.updated_at,
                (
                    SELECT c.email
                    FROM customers c
                    WHERE c.tenant_id = tx.tenant_id
                    ORDER BY c.id ASC
                    LIMIT 1
                ) as account_email
            FROM license_payment_transactions tx
            WHERE 1=1
        """
        params: Dict[str, Any] = {"limit": max(1, min(limit, 500)), "offset": max(0, offset)}

        normalized_status = (status or "").strip().upper()
        if normalized_status:
            query += " AND UPPER(COALESCE(tx.provider_status, '')) = :status"
            params["status"] = normalized_status

        normalized_email = (user_email or "").strip().lower()
        if normalized_email:
            query += """
                AND EXISTS (
                    SELECT 1 FROM customers c2
                    WHERE c2.tenant_id = tx.tenant_id
                      AND lower(c2.email) = :user_email
                )
            """
            params["user_email"] = normalized_email

        query += " ORDER BY tx.created_at DESC, tx.id DESC LIMIT :limit OFFSET :offset"

        rows = db.execute(text(query), params).fetchall()
        today = datetime.utcnow().date()
        summary = {
            "all": {
                "count": 0,
                "paid_count": 0,
                "failed_count": 0,
                "refund_count": 0,
                "attention_count": 0,
                "paid_today_halers": 0,
            },
            "live": {
                "count": 0,
                "paid_count": 0,
                "failed_count": 0,
                "refund_count": 0,
                "attention_count": 0,
                "paid_today_halers": 0,
            },
            "test": {
                "count": 0,
                "paid_count": 0,
                "failed_count": 0,
                "refund_count": 0,
                "attention_count": 0,
                "paid_today_halers": 0,
            },
        }
        items = []
        for row in rows:
            provider_status = str(row[10] or "")
            event_type = str(row[9] or "")
            payload_json = row[11]
            environment = _infer_payment_environment(
                payload_json=payload_json,
                provider_status=provider_status,
                event_type=event_type,
            )
            is_successful = _is_payment_successful(provider_status, event_type)
            is_failed = _is_payment_failed(provider_status, event_type)
            refund_status = _payment_refund_status(provider_status, event_type)
            needs_attention = _payment_needs_attention(provider_status, event_type)

            created_at_value = row[12]
            created_at = to_iso_datetime(created_at_value)
            created_at_dt = created_at_value if isinstance(created_at_value, datetime) else None
            if created_at_dt is None and isinstance(created_at_value, str):
                try:
                    created_at_dt = datetime.fromisoformat(created_at_value.replace("Z", "+00:00"))
                except ValueError:
                    created_at_dt = None

            for bucket_name in ("all", environment.lower()):
                bucket = summary[bucket_name]
                bucket["count"] += 1
                if is_successful:
                    bucket["paid_count"] += 1
                if is_failed:
                    bucket["failed_count"] += 1
                if refund_status == "refunded":
                    bucket["refund_count"] += 1
                if needs_attention:
                    bucket["attention_count"] += 1
                if (
                    is_successful
                    and created_at_dt is not None
                    and created_at_dt.date() == today
                ):
                    bucket["paid_today_halers"] += int(row[7] or 0)

            items.append(
                {
                    "id": row[0],
                    "tenant_id": row[1],
                    "provider": row[2],
                    "trans_id": row[3],
                    "ref_id": row[4],
                    "plan": row[5],
                    "billing_period": row[6],
                    "amount_halers": row[7],
                    "currency": row[8],
                    "event_type": row[9],
                    "provider_status": row[10],
                    "payment_environment": environment,
                    "is_successful": is_successful,
                    "is_failed": is_failed,
                    "refund_status": refund_status,
                    "created_at": created_at,
                    "updated_at": to_iso_datetime(row[13]),
                    "account_email": row[14],
                }
            )

        return {
            "items": items,
            "count": len(items),
            "limit": params["limit"],
            "offset": params["offset"],
            "summary": summary,
            "source": {
                "table": "license_payment_transactions",
                "db_file": str(get_db_file_path() or ""),
                "live_detection": "payload_json.test / payload_json.environment",
            },
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání plateb: {str(e)}")


@router.post("/control-center/payments/resync")
def resync_control_center_payments(
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Spustí synchronizační cyklus plateb/licencí."""
    try:
        from src.modules.vehicle_hub.routers_v1.license_status import process_license_subscription_jobs

        result = process_license_subscription_jobs(db=db)
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="payments.resync",
            target_resource="license_subscription_jobs",
            parameters={},
            result="success",
            status_code=200,
        )
        return {"message": "Platební resync dokončen", "result": result}
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="payments.resync",
            target_resource="license_subscription_jobs",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při resync plateb: {str(e)}")


@router.get("/control-center/user-insight/{user_id}")
def get_user_license_payment_insight(
    user_id: int,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Detail licence + plateb + online status konkrétního uživatele."""
    try:
        ensure_customer_account_state_schema(db)
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")

        license_row = db.query(License).filter(License.tenant_id == user.tenant_id).first()
        subscription_row = (
            db.query(LicenseSubscription)
            .filter(LicenseSubscription.tenant_id == user.tenant_id)
            .first()
        )

        payment_rows = (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.tenant_id == user.tenant_id)
            .order_by(LicensePaymentTransaction.created_at.desc())
            .limit(25)
            .all()
        )

        latest_license_admin_action = (
            db.query(DeveloperActionAuditLog)
            .filter(
                DeveloperActionAuditLog.target_resource.in_(
                    [f"user:{user_id}", f"tenant:{user.tenant_id}"]
                ),
                DeveloperActionAuditLog.action_type.in_(
                    ["license.change", "license.override", "user.create"]
                ),
            )
            .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
            .first()
        )

        presence_row = db.execute(
            text(
                """
                SELECT
                    (
                        SELECT MAX(s1.created_at)
                        FROM security_access_logs s1
                        WHERE lower(s1.user_email) = :user_email
                          AND s1.event_type IN ('api_activity', 'login_success', 'support_contact_submitted')
                    ) AS last_seen_at,
                    (
                        SELECT MAX(s2.created_at)
                        FROM security_access_logs s2
                        WHERE lower(s2.user_email) = :user_email
                          AND s2.event_type = 'login_success'
                    ) AS last_login_at,
                    (
                        SELECT COUNT(DISTINCT COALESCE(s3.ip_address, '') || '|' || COALESCE(s3.user_agent, ''))
                        FROM security_access_logs s3
                        WHERE lower(s3.user_email) = :user_email
                          AND s3.created_at >= :window_start
                          AND s3.event_type IN ('api_activity', 'login_success')
                    ) AS active_session_count
                """
            ),
            {
                "window_start": datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS),
                "user_email": user.email.lower(),
            },
        ).fetchone()

        last_seen_at = to_iso_datetime(presence_row[0] if presence_row else None)
        is_online = is_online_by_last_seen(last_seen_at)

        payments_payload = []
        has_paid = False
        first_paid_at: Optional[str] = None
        latest_paid_at: Optional[str] = None
        live_payments_count = 0
        test_payments_count = 0
        live_paid_count = 0
        test_paid_count = 0
        failed_payments_count = 0
        refunded_payments_count = 0
        for tx in payment_rows:
            provider_status = str(tx.provider_status or "").strip().upper()
            event_type = str(tx.event_type or "").strip().lower()
            payment_environment = _infer_payment_environment(
                payload_json=tx.payload_json,
                provider_status=provider_status,
                event_type=event_type,
            )
            is_successful = _is_payment_successful(provider_status, event_type)
            is_failed = _is_payment_failed(provider_status, event_type)
            refund_status = _payment_refund_status(provider_status, event_type)
            is_counted_paid = _payment_counts_as_paid(
                environment=payment_environment,
                is_successful=is_successful,
            )

            if payment_environment == "LIVE":
                live_payments_count += 1
            else:
                test_payments_count += 1
            if is_successful:
                if payment_environment == "LIVE":
                    live_paid_count += 1
                else:
                    test_paid_count += 1
            if is_failed:
                failed_payments_count += 1
            if refund_status == "refunded":
                refunded_payments_count += 1

            if is_counted_paid:
                has_paid = True
                tx_created = to_iso_datetime(tx.created_at)
                if tx_created:
                    latest_paid_at = latest_paid_at or tx_created
                    first_paid_at = tx_created

            payments_payload.append(
                {
                    "id": tx.id,
                    "provider": tx.provider,
                    "trans_id": tx.trans_id,
                    "ref_id": tx.ref_id,
                    "plan": tx.plan,
                    "billing_period": tx.billing_period,
                    "amount_halers": tx.amount_halers,
                    "currency": tx.currency,
                    "event_type": tx.event_type,
                    "provider_status": tx.provider_status,
                    "payment_environment": payment_environment,
                    "is_successful": is_successful,
                    "is_failed": is_failed,
                    "payment_timestamp": to_iso_datetime(tx.created_at),
                    "refund_status": refund_status,
                }
            )

        source_of_activation = "manual"
        if has_paid:
            source_of_activation = "payment"
        if latest_license_admin_action:
            action = str(latest_license_admin_action.action_type or "").strip().lower()
            if action in {"license.change", "license.override"}:
                source_of_activation = "developer_override"
            elif action == "user.create":
                source_of_activation = "trial_or_manual"

        activation_date = to_iso_datetime(license_row.valid_from if license_row else None)
        expiration_date = to_iso_datetime(license_row.valid_to if license_row else None)
        if not expiration_date:
            expiration_date = to_iso_datetime(subscription_row.current_period_end if subscription_row else None)

        next_renewal_date = to_iso_datetime(subscription_row.next_charge_at if subscription_row else None)
        purchase_date = first_paid_at or activation_date

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tenant_id": user.tenant_id,
                "is_disabled": bool(getattr(user, "is_disabled", False)),
                "is_deleted": bool(getattr(user, "is_deleted", False)),
                "session_version": customer_session_version(user),
            },
            "license": {
                "current_plan": license_row.plan if license_row else "free",
                "status": license_row.status if license_row else "active",
                "purchase_date": purchase_date,
                "activation_date": activation_date,
                "expiration_date": expiration_date,
                "next_renewal_date": next_renewal_date,
                "source_of_activation": source_of_activation,
                "valid_from": activation_date,
                "valid_to": expiration_date,
                "vehicles_limit": license_row.vehicles_limit if license_row else None,
            },
            "subscription": {
                "status": subscription_row.status if subscription_row else "legacy_manual",
                "provider": subscription_row.provider if subscription_row else None,
                "billing_period": subscription_row.billing_period if subscription_row else None,
                "plan_current": subscription_row.plan_current if subscription_row else None,
                "current_period_start": to_iso_datetime(subscription_row.current_period_start if subscription_row else None),
                "current_period_end": to_iso_datetime(subscription_row.current_period_end if subscription_row else None),
                "next_charge_at": to_iso_datetime(subscription_row.next_charge_at if subscription_row else None),
                "last_payment_at": to_iso_datetime(subscription_row.last_payment_at if subscription_row else None),
            },
            "presence": {
                "online_status": "ONLINE" if is_online else "OFFLINE",
                "last_seen_at": last_seen_at,
                "last_login_at": to_iso_datetime(presence_row[1] if presence_row else None),
                "active_session_count": int(presence_row[2] or 0) if presence_row else 0,
            },
            "payments_summary": {
                "has_paid": has_paid,
                "first_paid_at": first_paid_at,
                "last_paid_at": latest_paid_at,
                "provider": subscription_row.provider if subscription_row else None,
                "count": len(payments_payload),
                "count_live": live_payments_count,
                "count_test": test_payments_count,
                "live_paid_count": live_paid_count,
                "test_paid_count": test_paid_count,
                "failed_count": failed_payments_count,
                "refund_count": refunded_payments_count,
                "has_live_paid": live_paid_count > 0,
                "has_test_paid": test_paid_count > 0,
                "paid_counting_mode": "live_only" if not COUNT_TEST_PAYMENTS_AS_PAID else "live_and_test",
            },
            "payments": payments_payload,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání user insight: {str(e)}")


def _load_user_for_control_action(db: Session, user_id: int) -> Customer:
    ensure_customer_account_state_schema(db)
    user = db.query(Customer).filter(Customer.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return user


@router.post("/control-center/users/{user_id}/disable")
def disable_user_account(
    user_id: int,
    payload: UserStateActionRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    if customer_is_deleted(user):
        raise HTTPException(status_code=400, detail="Účet je již smazaný")

    user.is_disabled = True
    user.disabled_at = datetime.utcnow()
    increment_customer_session_version(user)
    db.commit()

    if admin_change_table_exists(db):
        record_admin_customer_change(
            db,
            customer_id=user.id,
            admin_email=email,
            change_key="account.disabled",
            summary_line="Účet byl administrátorem pozastaven",
            detail_text=(payload.reason or "").strip() or None,
        )
        db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.disable",
        target_resource=f"user:{user_id}",
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Účet {user.email} byl pozastaven",
        "user_id": user.id,
        "is_disabled": True,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/enable")
def enable_user_account(
    user_id: int,
    payload: UserStateActionRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    if customer_is_deleted(user):
        raise HTTPException(status_code=400, detail="Smazaný účet nelze znovu aktivovat")

    user.is_disabled = False
    user.disabled_at = None
    increment_customer_session_version(user)
    db.commit()

    if admin_change_table_exists(db):
        record_admin_customer_change(
            db,
            customer_id=user.id,
            admin_email=email,
            change_key="account.enabled",
            summary_line="Účet byl administrátorem znovu aktivován",
            detail_text=(payload.reason or "").strip() or None,
        )
        db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.enable",
        target_resource=f"user:{user_id}",
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Účet {user.email} byl aktivován",
        "user_id": user.id,
        "is_disabled": False,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/force-logout")
def force_logout_user_account(
    user_id: int,
    payload: UserStateActionRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    increment_customer_session_version(user)
    db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.force_logout",
        target_resource=f"user:{user_id}",
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Aktivní relace uživatele {user.email} byly ukončeny",
        "user_id": user.id,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/reset-password")
def reset_user_password_admin(
    user_id: int,
    payload: UserPasswordResetRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    if customer_is_deleted(user):
        raise HTTPException(status_code=400, detail="Smazanému účtu nelze resetovat heslo")

    generated = False
    new_password = (payload.new_password or "").strip()
    if payload.generate_random or not new_password:
        new_password = generate_temporary_password()
        generated = True

    try:
        user.password_hash = hash_password(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    increment_customer_session_version(user)
    db.commit()

    if admin_change_table_exists(db):
        record_admin_customer_change(
            db,
            customer_id=user.id,
            admin_email=email,
            change_key="account.password_reset",
            summary_line="Heslo bylo administrátorem resetováno",
            detail_text="Nové heslo z bezpečnostních důvodů do e-mailu neuvádíme.",
        )
        db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.password_reset",
        target_resource=f"user:{user_id}",
        parameters={"generated_random": generated, "reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Heslo uživatele {user.email} bylo resetováno",
        "user_id": user.id,
        "temporary_password": new_password if generated else None,
        "generated_random": generated,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/license")
def update_user_license_admin(
    user_id: int,
    payload: UserLicenseUpdateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    plan = normalize_license_plan(payload.plan, user.role)
    status = normalize_license_status(payload.status)
    source = (payload.source or "").strip().lower() or "developer_override"

    if plan and (not LICENSE_MANAGEMENT_AVAILABLE or not upgrade_license_plan):
        raise HTTPException(status_code=503, detail="Správa licencí není momentálně dostupná")

    ensure_default_license_for_tenant(db, user.tenant_id)
    license_row = db.query(License).filter(License.tenant_id == user.tenant_id).first()
    if not license_row:
        raise HTTPException(status_code=500, detail="Licence tenantu nebyla nalezena")

    plan_before = license_row.plan
    status_before = license_row.status
    valid_before = license_row.valid_to

    if plan:
        upgrade_license_plan(db, user.tenant_id, plan)
        db.refresh(license_row)

    if status:
        license_row.status = status
    if payload.valid_to is not None:
        license_row.valid_to = payload.valid_to
    db.commit()
    db.refresh(license_row)

    if admin_change_table_exists(db):
        detail_parts: List[str] = []
        if str(plan_before or "") != str(license_row.plan or ""):
            detail_parts.append(f"Plán: {plan_before} → {license_row.plan}")
        if str(status_before or "") != str(license_row.status or ""):
            detail_parts.append(f"Stav: {status_before} → {license_row.status}")
        if valid_before != license_row.valid_to:
            detail_parts.append(
                f"Platnost do: {to_iso_datetime(valid_before)} → {to_iso_datetime(license_row.valid_to)}"
            )
        if detail_parts:
            record_admin_customer_change(
                db,
                customer_id=user.id,
                admin_email=email,
                change_key="license.control_center",
                summary_line="Úprava licence administrátorem (Control Center)",
                detail_text="\n".join(detail_parts),
                payload={"tenant_id": user.tenant_id, "source": source},
            )
            db.commit()

    try:
        write_global_audit_log(
            db,
            entity_type="license",
            entity_id=int(user.tenant_id),
            action="license_admin_override",
            actor_user_id=None,
            actor_role="developer_admin",
            tenant_id=int(user.tenant_id),
            metadata={
                "target_user_id": user_id,
                "plan": plan,
                "status": status,
                "operator_email": email,
                "source": source,
            },
        )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="license.override",
        target_resource=f"user:{user_id}",
        parameters={
            "tenant_id": user.tenant_id,
            "plan": plan,
            "status": status,
            "valid_to": to_iso_datetime(payload.valid_to),
            "source": source,
            "reason": payload.reason,
        },
        result="success",
        status_code=200,
    )
    return {
        "message": "Licence byla aktualizována",
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "license": {
            "plan": license_row.plan,
            "status": license_row.status,
            "valid_from": to_iso_datetime(license_row.valid_from),
            "valid_to": to_iso_datetime(license_row.valid_to),
            "vehicles_limit": license_row.vehicles_limit,
            "source": source,
        },
    }


@router.get("/control-center/presence")
def get_users_presence(
    limit: int = 200,
    offset: int = 0,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """User online/offline monitoring (odvozené ze security logů)."""
    try:
        ensure_customer_account_state_schema(db)
        window_start = datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
        rows = db.execute(
            text(
                """
                SELECT
                    c.id,
                    c.email,
                    c.name,
                    c.role,
                    c.tenant_id,
                    (
                        SELECT MAX(s1.created_at)
                        FROM security_access_logs s1
                        WHERE lower(s1.user_email) = lower(c.email)
                          AND s1.event_type IN ('api_activity', 'login_success', 'support_contact_submitted')
                    ) AS last_seen_at,
                    (
                        SELECT MAX(s2.created_at)
                        FROM security_access_logs s2
                        WHERE lower(s2.user_email) = lower(c.email)
                          AND s2.event_type = 'login_success'
                    ) AS last_login_at,
                    (
                        SELECT COUNT(DISTINCT COALESCE(s3.ip_address, '') || '|' || COALESCE(s3.user_agent, ''))
                        FROM security_access_logs s3
                        WHERE lower(s3.user_email) = lower(c.email)
                          AND s3.created_at >= :window_start
                          AND s3.event_type IN ('api_activity', 'login_success')
                    ) AS active_session_count
                FROM customers c
                WHERE COALESCE(c.is_deleted, 0) = 0
                ORDER BY c.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "window_start": window_start,
                "limit": max(1, min(limit, 500)),
                "offset": max(0, offset),
            },
        ).fetchall()

        items = []
        for row in rows:
            last_seen_at = to_iso_datetime(row[5])
            is_online = is_online_by_last_seen(last_seen_at)
            items.append(
                {
                    "user_id": row[0],
                    "email": row[1],
                    "name": row[2],
                    "role": row[3],
                    "tenant_id": row[4],
                    "online_status": "ONLINE" if is_online else "OFFLINE",
                    "last_seen_at": last_seen_at,
                    "last_login_at": to_iso_datetime(row[6]),
                    "active_session_count": int(row[7] or 0),
                }
            )

        return {
            "items": items,
            "online_window_seconds": ONLINE_WINDOW_SECONDS,
            "count": len(items),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání online/offline stavu: {str(e)}")


@router.get("/control-center/security-monitor")
def get_security_monitor(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Bezpečnostní monitor: failed loginy, blokace IP, rate-limit události."""
    try:
        since_24h = datetime.utcnow() - timedelta(hours=24)
        since_7d = datetime.utcnow() - timedelta(days=7)

        failed_24h = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.event_type == "login_failed",
                SecurityAccessLog.created_at >= since_24h,
            )
            .count()
        )

        rate_limited_24h = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.event_type == "login_rate_limited",
                SecurityAccessLog.created_at >= since_24h,
            )
            .count()
        )

        source_probes_24h = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.event_type == "source_probe_blocked",
                SecurityAccessLog.created_at >= since_24h,
            )
            .count()
        )

        # GROUP BY musi pouzit stejny vyraz jako bucket (SQLite nevzdy podporuje alias ve GROUP BY).
        _probe_bucket_expr = (
            "COALESCE(NULLIF(TRIM(COALESCE(ip_address, '')), ''), '(bez IP)')"
        )
        source_probe_by_ip_rows = db.execute(
            text(
                f"""
                SELECT
                    {_probe_bucket_expr} AS ip_bucket,
                    COUNT(*) AS probe_count,
                    MAX(created_at) AS last_probe_at
                FROM security_access_logs
                WHERE event_type = 'source_probe_blocked'
                  AND created_at >= :since_24h
                GROUP BY {_probe_bucket_expr}
                ORDER BY probe_count DESC, last_probe_at DESC
                LIMIT 50
                """
            ),
            {"since_24h": since_24h},
        ).fetchall()

        suspicious_rows = db.execute(
            text(
                """
                SELECT
                    ip_address,
                    COUNT(*) as failed_count
                FROM security_access_logs
                WHERE event_type = 'login_failed'
                  AND created_at >= :since_24h
                  AND ip_address IS NOT NULL
                GROUP BY ip_address
                ORDER BY failed_count DESC
                LIMIT 20
                """
            ),
            {"since_24h": since_24h},
        ).fetchall()

        brute_force_alert_ips = int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT ip_address
                        FROM security_access_logs
                        WHERE event_type = 'login_failed'
                          AND created_at >= :since_24h
                          AND ip_address IS NOT NULL
                        GROUP BY ip_address
                        HAVING COUNT(*) >= 5
                    ) AS brute_ips
                    """
                ),
                {"since_24h": since_24h},
            ).scalar()
            or 0
        )

        blocked_ips = (
            db.query(SecurityBlockedIp)
            .order_by(SecurityBlockedIp.blocked_at.desc())
            .limit(200)
            .all()
        )

        blocked_ips_active = sum(1 for item in blocked_ips if item.is_active)
        control_center_alert_total = brute_force_alert_ips + blocked_ips_active + source_probes_24h

        security_event_types = ("login_failed", "login_rate_limited", "source_probe_blocked")
        security_events = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.created_at >= since_7d,
                SecurityAccessLog.event_type.in_(security_event_types),
            )
            .order_by(SecurityAccessLog.created_at.desc())
            .limit(500)
            .all()
        )

        latest_events = (
            db.query(SecurityAccessLog)
            .filter(SecurityAccessLog.created_at >= since_7d)
            .order_by(SecurityAccessLog.created_at.desc())
            .limit(400)
            .all()
        )

        def _security_log_row(item: SecurityAccessLog) -> Dict[str, Any]:
            loc_parts = [part for part in (item.city, item.region, item.country) if part]
            details_raw = (item.details or "").strip()
            details_short = details_raw
            if len(details_short) > 240:
                details_short = details_short[:237] + "..."
            return {
                "id": item.id,
                "event_type": item.event_type,
                "user_email": item.user_email,
                "ip_address": item.ip_address,
                "endpoint": item.endpoint,
                "created_at": to_iso_datetime(item.created_at),
                "country": item.country,
                "region": item.region,
                "city": item.city,
                "location_label": ", ".join(loc_parts) if loc_parts else None,
                "user_agent": item.user_agent,
                "details": details_raw or None,
                "details_preview": details_short or None,
            }

        return {
            "summary": {
                "failed_logins_24h": failed_24h,
                "rate_limited_24h": rate_limited_24h,
                "source_probes_24h": source_probes_24h,
                "blocked_ips_active": blocked_ips_active,
                "brute_force_alert_ips": brute_force_alert_ips,
                "control_center_alert_total": control_center_alert_total,
            },
            "top_failed_ips": [
                {"ip_address": row[0], "failed_count": int(row[1] or 0)}
                for row in suspicious_rows
            ],
            "blocked_ips": [
                {
                    "ip_address": item.ip_address,
                    "reason": item.reason,
                    "is_active": bool(item.is_active),
                    "blocked_at": to_iso_datetime(item.blocked_at),
                    "expires_at": to_iso_datetime(item.expires_at),
                    "blocked_by_email": item.blocked_by_email,
                    "unblocked_at": to_iso_datetime(item.unblocked_at),
                    "unblocked_by_email": item.unblocked_by_email,
                }
                for item in blocked_ips
            ],
            "source_probe_by_ip_24h": [
                {
                    "ip_address": row[0],
                    "probe_count": int(row[1] or 0),
                    "last_probe_at": to_iso_datetime(row[2]) if row[2] is not None else None,
                }
                for row in source_probe_by_ip_rows
            ],
            "security_events": [_security_log_row(item) for item in security_events],
            "latest_events": [_security_log_row(item) for item in latest_events],
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání security monitoru: {str(e)}")


@router.post("/control-center/security/block-ip")
def block_ip_address(
    payload: SecurityBlockIpRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Manuální blokace IP adresy (anti-abuse zásah)."""
    ip_text = str(payload.ip_address or "").strip()
    try:
        normalized_ip = str(ipaddress.ip_address(ip_text))
    except ValueError:
        raise HTTPException(status_code=400, detail="Neplatný formát IP adresy")

    actor = get_customer_by_email(db, email)
    expires_at = None
    if payload.expires_in_minutes and payload.expires_in_minutes > 0:
        expires_at = datetime.utcnow() + timedelta(minutes=min(payload.expires_in_minutes, 60 * 24 * 30))

    try:
        entry = db.query(SecurityBlockedIp).filter(SecurityBlockedIp.ip_address == normalized_ip).first()
        if not entry:
            entry = SecurityBlockedIp(
                ip_address=normalized_ip,
                reason=(payload.reason or "").strip() or None,
                blocked_by_customer_id=actor.id if actor else None,
                blocked_by_email=email.lower(),
                blocked_at=datetime.utcnow(),
                expires_at=expires_at,
                is_active=True,
            )
            db.add(entry)
        else:
            entry.reason = (payload.reason or "").strip() or entry.reason
            entry.blocked_by_customer_id = actor.id if actor else entry.blocked_by_customer_id
            entry.blocked_by_email = email.lower()
            entry.blocked_at = datetime.utcnow()
            entry.expires_at = expires_at
            entry.is_active = True
            entry.unblocked_at = None
            entry.unblocked_by_customer_id = None
            entry.unblocked_by_email = None

        db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.block_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"reason": payload.reason, "expires_at": to_iso_datetime(expires_at)},
            result="success",
            status_code=200,
        )
        return {
            "message": f"IP adresa {normalized_ip} byla zablokována",
            "ip_address": normalized_ip,
            "expires_at": to_iso_datetime(expires_at),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.block_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při blokaci IP: {str(e)}")


@router.post("/control-center/security/unblock-ip")
def unblock_ip_address(
    payload: SecurityUnblockIpRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Zrušení blokace IP adresy."""
    ip_text = str(payload.ip_address or "").strip()
    try:
        normalized_ip = str(ipaddress.ip_address(ip_text))
    except ValueError:
        raise HTTPException(status_code=400, detail="Neplatný formát IP adresy")

    actor = get_customer_by_email(db, email)
    try:
        entry = (
            db.query(SecurityBlockedIp)
            .filter(
                SecurityBlockedIp.ip_address == normalized_ip,
                SecurityBlockedIp.is_active.is_(True),
            )
            .first()
        )
        if not entry:
            raise HTTPException(status_code=404, detail="Aktivní blokace pro tuto IP neexistuje")

        entry.is_active = False
        entry.unblocked_at = datetime.utcnow()
        entry.unblocked_by_customer_id = actor.id if actor else None
        entry.unblocked_by_email = email.lower()
        if payload.reason:
            existing_reason = (entry.reason or "").strip()
            suffix = f" | unblock: {payload.reason.strip()}"
            entry.reason = f"{existing_reason}{suffix}" if existing_reason else f"unblock: {payload.reason.strip()}"

        db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.unblock_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"reason": payload.reason},
            result="success",
            status_code=200,
        )
        return {"message": f"IP adresa {normalized_ip} byla odblokována", "ip_address": normalized_ip}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.unblock_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při odblokování IP: {str(e)}")


@router.get("/control-center/backups")
def list_control_center_backups(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Seznam dostupných backup snapshotů."""
    return {"items": _list_backup_entries()}


@router.post("/control-center/backups/create")
def create_control_center_backup(
    payload: BackupCreateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Vytvoří snapshot databáze (+ volitelně data dir) pro restore operace."""
    db_file = get_db_file_path()
    if not db_file or not db_file.exists():
        raise HTTPException(status_code=400, detail="Aktuální databáze není dostupná pro backup")

    backup_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = CONTROL_CENTER_BACKUP_DIR / backup_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        backup_db = backup_dir / "vehicles.db"
        _create_sqlite_backup(db_file, backup_db)

        copied_data = []
        if payload.include_data_dir and DATA_DIR.exists():
            data_snapshot_root = backup_dir / "data"
            data_snapshot_root.mkdir(parents=True, exist_ok=True)
            for name in [
                "uploads",
                "vehicle_photos",
                "service_workspace_docs",
                "service_record_attachments",
                "images",
                "pdfs",
            ]:
                src = DATA_DIR / name
                if src.exists():
                    dst = data_snapshot_root / name
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    copied_data.append(name)

        manifest = {
            "backup_id": backup_id,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": email.lower(),
            "db_file": str(backup_db.name),
            "db_size_bytes": backup_db.stat().st_size if backup_db.exists() else 0,
            "include_data_dir": bool(payload.include_data_dir),
            "data_dirs": copied_data,
        }
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.create",
            target_resource=f"backup:{backup_id}",
            parameters=manifest,
            result="success",
            status_code=200,
        )
        return {"message": "Backup byl vytvořen", "backup": manifest}
    except Exception as e:
        shutil.rmtree(backup_dir, ignore_errors=True)
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.create",
            target_resource=f"backup:{backup_id}",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření backupu: {str(e)}")


@router.get("/control-center/backups/{backup_id}/download")
def download_control_center_backup(
    backup_id: str,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Download ZIP snapshotu."""
    backup_dir = CONTROL_CENTER_BACKUP_DIR / backup_id
    if not backup_dir.exists() or not backup_dir.is_dir():
        raise HTTPException(status_code=404, detail="Backup nenalezen")

    zip_path = backup_dir / f"{backup_id}.zip"
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in backup_dir.rglob("*"):
                if file_path == zip_path:
                    continue
                if file_path.is_file():
                    archive.write(file_path, arcname=str(file_path.relative_to(backup_dir)))

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"sprava-vozidel-backup-{backup_id}.zip",
    )


@router.post("/control-center/backups/restore")
def restore_control_center_backup(
    payload: BackupRestoreRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """
    Restore operace:
    - full: kompletní DB snapshot
    - user: částečný restore dat uživatele
    - vehicle: částečný restore dat vozidla
    """
    if (payload.confirm_text or "").strip().upper() != CONTROL_CENTER_DANGEROUS_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Pro restore je nutné potvrzení textem '{CONTROL_CENTER_DANGEROUS_CONFIRM}'",
        )

    normalized_scope = (payload.scope or "").strip().lower()
    if normalized_scope not in {"full", "user", "vehicle"}:
        raise HTTPException(status_code=400, detail="scope musí být full | user | vehicle")

    backup_dir = CONTROL_CENTER_BACKUP_DIR / payload.backup_id
    backup_db_file = backup_dir / "vehicles.db"
    target_db_file = get_db_file_path()
    if not backup_db_file.exists():
        raise HTTPException(status_code=404, detail="DB snapshot pro zvolený backup nebyl nalezen")
    if not target_db_file or not target_db_file.exists():
        raise HTTPException(status_code=400, detail="Cílová databáze není dostupná")

    action_target = f"backup:{payload.backup_id}:{normalized_scope}"
    try:
        pre_restore_id = datetime.utcnow().strftime("pre_restore_%Y%m%d_%H%M%S")
        pre_restore_dir = CONTROL_CENTER_BACKUP_DIR / pre_restore_id
        pre_restore_dir.mkdir(parents=True, exist_ok=True)
        _create_sqlite_backup(target_db_file, pre_restore_dir / "vehicles.db")
        (pre_restore_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "backup_id": pre_restore_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": email.lower(),
                    "reason": "automatic pre-restore snapshot",
                    "source_restore": payload.backup_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        restored_counts: Dict[str, int] = {}
        if normalized_scope == "full":
            _restore_sqlite_backup(backup_db_file, target_db_file)
            restored_counts = {"database": 1}

            data_snapshot_dir = backup_dir / "data"
            if data_snapshot_dir.exists():
                for subdir in data_snapshot_dir.iterdir():
                    if not subdir.is_dir():
                        continue
                    target_subdir = DATA_DIR / subdir.name
                    if target_subdir.exists():
                        shutil.rmtree(target_subdir, ignore_errors=True)
                    shutil.copytree(subdir, target_subdir, dirs_exist_ok=True)
        elif normalized_scope == "user":
            if not payload.user_id:
                raise HTTPException(status_code=400, detail="Pro scope=user je povinné user_id")
            restored_counts = _restore_user_scope_from_backup(
                backup_db_file=backup_db_file,
                target_db_file=target_db_file,
                user_id=int(payload.user_id),
            )
        else:
            if not payload.vehicle_id:
                raise HTTPException(status_code=400, detail="Pro scope=vehicle je povinné vehicle_id")
            restored_counts = _restore_vehicle_scope_from_backup(
                backup_db_file=backup_db_file,
                target_db_file=target_db_file,
                vehicle_id=int(payload.vehicle_id),
            )

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.restore",
            target_resource=action_target,
            parameters={
                "scope": normalized_scope,
                "backup_id": payload.backup_id,
                "user_id": payload.user_id,
                "vehicle_id": payload.vehicle_id,
                "restored_counts": restored_counts,
            },
            result="success",
            status_code=200,
        )
        return {
            "message": "Restore dokončen",
            "scope": normalized_scope,
            "backup_id": payload.backup_id,
            "pre_restore_backup_id": pre_restore_id,
            "restored_counts": restored_counts,
        }
    except HTTPException:
        raise
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.restore",
            target_resource=action_target,
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při restore: {str(e)}")


@router.get("/control-center/system-logs")
def get_control_center_system_logs(
    lines: int = 120,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Tail systémových logů."""
    safe_lines = max(20, min(lines, 500))
    log_files = [
        CONTROL_CENTER_LOG_DIR / "server.log",
        CONTROL_CENTER_LOG_DIR / "uvicorn.log",
        CONTROL_CENTER_LOG_DIR / "volume_backup.log",
        CONTROL_CENTER_LOG_DIR / "licensing_webhook.log",
    ]
    payload = []
    for file_path in log_files:
        payload.append(
            {
                "file": str(file_path),
                "exists": file_path.exists(),
                "tail": _tail_file_lines(file_path, safe_lines),
            }
        )
    return {"logs": payload, "lines": safe_lines}


@router.get("/control-center/webhook-monitor")
def get_control_center_webhook_monitor(
    lines: int = 200,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Monitor webhook událostí (licensing webhook log)."""
    log_file = CONTROL_CENTER_LOG_DIR / "licensing_webhook.log"
    tail = _tail_file_lines(log_file, max(20, min(lines, 1000)))

    success_count = 0
    failed_count = 0
    for line in tail:
        normalized = line.lower()
        if "success=true" in normalized:
            success_count += 1
        if "success=false" in normalized or "error=" in normalized:
            failed_count += 1

    return {
        "file": str(log_file),
        "exists": log_file.exists(),
        "tail_count": len(tail),
        "success_count": success_count,
        "failed_count": failed_count,
        "tail": tail,
    }


@router.get("/control-center/storage")
def get_control_center_storage(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Storage manager přehled."""
    db_file = get_db_file_path()
    db_size = db_file.stat().st_size if db_file and db_file.exists() else 0
    return {
        "database": {
            "path": str(db_file) if db_file else None,
            "exists": bool(db_file and db_file.exists()),
            "size_bytes": db_size,
            "size_human": _format_bytes(db_size),
        },
        "directories": {
            "data": _directory_usage(DATA_DIR),
            "logs": _directory_usage(CONTROL_CENTER_LOG_DIR),
            "backups": _directory_usage(CONTROL_CENTER_BACKUP_DIR),
        },
    }


@router.get("/control-center/storage/cleanup-preview")
def get_control_center_storage_cleanup_preview(
    logs_days: int = 30,
    backups_days: int = 30,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    old_logs = _collect_old_log_files(logs_days)
    old_backups = _collect_old_backup_dirs(backups_days)
    logs_bytes = sum(path.stat().st_size for path in old_logs if path.exists())
    backups_bytes = sum(
        sum(file_path.stat().st_size for file_path in backup_dir.rglob("*") if file_path.is_file())
        for backup_dir in old_backups
        if backup_dir.exists()
    )
    return {
        "confirm_text_required": CONTROL_CENTER_CLEANUP_CONFIRM,
        "logs_days": max(1, logs_days),
        "backups_days": max(1, backups_days),
        "old_logs_count": len(old_logs),
        "old_logs_bytes": logs_bytes,
        "old_logs_human": _format_bytes(logs_bytes),
        "old_backups_count": len(old_backups),
        "old_backups_bytes": backups_bytes,
        "old_backups_human": _format_bytes(backups_bytes),
        "sample_old_logs": [str(path) for path in old_logs[:20]],
        "sample_old_backups": [str(path) for path in old_backups[:20]],
    }


@router.post("/control-center/storage/cleanup")
def run_control_center_storage_cleanup(
    payload: StorageCleanupRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    if (payload.confirm_text or "").strip().upper() != CONTROL_CENTER_CLEANUP_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Pro cleanup je nutné potvrzení textem '{CONTROL_CENTER_CLEANUP_CONFIRM}'",
        )

    logs_days = max(1, int(payload.delete_old_logs_days or 30))
    backups_days = max(1, int(payload.delete_old_backups_days or 30))
    old_logs = _collect_old_log_files(logs_days)
    old_backups = _collect_old_backup_dirs(backups_days)

    deleted_logs = 0
    deleted_backups = 0
    reclaimed_bytes = 0
    errors: List[str] = []

    for file_path in old_logs:
        try:
            if file_path.exists():
                reclaimed_bytes += file_path.stat().st_size
                file_path.unlink()
                deleted_logs += 1
        except Exception as exc:
            errors.append(f"log:{file_path} -> {exc}")

    for backup_dir in old_backups:
        try:
            if backup_dir.exists():
                dir_bytes = sum(file_path.stat().st_size for file_path in backup_dir.rglob("*") if file_path.is_file())
                reclaimed_bytes += dir_bytes
                shutil.rmtree(backup_dir, ignore_errors=False)
                deleted_backups += 1
        except Exception as exc:
            errors.append(f"backup:{backup_dir} -> {exc}")

    result = {
        "deleted_logs": deleted_logs,
        "deleted_backups": deleted_backups,
        "reclaimed_bytes": reclaimed_bytes,
        "reclaimed_human": _format_bytes(reclaimed_bytes),
        "errors": errors,
    }
    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="storage.cleanup",
        target_resource="storage",
        parameters={"logs_days": logs_days, "backups_days": backups_days, "result": result},
        result="success" if not errors else "partial",
        status_code=200,
    )
    return {
        "message": "Storage cleanup dokončen",
        **result,
    }


@router.get("/control-center/api-monitor")
def get_control_center_api_monitor(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """API monitor: nejaktivnější endpointy za 24h."""
    since_24h = datetime.utcnow() - timedelta(hours=24)
    rows = db.execute(
        text(
            """
            SELECT
                COALESCE(endpoint, 'unknown') AS endpoint,
                COUNT(*) AS hits
            FROM security_access_logs
            WHERE event_type = 'api_activity'
              AND created_at >= :since_24h
            GROUP BY endpoint
            ORDER BY hits DESC
            LIMIT 50
            """
        ),
        {"since_24h": since_24h},
    ).fetchall()
    return {
        "items": [{"endpoint": row[0], "hits": int(row[1] or 0)} for row in rows],
        "window_hours": 24,
    }


@router.get("/control-center/email-monitor")
def get_control_center_email_monitor(
    limit: int = 120,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Email monitor (odeslané/failed notifikace)."""
    safe_limit = max(20, min(limit, 500))
    since_24h = datetime.utcnow() - timedelta(hours=24)
    sent_24h = (
        db.query(EmailNotificationLog)
        .filter(
            EmailNotificationLog.sent_at >= since_24h,
            EmailNotificationLog.status == "sent",
        )
        .count()
    )
    failed_24h = (
        db.query(EmailNotificationLog)
        .filter(
            EmailNotificationLog.sent_at >= since_24h,
            EmailNotificationLog.status == "failed",
        )
        .count()
    )
    rows = (
        db.query(EmailNotificationLog)
        .order_by(EmailNotificationLog.sent_at.desc())
        .limit(safe_limit)
        .all()
    )
    return {
        "summary": {
            "sent_24h": sent_24h,
            "failed_24h": failed_24h,
        },
        "items": [
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "customer_id": row.customer_id,
                "email": row.email,
                "subject": row.subject,
                "notification_type": row.notification_type,
                "entity_id": row.entity_id,
                "status": row.status,
                "error_message": row.error_message,
                "sent_at": to_iso_datetime(row.sent_at),
            }
            for row in rows
        ],
    }


@router.get("/control-center/debug-tools")
def get_control_center_debug_tools(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Debug tools snapshot (read-only diagnostika runtime)."""
    return {
        "runtime": {
            "environment": ENVIRONMENT,
            "host": HOST,
            "port": PORT,
            "jwt_expire_minutes": JWT_EXPIRE_MINUTES,
            "allowed_origins": ALLOWED_ORIGINS,
        },
        "tables": inspect(db.bind).get_table_names(),
        "settings_file": str(ADMIN_SETTINGS_FILE),
        "settings_file_exists": ADMIN_SETTINGS_FILE.exists(),
    }


@router.get("/control-center/jobs")
def get_control_center_jobs(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Background job control status."""
    reminder_env_enabled = os.getenv("ENABLE_REMINDER_NOTIFICATION_WORKER", "1") in {"1", "true", "True"}
    license_env_enabled = os.getenv("ENABLE_LICENSE_SUBSCRIPTION_WORKER", "1") in {"1", "true", "True"}

    jobs = []
    for name, env_enabled, interval in [
        (
            "license.subscription.cycle",
            license_env_enabled,
            max(300, int(os.getenv("LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC", "3600"))),
        ),
        (
            "reminders.notification.check",
            reminder_env_enabled,
            max(60, int(os.getenv("REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC", "300"))),
        ),
    ]:
        paused = is_job_paused(name)
        pause_meta = get_job_pause_metadata(name)
        jobs.append(
            {
                "name": name,
                "env_enabled": env_enabled,
                "is_paused": paused,
                "state": "paused" if paused else ("running" if env_enabled else "disabled"),
                "effective_enabled": bool(env_enabled and not paused),
                "interval_seconds": interval,
                "paused_at": pause_meta.get("paused_at"),
                "paused_by": pause_meta.get("paused_by"),
                "pause_reason": pause_meta.get("reason"),
            }
        )

    return {
        "jobs": jobs
    }


@router.post("/control-center/jobs/run")
def run_control_center_job(
    payload: Dict[str, Any],
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Manuální spuštění interního jobu."""
    job_name = resolve_job_name(str(payload.get("job_name") or ""))
    force_run = bool(payload.get("force"))

    try:
        if is_job_paused(job_name) and not force_run:
            raise HTTPException(
                status_code=409,
                detail=f"Job '{job_name}' je pozastaven. Použijte force=true nebo jej obnovte.",
            )

        if job_name == "license.subscription.cycle":
            from src.modules.vehicle_hub.routers_v1.license_status import process_license_subscription_jobs

            result = process_license_subscription_jobs(db=db)
        elif job_name == "reminders.notification.check":
            from src.modules.vehicle_hub.routers_v1.reminders import check_and_send_reminder_notifications

            result = check_and_send_reminder_notifications(db=db)
        else:
            raise HTTPException(status_code=400, detail="Nepodporovaný job_name")

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="jobs.run",
            target_resource=job_name,
            parameters={},
            result="success",
            status_code=200,
        )
        return {"message": f"Job '{job_name}' dokončen", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="jobs.run",
            target_resource=job_name,
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při spuštění jobu: {str(e)}")


@router.post("/control-center/jobs/pause")
def pause_control_center_job(
    payload: JobStateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    job_name = resolve_job_name(payload.job_name)
    set_job_paused(job_name, True, actor_email=email, reason=payload.reason)
    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="jobs.pause",
        target_resource=job_name,
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {"message": f"Job '{job_name}' byl pozastaven", "job_name": job_name, "paused": True}


@router.post("/control-center/jobs/resume")
def resume_control_center_job(
    payload: JobStateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    job_name = resolve_job_name(payload.job_name)
    set_job_paused(job_name, False, actor_email=email, reason=payload.reason)
    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="jobs.resume",
        target_resource=job_name,
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {"message": f"Job '{job_name}' byl obnoven", "job_name": job_name, "paused": False}


@router.get("/control-center/notifications")
def list_control_center_notifications(
    limit: int = 100,
    offset: int = 0,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SystemNotification)
        .order_by(SystemNotification.created_at.desc(), SystemNotification.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "target_type": row.target_type,
                "target_value": row.target_value,
                "title": row.title,
                "message": row.message,
                "message_kind": notification_message_kind(row.message),
                "severity": row.severity,
                "starts_at": to_iso_datetime(row.starts_at),
                "expires_at": to_iso_datetime(row.expires_at),
                "is_active": bool(row.is_active),
                "created_by_email": row.created_by_email,
                "created_at": to_iso_datetime(row.created_at),
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/control-center/notifications/broadcast")
def broadcast_system_notification(
    payload: BroadcastNotificationRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """
    Interní broadcast (bez OS shell commandů): uloží oznámení do append-only logu.
    Frontend může log číst a zobrazovat.
    """
    try:
        message = prepare_broadcast_notification_storage_message(payload.message or "", rich=bool(payload.rich))
    except HTTPException:
        raise

    severity = normalize_broadcast_severity(payload.severity)
    target_type, target_value = normalize_notification_target(payload.target_type, payload.target_value)
    expires_at = None
    if payload.expires_in_hours is not None:
        safe_hours = max(1, min(int(payload.expires_in_hours), 24 * 180))
        expires_at = datetime.utcnow() + timedelta(hours=safe_hours)

    notifications_file = DATA_DIR / "system_notifications.jsonl"
    notifications_file.parent.mkdir(parents=True, exist_ok=True)
    actor = get_customer_by_email(db, email)
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "title": (payload.title or "").strip() or None,
        "message": message,
        "message_kind": notification_message_kind(message),
        "rich": bool(payload.rich),
        "severity": severity,
        "target_type": target_type,
        "target_value": target_value,
        "expires_at": to_iso_datetime(expires_at),
        "created_by": email.lower(),
    }
    with open(notifications_file, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    notification_row = SystemNotification(
        target_type=target_type,
        target_value=target_value,
        title=(payload.title or "").strip() or None,
        message=message,
        severity=severity,
        starts_at=datetime.utcnow(),
        expires_at=expires_at,
        is_active=True,
        created_by_customer_id=actor.id if actor else None,
        created_by_email=email.lower(),
    )
    db.add(notification_row)
    db.commit()
    db.refresh(notification_row)

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="notifications.broadcast",
        target_resource="system_notifications",
        parameters={
            "message": message[:2400],
            "message_kind": notification_message_kind(message),
            "rich": bool(payload.rich),
            "title": event.get("title"),
            "severity": severity,
            "target_type": target_type,
            "target_value": target_value,
            "expires_at": to_iso_datetime(expires_at),
        },
        result="success",
        status_code=200,
    )
    return {
        "message": "Broadcast uložen",
        "event": event,
        "notification_id": notification_row.id,
    }


@router.get("/control-center/audit-actions")
def get_developer_action_audit(
    limit: int = 200,
    offset: int = 0,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Immutable audit log developer akcí."""
    rows = (
        db.query(DeveloperActionAuditLog)
        .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "developer_id": row.developer_id,
                "developer_email": row.developer_email,
                "action_type": row.action_type,
                "target_resource": row.target_resource,
                "parameters_json": row.parameters_json,
                "result": row.result,
                "status_code": row.status_code,
                "request_ip": row.request_ip,
                "created_at": to_iso_datetime(row.created_at),
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/control-center/commands/execute")
def execute_internal_control_command(
    payload: InternalCommandRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """
    Command console bez OS shell přístupu.
    Podporované interní příkazy:
      - system.health
      - broadcast "text"
      - license.recheck USER_ID
      - jobs.run JOB_NAME
      - jobs.pause JOB_NAME
      - jobs.resume JOB_NAME
      - payments.resync
      - logs.tail
    """
    command = (payload.command or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="Příkaz je prázdný")

    def _ok(result: Dict[str, Any]) -> Dict[str, Any]:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="command.execute",
            target_resource=command,
            parameters={"command": command},
            result="success",
            status_code=200,
        )
        return {"ok": True, "command": command, "result": result}

    try:
        normalized = command.strip()
        normalized_lc = normalized.lower()

        if normalized_lc == "system.health":
            result = get_control_center_health(email=email, db=db)
            return _ok(result)

        if normalized_lc.startswith("broadcast "):
            message = normalized[len("broadcast "):].strip().strip('"').strip("'")
            result = broadcast_system_notification(
                payload=BroadcastNotificationRequest(message=message),
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("license.recheck "):
            user_id_text = normalized[len("license.recheck "):].strip()
            if not user_id_text.isdigit():
                raise HTTPException(status_code=400, detail="license.recheck vyžaduje USER_ID")
            result = get_user_license_payment_insight(
                user_id=int(user_id_text),
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("jobs.run "):
            job_name = normalized[len("jobs.run "):].strip()
            result = run_control_center_job(
                payload={"job_name": job_name},
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("jobs.pause "):
            job_name = normalized[len("jobs.pause "):].strip()
            result = pause_control_center_job(
                payload=JobStateRequest(job_name=job_name),
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("jobs.resume "):
            job_name = normalized[len("jobs.resume "):].strip()
            result = resume_control_center_job(
                payload=JobStateRequest(job_name=job_name),
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc == "payments.resync":
            result = resync_control_center_payments(
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc == "logs.tail":
            result = get_control_center_system_logs(lines=80, email=email, db=db)
            return _ok(result)

        raise HTTPException(status_code=400, detail="Nepodporovaný příkaz")
    except HTTPException:
        raise
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="command.execute",
            target_resource=command,
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Command failed: {str(e)}")


# ============= TENANTS & INSTANCES (Multi-tenant) =============

@router.get("/tenants", response_model=List[TenantListItem])
def list_tenants(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech tenants - pouze pro developer_admin"""
    if not TENANTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Tenants modely nejsou dostupné")
    
    try:
        tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(limit).all()
        return [TenantListItem(
            id=t.id,
            name=t.name,
            license_key=t.license_key,
            created_at=t.created_at
        ) for t in tenants]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání tenants: {str(e)}")


@router.get("/tenants/{tenant_id}/instances", response_model=List[InstanceListItem])
def list_instances(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam instancí pro daného tenanta - pouze pro developer_admin"""
    if not TENANTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Instances modely nejsou dostupné")
    
    try:
        # Zkontrolovat, zda tenant existuje
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant nenalezen")
        
        instances = db.query(Instance).filter(
            Instance.tenant_id == tenant_id
        ).order_by(Instance.last_seen_at.desc()).offset(offset).limit(limit).all()
        
        return [InstanceListItem(
            id=i.id,
            device_id=i.device_id,
            app_version=i.app_version,
            last_seen_at=i.last_seen_at
        ) for i in instances]
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání instancí: {str(e)}")
