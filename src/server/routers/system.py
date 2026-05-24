from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import func

from src.core.auth import get_current_user_email
from src.core.branding import APP_API_DISPLAY_NAME, APP_DISPLAY_NAME, APP_OPS_PROJECT_LABEL
from src.core.config import (
    DATABASE_URL,
    ENABLE_AI_FEATURES,
    ENABLE_AUTOPILOT_API,
    ENABLE_CUSTOMER_COMMANDS,
    ENVIRONMENT,
    HAS_LEGACY_APP_DATA_DB,
    LEGACY_APP_DATA_DB_DRIFT,
    LEGACY_APP_DATA_DB_PATH,
    LEGACY_APP_DATA_DB_REALPATH,
    PRODUCTION_LOCK_MODE,
    RUNTIME_DB_PATH,
)
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, Vehicle as VehicleModel, VehicleOwnership
from src.server.main_helpers import APP_VERSION, APP_VERSION_NAME, BUILD_DATE, UPDATE_INFO


router = APIRouter()
public_path = Path(__file__).parent.parent.parent.parent / "public_share"
public_path.mkdir(parents=True, exist_ok=True)
web_path = Path(__file__).parent.parent.parent.parent / "web"


def _version_context() -> tuple[str, str, str, str]:
    try:
        from VERSION import __build_date__, __update_info__, __version__, __version_name__

        return __version__, __version_name__, __build_date__, __update_info__
    except ImportError:
        return APP_VERSION, APP_VERSION_NAME, BUILD_DATE, UPDATE_INFO


@router.get("/public/", response_class=HTMLResponse)
@router.get("/public/{path:path}", response_class=HTMLResponse)
def public_file_list(path: str = ""):
    path_clean = path.strip("/") if path else ""
    path_parts = [p for p in path_clean.split("/") if p and p != "." and p != ".."]
    target_path = public_path
    if path_parts:
        target_path = public_path / "/".join(path_parts)

    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(public_path.resolve())):
            raise HTTPException(status_code=403, detail="Neplatná cesta")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Cesta nenalezena") from exc

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Cesta neexistuje")

    if target_path.is_file():
        return FileResponse(target_path)

    items = []
    try:
        for item in sorted(target_path.iterdir()):
            if item.name.startswith("."):
                continue

            rel_path = str(item.relative_to(public_path)).replace("\\", "/")
            size = ""
            if item.is_file():
                size_bytes = item.stat().st_size
                if size_bytes < 1024:
                    size = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size = f"{size_bytes / 1024:.1f} KB"
                else:
                    size = f"{size_bytes / (1024 * 1024):.1f} MB"

            items.append(
                {
                    "name": item.name,
                    "path": rel_path,
                    "is_dir": item.is_dir(),
                    "size": size,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                }
            )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Přístup zamítnut") from exc

    breadcrumb = '<a href="/public/">🏠 Kořen</a>'
    current_breadcrumb_path = ""
    for part in path_parts:
        current_breadcrumb_path += "/" + part
        breadcrumb += f' / <a href="/public{current_breadcrumb_path}/">{part}</a>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Veřejné soubory - {APP_DISPLAY_NAME}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                font-size: 2em;
                margin-bottom: 10px;
            }}
            .breadcrumb {{
                background: #f8f9fa;
                padding: 15px 30px;
                border-bottom: 1px solid #dee2e6;
                font-size: 14px;
            }}
            .breadcrumb a {{
                color: #667eea;
                text-decoration: none;
            }}
            .breadcrumb a:hover {{
                text-decoration: underline;
            }}
            .file-list {{
                padding: 30px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th {{
                background: #f8f9fa;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                color: #495057;
                border-bottom: 2px solid #dee2e6;
            }}
            td {{
                padding: 15px;
                border-bottom: 1px solid #f0f0f0;
            }}
            tr:hover {{
                background: #f8f9fa;
            }}
            .folder {{
                color: #ff9800;
                font-weight: bold;
            }}
            .folder::before {{
                content: "📁 ";
            }}
            .file {{
                color: #2196F3;
            }}
            .file::before {{
                content: "📄 ";
            }}
            a {{
                color: inherit;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .size {{
                color: #6c757d;
                font-size: 0.9em;
            }}
            .modified {{
                color: #6c757d;
                font-size: 0.9em;
            }}
            .empty {{
                text-align: center;
                padding: 60px 20px;
                color: #6c757d;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📁 Veřejné soubory</h1>
                <p>{APP_DISPLAY_NAME} - Veřejné soubory</p>
            </div>
            <div class="breadcrumb">
                {breadcrumb}
            </div>
            <div class="file-list">
    """

    if items:
        html += """
                <table>
                    <thead>
                        <tr>
                            <th>Název</th>
                            <th>Velikost</th>
                            <th>Upraveno</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for item in items:
            if item["is_dir"]:
                link = f'/public/{item["path"]}/'
                html += f"""
                        <tr>
                            <td class="folder"><a href="{link}">{item["name"]}</a></td>
                            <td class="size">-</td>
                            <td class="modified">{item["modified"]}</td>
                        </tr>
                """
            else:
                link = f'/public/{item["path"]}'
                html += f"""
                        <tr>
                            <td class="file"><a href="{link}" target="_blank">{item["name"]}</a></td>
                            <td class="size">{item["size"]}</td>
                            <td class="modified">{item["modified"]}</td>
                        </tr>
                """

        html += """
                    </tbody>
                </table>
        """
    else:
        html += """
                <div class="empty">
                    <p>📂 Tato složka je prázdná</p>
                </div>
        """

    html += """
            </div>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(content=html)


@router.get("/")
def root():
    return RedirectResponse(url="/web/index.html", status_code=302)


def _shell_index_canonical_path() -> Path:
    return (web_path / "index.html").resolve()


def _apply_shell_index_headers(response: FileResponse, index_path: Path) -> None:
    """Hlavičky pro HTML shell (+ diagnostika při porovnávání, co telefon opravdu stáhl)."""
    try:
        response.headers["X-Shell-Index-Mtime"] = str(int(index_path.stat().st_mtime))
    except OSError:
        pass
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Surrogate-Control"] = "no-store"


def _spa_index_response() -> FileResponse:
    index_path = web_path / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Web interface není k dispozici")
    response = FileResponse(index_path)
    _apply_shell_index_headers(response, index_path)
    return response


# Přípony skutečných statických souborů: chybějící soubor = 404 (ne SPA shell).
_ASSET_FILE_SUFFIXES: tuple[str, ...] = (
    ".js",
    ".mjs",
    ".css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".json",
    ".xml",
    ".txt",
    ".pdf",
    ".wasm",
    ".webmanifest",
)


def _serve_web_relative_file_or_spa(relative_path: str) -> FileResponse:
    """
    Obsluha cest pod /web/…: existující soubor z disku, jinak SPA index (deep link).
    Chybějící soubor s typickou příponou assetu → 404 (aby se nevracel HTML místo 404 u /web/assets/…).
    """
    rel = (relative_path or "").strip().lstrip("/")
    if ".." in rel.split("/"):
        raise HTTPException(status_code=403, detail="Neplatná cesta")
    base = web_path.resolve()
    target = (web_path / rel).resolve()
    if not str(target).startswith(str(base)):
        raise HTTPException(status_code=403, detail="Neplatná cesta")
    if target.is_file():
        # GET /web/index.html jinak vracel holý FileResponse bez no-store → CDN/prohlížeč mohly držet starší shell.
        if target.resolve() == _shell_index_canonical_path():
            response = FileResponse(target)
            _apply_shell_index_headers(response, target)
            return response
        return FileResponse(target)
    if target.is_dir():
        nested = target / "index.html"
        if nested.is_file():
            return FileResponse(nested)
        raise HTTPException(status_code=404, detail="Not Found")
    lower = rel.lower()
    if any(lower.endswith(sfx) for sfx in _ASSET_FILE_SUFFIXES):
        raise HTTPException(status_code=404, detail="Not Found")
    return _spa_index_response()


@router.api_route("/web", methods=["GET", "HEAD"])
@router.api_route("/web/", methods=["GET", "HEAD"])
def spa_web_root_shell():
    """SPA shell pro /web a /web/ (F5, přímý vstup)."""
    return _spa_index_response()


@router.api_route("/web/{full_path:path}", methods=["GET", "HEAD"])
def spa_web_deep_shell(full_path: str):
    """
    Veškerý obsah pod /web kromě skutečných souborů → index.html (deep linky /web/app/…).
    Musí být registrováno před mountem StaticFiles na /web (mount je odstraněn — viz bootstrap).
    """
    return _serve_web_relative_file_or_spa(full_path)


@router.get("/login")
@router.get("/register")
@router.get("/forgot-password")
@router.get("/funkce")
@router.get("/pro-koho")
@router.get("/kontakt")
def spa_public_shell():
    """Deep-link friendly HTML shell (routing řeší SPA v prohlížeči)."""
    return _spa_index_response()


@router.get("/favicon.ico")
def favicon_redirect():
    icon_path = web_path / "assets" / "toozservis-logo-icon.png"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Not Found")


@router.api_route("/app", methods=["GET", "HEAD"])
@router.api_route("/app/", methods=["GET", "HEAD"])
def spa_app_root_shell():
    """Kořen /app po reloadu (bez další cesty)."""
    return _spa_index_response()


@router.api_route("/app/{full_path:path}", methods=["GET", "HEAD"])
def spa_app_workspace_shell(full_path: str):
    """Privátní /app/... URL musí vrátit index.html, aby SPA mohla načíst stav z relace."""
    return _spa_index_response()


@router.get("/verify/{token:path}")
def verify_document_page(token: str = ""):
    verify_page = web_path / "verify.html"
    if not verify_page.exists():
        raise HTTPException(status_code=404, detail="Ověřovací stránka není dostupná")
    return FileResponse(verify_page)


@router.get("/api")
def api_root():
    version, version_name, build_date, update_info = _version_context()
    return {
        "message": APP_API_DISPLAY_NAME,
        "version": version,
        "version_name": version_name,
        "build_date": build_date,
        "update_info": update_info,
        "environment": ENVIRONMENT,
        "features": {
            "jwt_auth": True,
            "bcrypt_passwords": True,
            "vehicles": True,
            "vin_decoder": True,
            "ai_features": ENABLE_AI_FEATURES,
            "customer_commands": ENABLE_CUSTOMER_COMMANDS,
            "autopilot_api": ENABLE_AUTOPILOT_API,
        },
        "endpoints": {
            "register": "/user/register",
            "register_service_request": "/user/register/service-request",
            "login": "/user/login",
            "me": "/api/me",
            "me_legacy": "/user/me",
            "me_export": "/user/me/export",
            "me_delete": "/user/me",
            "ares": "/user/ares?ico=ICO",
            "support": "/user/support",
            "vehicles": "/api/v1/vehicles",
            "decode_vin": "/api/vehicles/decode-vin",
        },
        "web_interface": "/web/index.html" if Path(__file__).parent.parent.parent.parent.joinpath("web").exists() else None,
    }


@router.get("/health")
@router.options("/health")
def health_check():
    version, version_name, build_date, update_info = _version_context()
    return {
        "status": "ok",
        "project": APP_OPS_PROJECT_LABEL,
        "service": APP_API_DISPLAY_NAME,
        "version": version,
        "version_name": version_name,
        "build_date": build_date,
        "update_info": update_info,
        "environment": ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/config")
@router.options("/health/config")
def health_config():
    try:
        from src.core.config_validator import validate_config

        is_valid, config_status, missing_keys = validate_config()
        return {
            "status": "ok" if is_valid else "warning",
            "environment": config_status["environment"],
            "jwt_configured": config_status["jwt_configured"],
            "dataovo_configured": config_status["dataovo_configured"],
            "smtp_configured": config_status["smtp_configured"],
            "env_file_exists": config_status["env_file_exists"],
            "env_file_readable": config_status["env_file_readable"],
            "env_file_path": config_status["env_file_path"],
            "missing_keys": missing_keys,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/version")
def get_version():
    try:
        from src.server.version import get_version_info

        return get_version_info()
    except Exception:
        version, _, _, _ = _version_context()
        return {
            "project": APP_DISPLAY_NAME,
            "version": version,
            "build_time": datetime.now().isoformat(),
        }


@router.get("/api/_debug/routes")
def debug_routes(request: Request, current_user_email: str = Depends(get_current_user_email)):
    if PRODUCTION_LOCK_MODE:
        raise HTTPException(status_code=404, detail="Not Found")
    routes_list = []
    for route in request.app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            for method in sorted(route.methods):
                if method in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]:
                    routes_list.append({"method": method, "path": route.path})

    routes_list.sort(key=lambda x: x["path"])
    return {
        "total_routes": len(routes_list),
        "routes": routes_list,
        "api_v1_routes": [r for r in routes_list if "/api/v1/" in r["path"]],
        "vehicles_routes": [r for r in routes_list if "/vehicles" in r["path"]],
        "user_email": current_user_email,
    }


@router.get("/api/_debug/db_stats")
def debug_db_stats(
    current_user_email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    if PRODUCTION_LOCK_MODE:
        raise HTTPException(status_code=404, detail="Not Found")
    db_url = DATABASE_URL
    cwd = str(Path.cwd())

    if db_url.startswith("sqlite"):
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = os.path.join(cwd, db_path)
        else:
            db_path = db_url
        db_exists = os.path.exists(db_path)
        db_size = os.path.getsize(db_path) if db_exists else 0
    else:
        db_path = db_url
        db_exists = True
        db_size = None

    legacy_db_path = str(LEGACY_APP_DATA_DB_PATH)
    legacy_db_realpath = str(LEGACY_APP_DATA_DB_REALPATH) if LEGACY_APP_DATA_DB_REALPATH else None
    runtime_db_realpath = str(RUNTIME_DB_PATH) if RUNTIME_DB_PATH else None
    legacy_db_exists = bool(HAS_LEGACY_APP_DATA_DB)
    legacy_db_size = None
    if legacy_db_exists:
        try:
            legacy_db_size = os.path.getsize(legacy_db_path)
        except OSError:
            legacy_db_size = None

    try:
        vehicles_total = db.query(VehicleModel).filter(VehicleModel.status != "archived").count()
        users_total = db.query(Customer).count()
        current_user = db.query(Customer).filter(Customer.email == current_user_email).first()

        vehicles_for_user = 0
        vehicles_for_user_with_tenant = 0
        vehicles_user_emails: list[str] = []
        if current_user:
            vehicles_for_user = (
                db.query(func.count(func.distinct(VehicleOwnership.vehicle_id)))
                .filter(
                    VehicleOwnership.customer_id == current_user.id,
                    VehicleOwnership.is_active.is_(True),
                )
                .scalar()
                or 0
            )
            tenant_filter = [VehicleOwnership.customer_id == current_user.id, VehicleOwnership.is_active.is_(True)]
            if current_user.tenant_id:
                tenant_filter.append(VehicleOwnership.tenant_id == current_user.tenant_id)
            vehicles_for_user_with_tenant = (
                db.query(func.count(func.distinct(VehicleOwnership.vehicle_id)))
                .filter(*tenant_filter)
                .scalar()
                or 0
            )

        owner_rows = (
            db.query(Customer.email)
            .join(VehicleOwnership, VehicleOwnership.customer_id == Customer.id)
            .filter(VehicleOwnership.is_active.is_(True))
            .distinct()
            .all()
        )
        vehicles_user_emails = [row[0] for row in owner_rows if row and row[0]]
        vehicles_tenant_ids = db.query(VehicleModel.tenant_id).distinct().all()
        vehicles_tenant_ids_list = [tid[0] for tid in vehicles_tenant_ids if tid[0] is not None]

        return {
            "db_url": db_url,
            "db_path": db_path,
            "runtime_db_realpath": runtime_db_realpath,
            "db_exists": db_exists,
            "db_size": db_size,
            "legacy_app_data_db": {
                "path": legacy_db_path,
                "realpath": legacy_db_realpath,
                "exists": legacy_db_exists,
                "size_bytes": legacy_db_size,
                "drift_from_runtime_db": bool(LEGACY_APP_DATA_DB_DRIFT),
            },
            "cwd": cwd,
            "vehicles_total": vehicles_total,
            "vehicles_for_user": int(vehicles_for_user),
            "vehicles_for_user_with_tenant": int(vehicles_for_user_with_tenant),
            "users_total": users_total,
            "current_user_email": current_user_email,
            "current_user_tenant_id": getattr(current_user, "tenant_id", None) if current_user else None,
            "vehicles_user_emails": vehicles_user_emails,
            "vehicles_tenant_ids": vehicles_tenant_ids_list,
        }
    except Exception as exc:
        import traceback

        return {
            "db_url": db_url,
            "db_path": db_path,
            "runtime_db_realpath": runtime_db_realpath,
            "db_exists": db_exists,
            "db_size": db_size,
            "legacy_app_data_db": {
                "path": legacy_db_path,
                "realpath": legacy_db_realpath,
                "exists": legacy_db_exists,
                "size_bytes": legacy_db_size,
                "drift_from_runtime_db": bool(LEGACY_APP_DATA_DB_DRIFT),
            },
            "cwd": cwd,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


@router.get("/version/history")
def get_version_history(db=Depends(get_db)):
    try:
        from src.modules.vehicle_hub.models import VersionHistory

        history = db.query(VersionHistory).order_by(VersionHistory.applied_at.desc()).all()
        return {
            "history": [
                {
                    "id": entry.id,
                    "version": entry.version,
                    "description": entry.description,
                    "applied_at": entry.applied_at.isoformat() if entry.applied_at else None,
                }
                for entry in history
            ],
            "total": len(history),
        }
    except Exception as exc:
        print(f"[VERSION] Warning: Nelze načíst historii verzí: {exc}")
        return {
            "history": [],
            "total": 0,
            "error": "Historie verzí není dostupná",
        }
