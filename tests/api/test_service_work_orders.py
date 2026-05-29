from __future__ import annotations

import base64
import json
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.central_vehicle_identity import build_owner_safe_service_history
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceAccessRequest,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceQuote,
    ServiceRecord,
    ServiceWorkAccess,
    ServiceWorkOrder,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehiclePhotoAsset,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as dashboard_router
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace_router
from src.modules.vehicle_hub.routers_v1 import services as services_router
from src.modules.vehicle_hub.routers_v1.work_order_photos_api import (
    WorkOrderPhotoUploadRequest,
    WorkOrderPhotoVisibilityUpdateRequest,
    delete_work_order_photo,
    filter_owner_safe_work_order_photos,
    list_work_order_photos,
    update_work_order_photo_visibility,
    upload_work_order_photo,
)
from src.modules.vehicle_hub.routers_v1.service_invoices import (
    create_invoice_from_quote,
    get_service_invoice_pdf,
    list_service_invoices,
)
from src.modules.vehicle_hub.routers_v1.work_order_billing_api import (
    WorkOrderBillingContactRequest,
    WorkOrderInvoiceCreateRequest,
    create_work_order_billing_contact,
    create_work_order_invoice,
    create_work_order_quote,
    get_work_order_billing_contact,
    get_work_order_invoice,
    get_work_order_quote,
    list_service_billing_quotes,
    update_work_order_billing_contact,
    work_order_items_to_quote_items,
)
from src.modules.vehicle_hub.routers_v1.work_order_items_api import (
    ServiceWorkOrderCreateRecordRequest,
    ServiceWorkOrderLaborCreateRequest,
    ServiceWorkOrderPartCreateRequest,
    ServiceWorkOrderTimeCreateRequest,
    add_work_order_labor,
    add_work_order_part,
    add_work_order_time,
    complete_work_order,
    create_service_record_from_work_order,
)


def _service_user(service: Customer) -> SimpleNamespace:
    return SimpleNamespace(
        id=service.id,
        email=service.email,
        role="service",
        name=service.name,
        tenant_id=service.tenant_id,
    )


def _seed_ctx(tmp_path: Path):
    db_path = tmp_path / "service_work_orders.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    tenant = Tenant(name="Work Orders Tenant", license_key="work-orders-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    owner = Customer(tenant_id=tenant.id, email="owner@example.com", password_hash="x", role="user", name="Owner")
    service = Customer(tenant_id=tenant.id, email="service@example.com", password_hash="x", role="service", name="Service")
    foreign_service = Customer(
        tenant_id=tenant.id,
        email="foreign-service@example.com",
        password_hash="x",
        role="service",
        name="Foreign Service",
    )
    db.add_all([owner, service, foreign_service])
    db.commit()
    db.refresh(owner)
    db.refresh(service)
    db.refresh(foreign_service)

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        brand="Skoda",
        model="Octavia",
        vin="TMB12345678901234",
        plate="1AB2345",
        stk_valid_until=date(2030, 1, 1),
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            ownership_type="owner",
            ownership_origin="manual",
            is_primary=True,
            is_active=True,
        )
    )
    db.add(
        ServiceCustomerLink(
            service_tenant_id=tenant.id,
            service_customer_id=service.id,
            customer_tenant_id=tenant.id,
            customer_id=owner.id,
            status="active",
        )
    )
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
            approved_at=datetime.utcnow(),
            approved_by_customer_id=owner.id,
        )
    )
    db.commit()
    return engine, db, owner, service, foreign_service, vehicle


def _seed_unowned_vehicle(db, service: Customer, *, vin: str):
    """Vozidlo service_provisioned_unowned bez VehicleOwnership."""
    vehicle = Vehicle(
        tenant_id=service.tenant_id,
        user_email=f"_service_unowned_{service.id}@test.local",
        brand="Skoda",
        model="Fabia",
        vin=vin,
        plate=None,
        stk_valid_until=date(2030, 1, 1),
        provisioned_by_service_customer_id=service.id,
        provisioned_by_service_tenant_id=service.tenant_id,
        global_vehicle_status="service_provisioned_unowned",
        source_origin="service_created",
        claim_status="unclaimed",
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def test_service_work_order_list_loads(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Diagnostika",
                status="in_progress",
            ),
            current_user=_service_user(service),
            db=db,
        )
        rows = dashboard_router.list_service_work_orders(current_user=_service_user(service), db=db)
        assert len(rows["items"]) == 1
        assert rows["items"][0]["status"] == "in_progress"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_authorized_vehicle(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Příjem",
                status="awaiting_client_approval",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["vehicle_id"] == vehicle.id
        assert created["owner_id"] == owner.id
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_forbidden_without_access(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        with pytest.raises(HTTPException) as exc:
            dashboard_router.create_service_work_order(
                payload=dashboard_router.ServiceWorkOrderCreateRequest(
                    owner_id=owner.id,
                    vehicle_id=vehicle.id,
                    technician_id=foreign_service.id,
                    title="Bez přístupu",
                    status="approved",
                ),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_service_can_create_work_access_without_owner_approval(tmp_path: Path) -> None:
    engine, db, owner, _service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        before_owner_links = db.query(VehicleServiceLink).filter(
            VehicleServiceLink.service_customer_id == foreign_service.id,
            VehicleServiceLink.vehicle_id == vehicle.id,
        ).count()
        result = workspace_router.create_service_vehicle_work_access(
            vehicle_id=int(vehicle.id),
            payload=workspace_router.ServiceWorkAccessRequestV1(
                reason="Jednorázová diagnostika",
                source="service_lookup",
            ),
            current_user=_service_user(foreign_service),
            db=db,
        )
        assert result["status"] == "work_access"
        assert result["owner_data"] is None
        assert db.query(ServiceWorkAccess).filter(
            ServiceWorkAccess.service_customer_id == foreign_service.id,
            ServiceWorkAccess.vehicle_id == vehicle.id,
            ServiceWorkAccess.status == "active",
        ).count() == 1
        assert db.query(VehicleServiceLink).filter(
            VehicleServiceLink.service_customer_id == foreign_service.id,
            VehicleServiceLink.vehicle_id == vehicle.id,
        ).count() == before_owner_links
        assert db.query(VehicleOwnership).filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == owner.id,
            VehicleOwnership.is_active.is_(True),
        ).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_service_can_create_work_order_with_work_access(tmp_path: Path) -> None:
    engine, db, _owner, _service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        workspace_router.create_service_vehicle_work_access(
            vehicle_id=int(vehicle.id),
            payload=workspace_router.ServiceWorkAccessRequestV1(reason="Jednorázový servis", source="manual"),
            current_user=_service_user(foreign_service),
            db=db,
        )
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=foreign_service.id,
                title="Jednorázový zásah",
                status="approved",
            ),
            current_user=_service_user(foreign_service),
            db=db,
        )
        assert created["vehicle_id"] == vehicle.id
        assert created["owner_id"] is None
        assert created["access_status"] == "work_access"
        work_access = db.query(ServiceWorkAccess).filter(
            ServiceWorkAccess.service_customer_id == foreign_service.id,
            ServiceWorkAccess.vehicle_id == vehicle.id,
        ).one()
        assert int(work_access.work_order_id) == int(created["id"])
    finally:
        db.close()
        engine.dispose()


def test_service_cannot_read_owner_pii_with_work_access(tmp_path: Path) -> None:
    engine, db, _owner, _service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        workspace_router.create_service_vehicle_work_access(
            vehicle_id=int(vehicle.id),
            payload=workspace_router.ServiceWorkAccessRequestV1(reason="Bez propojení", source="manual"),
            current_user=_service_user(foreign_service),
            db=db,
        )
        detail = workspace_router.get_service_vehicle_detail(
            vehicle_id=int(vehicle.id),
            current_user=_service_user(foreign_service),
            db=db,
        )
        assert detail["access_mode"] == "service_work_access"
        assert detail["owner_customer_id"] is None
        assert detail["owner_name"] is None
        assert detail["vin"] is None
        assert detail["plate"] is None
        assert detail["vin_masked"]
        assert detail["plate_masked"]
    finally:
        db.close()
        engine.dispose()


def test_service_safe_technical_history_anonymizes_other_service_records(tmp_path: Path) -> None:
    engine, db, _owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        other_record = ServiceRecord(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            user_id=service.id,
            service_id=service.id,
            created_by_service_customer_id=service.id,
            performed_at=datetime.utcnow(),
            mileage=111000,
            description="Výměna oleje\nCelkem 2 500 Kč\nInterní poznámka",
            notes_customer_visible="Výměna oleje a filtru",
            price=2500,
            total_price=2500,
            category="Údržba",
            service_type="maintenance",
            visibility_scope="owner_visible_no_prices",
        )
        db.add(other_record)
        db.commit()

        workspace_router.create_service_vehicle_work_access(
            vehicle_id=int(vehicle.id),
            payload=workspace_router.ServiceWorkAccessRequestV1(reason="Jednorázově", source="manual"),
            current_user=_service_user(foreign_service),
            db=db,
        )
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=foreign_service.id,
                title="Vlastní brzdy",
                status="approved",
            ),
            current_user=_service_user(foreign_service),
            db=db,
        )
        add_work_order_part(
            int(created["id"]),
            ServiceWorkOrderPartCreateRequest(name="Brzdové destičky", quantity=1, unit_price_without_vat=1800),
            current_user=_service_user(foreign_service),
            db=db,
        )
        complete_work_order(int(created["id"]), current_user=_service_user(foreign_service), db=db)
        create_service_record_from_work_order(
            int(created["id"]),
            ServiceWorkOrderCreateRecordRequest(mileage=112000),
            current_user=_service_user(foreign_service),
            db=db,
        )

        history = workspace_router.get_service_vehicle_safe_technical_history(
            vehicle_id=int(vehicle.id),
            current_user=_service_user(foreign_service),
            db=db,
        )
        own_items = [item for item in history["items"] if item["own_record"]]
        other_items = [item for item in history["items"] if not item["own_record"]]
        assert own_items and own_items[0]["price"] is not None
        assert other_items
        blob = json.dumps(other_items, ensure_ascii=False).lower()
        assert "2500" not in blob
        assert "kč" not in blob
        assert "service_id" not in blob
        assert "invoice" not in blob
    finally:
        db.close()
        engine.dispose()


def test_cross_service_work_access_forbidden(tmp_path: Path) -> None:
    engine, db, _owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        workspace_router.create_service_vehicle_work_access(
            vehicle_id=int(vehicle.id),
            payload=workspace_router.ServiceWorkAccessRequestV1(reason="Cizí zásah", source="manual"),
            current_user=_service_user(foreign_service),
            db=db,
        )
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=foreign_service.id,
                title="Cizí zakázka",
                status="approved",
            ),
            current_user=_service_user(foreign_service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            dashboard_router.get_service_work_order_detail(
                int(created["id"]),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 404
    finally:
        db.close()
        engine.dispose()


def test_owner_can_approve_service_link(tmp_path: Path) -> None:
    engine, db, owner, _service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        request_row = ServiceAccessRequest(
            tenant_id=vehicle.tenant_id,
            service_customer_id=foreign_service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            requested_scope="history_read_create_record",
            status="pending",
            request_message="Dlouhodobé propojení",
            requested_at=datetime.utcnow(),
        )
        db.add(request_row)
        db.commit()
        db.refresh(request_row)
        result = services_router.resolve_service_access_request(
            int(request_row.id),
            services_router.ServiceAccessRequestDecisionV1(decision="approved"),
            current_user=owner,
            db=db,
        )
        assert result["decision"] == "approved"
        assert db.query(VehicleServiceLink).filter(
            VehicleServiceLink.service_customer_id == foreign_service.id,
            VehicleServiceLink.vehicle_id == vehicle.id,
            VehicleServiceLink.status == "approved",
        ).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_owner_can_reject_service_link_and_service_keeps_own_work_records(tmp_path: Path) -> None:
    engine, db, owner, _service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        workspace_router.create_service_vehicle_work_access(
            vehicle_id=int(vehicle.id),
            payload=workspace_router.ServiceWorkAccessRequestV1(reason="Před žádostí", source="manual"),
            current_user=_service_user(foreign_service),
            db=db,
        )
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=foreign_service.id,
                title="Vlastní zásah před odmítnutím",
                status="completed",
            ),
            current_user=_service_user(foreign_service),
            db=db,
        )
        request_row = ServiceAccessRequest(
            tenant_id=vehicle.tenant_id,
            service_customer_id=foreign_service.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            requested_scope="history_read_create_record",
            status="pending",
            request_message="Žádost po zásahu",
            requested_at=datetime.utcnow(),
        )
        db.add(request_row)
        db.commit()
        db.refresh(request_row)

        result = services_router.resolve_service_access_request(
            int(request_row.id),
            services_router.ServiceAccessRequestDecisionV1(decision="rejected"),
            current_user=owner,
            db=db,
        )
        assert result["decision"] == "rejected"
        assert db.query(VehicleServiceLink).filter(
            VehicleServiceLink.service_customer_id == foreign_service.id,
            VehicleServiceLink.vehicle_id == vehicle.id,
            VehicleServiceLink.status == "approved",
        ).count() == 0
        assert db.query(ServiceWorkAccess).filter(
            ServiceWorkAccess.service_customer_id == foreign_service.id,
            ServiceWorkAccess.vehicle_id == vehicle.id,
            ServiceWorkAccess.status == "active",
        ).count() == 1
        assert dashboard_router.get_service_work_order_detail(
            int(created["id"]),
            current_user=_service_user(foreign_service),
            db=db,
        )["id"] == int(created["id"])
    finally:
        db.close()
        engine.dispose()


def test_claim_does_not_auto_approve_service_links(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router

    engine, db, owner, service, _foreign_service, _vehicle = _seed_ctx(tmp_path)
    try:
        unowned = _seed_unowned_vehicle(db, service, vin="TMBCLAMWRK1234567")
        workspace_router.create_service_vehicle_work_access(
            vehicle_id=int(unowned.id),
            payload=workspace_router.ServiceWorkAccessRequestV1(reason="Před claimem", source="manual"),
            current_user=_service_user(service),
            db=db,
        )
        vehicles_router.owner_vehicle_claim_init(
            int(unowned.id),
            vehicles_router.VehicleClaimInitRequestV1(vin=unowned.vin),
            current_user=owner,
            db=db,
        )
        vehicles_router.owner_vehicle_claim_confirm(
            int(unowned.id),
            vehicles_router.VehicleClaimConfirmRequestV1(confirm_ownership=True, vin=unowned.vin),
            current_user=owner,
            db=db,
        )
        assert db.query(VehicleServiceLink).filter(
            VehicleServiceLink.service_customer_id == service.id,
            VehicleServiceLink.vehicle_id == unowned.id,
            VehicleServiceLink.status == "approved",
        ).count() == 0
        assert db.query(ServiceWorkAccess).filter(
            ServiceWorkAccess.service_customer_id == service.id,
            ServiceWorkAccess.vehicle_id == unowned.id,
            ServiceWorkAccess.status == "active",
        ).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_from_intake_context(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Z intake",
                source_type="intake",
                source_intake_id=77,
                status="approved",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["source"] == "intake"
        assert created["status"] == "approved"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_status_update(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Status update",
            ),
            current_user=_service_user(service),
            db=db,
        )
        updated = dashboard_router.update_service_work_order(
            work_order_id=int(created["id"]),
            payload=dashboard_router.ServiceWorkOrderUpdateRequest(status="completed"),
            current_user=_service_user(service),
            db=db,
        )
        assert updated["status"] == "completed"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_audit_written(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Audit trail",
            ),
            current_user=_service_user(service),
            db=db,
        )
        row = db.execute(
            text("SELECT action FROM service_work_order_audit_logs WHERE work_order_id = :id ORDER BY id DESC LIMIT 1"),
            {"id": int(created["id"])},
        ).fetchone()
        assert row is not None
        assert row[0] == "create"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_unowned_vehicle(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        unowned = _seed_unowned_vehicle(db, service, vin="TMBJH7NP9N7099991")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=unowned.id,
                technician_id=service.id,
                title="Nepřiřazené auto",
                status="awaiting_client_approval",
                source_type="intake",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["vehicle_id"] == unowned.id
        assert created["owner_id"] is None
        assert created["is_unowned_vehicle"] is True
        assert created["customer_name"] == "Jednorázový servisní zásah"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_unowned_vehicle_no_owner_created(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        unowned = _seed_unowned_vehicle(db, service, vin="TMBJH7NP9N7099992")
        dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=unowned.id,
                technician_id=service.id,
                title="Bez majitele",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == unowned.id).count() == 0
        order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.vehicle_id == unowned.id).one()
        assert order.owner_customer_id is None
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_unowned_vehicle_only_same_service(tmp_path: Path) -> None:
    engine, db, _owner, service, foreign_service, _vehicle = _seed_ctx(tmp_path)
    try:
        unowned = _seed_unowned_vehicle(db, service, vin="TMBJH7NP9N7099993")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=unowned.id,
                technician_id=service.id,
                title="Stejný servis",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["id"] > 0
        with pytest.raises(HTTPException) as exc:
            dashboard_router.create_service_work_order(
                payload=dashboard_router.ServiceWorkOrderCreateRequest(
                    vehicle_id=unowned.id,
                    technician_id=foreign_service.id,
                    title="Cizí servis",
                ),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_other_service_unowned_forbidden(tmp_path: Path) -> None:
    engine, db, _owner, service, foreign_service, _vehicle = _seed_ctx(tmp_path)
    try:
        foreign_unowned = _seed_unowned_vehicle(db, foreign_service, vin="TMBJH7NP9N7099994")
        with pytest.raises(HTTPException) as exc:
            dashboard_router.create_service_work_order(
                payload=dashboard_router.ServiceWorkOrderCreateRequest(
                    vehicle_id=foreign_unowned.id,
                    technician_id=service.id,
                    title="Cizí unowned",
                ),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_owned_vehicle_without_owner_id_creates_work_access(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Owned bez owner_id",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["owner_id"] is None
        assert db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle.id).count() == 1
        assert db.query(ServiceWorkAccess).filter(
            ServiceWorkAccess.service_customer_id == service.id,
            ServiceWorkAccess.vehicle_id == vehicle.id,
            ServiceWorkAccess.status == "active",
        ).count() == 1
        assert owner.email == "owner@example.com"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_owned_vehicle_without_access_forbidden(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        with pytest.raises(HTTPException) as exc:
            dashboard_router.create_service_work_order(
                payload=dashboard_router.ServiceWorkOrderCreateRequest(
                    owner_id=owner.id,
                    vehicle_id=vehicle.id,
                    technician_id=foreign_service.id,
                    title="Bez přístupu",
                ),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_for_authorized_vehicle_still_works(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Autorizované",
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert created["owner_id"] == owner.id
        assert created["is_unowned_vehicle"] is False
    finally:
        db.close()
        engine.dispose()


def test_service_workspace_lookup_accepts_vin_plate_payload() -> None:
    """CentralVehicleLookupRequestV1 accepts vin/plate without query string."""
    from src.modules.vehicle_hub.routers_v1 import service_workspace

    payload = service_workspace.CentralVehicleLookupRequestV1(
        vin="TMBJH7NP9N7088881",
        plate="8AB8888",
        source="service_intake",
        context="intake_route",
    )
    assert str(payload.vin or "").strip()
    assert str(payload.plate or "").strip()


def _jpeg_base64() -> str:
    buf = BytesIO()
    Image.new("RGB", (48, 36), color=(120, 160, 200)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _create_basic_work_order(db, owner, service, vehicle):
    return dashboard_router.create_service_work_order(
        payload=dashboard_router.ServiceWorkOrderCreateRequest(
            owner_id=owner.id,
            vehicle_id=vehicle.id,
            technician_id=service.id,
            title="Položky zakázky",
        ),
        current_user=_service_user(service),
        db=db,
    )


def test_service_work_order_add_labor(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        add_work_order_labor(
            int(created["id"]),
            ServiceWorkOrderLaborCreateRequest(name="Výměna oleje", hours=1.5, unit_price_without_vat=900),
            current_user=_service_user(service),
            db=db,
        )
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=int(created["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert len(detail["items"]["labor"]) == 1
        assert detail["items"]["labor"][0]["name"] == "Výměna oleje"
        assert detail["capabilities"]["labor"] is True
        assert detail["capabilities"]["photos"] is True
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_add_part(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        add_work_order_part(
            int(created["id"]),
            ServiceWorkOrderPartCreateRequest(name="Filtr oleje", quantity=1, unit="ks"),
            current_user=_service_user(service),
            db=db,
        )
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=int(created["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert len(detail["items"]["parts"]) == 1
        assert detail["items"]["parts"][0]["unit"] == "ks"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_add_time(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        add_work_order_time(
            int(created["id"]),
            ServiceWorkOrderTimeCreateRequest(minutes=90, note="Diagnostika"),
            current_user=_service_user(service),
            db=db,
        )
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=int(created["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert len(detail["items"]["time"]) == 1
        assert detail["items"]["time"][0]["quantity"] == 90
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_upload_for_authorized_vehicle(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        uploaded = upload_work_order_photo(
            wid,
            WorkOrderPhotoUploadRequest(
                photo_type="damage",
                file_name="damage.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert uploaded["photo_type"] == "damage"
        assert uploaded["visibility_scope"] == "service_private"
        assert "storage_path" not in uploaded
        assert "/opt/" not in str(uploaded)
        listed = list_work_order_photos(wid, current_user=_service_user(service), db=db)
        assert listed["count"] == 1
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=wid,
            current_user=_service_user(service),
            db=db,
        )
        assert detail["capabilities"]["photos"] is True
        assert len(detail["photos"]) == 1
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_upload_for_unowned_vehicle(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, _owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBPHOTOS123456789")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Unowned photos",
            ),
            current_user=_service_user(service),
            db=db,
        )
        wid = int(created["id"])
        upload_work_order_photo(
            wid,
            WorkOrderPhotoUploadRequest(
                photo_type="intake",
                file_name="intake.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        listed = list_work_order_photos(wid, current_user=_service_user(service), db=db)
        assert listed["count"] == 1
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_forbidden_cross_service(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        with pytest.raises(HTTPException) as exc:
            upload_work_order_photo(
                int(created["id"]),
                WorkOrderPhotoUploadRequest(
                    photo_type="damage",
                    file_name="x.jpg",
                    file_mime_type="image/jpeg",
                    file_content_base64=_jpeg_base64(),
                ),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_list_only_own_work_order(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        wo1 = _create_basic_work_order(db, owner, service, vehicle)
        complete_work_order(int(wo1["id"]), current_user=_service_user(service), db=db)
        wo2 = _create_basic_work_order(db, owner, service, vehicle)
        upload_work_order_photo(
            int(wo1["id"]),
            WorkOrderPhotoUploadRequest(
                photo_type="part",
                file_name="a.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        listed = list_work_order_photos(int(wo2["id"]), current_user=_service_user(service), db=db)
        assert listed["count"] == 0
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_visibility_change(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        uploaded = upload_work_order_photo(
            wid,
            WorkOrderPhotoUploadRequest(
                photo_type="completion",
                file_name="done.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        updated = update_work_order_photo_visibility(
            wid,
            int(uploaded["id"]),
            WorkOrderPhotoVisibilityUpdateRequest(visibility_scope="owner_visible"),
            current_user=_service_user(service),
            db=db,
        )
        assert updated["visibility_scope"] == "owner_visible"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_delete_or_hide(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        uploaded = upload_work_order_photo(
            wid,
            WorkOrderPhotoUploadRequest(
                photo_type="work_progress",
                file_name="p.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        delete_work_order_photo(
            wid,
            int(uploaded["id"]),
            current_user=_service_user(service),
            db=db,
        )
        listed = list_work_order_photos(wid, current_user=_service_user(service), db=db)
        assert listed["count"] == 0
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_rejects_non_image(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        with pytest.raises(HTTPException) as exc:
            upload_work_order_photo(
                int(created["id"]),
                WorkOrderPhotoUploadRequest(
                    photo_type="damage",
                    file_name="bad.txt",
                    file_mime_type="text/plain",
                    file_content_base64=base64.b64encode(b"not-a-valid-image-payload").decode("ascii"),
                ),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 415
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_rejects_too_large(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        huge = base64.b64encode(b"x" * (11 * 1024 * 1024)).decode("ascii")
        with pytest.raises(HTTPException) as exc:
            upload_work_order_photo(
                int(created["id"]),
                WorkOrderPhotoUploadRequest(
                    photo_type="damage",
                    file_name="big.jpg",
                    file_mime_type="image/jpeg",
                    file_content_base64=huge,
                ),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 413
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_photo_default_service_private(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        uploaded = upload_work_order_photo(
            int(created["id"]),
            WorkOrderPhotoUploadRequest(
                photo_type="internal",
                file_name="internal.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        assert uploaded["visibility_scope"] == "internal_only"
        row = db.query(VehiclePhotoAsset).filter(VehiclePhotoAsset.id == int(uploaded["id"])).first()
        assert row.visibility_scope == "internal_only"
    finally:
        db.close()
        engine.dispose()


def test_owner_safe_history_does_not_include_private_photos(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        upload_work_order_photo(
            wid,
            WorkOrderPhotoUploadRequest(
                photo_type="damage",
                visibility_scope="service_private",
                file_name="private.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        rows = db.query(VehiclePhotoAsset).filter(VehiclePhotoAsset.work_order_id == wid).all()
        safe = filter_owner_safe_work_order_photos(rows)
        assert safe == []
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        blob = str(history)
        assert "private.jpg" not in blob
        assert "photos" not in blob or "photos': []" in blob.replace(" ", "")
    finally:
        db.close()
        engine.dispose()


def test_owner_claim_does_not_leak_internal_photos(tmp_path: Path, monkeypatch) -> None:
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.modules.vehicle_hub.routers_v1.work_order_photos_api.VEHICLE_PHOTOS_DIR", photos_dir)
    engine, db, _owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBCLAIMPHOTOS12345")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Claim photos",
            ),
            current_user=_service_user(service),
            db=db,
        )
        wid = int(created["id"])
        upload_work_order_photo(
            wid,
            WorkOrderPhotoUploadRequest(
                photo_type="internal",
                file_name="secret.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        upload_work_order_photo(
            wid,
            WorkOrderPhotoUploadRequest(
                photo_type="completion",
                visibility_scope="safe_after_claim",
                file_name="safe.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=_jpeg_base64(),
            ),
            current_user=_service_user(service),
            db=db,
        )
        rows = db.query(VehiclePhotoAsset).filter(VehiclePhotoAsset.work_order_id == wid).all()
        safe = filter_owner_safe_work_order_photos(rows)
        assert len(safe) == 1
        assert safe[0]["photo_type"] == "completion"
        assert all(item["photo_type"] != "internal" for item in safe)
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_complete(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        completed = complete_work_order(
            int(created["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert completed["status"] == "completed"
        assert completed["completed_at"] is not None
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_service_record(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Brzdy", hours=2),
            current_user=_service_user(service),
            db=db,
        )
        add_work_order_part(
            wid,
            ServiceWorkOrderPartCreateRequest(name="Destičky", quantity=2, unit="ks"),
            current_user=_service_user(service),
            db=db,
        )
        complete_work_order(wid, current_user=_service_user(service), db=db)
        result = create_service_record_from_work_order(
            wid,
            ServiceWorkOrderCreateRecordRequest(mileage=125000),
            current_user=_service_user(service),
            db=db,
        )
        assert result["service_record_id"] > 0
        record = db.query(ServiceRecord).filter(ServiceRecord.id == int(result["service_record_id"])).first()
        assert record is not None
        assert int(record.work_order_id or 0) == wid
        assert record.visibility_scope == "owner_visible_no_prices"
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_service_record_safe_history_no_prices(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_part(
            wid,
            ServiceWorkOrderPartCreateRequest(name="Olej 5W30", quantity=5, unit="l", unit_price_without_vat=100),
            current_user=_service_user(service),
            db=db,
        )
        complete_work_order(wid, current_user=_service_user(service), db=db)
        create_service_record_from_work_order(
            wid,
            ServiceWorkOrderCreateRecordRequest(),
            current_user=_service_user(service),
            db=db,
        )
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        assert history
        entry = history[0]
        assert "price" not in entry
        assert "total_price" not in entry
        assert "invoice_id" not in entry
        assert entry["parts"]
        assert entry["parts"][0]["name"] == "Olej 5W30"
        assert "unit_price" not in entry["parts"][0]
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_service_record_safe_history_no_invoice(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        complete_work_order(wid, current_user=_service_user(service), db=db)
        create_service_record_from_work_order(
            wid,
            ServiceWorkOrderCreateRecordRequest(),
            current_user=_service_user(service),
            db=db,
        )
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        blob = str(history[0])
        assert "invoice" not in blob.lower()
        assert "faktura" not in blob.lower()
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_forbidden_cross_service_items(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        with pytest.raises(HTTPException) as exc:
            add_work_order_labor(
                int(created["id"]),
                ServiceWorkOrderLaborCreateRequest(name="Cizí servis", hours=1),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_unowned_flow_still_works(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBUNOWN123456789")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Unowned items",
            ),
            current_user=_service_user(service),
            db=db,
        )
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Kontrola", hours=1),
            current_user=_service_user(service),
            db=db,
        )
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=wid,
            current_user=_service_user(service),
            db=db,
        )
        assert detail["is_unowned_vehicle"] is True
        assert len(detail["items"]["labor"]) == 1
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_quote_from_items(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Diagnostika", hours=2, unit_price_without_vat=500),
            current_user=_service_user(service),
            db=db,
        )
        add_work_order_part(
            wid,
            ServiceWorkOrderPartCreateRequest(name="Filtr", quantity=1, unit="ks", unit_price_without_vat=200),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        assert int(quote["id"]) > 0
        assert int(quote["work_order_id"]) == wid
        assert float(quote["total_price"]) >= 1000
        items = quote.get("items") or []
        assert len(items) >= 2
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=wid,
            current_user=_service_user(service),
            db=db,
        )
        assert detail["quote_summary"]["quote_id"] == int(quote["id"])
        assert detail["capabilities"]["quotes"] is True
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_quote_for_unowned(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBQUOTEUNOWNED1234")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Unowned quote",
            ),
            current_user=_service_user(service),
            db=db,
        )
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Kontrola", hours=1, unit_price_without_vat=300),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        assert quote["customer_id"] is None
        assert int(quote["work_order_id"]) == wid
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_quote_forbidden_cross_service(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        add_work_order_labor(
            int(created["id"]),
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1),
            current_user=_service_user(service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            create_work_order_quote(
                int(created["id"]),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_quote_forbidden_owned_without_access(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        add_work_order_labor(
            int(created["id"]),
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1),
            current_user=_service_user(service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            create_work_order_quote(
                int(created["id"]),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_create_invoice_from_items(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_part(
            wid,
            ServiceWorkOrderPartCreateRequest(name="Olej", quantity=4, unit="l", unit_price_without_vat=150),
            current_user=_service_user(service),
            db=db,
        )
        invoice = create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        assert int(invoice["id"]) > 0
        assert int(invoice["work_order_id"]) == wid
        assert float(invoice["total"]) > 0
        assert len(invoice.get("lines") or []) >= 1
        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=wid,
            current_user=_service_user(service),
            db=db,
        )
        assert detail["invoice_summary"]["invoice_id"] == int(invoice["id"])
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_invoice_for_unowned_requires_customer(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBINVUNOWNED123456")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Unowned invoice",
            ),
            current_user=_service_user(service),
            db=db,
        )
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1, unit_price_without_vat=100),
            current_user=_service_user(service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            create_work_order_invoice(
                wid,
                WorkOrderInvoiceCreateRequest(),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 422
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_invoice_forbidden_cross_service(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        add_work_order_labor(
            int(created["id"]),
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1, unit_price_without_vat=50),
            current_user=_service_user(service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            create_work_order_invoice(
                int(created["id"]),
                WorkOrderInvoiceCreateRequest(),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_invoice_pdf_or_limited(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Servis", hours=1, unit_price_without_vat=400),
            current_user=_service_user(service),
            db=db,
        )
        create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        payload = get_work_order_invoice(wid, current_user=_service_user(service), db=db)
        assert payload["invoice"] is not None
        assert payload["invoice"]["pdf_available"] is True
        assert "/pdf" in str(payload["invoice"]["pdf_url"])
    finally:
        db.close()
        engine.dispose()


def test_service_invoice_not_in_owner_safe_history(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Servis", hours=2, unit_price_without_vat=900),
            current_user=_service_user(service),
            db=db,
        )
        create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        blob = str(history)
        assert "invoice_id" not in blob
        assert "total_price" not in blob
        assert "quote_id" not in blob
    finally:
        db.close()
        engine.dispose()


def test_service_quote_not_in_owner_safe_history(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Nabídka práce", hours=1, unit_price_without_vat=600),
            current_user=_service_user(service),
            db=db,
        )
        create_work_order_quote(wid, current_user=_service_user(service), db=db)
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        assert "quote_id" not in str(history)
        assert "total_price" not in str(history)
    finally:
        db.close()
        engine.dispose()


def test_service_billing_list_scoped_to_service(tmp_path: Path) -> None:
    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1, unit_price_without_vat=100),
            current_user=_service_user(service),
            db=db,
        )
        create_work_order_quote(wid, current_user=_service_user(service), db=db)
        create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        quotes = list_service_billing_quotes(current_user=_service_user(service), db=db)
        assert quotes["count"] == 1
        invoices = list_service_invoices(current_user=_service_user(service), db=db)
        assert len(invoices["items"]) == 1
        foreign_quotes = list_service_billing_quotes(current_user=_service_user(foreign_service), db=db)
        assert foreign_quotes["count"] == 0
        foreign_invoices = list_service_invoices(current_user=_service_user(foreign_service), db=db)
        assert len(foreign_invoices["items"]) == 0
    finally:
        db.close()
        engine.dispose()


def test_service_work_order_items_to_quote_items_maps_prices(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_part(
            wid,
            ServiceWorkOrderPartCreateRequest(name="Destičky", quantity=2, unit="ks", unit_price_without_vat=250),
            current_user=_service_user(service),
            db=db,
        )
        from src.modules.vehicle_hub.models import ServiceWorkOrderItem

        rows = db.query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.work_order_id == wid).all()
        items = work_order_items_to_quote_items(rows)
        assert items[0]["total_price"] == 500
    finally:
        db.close()
        engine.dispose()


def test_service_quote_detail(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Detail práce", hours=1, unit_price_without_vat=100),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        detail = dashboard_router.get_service_quote_detail(
            int(quote["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert int(detail["id"]) == int(quote["id"])
        assert len(detail["items"]) >= 1
    finally:
        db.close()
        engine.dispose()


def test_service_invoice_detail(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1.service_invoices import get_service_invoice

    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_part(
            wid,
            ServiceWorkOrderPartCreateRequest(name="Olej", quantity=1, unit="l", unit_price_without_vat=200),
            current_user=_service_user(service),
            db=db,
        )
        invoice = create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        detail = get_service_invoice(
            int(invoice["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert int(detail["id"]) == int(invoice["id"])
        assert len(detail["lines"]) >= 1
    finally:
        db.close()
        engine.dispose()


def test_service_create_invoice_from_quote(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1.service_invoices import InvoiceFromQuoteRequest

    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce z nabídky", hours=2, unit_price_without_vat=400),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        invoice = create_invoice_from_quote(
            int(quote["id"]),
            InvoiceFromQuoteRequest(),
            current_user=_service_user(service),
            db=db,
        )
        assert int(invoice["work_order_id"]) == wid
        assert float(invoice["total"]) > 0
        assert len(invoice["lines"]) >= 1
    finally:
        db.close()
        engine.dispose()


def test_service_create_invoice_from_quote_duplicate_guard(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1.service_invoices import InvoiceFromQuoteRequest

    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1, unit_price_without_vat=100),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        create_invoice_from_quote(
            int(quote["id"]),
            InvoiceFromQuoteRequest(),
            current_user=_service_user(service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            create_invoice_from_quote(
                int(quote["id"]),
                InvoiceFromQuoteRequest(),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 409
    finally:
        db.close()
        engine.dispose()


def test_service_create_invoice_from_quote_owned_without_access_forbidden(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1.service_invoices import InvoiceFromQuoteRequest

    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        with pytest.raises(HTTPException) as exc:
            create_invoice_from_quote(
                int(quote["id"]),
                InvoiceFromQuoteRequest(),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_create_invoice_from_quote_forbidden_cross_service(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1.service_invoices import InvoiceFromQuoteRequest

    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        with pytest.raises(HTTPException) as exc:
            create_invoice_from_quote(
                int(quote["id"]),
                InvoiceFromQuoteRequest(),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_create_invoice_from_quote_unowned_without_billing_customer_returns_422(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1.service_invoices import InvoiceFromQuoteRequest

    engine, db, _owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBINVFROMQUOTE12345")
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="Unowned quote invoice",
            ),
            current_user=_service_user(service),
            db=db,
        )
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1, unit_price_without_vat=50),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        with pytest.raises(HTTPException) as exc:
            create_invoice_from_quote(
                int(quote["id"]),
                InvoiceFromQuoteRequest(),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 422
        detail = exc.value.detail
        if isinstance(detail, dict):
            assert "fakturační kontakt" in str(detail.get("message", "")).lower()
    finally:
        db.close()
        engine.dispose()


def test_service_create_invoice_from_quote_unowned_does_not_create_owner(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1.service_invoices import InvoiceFromQuoteRequest

    engine, db, _owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        vehicle = _seed_unowned_vehicle(db, service, vin="TMBINVNOOWNER1234567")
        before_owners = db.query(VehicleOwnership).count()
        created = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                vehicle_id=vehicle.id,
                technician_id=service.id,
                title="No owner from quote",
            ),
            current_user=_service_user(service),
            db=db,
        )
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1, unit_price_without_vat=50),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        with pytest.raises(HTTPException):
            create_invoice_from_quote(
                int(quote["id"]),
                InvoiceFromQuoteRequest(),
                current_user=_service_user(service),
                db=db,
            )
        assert db.query(VehicleOwnership).count() == before_owners
    finally:
        db.close()
        engine.dispose()


def test_service_invoice_pdf_access_scoped_to_service(tmp_path: Path) -> None:
    from fastapi.responses import Response

    engine, db, owner, service, foreign_service, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="PDF", hours=1, unit_price_without_vat=100),
            current_user=_service_user(service),
            db=db,
        )
        invoice = create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        resp = get_service_invoice_pdf(
            int(invoice["id"]),
            current_user=_service_user(service),
            db=db,
        )
        assert isinstance(resp, Response)
        assert resp.media_type == "application/pdf"
        with pytest.raises(HTTPException) as exc:
            get_service_invoice_pdf(
                int(invoice["id"]),
                current_user=_service_user(foreign_service),
                db=db,
            )
        assert exc.value.status_code == 404
    finally:
        db.close()
        engine.dispose()


def test_owner_safe_history_no_quote_invoice_pdf_prices(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Safe", hours=1, unit_price_without_vat=999),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        create_work_order_invoice(wid, WorkOrderInvoiceCreateRequest(), current_user=_service_user(service), db=db)
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        blob = json.dumps(history, ensure_ascii=False).lower()
        for forbidden in (
            "invoice_id",
            "quote_id",
            "invoice_number",
            "total_price",
            "pdf_url",
            "unit_price",
            "unit_price_without_vat",
            "vat",
            "billing",
        ):
            assert forbidden not in blob
        assert "999" not in blob
    finally:
        db.close()
        engine.dispose()


def _billing_contact_payload(**overrides) -> WorkOrderBillingContactRequest:
    base = {
        "name": "Jan Nepřiřazený",
        "email": "jan.neprirazeny@example.test",
        "phone": "+420777888999",
        "company_name": "Autoservis zákazník s.r.o.",
        "street": "Hlavní",
        "city": "Praha",
        "zip": "11000",
    }
    base.update(overrides)
    return WorkOrderBillingContactRequest(**base)


def _unowned_work_order_with_labor(db, service, *, vin: str):
    vehicle = _seed_unowned_vehicle(db, service, vin=vin)
    created = dashboard_router.create_service_work_order(
        payload=dashboard_router.ServiceWorkOrderCreateRequest(
            vehicle_id=vehicle.id,
            technician_id=service.id,
            title="Unowned billing contact",
        ),
        current_user=_service_user(service),
        db=db,
    )
    wid = int(created["id"])
    add_work_order_labor(
        wid,
        ServiceWorkOrderLaborCreateRequest(name="Práce", hours=1, unit_price_without_vat=500),
        current_user=_service_user(service),
        db=db,
    )
    return vehicle, wid


def test_service_create_billing_contact_for_unowned_work_order(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        _vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBBILLINGCONTACT01")
        result = create_work_order_billing_contact(
            wid,
            _billing_contact_payload(),
            current_user=_service_user(service),
            db=db,
        )
        contact = result["billing_contact"]
        assert contact["ready_for_invoice"] is True
        assert contact["name"] == "Jan Nepřiřazený"
        fetched = get_work_order_billing_contact(wid, current_user=_service_user(service), db=db)
        assert fetched["billing_contact"]["billing_contact_id"] == contact["billing_contact_id"]
    finally:
        db.close()
        engine.dispose()


def test_service_update_billing_contact(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        _vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBBILLINGCONTACT02")
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(),
            current_user=_service_user(service),
            db=db,
        )
        updated = update_work_order_billing_contact(
            wid,
            _billing_contact_payload(name="Petr Upravený", email="petr.upraveny@example.test"),
            current_user=_service_user(service),
            db=db,
        )
        assert updated["billing_contact"]["name"] == "Petr Upravený"
    finally:
        db.close()
        engine.dispose()


def test_service_invoice_with_billing_contact(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        _vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBBILLINGINVCE01")
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(),
            current_user=_service_user(service),
            db=db,
        )
        invoice = create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        assert float(invoice["total"]) > 0
        assert db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == _vehicle.id).count() == 0
    finally:
        db.close()
        engine.dispose()


def test_service_quote_with_billing_contact(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        _vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBBILLINGQUOTE001")
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(),
            current_user=_service_user(service),
            db=db,
        )
        quote = create_work_order_quote(wid, current_user=_service_user(service), db=db)
        assert quote.get("customer_id") is not None
    finally:
        db.close()
        engine.dispose()


def test_service_invoice_without_billing_contact_returns_422(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        _vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBBILLINGNOCONT01")
        with pytest.raises(HTTPException) as exc:
            create_work_order_invoice(
                wid,
                WorkOrderInvoiceCreateRequest(),
                current_user=_service_user(service),
                db=db,
            )
        assert exc.value.status_code == 422
        detail = exc.value.detail
        if isinstance(detail, dict):
            assert "fakturační kontakt" in str(detail.get("message", "")).lower()
    finally:
        db.close()
        engine.dispose()


def test_service_billing_contact_cross_service_forbidden(tmp_path: Path) -> None:
    engine, db, _owner, service, foreign_service, _vehicle = _seed_ctx(tmp_path)
    try:
        _vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBBILLINGCROSS01")
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(),
            current_user=_service_user(service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            get_work_order_billing_contact(wid, current_user=_service_user(foreign_service), db=db)
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_service_billing_contact_does_not_create_vehicle_ownership(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBBILLINGNOOWN01")
        before = db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle.id).count()
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(),
            current_user=_service_user(service),
            db=db,
        )
        create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        after = db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle.id).count()
        assert before == 0
        assert after == 0
    finally:
        db.close()
        engine.dispose()


def test_owner_claim_does_not_reveal_invoice(tmp_path: Path) -> None:
    from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router

    engine, db, owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBCLMNV0CE123456")
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(email="claim.invoice@example.test"),
            current_user=_service_user(service),
            db=db,
        )
        create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        vehicles_router.owner_vehicle_claim_init(
            vehicle.id,
            vehicles_router.VehicleClaimInitRequestV1(
                vin=vehicle.vin,
                verification_method="manual_confirmation",
            ),
            current_user=owner,
            db=db,
        )
        vehicles_router.owner_vehicle_claim_confirm(
            vehicle.id,
            vehicles_router.VehicleClaimConfirmRequestV1(vin=vehicle.vin, confirm_ownership=True),
            current_user=owner,
            db=db,
        )
        history = build_owner_safe_service_history(db, vehicle_id=int(vehicle.id), owner_customer_id=int(owner.id))
        blob = json.dumps(history, ensure_ascii=False).lower()
        assert "invoice" not in blob
        assert "faktura" not in blob
        assert "billing_contact" not in blob
        owner_invoices_exc = None
        try:
            list_service_invoices(current_user=owner, db=db)
        except HTTPException as exc:
            owner_invoices_exc = exc
        assert owner_invoices_exc is not None
        assert owner_invoices_exc.status_code == 403
    finally:
        db.close()
        engine.dispose()


def test_owner_safe_history_no_billing_contact_data(tmp_path: Path) -> None:
    engine, db, _owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBSAFEBILLING001")
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(ico="12345678", dic="CZ12345678"),
            current_user=_service_user(service),
            db=db,
        )
        create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        record = ServiceRecord(
            tenant_id=service.tenant_id,
            vehicle_id=vehicle.id,
            user_id=service.id,
            service_id=service.id,
            created_by_service_customer_id=service.id,
            performed_at=datetime.utcnow(),
            category="SERVIS",
            service_type="maintenance",
            description="Bezpečný záznam",
            visibility_scope="safe_history_after_claim",
        )
        db.add(record)
        db.commit()
        history = build_owner_safe_service_history(
            db,
            vehicle_id=int(vehicle.id),
            owner_customer_id=int(service.id),
        )
        blob = json.dumps(history, ensure_ascii=False).lower()
        for token in ("billing_contact", "12345678", "cz12345678", "invoice_number", "billing_customer"):
            assert token not in blob
    finally:
        db.close()
        engine.dispose()


def test_service_invoice_pdf_not_available_to_owner(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, _vehicle = _seed_ctx(tmp_path)
    try:
        vehicle, wid = _unowned_work_order_with_labor(db, service, vin="TMBPDFOWNERBLK01")
        create_work_order_billing_contact(
            wid,
            _billing_contact_payload(),
            current_user=_service_user(service),
            db=db,
        )
        invoice = create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        with pytest.raises(HTTPException) as exc:
            get_service_invoice_pdf(
                int(invoice["id"]),
                current_user=owner,
                db=db,
            )
        assert exc.value.status_code in {403, 404}
    finally:
        db.close()
        engine.dispose()


def test_authorized_owned_invoice_still_works(tmp_path: Path) -> None:
    engine, db, owner, service, _foreign, vehicle = _seed_ctx(tmp_path)
    try:
        created = _create_basic_work_order(db, owner, service, vehicle)
        wid = int(created["id"])
        add_work_order_labor(
            wid,
            ServiceWorkOrderLaborCreateRequest(name="Owned", hours=1, unit_price_without_vat=200),
            current_user=_service_user(service),
            db=db,
        )
        invoice = create_work_order_invoice(
            wid,
            WorkOrderInvoiceCreateRequest(),
            current_user=_service_user(service),
            db=db,
        )
        assert int(invoice["customer_id"]) == int(owner.id)
    finally:
        db.close()
        engine.dispose()
