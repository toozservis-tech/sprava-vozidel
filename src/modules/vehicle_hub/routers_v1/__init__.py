"""
API Routery pro Správu vozidel (API v1)
Všechny endpointy pod prefixem /api/v1/
"""
from fastapi import APIRouter

from . import (
    tutorials,
    vehicles,
    vehicle_image,
    service_records,
    analytics,
    service_intake,
    reservations,
    reminders,
    reminder_settings,
    ai,
    services,
    vehicle_lifecycle,
    service_workspace,
    service_workspace_cases,
    bot,
    vin_lookup,
    ares_lookup,
    license_status,
    push,
    system_notifications,
    capabilities,
    admin_service_read,
)

# Hlavní router pro v1 API
api_router = APIRouter(prefix="/api/v1", tags=["api-v1"])

# vehicle_lifecycle (/vehicles/...) musí být před vehicles.router — jinak koncovky jako
# POST /vehicles/transfer-technical-refresh-before-claim kolidují s GET /vehicles/{vehicle_id}
# (Starlette PARTIAL match → HTTP 405 Method Not Allowed na POST).
api_router.include_router(vehicle_lifecycle.router)
api_router.include_router(tutorials.router)
api_router.include_router(vehicles.router)
api_router.include_router(vehicle_image.router)
api_router.include_router(service_records.router)
api_router.include_router(analytics.router)  # Náklady, kategorie, měsíční trendy
api_router.include_router(service_intake.router)
api_router.include_router(reservations.router)
api_router.include_router(reminders.router)
api_router.include_router(reminder_settings.router)  # Nastavení připomínek
api_router.include_router(services.router)
api_router.include_router(service_workspace.router)
api_router.include_router(service_workspace_cases.router)
from .service_workspace_customer_centre import router as service_workspace_customer_centre_router

api_router.include_router(service_workspace_customer_centre_router, prefix="/services/workspace")
api_router.include_router(ai.router)
api_router.include_router(bot.router)  # AI Asistent Bot
api_router.include_router(vin_lookup.router)  # VIN lookup
api_router.include_router(ares_lookup.router)  # ARES lookup
api_router.include_router(push.router)  # Web Push notifications
api_router.include_router(system_notifications.router)  # System notifications
api_router.include_router(capabilities.router)  # Runtime capabilities
api_router.include_router(admin_service_read.router)

# License status router - explicitní kontrola
try:
    api_router.include_router(license_status.router)  # License status
    print(f"[ROUTERS_V1] ✓ License status router zaregistrován (prefix: {license_status.router.prefix})")
except Exception as e:
    print(f"[ROUTERS_V1] ❌ ERROR při registraci license_status routeru: {e}")
    import traceback
    traceback.print_exc()

__all__ = ["api_router"]
