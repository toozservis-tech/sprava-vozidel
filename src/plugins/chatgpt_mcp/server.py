from __future__ import annotations

import os
from typing import Any, Callable

from mcp.server import MCPServer

from src.modules.vehicle_hub.database import SessionLocal
from src.plugins.chatgpt_mcp import service


MCP_HOST = str(os.getenv("CHATGPT_MCP_HOST") or "127.0.0.1").strip()
MCP_PORT = int(str(os.getenv("CHATGPT_MCP_PORT") or "8011").strip())
_PRIVATE_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}

mcp = MCPServer(
    "TooZ Mechanic",
    version="0.1.0",
    instructions=(
        "Pracovní plugin pro autoservis. Používej VIN/SPZ pouze k vyhledání vozidla, "
        "nikdy neprozrazuj osobní údaje majitele. Před zápisem servisního záznamu musí existovat "
        "schválený přístup servisu k vozidlu. Diagnostické závěry vždy odděluj od naměřených faktů. "
        "Nevytvářej duplicitní servisní případ, měření práce ani finální servisní záznam."
    ),
)


def _assert_private_bind() -> None:
    """v0.1 používá pevnou servisní identitu; nesmí být přímo vystavena do veřejné sítě."""
    if MCP_HOST.lower() not in _PRIVATE_BIND_HOSTS:
        raise RuntimeError(
            "TooZ Mechanic v0.1 smí poslouchat pouze na loopbacku. "
            "Použijte Secure MCP Tunnel. Veřejný endpoint vyžaduje OAuth variantu."
        )


def _call(fn: Callable[..., dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
    db = SessionLocal()
    try:
        return fn(db, **kwargs)
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        detail = getattr(exc, "detail", None)
        if detail:
            raise RuntimeError(str(detail)) from exc
        raise RuntimeError(str(exc)) from exc
    finally:
        db.close()


@mcp.tool(description="Ověří, zda je TooZ Mechanic připravený, kdo je servisní operátor a kolik má dostupných vozidel/případů. Nemění servisní data.")
def tooz_status() -> dict[str, Any]:
    return _call(service.plugin_status)


@mcp.tool(description="Vrátí vozidla, ke kterým má přihlášený servis schválený přístup. Nevrací osobní údaje majitelů.")
def tooz_my_vehicles(limit: int = 20) -> dict[str, Any]:
    return _call(service.list_assigned_vehicles, limit=limit)


@mcp.tool(description="Vyhledá vozidlo podle VIN nebo SPZ. Bez schváleného přístupu vrátí jen maskované identifikátory a stav oprávnění. Lookup se auditně zaznamená.")
def tooz_find_vehicle(query: str) -> dict[str, Any]:
    return _call(service.lookup_vehicle, query=query)


@mcp.tool(description="Načte technický a servisní kontext schváleného vozidla: identifikaci auta, servisní historii, km a servisní případy. Nevrací osobní údaje majitele.")
def tooz_vehicle_context(vehicle_id: int, history_limit: int = 12) -> dict[str, Any]:
    return _call(service.vehicle_context, vehicle_id=vehicle_id, history_limit=history_limit)


@mcp.tool(description="Založí nový servisní případ k vozidlu, ke kterému má servis schválený přístup. Pokud už existuje otevřený případ, vrátí jej místo vytvoření duplicity.")
def tooz_create_service_case(
    vehicle_id: int,
    customer_request: str,
    mileage_km: int | None = None,
    intake_note: str | None = None,
) -> dict[str, Any]:
    return _call(
        service.create_service_case,
        vehicle_id=vehicle_id,
        customer_request=customer_request,
        mileage_km=mileage_km,
        intake_note=intake_note,
    )


@mcp.tool(description="Uloží strukturovanou diagnostiku do existujícího servisního případu: příznaky, DTC, skutečná měření a závěr. Zápis je auditovaný.")
def tooz_record_diagnosis(
    case_id: int,
    symptoms: list[str] | None = None,
    dtcs: list[str] | None = None,
    measurements: list[dict[str, Any]] | None = None,
    conclusion: str | None = None,
    internal_note: str | None = None,
    visible_to_owner_note: str | None = None,
) -> dict[str, Any]:
    return _call(
        service.record_diagnosis,
        case_id=case_id,
        symptoms=symptoms,
        dtcs=dtcs,
        measurements=measurements,
        conclusion=conclusion,
        internal_note=internal_note,
        visible_to_owner_note=visible_to_owner_note,
    )


@mcp.tool(description="Spustí měření času práce na servisním případu. Opakované spuštění nevytvoří druhé paralelní měření.")
def tooz_start_work(case_id: int) -> dict[str, Any]:
    return _call(service.start_work, case_id=case_id)


@mcp.tool(description="Zastaví aktuální měření práce a přepočítá celkový čas případu. Když nic neběží, vrátí bezpečný stav bez chyby a bez zápisu duplicity.")
def tooz_stop_work(case_id: int) -> dict[str, Any]:
    return _call(service.stop_work, case_id=case_id)


@mcp.tool(description="Uzavře servisní případ do ověřeného servisního záznamu, zapíše km a audit. Druhé volání nad stejným případem vrátí existující záznam místo vytvoření duplicity.")
def tooz_finalize_service_record(
    case_id: int,
    description: str,
    category: str = "diagnostics",
    mileage_km: int | None = None,
    price: float | None = None,
    repair_summary: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return _call(
        service.finalize_service_record,
        case_id=case_id,
        description=description,
        category=category,
        mileage_km=mileage_km,
        price=price,
        repair_summary=repair_summary,
        note=note,
    )


if __name__ == "__main__":
    _assert_private_bind()
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )
