"""
Deterministic schema checks for active modules.
No runtime create_all/ALTER TABLE in request flow.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session


MODULE_REQUIREMENTS: Dict[str, Dict[str, object]] = {
    "vehicles": {
        "tables": {
            "vehicles",
            "vehicle_ownerships",
            "vehicle_tachometer_history_entries",
            "vehicle_orv_scans",
            "vehicle_photos",
            "vehicle_photo_assets",
            "vehicle_transfer_tokens",
            "vehicle_removal_events",
            "audit_log",
            "vehicle_mileage",
        },
        "columns": {
            "vehicles": {
                "primary_photo_asset_id",
                "photo_path",
                "fuel",
                "body_type",
                "status",
                "updated_at",
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
                "normalized_vin",
                "normalized_plate",
                "global_vehicle_status",
                "source_origin",
                "claim_status",
                "claimed_at",
                "claimed_by_customer_id",
                "provisioned_by_service_tenant_id",
                "merge_guard_hash",
            },
            "vehicle_ownerships": {
                "ownership_origin",
                "relation_type",
                "acquisition_reason",
                "deactivation_reason",
                "transfer_token_id",
                "owned_from",
                "owned_until",
            },
            "vehicle_photo_assets": {
                "tenant_id",
                "vehicle_id",
                "owner_customer_id",
                "related_case_id",
                "role",
                "photo_kind",
                "vin",
                "capture_date",
                "storage_key",
                "storage_path_original",
                "storage_path_preview",
                "original_filename",
                "mime_type",
                "file_size_bytes",
                "width",
                "height",
                "sha256_hex",
                "uploaded_by_customer_id",
                "created_at",
                "deleted_at",
                "sort_order",
            },
            "vehicle_tachometer_history_entries": {
                "findings_summary",
                "findings_items_json",
                "detail_snapshot_json",
                "source_detail_reference",
            },
        },
    },
    "service_records": {
        "tables": {"service_records", "service_record_audit_logs"},
        "columns": {
            "service_records": {
                "is_deleted",
                "deleted_at",
                "deleted_by_user_id",
                "deletion_reason",
                "snapshot_hash",
                "created_by_service_customer_id",
                "service_access_link_id",
                "customer_id",
                "service_id",
                "work_order_id",
                "quote_id",
                "record_status",
                "service_type",
                "recommended_next_service_text",
                "recommended_next_service_date",
                "notes_customer_visible",
                "total_price",
                "updated_at",
                "origin",
                "service_case_id",
                "labor_seconds",
                "recommended_next_service_km",
                "visibility_scope",
            }
        },
    },
    "reminders": {
        "tables": {"reminders"},
        "columns": {
            "reminders": {
                "notify_at",
                "last_notified_at",
                "notification_method",
                "is_manual",
                "is_completed",
                "recurrence_group_id",
                "recurrence_index",
                "repeat_interval_days",
            }
        },
    },
    "service_workspace": {
        "tables": {
            "service_customer_links",
            "service_customer_invites",
            "service_vehicle_access",
            "service_document_ingestions",
            "service_access_requests",
            "vehicle_service_links",
            "service_vehicle_lookup_audit",
            "user_onboarding_tokens",
            "vehicle_qr_tokens",
            "vehicle_qr_access_logs",
            "service_intakes",
            "service_labor_sessions",
            "vehicle_transfer_tokens",
            "vehicle_removal_events",
        },
        "columns": {
            "customers": {
                "partner_catalog_approved",
                "partner_public_profile",
                "force_password_change",
                "email_normalized",
                "phone_normalized",
            },
            "vehicles": {
                "provisioned_by_service_customer_id",
                "provisioned_by_service_tenant_id",
                "normalized_vin",
                "normalized_plate",
                "global_vehicle_status",
                "source_origin",
                "claim_status",
                "claimed_at",
                "claimed_by_customer_id",
                "merge_guard_hash",
            },
            "service_customer_links": {
                "link_source",
                "consent_basis",
                "consent_note",
                "internal_service_note",
                "approved_at",
                "revoked_at",
                "created_by_service_user_id",
                "last_interaction_at",
            },
            "service_vehicle_access": {
                "service_tenant_id",
                "access_scope_json",
                "revoke_reason",
            },
            "vehicle_qr_tokens": {
                "token",
                "public_mode",
                "explicit_full_consent",
                "issued_at",
                "revoked_at",
                "last_access_at",
                "signature_hash",
                "active",
            },
            "vehicle_qr_access_logs": {
                "qr_token_id",
                "access_status",
                "public_mode",
                "access_signature_valid",
            },
        },
    },
    "service_invoices": {
        "tables": {
            "service_invoices",
            "service_invoice_lines",
            "service_invoice_counters",
            "audit_log",
            "service_customer_links",
            "vehicle_service_links",
        },
        "columns": {
            "service_invoices": {
                "invoice_number",
                "status",
                "subtotal",
                "tax_total",
                "total",
                "currency",
                "issued_at",
                "due_at",
                "cancelled_at",
                "notes",
                "extra_json",
                "fakturyweb_code",
                "fakturyweb_number",
                "fakturyweb_status",
                "fakturyweb_pdf_url",
                "fakturyweb_exported_at",
                "fakturyweb_last_sync_at",
                "service_record_id",
                "work_order_id",
            },
            "service_invoice_lines": {
                "description",
                "quantity",
                "unit",
                "unit_price",
                "tax_rate",
                "line_total",
                "sort_order",
            },
            "service_invoice_counters": {"next_seq"},
        },
    },
    "service_dashboard": {
        "tables": {
            "service_work_orders",
            "service_work_order_audit_logs",
            "service_quotes",
            "service_quote_audit_logs",
            "service_quote_access_tokens",
            "service_quote_access_logs",
            "audit_log",
            "service_customer_links",
            "vehicle_service_links",
        },
        "columns": {
            "service_work_orders": {
                "technician_id",
                "source_type",
                "status",
                "due_date",
            },
            "service_quotes": {
                "service_record_id",
                "items_json",
                "labor_hours",
                "labor_rate",
                "total_price",
                "status",
                "approved_at",
                "rejected_at",
            },
            "service_quote_access_tokens": {
                "quote_id",
                "token",
                "issued_at",
                "expires_at",
                "revoked_at",
                "last_access_at",
            },
            "service_quote_access_logs": {
                "quote_id",
                "quote_access_token_id",
                "action",
                "remote_addr",
                "user_agent",
            },
        },
    },
    "reservations": {
        "tables": {"reservations", "service_vehicle_access"},
        "columns": {"reservations": {"source_platform"}},
    },
    "subscriptions": {
        "tables": {
            "licenses",
            "license_subscriptions",
            "license_payment_transactions",
            "payment_events",
            "license_audit_log",
        },
        "columns": {
            "license_subscriptions": {
                "credit_balance_halers",
                "provider_init_transaction_id",
                "recurring_ready",
                "recurring_block_reason",
                "last_recurring_attempt_at",
                "last_recurring_result",
            },
            "license_payment_transactions": {
                "subscription_id",
                "payment_type",
                "parent_provider_transaction_id",
                "parent_init_recurring_id",
                "period_start",
                "period_end",
                "raw_provider_payload_hash",
                "provider_response_code",
                "provider_response_message",
            },
        },
    },
    "push": {
        "tables": {"push_subscriptions"},
    },
    "system_notifications": {
        "tables": {"system_notifications"},
    },
    "security": {
        "tables": {
            "customer_security_settings",
            "security_access_logs",
            "security_blocked_ips",
            "customer_deletion_labels",
            "demo_access_leads",
            "demo_access_tokens",
        },
        "columns": {
            "customers": {
                "admin_ordinal",
                "workspace_entitlements",
                "workspace_ui_default",
                "account_status",
                "email_verified_at",
                "email_verification_token_hash",
                "email_verification_expires_at",
                "email_verification_sent_at",
                "phone_e164",
                "phone_verified_at",
                "registration_ip",
                "registration_user_agent",
                "registration_risk_flags",
            },
        },
    },
    "admin_audit": {
        "tables": {"developer_action_audit_logs", "admin_customer_change_events"},
    },
}


def _table_names(db: Session) -> set[str]:
    inspector = inspect(db.bind)
    return set(inspector.get_table_names())


def _column_names(db: Session, table_name: str) -> set[str]:
    inspector = inspect(db.bind)
    return {str(col.get("name")) for col in inspector.get_columns(table_name) if col.get("name")}


def module_schema_report(db: Session, module_name: str) -> dict:
    requirements = MODULE_REQUIREMENTS.get(module_name, {})
    required_tables = set(requirements.get("tables") or set())
    required_columns: Mapping[str, Iterable[str]] = requirements.get("columns") or {}

    tables = _table_names(db)
    missing_tables = sorted(table for table in required_tables if table not in tables)
    missing_columns: List[str] = []

    for table_name, columns in required_columns.items():
        if table_name not in tables:
            for column in columns:
                missing_columns.append(f"{table_name}.{column}")
            continue
        existing_columns = _column_names(db, table_name)
        for column in columns:
            if column not in existing_columns:
                missing_columns.append(f"{table_name}.{column}")

    available = not missing_tables and not missing_columns
    return {
        "module": module_name,
        "available": available,
        "missing_tables": missing_tables,
        "missing_columns": sorted(missing_columns),
    }


def assert_module_ready(db: Session, module_name: str, *, detail_prefix: str) -> None:
    report = module_schema_report(db, module_name)
    if report["available"]:
        return
    problems = []
    if report["missing_tables"]:
        problems.append("tabulky: " + ", ".join(report["missing_tables"]))
    if report["missing_columns"]:
        problems.append("sloupce: " + ", ".join(report["missing_columns"]))
    raise HTTPException(
        status_code=503,
        detail=f"{detail_prefix}. Chybí { '; '.join(problems) }. Spusťte migrace.",
    )


def get_capabilities(db: Session) -> dict:
    modules = {
        name: module_schema_report(db, name)
        for name in sorted(MODULE_REQUIREMENTS.keys())
    }
    return {
        "modules": modules,
    }
