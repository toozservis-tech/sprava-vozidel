from __future__ import annotations

import os
from typing import Any, Callable

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from src.modules.vehicle_hub.database import SessionLocal
from src.plugins.chatgpt_mcp import service


MCP_HOST = str(os.getenv("CHATGPT_MCP_HOST") or "127.0.0.1").strip()
MCP_PORT = int(str(os.getenv("CHATGPT_MCP_PORT") or "8011").strip())
_PRIVATE_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_SAFE_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_NON_DESTRUCTIVE_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=False,
)

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


@mcp.tool(
    title="Stav TooZ Mechanic",
    description="Ověří připravenost pluginu a počet dostupných vozidel/případů. Nemění servisní data.",
    annotations=_READ_ONLY,
)
def tooz_status() -> dict[str, Any]:
    return _call(service.plugin_status)


@mcp.tool(
    title="Moje servisní vozidla",
    description="Vrátí vozidla, ke kterým má servis schválený přístup. Nevrací osobní údaje majitelů.",
    annotations=_READ_ONLY,
)
def tooz_my_vehicles(limit: int = 20) -> dict[str, Any]:
    return _call(service.list_assigned_vehicles, limit=limit)


@mcp.tool(
    title="Najít vozidlo podle VIN nebo SPZ",
    description="Vyhledá vozidlo podle VIN nebo SPZ. Bez schváleného přístupu vrátí pouze maskované identifikátory a stav oprávnění. Lookup se auditně zaznamená.",
    annotations=_READ_ONLY,
)
def tooz_find_vehicle(query: str) -> dict[str, Any]:
    return _call(service.lookup_vehicle, query=query)


@mcp.tool(
    title="Otevřít servisní kontext vozidla",
    description="Načte technická data, servisní historii, km a servisní případy schváleného vozidla bez osobních údajů majitele.",
    annotations=_READ_ONLY,
)
def tooz_vehicle_context(vehicle_id: int, history_limit: int = 12) -> dict[str, Any]:
    return _call(service.vehicle_context, vehicle_id=vehicle_id, history_limit=history_limit)


@mcp.tool(
    title="Založit servisní případ",
    description="Založí nový servisní případ ke schválenému vozidlu. Pokud už je otevřený, vrátí existující případ místo duplicity.",
    annotations=_SAFE_WRITE,
)
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


@mcp.tool(
    title="Uložit diagnostiku",
    description="Uloží příznaky, DTC, skutečná měření a diagnostický závěr do existujícího servisního případu. Zápis je auditovaný a nic nemaže.",
    annotations=_NON_DESTRUCTIVE_WRITE,
)
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


@mcp.tool(
    title="Spustit čas práce",
    description="Spustí měření práce na servisním případu. Opakované spuštění nevytvoří druhý paralelní timer.",
    annotations=_SAFE_WRITE,
)
def tooz_start_work(case_id: int) -> dict[str, Any]:
    return _call(service.start_work, case_id=case_id)


@mcp.tool(
    title="Zastavit čas práce",
    description="Zastaví aktuální měření a přepočítá celkový čas. Když nic neběží, vrátí bezpečný stav bez duplicity.",
    annotations=_SAFE_WRITE,
)
def tooz_stop_work(case_id: int) -> dict[str, Any]:
    return _call(service.stop_work, case_id=case_id)


@mcp.tool(
    title="Dokončit servisní záznam",
    description="Uzavře případ do ověřeného servisního záznamu, zapíše km a audit. Opakované volání vrátí existující record ID místo vytvoření duplicity.",
    annotations=_SAFE_WRITE,
)
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
