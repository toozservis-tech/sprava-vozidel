from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_head_creates_active_schema(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    db_path = tmp_path / "migration_smoke.sqlite"
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(alembic_cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert "vehicle_ownerships" in tables
    assert "vehicle_tachometer_history_entries" in tables
    assert "vehicle_orv_scans" in tables
    assert "service_record_audit_logs" in tables
    assert "service_work_orders" in tables
    assert "service_work_order_audit_logs" in tables
    assert "service_access_requests" in tables
    assert "vehicle_service_links" in tables
    assert "service_vehicle_lookup_audit" in tables
    assert "license_subscriptions" in tables
    assert "license_payment_transactions" in tables
    assert "push_subscriptions" in tables
    assert "system_notifications" in tables

    service_record_columns = {col["name"] for col in inspector.get_columns("service_records")}
    assert {
        "is_deleted",
        "deleted_at",
        "deleted_by_user_id",
        "deletion_reason",
        "snapshot_hash",
        "created_by_service_customer_id",
        "service_access_link_id",
    } <= service_record_columns

    vehicle_columns = {col["name"] for col in inspector.get_columns("vehicles")}
    assert {
        "photo_path",
        "current_mileage_km",
        "last_stk_mileage_km",
        "mileage_checked_at",
        "orv_number",
        "orv_scan_source",
        "orv_front_image_path",
        "orv_back_image_path",
        "orv_scanned_at",
        "orv_confidence_json",
        "data_trust_state",
    } <= vehicle_columns

    vehicle_ownership_columns = {col["name"] for col in inspector.get_columns("vehicle_ownerships")}
    assert {
        "ownership_origin",
        "owned_from",
        "owned_until",
    } <= vehicle_ownership_columns

    reminder_columns = {col["name"] for col in inspector.get_columns("reminders")}
    assert {
        "notify_at",
        "last_notified_at",
        "notification_method",
        "is_manual",
        "is_completed",
        "recurrence_group_id",
        "recurrence_index",
        "repeat_interval_days",
    } <= reminder_columns

    tachometer_columns = {col["name"] for col in inspector.get_columns("vehicle_tachometer_history_entries")}
    assert {
        "findings_summary",
        "findings_items_json",
        "detail_snapshot_json",
        "source_detail_reference",
    } <= tachometer_columns
