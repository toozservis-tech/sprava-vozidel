from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_vehicle_delete_cannot_bypass_lifecycle_flow() -> None:
    source = read("src/modules/vehicle_hub/routers_v1/vehicles.py")
    assert '@router.delete("/{vehicle_id}")' in source
    start = source.index('@router.delete("/{vehicle_id}")')
    delete_block = source[start : start + 1200]
    assert "remove/init" in delete_block
    assert "remove/confirm" in delete_block
    assert "status_code=409" in delete_block


def test_service_record_requires_approved_service_access() -> None:
    canonical = read("src/modules/vehicle_hub/routers_v1/service_canonical.py")
    records = read("src/modules/vehicle_hub/routers_v1/service_records.py")
    access = read("src/modules/vehicle_hub/service_access.py")
    assert "require_service_vehicle_link" in canonical
    assert "require_create_record=True" in canonical
    assert "service_record_created_from_intake" in canonical
    assert "require_service_vehicle_link" in records
    assert "status == \"approved\"" in access or "status != \"approved\"" in access


def test_api_me_workspace_contract_fields_are_locked() -> None:
    source = read("src/server/routers/session_me.py")
    for field in ["workspace_route_kind", "default_app_path", "account_type", "account_slug"]:
        assert field in source
    assert "@router.get(\"/api/me\")" in source
    assert "build_default_app_path" in source
    assert "resolve_workspace_route_kind_for_customer" in source


def test_vehicle_lifecycle_response_structure_is_locked() -> None:
    source = read("src/modules/vehicle_hub/routers_v1/vehicle_lifecycle.py")
    for endpoint in [
        "@router.post(\"/{vehicle_id}/remove/init\")",
        "@router.post(\"/{vehicle_id}/remove/confirm\")",
        "@router.post(\"/claim-by-transfer\")",
        "@router.post(\"/transfer-claim\")",
        "@router.post(\"/transfer-technical-refresh-before-claim\")",
        "@router.get(\"/{vehicle_id}/digital-report\")",
    ]:
        assert endpoint in source
    for key in [
        "required_followup_field",
        "required_followup_fields",
        "will_generate_digital_report",
        "archive_bundle_path",
        "digital_report_url",
        "transfer",
        "history_preserved",
        "claimed",
    ]:
        assert key in source


def test_transfer_tokens_are_hash_only() -> None:
    source = read("src/modules/vehicle_hub/routers_v1/vehicle_lifecycle.py")
    assert "token_hash=_token_hash(raw_token)" in source
    assert "VehicleTransferToken.token_hash == _token_hash" in source
    assert "claimed_by_user_id" in source
    assert "transfer_token_claimed" in source


def test_critical_audit_events_are_present() -> None:
    lifecycle = read("src/modules/vehicle_hub/routers_v1/vehicle_lifecycle.py")
    canonical = read("src/modules/vehicle_hub/routers_v1/service_canonical.py")
    session_me = read("src/server/routers/session_me.py")
    for action in [
        "transfer_token_issued",
        "digital_report_generated",
        "vehicle_removed_archived",
        "transfer_token_claimed",
    ]:
        assert action in lifecycle
    assert "transfer_technical_overview_pre_claim_refresh" in lifecycle
    assert "perform_transfer_technical_refresh_before_claim" in lifecycle
    for action in [
        "service_intake_created_from_spz_photo",
        "service_access_requested_from_intake",
        "labor_started",
        "labor_stopped",
        "service_record_created_from_intake",
    ]:
        assert action in canonical
    assert "workspace_route_denied" in session_me


def test_production_storage_and_lock_mode_guards_are_registered() -> None:
    bootstrap = read("src/server/bootstrap.py")
    config = read("src/core/config.py")
    assert "REQUIRED_PRODUCTION_STORAGE_DIRS" in bootstrap
    assert "_validate_required_production_storage()" in bootstrap
    assert "ProductionLockWriteAuditMiddleware" in bootstrap
    assert "PRODUCTION_LOCK_MODE" in config
    assert "workspace debug router disabled" in bootstrap


def test_admin_vehicle_lifecycle_router_is_dual_mounted() -> None:
    bootstrap = read("src/server/bootstrap.py")
    assert 'app.include_router(admin_vehicle_lifecycle_router, prefix="/admin-api")' in bootstrap
    assert 'app.include_router(admin_vehicle_lifecycle_router, prefix="/api/admin")' in bootstrap
    assert 'app.include_router(admin_vehicle_support_router, prefix="/admin-api")' in bootstrap
    assert 'app.include_router(admin_vehicle_support_router, prefix="/api/admin")' not in bootstrap


def test_admin_path_prefixes_include_api_admin_alias() -> None:
    mw = read("src/core/security_middleware.py")
    assert "_ADMIN_PATH_PREFIXES" in mw
    assert '"/api/admin"' in mw


def test_admin_vehicle_lifecycle_list_is_removal_event_backed_not_all_vehicles() -> None:
    admin_lc = read("src/server/admin_vehicle_lifecycle.py")
    assert (
        "db.query(VehicleRemovalEvent, Vehicle).join(Vehicle, Vehicle.id == VehicleRemovalEvent.vehicle_id)"
        in admin_lc
    )
    assert "require_developer_admin" in admin_lc


def test_admin_vehicle_lifecycle_revoke_does_not_delete_vehicle() -> None:
    """Kontrola zdroje: revoke mění jen status tokenu + audit, bez mazání řádků vozidla."""
    admin_lc = read("src/server/admin_vehicle_lifecycle.py")
    assert 'tok.status = "revoked"' in admin_lc
    assert ".delete(" not in admin_lc


def test_public_vehicle_transfer_get_never_returns_vehicle_id_or_plain_spz() -> None:
    pub = read("src/server/routers/public_vehicle_transfer.py")
    assert '"vehicle_id"' not in pub.split("return {")[1].split("@router.post")[0]
    assert "spz_masked" in pub
    assert "_mask_spz_public" in pub
