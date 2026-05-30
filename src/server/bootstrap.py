from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.branding import APP_API_DISPLAY_NAME, APP_DISPLAY_NAME
from src.core.config import (
    ALLOWED_ORIGINS,
    DATA_DIR,
    ENABLE_AI_FEATURES,
    ENABLE_AUTOPILOT_API,
    ENABLE_CUSTOMER_COMMANDS,
    ENVIRONMENT,
    FAKTURYWEB_ENABLED,
    HOST,
    JWT_SECRET_KEY,
    LISTEN_HOST,
    PORT,
    PRODUCTION_LOCK_MODE,
)
from src.core.cloudflare_access import validate_cloudflare_access_admin_env
from src.core.security_middleware import (
    AdminNetworkGuardMiddleware,
    AntiTamperingMiddleware,
    CloudflareAccessAdminMiddleware,
    HttpsRedirectMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SourceCodeProtectionMiddleware,
)
from src.modules.vehicle_hub.account_state import ensure_customer_account_state_schema
from src.modules.vehicle_hub.database import SessionLocal, engine
from src.modules.vehicle_hub.schema_management import get_capabilities
from src.server.control_center_jobs import is_job_paused
from src.server.main_helpers import APP_VERSION, APP_VERSION_NAME, BUILD_DATE, UPDATE_INFO
from src.server.routers import instances
from src.server.routers.system import public_path, router as system_router
from src.server.routers.user_account import router as user_account_router
from src.server.routers.user_auth import router as user_auth_router
from src.server.routers.user_security import router as user_security_router
from src.server.routers.user_settings import router as user_settings_router
from src.server.routers.user_service_requests import router as user_service_requests_router
from src.server.routers.session_me import router as session_me_router
from src.server.routers.workspace_debug import router as workspace_debug_router
from src.server.maintenance_runtime_notice import maintenance_lockout_message_html
from src.server.runtime_settings import get_runtime_setting_bool, load_runtime_settings


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_REMINDER_NOTIFICATION_WORKER = _env_bool("ENABLE_REMINDER_NOTIFICATION_WORKER", True)
try:
    REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC = max(
        60,
        int(os.getenv("REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC", "300")),
    )
except ValueError:
    REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC = 300

ENABLE_LICENSE_SUBSCRIPTION_WORKER = _env_bool("ENABLE_LICENSE_SUBSCRIPTION_WORKER", True)
try:
    LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC = max(
        300,
        int(os.getenv("LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC", "3600")),
    )
except ValueError:
    LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC = 3600

ENABLE_MDCR_OPEN_DATA_SCHEDULE_WORKER = _env_bool("ENABLE_MDCR_OPEN_DATA_SCHEDULE_WORKER", True)


def _parse_env_bounded_int(name: str, default: int, *, min_val: int, max_val: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(min_val, min(max_val, value))


MDCR_SCHEDULE_HOUR_PRAGUE = _parse_env_bounded_int("MDCR_SCHEDULE_HOUR_PRAGUE", 3, min_val=0, max_val=23)
MDCR_SCHEDULE_MINUTE_PRAGUE = _parse_env_bounded_int("MDCR_SCHEDULE_MINUTE_PRAGUE", 30, min_val=0, max_val=59)


def _seconds_until_next_prague_time(hour: int, minute: int) -> float:
    """Spočítá počet sekund do příštího plánu v Europe/Prague."""
    try:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Prague")
        now = datetime.now(tz)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max(45.0, (target - now).total_seconds())
    except Exception as exc:
        print(f"[MDCR_SCHEDULE_WORKER] Europe/Prague schedule fallback to 86400s: {exc}")
        return 86400.0


ENABLE_FILE_BROWSER = _env_bool("ENABLE_FILE_BROWSER", False)

REQUIRED_PRODUCTION_STORAGE_DIRS = (
    DATA_DIR / "vehicle_archives",
    DATA_DIR / "vehicle_reports",
    DATA_DIR / "uploads" / "vehicles",
)

_reminder_notification_task: asyncio.Task | None = None
_license_subscription_task: asyncio.Task | None = None
_mdcr_open_data_schedule_task: asyncio.Task | None = None

_MAINTENANCE_BYPASS_PREFIXES = (
    "/admin-api",
    "/web_admin",
    "/admin-static",
    "/health",
)


def _validate_required_production_storage() -> None:
    missing = [str(path) for path in REQUIRED_PRODUCTION_STORAGE_DIRS if not path.is_dir()]
    if missing:
        message = "[STORAGE] ERROR: missing required production storage directories: " + ", ".join(missing)
        print(message)
        raise RuntimeError(message)
    for path in REQUIRED_PRODUCTION_STORAGE_DIRS:
        print(f"[STORAGE] OK: {path}")


class ProductionLockWriteAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            print(
                "[PRODUCTION_LOCK] write request "
                f"method={request.method.upper()} path={request.url.path} "
                f"client={request.client.host if request.client else '-'}"
            )
        return await call_next(request)
_MAINTENANCE_BYPASS_EXACT: set[str] = {
    "/version",
    "/version/history",
    "/user/login",
    "/user/login/2fa",
}
_MAINTENANCE_BYPASS_RUNTIME_PREFIXES = (
    "/api/v1/license/comgate/result",
)


if ENVIRONMENT == "production":
    default_secret = "sprava-vozidel-dev-secret-change-in-production"
    if JWT_SECRET_KEY == default_secret:
        print("[SERVER] ERROR: KRITICKA CHYBA BEZPECNOSTI!")
        print("[SERVER] V produkci musí být nastaven JWT_SECRET_KEY v .env souboru!")
        print("[SERVER] Výchozí hodnota není bezpečná.")
        print('[SERVER] Vygenerujte nový klíč pomocí: python -c "import secrets; print(secrets.token_urlsafe(32))"')
        raise SystemExit(1)
    print("[SERVER] OK: JWT_SECRET_KEY je nastaven (neni vychozi hodnota)")

_cf_access_errs = validate_cloudflare_access_admin_env()
if ENVIRONMENT == "production" and _cf_access_errs:
    for _msg in _cf_access_errs:
        print(f"[SERVER] ERROR (Cloudflare Access): {_msg}")
    raise SystemExit(1)

try:
    from src.core.config_validator import log_config_status

    config_valid, config_status, missing_keys = log_config_status()
    if ENVIRONMENT == "production" and not config_valid:
        if "JWT_SECRET_KEY" in missing_keys:
            print("[SERVER] FATAL: Aplikace nemůže běžet bez JWT_SECRET_KEY v produkci!")
            raise SystemExit(1)
        print("[SERVER] WARNING: Některé klíče chybí, ale aplikace může běžet")
except Exception as exc:
    print(f"[SERVER] WARNING: Chyba při validaci konfigurace: {exc}")
    import traceback

    traceback.print_exc()


async def _reminder_notification_worker() -> None:
    await asyncio.sleep(20)
    while True:
        db = SessionLocal()
        try:
            if is_job_paused("reminders.notification.check"):
                print("[REMINDERS_WORKER] paused by Developer Control Center")
            else:
                from src.modules.vehicle_hub.routers_v1.reminders import check_and_send_reminder_notifications

                result = check_and_send_reminder_notifications(db=db)
                print(
                    "[REMINDERS_WORKER] check done: "
                    f"sent={result.get('notifications_sent', 0)}, "
                    f"email={result.get('email_notifications_sent', 0)}, "
                    f"push={result.get('push_notifications_sent', 0)}, "
                    f"errors={result.get('errors', 0)}"
                )
        except Exception as exc:
            print(f"[REMINDERS_WORKER] check failed: {exc}")
        finally:
            db.close()

        await asyncio.sleep(REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC)


async def _license_subscription_worker() -> None:
    await asyncio.sleep(30)
    while True:
        db = SessionLocal()
        try:
            if is_job_paused("license.subscription.cycle"):
                print("[LICENSE_SUBSCRIPTION_WORKER] paused by Developer Control Center")
            else:
                from src.modules.vehicle_hub.routers_v1.license_status import process_license_subscription_jobs

                result = process_license_subscription_jobs(db=db)
                print(
                    "[LICENSE_SUBSCRIPTION_WORKER] cycle: "
                    f"renewal_success={result.get('renewal_success', 0)}, "
                    f"renewal_failed={result.get('renewal_failed', 0)}, "
                    f"downgraded_free={result.get('downgraded_free', 0)}, "
                    f"cancel_finalized={result.get('cancel_finalized', 0)}, "
                    f"notified={result.get('notified', 0)}, "
                    f"errors={result.get('errors', 0)}"
                )
        except Exception as exc:
            print(f"[LICENSE_SUBSCRIPTION_WORKER] cycle failed: {exc}")
        finally:
            db.close()

        await asyncio.sleep(LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC)


def _mdcr_open_data_schedule_tick() -> None:
    from fastapi import HTTPException

    db = SessionLocal()
    try:
        if is_job_paused("mdcr.open_data.schedule"):
            print("[MDCR_SCHEDULE_WORKER] paused (Developer Control Center job_state)")
            return
        from src.server.admin_api import MdcrOpenDataImportRequest, _run_mdcr_open_data_import

        dry_schedule = _env_bool("MDCR_SCHEDULE_DRY_RUN", False)
        payload = MdcrOpenDataImportRequest(
            source_url=None,
            use_latest_source=True,
            dry_run=dry_schedule,
            limit=None,
            update_vehicle_profile=True,
        )
        audit_email = (os.getenv("MDCR_SCHEDULE_AUDIT_EMAIL") or "").strip()
        summary = _run_mdcr_open_data_import(
            db,
            payload,
            admin_email=audit_email or "mdcr-schedule",
            request=None,
        )
        print(
            "[MDCR_SCHEDULE_WORKER] import finished "
            f"dry_run={summary.get('dry_run')} scanned={summary.get('scanned_records')} "
            f"matched_records={summary.get('matched_records')} matched_vehicles={summary.get('matched_vehicles')} "
            f"ins+={summary.get('inspection_inserted')} ins~={summary.get('inspection_updated')} "
            f"profiles={summary.get('vehicle_profile_updated')}"
        )
    except HTTPException as he:
        print(f"[MDCR_SCHEDULE_WORKER] HTTPException {he.status_code}: {he.detail}")
        try:
            db.rollback()
        except Exception:
            pass
    except Exception as exc:
        print(f"[MDCR_SCHEDULE_WORKER] import error: {exc}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


async def _mdcr_open_data_schedule_worker() -> None:
    while True:
        wait_sec = _seconds_until_next_prague_time(
            MDCR_SCHEDULE_HOUR_PRAGUE,
            MDCR_SCHEDULE_MINUTE_PRAGUE,
        )
        print(
            f"[MDCR_SCHEDULE_WORKER] next wake in {wait_sec:.0f}s "
            f"(target clock {MDCR_SCHEDULE_HOUR_PRAGUE:02d}:{MDCR_SCHEDULE_MINUTE_PRAGUE:02d} Europe/Prague)"
        )
        await asyncio.sleep(wait_sec)
        try:
            await asyncio.to_thread(_mdcr_open_data_schedule_tick)
        except Exception as exc:
            print(f"[MDCR_SCHEDULE_WORKER] tick failed (async wrapper): {exc}")


def _is_maintenance_bypass_path(path: str) -> bool:
    path_lc = (path or "").lower()
    if path_lc in _MAINTENANCE_BYPASS_EXACT:
        return True
    if any(path_lc.startswith(prefix) for prefix in _MAINTENANCE_BYPASS_RUNTIME_PREFIXES):
        return True
    return any(path_lc.startswith(prefix) for prefix in _MAINTENANCE_BYPASS_PREFIXES)


def _register_exception_handler(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import traceback

        error_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f"[ERROR] Neošetřená výjimka: {type(exc).__name__}: {str(exc)}")
        print(f"[ERROR] Path: {request.url.path}")
        print(f"[ERROR] Method: {request.method}")
        print(f"[ERROR] Traceback:\n{error_traceback}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Interní chyba serveru: {str(exc)}",
                "type": type(exc).__name__,
                "path": request.url.path,
            },
        )


def _register_middlewares(app: FastAPI) -> None:
    if PRODUCTION_LOCK_MODE:
        app.add_middleware(ProductionLockWriteAuditMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SourceCodeProtectionMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        allow_headers=["*", "Authorization", "Content-Type", "Accept"],
        expose_headers=["*"],
    )
    app.add_middleware(AntiTamperingMiddleware)
    app.add_middleware(RateLimitMiddleware, calls=100, period=60)
    app.add_middleware(AdminNetworkGuardMiddleware)
    app.add_middleware(CloudflareAccessAdminMiddleware)
    app.add_middleware(HttpsRedirectMiddleware)

    @app.middleware("http")
    async def maintenance_mode_middleware(request: Request, call_next):
        maintenance_enabled = get_runtime_setting_bool("general", "maintenance_mode", False)
        if not maintenance_enabled:
            return await call_next(request)

        path = (request.url.path or "").lower()
        if _is_maintenance_bypass_path(path):
            return await call_next(request)

        retry_after_sec = "300"
        settings_snap = load_runtime_settings()
        extra_notice_html = maintenance_lockout_message_html(settings_snap)
        extra_notice_paragraph = ""
        if extra_notice_html.strip():
            extra_notice_paragraph = f'<p class="extra-notice">{extra_notice_html}</p>'

        if path.startswith("/api/") or path.startswith("/user/"):
            response = JSONResponse(
                status_code=503,
                content={
                    "detail": "Aplikace je dočasně v režimu údržby. Zkuste to prosím za několik minut.",
                    "maintenance_mode": True,
                },
            )
        else:
            response = HTMLResponse(
                status_code=503,
                content=(
                    "<!doctype html><html lang='cs'><head><meta charset='utf-8'>"
                    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                    f"<title>{APP_DISPLAY_NAME} - Údržba</title>"
                    "<style>body{font-family:Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0;}"
                    ".wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;}"
                    ".card{max-width:680px;background:#1e293b;border:1px solid #334155;border-radius:16px;padding:28px;}"
                    "h1{margin:0 0 10px;font-size:28px;}p{margin:0 0 8px;line-height:1.55;color:#cbd5e1;}"
                    "p.extra-notice{margin-top:14px;color:#fcd34d;}"
                    "</style></head><body><div class='wrap'><div class='card'>"
                    "<h1>Aplikace je v režimu údržby</h1>"
                    "<p>Probíhá aktualizace systému. Dočasně není možné aplikaci používat.</p>"
                    f"{extra_notice_paragraph}"
                    "<p>Zkuste to prosím znovu za několik minut.</p>"
                    "</div></div></body></html>"
                ),
            )

        response.headers["Retry-After"] = retry_after_sec
        return response

    @app.middleware("http")
    async def admin_assets_no_cache_middleware(request: Request, call_next):
        path = (request.url.path or "").lower()
        is_frontend_asset = (
            path.startswith("/web_admin")
            or path.startswith("/admin-static")
            or path == "/web"
            or path.startswith("/web/")
        )

        response = await call_next(request)

        if is_frontend_asset:
            suffix = Path(path).suffix
            is_html_shell = (
                suffix in {"", ".html"}
                or path in {"/web", "/web/"}
                or response.headers.get("content-type", "").lower().startswith("text/html")
            )
            if is_html_shell:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                response.headers["Surrogate-Control"] = "no-store"
            else:
                response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
                for header_name in ("Pragma", "Expires", "Surrogate-Control"):
                    if header_name in response.headers:
                        del response.headers[header_name]
        return response


def _include_feature_routers(app: FastAPI) -> None:
    try:
        from src.modules.vehicle_hub.decoder.router import router as decoder_router

        app.include_router(decoder_router)
        print("[SERVER] Vehicle Decoder Engine router zaregistrován: /api/vehicles/decode-vin, /api/vehicles/decode-plate")
    except ImportError as exc:
        print(f"[SERVER] Warning: Vehicle Decoder Engine není dostupný: {exc}")

    if ENABLE_FILE_BROWSER:
        try:
            from src.server.file_browser import router as file_browser_router

            app.include_router(file_browser_router)
            print("[SERVER] File Browser zaregistrován: /files/ (ENABLE_FILE_BROWSER=1)")
        except ImportError as exc:
            print(f"[SERVER] Warning: File Browser není dostupný: {exc}")
    else:
        print("[SERVER] File Browser router přeskočen (ENABLE_FILE_BROWSER=false)")

    try:
        from src.modules.vehicle_hub.routers_v1 import api_router as v1_api_router

        app.include_router(v1_api_router)
        print("[SERVER] API v1 routery zaregistrovány: /api/v1/")
    except ImportError as exc:
        print(f"[SERVER] Warning: API v1 routery nejsou dostupné: {exc}")
        import traceback

        traceback.print_exc()

    try:
        from src.modules.vehicle_hub.routers_v1.service_dashboard import router as service_dashboard_router
        from src.modules.vehicle_hub.routers_v1.service_invoices import router as service_invoices_router
        from src.modules.vehicle_hub.routers_v1.service_canonical import router as service_canonical_router

        app.include_router(service_dashboard_router)
        app.include_router(service_invoices_router)
        app.include_router(service_canonical_router)
        print("[SERVER] Service Dashboard + Service Invoices + canonical intake routery zaregistrovány: /api/service/")
    except ImportError as exc:
        print(f"[SERVER] Warning: Service Dashboard router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    if FAKTURYWEB_ENABLED:
        try:
            from src.modules.service_workspace.fakturyweb_router import router as fakturyweb_workspace_router

            app.include_router(fakturyweb_workspace_router)
            print("[SERVER] FakturyWeb workspace test router zaregistrován (FAKTURYWEB_ENABLED=true)")
        except ImportError as exc:
            print(f"[SERVER] Warning: FakturyWeb workspace test router není dostupný: {exc}")
            import traceback

            traceback.print_exc()
    else:
        print("[SERVER] FakturyWeb workspace test router přeskočen (FAKTURYWEB_ENABLED=false)")

    try:
        from src.server.routers.public_vehicle_history import router as public_vehicle_history_router

        app.include_router(public_vehicle_history_router)
        print("[SERVER] Public vehicle history router zaregistrován: /api/public/vehicle-history/")
    except ImportError as exc:
        print(f"[SERVER] Warning: Public vehicle history router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    try:
        from src.server.routers.public_vehicle_transfer import router as public_vehicle_transfer_router

        app.include_router(public_vehicle_transfer_router)
        print("[SERVER] Public vehicle transfer router zaregistrován: /api/public/vehicle-transfer/")
    except ImportError as exc:
        print(f"[SERVER] Warning: Public vehicle transfer router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    try:
        from src.server.routers.public_quote import router as public_quote_router

        app.include_router(public_quote_router)
        print("[SERVER] Public quote router zaregistrován: /api/public/quote/")
    except ImportError as exc:
        print(f"[SERVER] Warning: Public quote router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    try:
        from src.server.routers.public_documents import router as public_documents_router

        app.include_router(public_documents_router)
        print("[SERVER] Public documents verify router zaregistrován: /api/public/documents/")
    except ImportError as exc:
        print(f"[SERVER] Warning: Public documents router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    try:
        from src.server.routers.public_demo_account import router as public_demo_account_router

        app.include_router(public_demo_account_router)
        print("[SERVER] Public demo account router zaregistrován: /api/public/demo-account")
    except ImportError as exc:
        print(f"[SERVER] Warning: Public demo account router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    if ENABLE_AUTOPILOT_API:
        try:
            from src.modules.vehicle_hub.routers_v1.autopilot import router as autopilot_router

            app.include_router(autopilot_router)
            print("[SERVER] Autopilot M2M API router zaregistrován: /api/autopilot/")
        except ImportError as exc:
            print(f"[SERVER] Warning: Autopilot M2M API router není dostupný: {exc}")
            import traceback

            traceback.print_exc()
    else:
        print("[SERVER] Autopilot M2M API router přeskočen (ENABLE_AUTOPILOT_API=false)")

    if ENABLE_CUSTOMER_COMMANDS:
        try:
            from src.modules.vehicle_hub.routers_v1.customer_commands import router as customer_commands_router

            app.include_router(customer_commands_router)
            print("[SERVER] Customer Commands API router zaregistrován: /api/customer-commands/")
        except ImportError as exc:
            print(f"[SERVER] Warning: Customer Commands API router není dostupný: {exc}")
            import traceback

            traceback.print_exc()
    else:
        print("[SERVER] Customer Commands API router přeskočen (ENABLE_CUSTOMER_COMMANDS=false)")

    try:
        from src.server.admin_api import router as admin_api_router

        app.include_router(admin_api_router)
        print("[SERVER] Admin API router zaregistrován: /admin-api/")
        try:
            from src.server.admin_vehicle_support import router as admin_vehicle_support_router

            app.include_router(admin_vehicle_support_router, prefix="/admin-api")
            print("[SERVER] Admin vehicle support router zaregistrován: /admin-api/vehicles/...")
        except ImportError as exc_inner:
            print(f"[SERVER] Warning: Admin vehicle support router není dostupný: {exc_inner}")
        try:
            from src.server.admin_vehicle_lifecycle import router as admin_vehicle_lifecycle_router

            app.include_router(admin_vehicle_lifecycle_router, prefix="/admin-api")
            app.include_router(admin_vehicle_lifecycle_router, prefix="/api/admin")
            print("[SERVER] Admin vehicle lifecycle router zaregistrován: /admin-api/vehicle-lifecycle a /api/admin/vehicle-lifecycle")
        except ImportError as exc_inner:
            print(f"[SERVER] Warning: Admin vehicle lifecycle router není dostupný: {exc_inner}")
    except ImportError as exc:
        print(f"[SERVER] Warning: Admin API router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    app.include_router(instances.router)
    print("[SERVER] Instances API router zaregistrován: /api/instances/")

    if ENABLE_AI_FEATURES:
        try:
            from src.modules.ai_features.routers import router as ai_features_router

            app.include_router(ai_features_router)
            print("[SERVER] AI Features router zaregistrován: /api/v1/ai-features/")
        except ImportError as exc:
            print(f"[SERVER] Warning: AI Features router není dostupný: {exc}")
            import traceback

            traceback.print_exc()
    else:
        print("[SERVER] AI Features router přeskočen (ENABLE_AI_FEATURES=false)")

    try:
        from src.server.routers.support import router as support_router
        app.include_router(support_router)
        print("[SERVER] Support router zaregistrován: /api/v1/support/")
    except ImportError as exc:
        print(f"[SERVER] Warning: Support router není dostupný: {exc}")
        import traceback
        traceback.print_exc()

    app.include_router(session_me_router)
    if PRODUCTION_LOCK_MODE:
        print("[PRODUCTION_LOCK] workspace debug router disabled")
    else:
        app.include_router(workspace_debug_router)
    app.include_router(user_auth_router)
    app.include_router(user_account_router)
    app.include_router(user_security_router)
    app.include_router(user_settings_router, prefix="/api/v1")
    app.include_router(user_service_requests_router, prefix="/api/v1")
    app.include_router(system_router)


def _mount_static_directories(app: FastAPI) -> None:
    try:
        if public_path.exists():
            app.mount("/public", StaticFiles(directory=str(public_path)), name="public_static")
            print(f"[SERVER] Public file server zaregistrován: /public/ (directory: {public_path})")
    except (OSError, ValueError) as exc:
        print(f"[SERVER] Warning: Could not mount public directory: {exc}")

    try:
        admin_web_path = Path(__file__).parent.parent.parent / "web_admin"
        if admin_web_path.exists():
            app.mount("/web_admin", StaticFiles(directory=str(admin_web_path), html=True), name="web_admin")
            print(f"[SERVER] Admin web zaregistrován: /web_admin/ (directory: {admin_web_path})")
            app.mount("/admin-static", StaticFiles(directory=str(admin_web_path)), name="admin_static")
            print(f"[SERVER] Admin static files zaregistrovány: /admin-static/ (directory: {admin_web_path})")
    except (OSError, ValueError) as exc:
        print(f"[SERVER] Warning: Could not mount admin web directory: {exc}")

    # /web se nesmí mountovat jako čistý StaticFiles — deep linky (/web/app/u/…/dashboard) by vracely 404 JSON.
    # Soubory pod /web obsluhuje system_router (spa_web_deep_shell + FileResponse).
    try:
        web_path = Path(__file__).parent.parent.parent / "web"
        if web_path.exists():
            print(
                "[SERVER] Web SPA + statické soubory: GET/HEAD /web a /web/{path} "
                f"(FileResponse z {web_path}, viz system_router — bez mount StaticFiles na /web)"
            )
        else:
            print(f"[SERVER] WARNING: Web directory not found: {web_path}")
    except (OSError, ValueError) as exc:
        print(f"[SERVER] Warning: Could not verify web directory: {exc}")


def _register_lifecycle_hooks(app: FastAPI) -> None:
    @app.on_event("startup")
    async def _start_background_workers() -> None:
        global _reminder_notification_task, _license_subscription_task, _mdcr_open_data_schedule_task
        _validate_required_production_storage()
        db = SessionLocal()
        try:
            ensure_customer_account_state_schema(db)
            capabilities = get_capabilities(db)
            unavailable = [
                name
                for name, report in (capabilities.get("modules") or {}).items()
                if not report.get("available")
            ]
            if unavailable:
                print(f"[SCHEMA] WARNING: disabled modules until migrations run: {', '.join(unavailable)}")
            else:
                print("[SCHEMA] active modules verified")
            from src.modules.vehicle_hub.routers_v1.license_status import _ensure_subscription_schema

            if _ensure_subscription_schema(db, strict=False):
                print("[LICENSE_SUBSCRIPTION] schema check OK")
            else:
                print(
                    "[LICENSE_SUBSCRIPTION] WARNING: missing subscription tables. "
                    "Run: python3 scripts/migrate_database.py"
                )
        except Exception as exc:
            print(f"[LICENSE_SUBSCRIPTION] WARNING: schema check failed: {exc}")
        finally:
            db.close()

        if not ENABLE_REMINDER_NOTIFICATION_WORKER:
            print("[REMINDERS_WORKER] disabled (ENABLE_REMINDER_NOTIFICATION_WORKER=0)")
        elif _reminder_notification_task is None:
            _reminder_notification_task = asyncio.create_task(_reminder_notification_worker())
            print(f"[REMINDERS_WORKER] started (interval={REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC}s)")

        if not ENABLE_LICENSE_SUBSCRIPTION_WORKER:
            print("[LICENSE_SUBSCRIPTION_WORKER] disabled (ENABLE_LICENSE_SUBSCRIPTION_WORKER=0)")
        elif _license_subscription_task is None:
            _license_subscription_task = asyncio.create_task(_license_subscription_worker())
            print(f"[LICENSE_SUBSCRIPTION_WORKER] started (interval={LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC}s)")

        if not ENABLE_MDCR_OPEN_DATA_SCHEDULE_WORKER:
            print("[MDCR_SCHEDULE_WORKER] disabled (ENABLE_MDCR_OPEN_DATA_SCHEDULE_WORKER=0)")
        elif _mdcr_open_data_schedule_task is None:
            _mdcr_open_data_schedule_task = asyncio.create_task(_mdcr_open_data_schedule_worker())
            print(
                f"[MDCR_SCHEDULE_WORKER] started "
                f"(daily ~{MDCR_SCHEDULE_HOUR_PRAGUE:02d}:{MDCR_SCHEDULE_MINUTE_PRAGUE:02d} Europe/Prague; "
                f"pause via job mdcr.open_data.schedule)"
            )

    @app.on_event("shutdown")
    async def _stop_background_workers() -> None:
        global _reminder_notification_task, _license_subscription_task, _mdcr_open_data_schedule_task
        if _reminder_notification_task is not None:
            _reminder_notification_task.cancel()
            try:
                await _reminder_notification_task
            except asyncio.CancelledError:
                pass
            finally:
                _reminder_notification_task = None
            print("[REMINDERS_WORKER] stopped")

        if _license_subscription_task is not None:
            _license_subscription_task.cancel()
            try:
                await _license_subscription_task
            except asyncio.CancelledError:
                pass
            finally:
                _license_subscription_task = None
            print("[LICENSE_SUBSCRIPTION_WORKER] stopped")

        if _mdcr_open_data_schedule_task is not None:
            _mdcr_open_data_schedule_task.cancel()
            try:
                await _mdcr_open_data_schedule_task
            except asyncio.CancelledError:
                pass
            finally:
                _mdcr_open_data_schedule_task = None
            print("[MDCR_SCHEDULE_WORKER] stopped")


def create_app() -> FastAPI:
    app = FastAPI(title=APP_API_DISPLAY_NAME, version=APP_VERSION)
    _register_exception_handler(app)
    _register_middlewares(app)
    _include_feature_routers(app)
    _mount_static_directories(app)
    _register_lifecycle_hooks(app)
    return app


def init_version_history() -> None:
    try:
        from src.modules.vehicle_hub.models import VersionHistory
        from src.server.version import log_version_update, read_version

        db = SessionLocal()
        try:
            current_version = read_version()
            existing = db.query(VersionHistory).filter(VersionHistory.version == current_version).first()
            if not existing:
                log_version_update(
                    db=db,
                    version=current_version,
                    description="Kompletní redesign UI + zavedení verzování",
                )
                print(f"[SERVER] OK: Verze {current_version} zapisana do historie verzi")
            else:
                print(f"[SERVER] INFO: Verze {current_version} uz je v historii verzi")
        finally:
            db.close()
    except Exception as exc:
        print(f"[SERVER] Warning: Nelze inicializovat historii verzí: {exc}")
        import traceback

        traceback.print_exc()


def log_database_info() -> None:
    print("=" * 60)
    print("[DATABASE] Database Configuration")
    print("=" * 60)
    try:
        print(f"[DATABASE] Engine URL: {engine.url}")
        print(f"[DATABASE] Current working directory: {os.getcwd()}")

        if hasattr(engine.url, "database") and engine.url.database:
            db_path = engine.url.database
            abs_path = db_path if os.path.isabs(db_path) else os.path.abspath(db_path)
            print(f"[DATABASE] Database path (absolute): {abs_path}")
            if os.path.exists(abs_path):
                print(f"[DATABASE] ✅ Database file exists ({os.path.getsize(abs_path)} bytes)")
            else:
                print(f"[DATABASE] ⚠️  Database file does NOT exist: {abs_path}")
        else:
            print(f"[DATABASE] Database path: {engine.url}")
    except Exception as exc:
        print(f"[DATABASE] ERROR při získávání DB info: {exc}")
    print("=" * 60)
    print()


def initialize_process_runtime() -> None:
    try:
        init_version_history()
    except Exception as exc:
        print(f"[SERVER] Warning: Chyba při inicializaci historie verzí: {exc}")
    log_database_info()


def run_server(app: FastAPI) -> None:
    import uvicorn

    version = APP_VERSION
    version_name = APP_VERSION_NAME
    build_date = BUILD_DATE
    update_info = UPDATE_INFO

    print("=" * 60)
    print(f"[SERVER] 🚀 {APP_API_DISPLAY_NAME}")
    print(f"[SERVER] 📦 Verze: {version} ({version_name})")
    print(f"[SERVER] 📅 Datum buildu: {build_date}")
    print(f"[SERVER] 🔄 Aktualizace: {update_info}")
    print("=" * 60)
    print(f"[SERVER] Spouštím server na {LISTEN_HOST}:{PORT} (HOST v konfiguraci: {HOST})")
    print(f"[SERVER] Režim: {ENVIRONMENT}")
    print(f"[SERVER] CORS origins: {ALLOWED_ORIGINS}")
    print("")

    print("\n=== API ROUTES VERIFICATION ===")
    api_routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            if "/api/" in route.path:
                for method in sorted(route.methods):
                    if method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        api_routes.append(f"{method:6} {route.path}")

    if api_routes:
        print(f"Found {len(api_routes)} API routes:")
        for route in sorted(api_routes):
            print(f"  {route}")
    else:
        print("WARNING: No API routes found!")

    critical_routes = [
        "/api/v1/vehicles",
        "/api/v1/reminders",
        "/api/v1/reservations/my",
        "/api/v1/license/status",
    ]
    found_critical = []
    for route in app.routes:
        if hasattr(route, "path"):
            for critical in critical_routes:
                if route.path == critical or route.path.startswith(critical + "/"):
                    found_critical.append(critical)
                    break

    missing = set(critical_routes) - set(found_critical)
    if missing:
        print(f"\nWARNING: Missing critical routes: {missing}")
    else:
        print(f"\n✓ All critical routes found: {critical_routes}")

    print("\n=== LICENSE ROUTES VERIFICATION ===")
    license_routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            if "license" in route.path.lower():
                for method in sorted(route.methods):
                    if method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        license_routes.append(f"{method:6} {route.path}")

    if license_routes:
        print(f"Found {len(license_routes)} license route(s):")
        for route in sorted(license_routes):
            print(f"  {route}")
        if any("/api/v1/license/status" in r for r in license_routes):
            print("✓ /api/v1/license/status endpoint is registered")
        else:
            print("❌ WARNING: /api/v1/license/status NOT FOUND!")
    else:
        print("❌ WARNING: No license routes found!")

    print("=" * 40)
    print("")
    uvicorn.run(app, host=LISTEN_HOST, port=PORT)
