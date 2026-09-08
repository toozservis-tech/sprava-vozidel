from __future__ import annotations

import pytest
from mcp import Client

from src.plugins.chatgpt_mcp.server import mcp


EXPECTED_TOOLS = {
    "tooz_status",
    "tooz_my_vehicles",
    "tooz_find_vehicle",
    "tooz_vehicle_context",
    "tooz_create_service_case",
    "tooz_record_diagnosis",
    "tooz_start_work",
    "tooz_stop_work",
    "tooz_finalize_service_record",
}


@pytest.mark.asyncio
async def test_mcp_contract_exposes_exact_workshop_tools():
    async with Client(mcp) as client:
        result = await client.list_tools()

    tools = {tool.name: tool for tool in result.tools}
    assert set(tools) == EXPECTED_TOOLS

    assert tools["tooz_status"].annotations.read_only_hint is True
    assert tools["tooz_find_vehicle"].annotations.read_only_hint is True
    assert tools["tooz_vehicle_context"].annotations.read_only_hint is True

    for name in {
        "tooz_create_service_case",
        "tooz_start_work",
        "tooz_stop_work",
        "tooz_finalize_service_record",
    }:
        assert tools[name].annotations.read_only_hint is False
        assert tools[name].annotations.destructive_hint is False
        assert tools[name].annotations.idempotent_hint is True
        assert tools[name].annotations.open_world_hint is False

    diagnosis = tools["tooz_record_diagnosis"]
    assert diagnosis.annotations.read_only_hint is False
    assert diagnosis.annotations.destructive_hint is False
    assert diagnosis.annotations.idempotent_hint is False


def test_mcp_contract_has_required_write_parameters():
    # Schema je přesně to, co ChatGPT skenuje před zpřístupněním nástroje.
    import asyncio

    async def _load():
        async with Client(mcp) as client:
            return await client.list_tools()

    result = asyncio.run(_load())
    tools = {tool.name: tool for tool in result.tools}

    create_required = set(tools["tooz_create_service_case"].input_schema.get("required", []))
    finalize_required = set(tools["tooz_finalize_service_record"].input_schema.get("required", []))

    assert {"vehicle_id", "customer_request"}.issubset(create_required)
    assert {"case_id", "description"}.issubset(finalize_required)
