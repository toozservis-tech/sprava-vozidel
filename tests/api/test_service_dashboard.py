from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    Reminder,
    Reservation,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceQuote,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_dashboard as dashboard_router


def _seed_vehicle(db, *, tenant_id: int, owner: Customer, nickname: str) -> Vehicle:
    vehicle = Vehicle(
        tenant_id=tenant_id,
        user_email=owner.email,
        nickname=nickname,
        brand="Skoda",
        model="Octavia",
        vin=f"VIN{nickname}".replace(" ", "").upper()[:17].ljust(17, "1"),
        plate=f"{nickname[:3].upper()}1234",
        stk_valid_until=date.today() + timedelta(days=180),
    )
    db.add(vehicle)
    db.flush()
    db.add(
        VehicleOwnership(
            tenant_id=tenant_id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            ownership_type="owner",
            is_primary=True,
            is_active=True,
            assigned_by_customer_id=owner.id,
            assigned_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    db.flush()
    return vehicle


def test_service_dashboard_work_orders_and_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "service_dashboard.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        tenant = Tenant(name="Service Dashboard Tenant", license_key="service-dashboard-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        owner = Customer(
            tenant_id=tenant.id,
            email="owner@example.com",
            password_hash="hash-owner",
            role="user",
            name="Klient Dashboard",
        )
        service = Customer(
            tenant_id=tenant.id,
            email="service@example.com",
            password_hash="hash-service",
            role="service",
            name="Servis Dashboard",
        )
        technician = Customer(
            tenant_id=tenant.id,
            email="technician@example.com",
            password_hash="hash-technician",
            role="service",
            name="Technik Petr",
        )
        db.add_all([owner, service, technician])
        db.commit()
        db.refresh(owner)
        db.refresh(service)
        db.refresh(technician)

        vehicle = _seed_vehicle(db, tenant_id=tenant.id, owner=owner, nickname="Dash Car")
        second_vehicle = _seed_vehicle(db, tenant_id=tenant.id, owner=owner, nickname="Dash Car Two")
        db.add(
            ServiceCustomerLink(
                service_tenant_id=service.tenant_id,
                service_customer_id=service.id,
                customer_tenant_id=owner.tenant_id,
                customer_id=owner.id,
                status="active",
                note="dashboard test",
            )
        )
        db.add(
            VehicleServiceLink(
                tenant_id=tenant.id,
                service_customer_id=service.id,
                owner_customer_id=owner.id,
                vehicle_id=vehicle.id,
                source_type="manual_test",
                status="approved",
                approved_at=datetime.utcnow(),
                approved_by_customer_id=owner.id,
            )
        )
        db.add(
            VehicleServiceLink(
                tenant_id=tenant.id,
                service_customer_id=service.id,
                owner_customer_id=owner.id,
                vehicle_id=second_vehicle.id,
                source_type="manual_test",
                status="approved",
                approved_at=datetime.utcnow(),
                approved_by_customer_id=owner.id,
            )
        )
        db.commit()

        dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=vehicle.id,
                technician_id=technician.id,
                title="Diagnostika motoru",
                description="Kontrola chodu a čidel",
                due_date=date.today(),
                status="in_progress",
            ),
            current_user=service,
            db=db,
        )
        awaiting_order = dashboard_router.create_service_work_order(
            payload=dashboard_router.ServiceWorkOrderCreateRequest(
                owner_id=owner.id,
                vehicle_id=second_vehicle.id,
                technician_id=technician.id,
                title="Schválení opravy",
                due_date=date.today() - timedelta(days=1),
                status="awaiting_client_approval",
            ),
            current_user=service,
            db=db,
        )
        assert awaiting_order["status"] == "awaiting_client_approval"
        assert awaiting_order["customer_name"] == owner.name

        db.add(
            Reservation(
                tenant_id=tenant.id,
                service_id=service.id,
                customer_id=owner.id,
                vehicle_id=vehicle.id,
                service_type="Diagnostika",
                note="Nová rezervace",
                start_datetime=datetime.utcnow(),
                end_datetime=datetime.utcnow() + timedelta(hours=1),
                status="PENDING",
            )
        )
        db.add(
            ServiceQuote(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                customer_id=owner.id,
                service_id=service.id,
                work_order_id=int(awaiting_order["id"]),
                items_json='[{"name":"Diagnostika","quantity":1,"unit_price":1500,"total_price":1500}]',
                total_price=1500,
                status="sent",
            )
        )
        db.add(
            ServiceInvoice(
                tenant_id=tenant.id,
                service_id=service.id,
                customer_id=owner.id,
                vehicle_id=vehicle.id,
                status="draft",
                subtotal=1500,
                tax_total=315,
                total=1815,
                currency="CZK",
            )
        )
        db.add(
            Reminder(
                tenant_id=tenant.id,
                customer_id=owner.id,
                vehicle_id=vehicle.id,
                type="SERVIS",
                text="Zavolat klientovi",
                due_date=date.today(),
                is_manual=True,
                is_completed=False,
            )
        )
        db.commit()

        summary = dashboard_router.get_service_dashboard_summary(current_user=service, db=db)
        assert summary["active_jobs"] == 1
        assert summary["awaiting_approval"] == 1
        assert summary["due_today"] == 1
        assert summary["overdue"] == 1
        assert summary["new_reservations"] == 1
        assert summary["pending_quotes"] == 1
        assert summary["draft_invoices"] == 1
        assert summary["open_reminders"] == 1

        work_orders = dashboard_router.list_service_work_orders(current_user=service, db=db)
        items = work_orders["items"]
        assert len(items) == 2
        assert {item["customer_name"] for item in items} == {owner.name}
        assert {item["vehicle_vin"] for item in items} == {vehicle.vin, second_vehicle.vin}

        in_progress_item = next(item for item in items if item["status"] == "in_progress")

        detail = dashboard_router.get_service_work_order_detail(
            work_order_id=int(in_progress_item["id"]),
            current_user=service,
            db=db,
        )
        assert detail["audit_log"], "Detail zakázky musí obsahovat audit log"
        assert detail["entity_type"] == "work_order"
        assert detail["disclosure"] == "full"
        assert detail["can_edit"] is True
        assert detail["can_create_work_order"] is False

        updated = dashboard_router.update_service_work_order(
            work_order_id=int(in_progress_item["id"]),
            payload=dashboard_router.ServiceWorkOrderUpdateRequest(status="completed", description="Uzavřeno"),
            current_user=service,
            db=db,
        )
        assert updated["status"] == "completed"
        assert updated["description"] == "Uzavřeno"
        assert updated["can_edit"] is True

        performance = dashboard_router.get_service_technician_performance(current_user=service, db=db)
        assert performance["items"]
        assert performance["items"][0]["name"] in {technician.name, service.name}

        queue = dashboard_router.get_service_dashboard_queue(current_user=service, db=db)
        assert queue["awaiting_approval"] == 1
        assert queue["new_jobs"] == queue["new_orders"]
        assert queue["missing_documents"] >= 1
        assert queue["missing_client_consent"] == 1
        assert queue["unfinished_jobs"] == 1
        assert queue["new_reservations"] == 1
        assert queue["pending_quotes"] == 1
        assert queue["draft_invoices"] == 1
        assert queue["open_reminders"] == 1
        assert any(item["label"] == "Chybí souhlas klienta" for item in queue["alerts"])

        try:
            dashboard_router.create_service_work_order(
                payload=dashboard_router.ServiceWorkOrderCreateRequest(
                    owner_id=owner.id,
                    vehicle_id=second_vehicle.id,
                    technician_id=technician.id,
                    title="Schválení opravy",
                    due_date=date.today(),
                    status="approved",
                ),
                current_user=service,
                db=db,
            )
            raise AssertionError("Duplicitní otevřená zakázka měla skončit 409 chybou.")
        except HTTPException as exc:
            assert exc.status_code == 409
            assert exc.detail["code"] == "duplicate_work_order"
            assert exc.detail["existing_work_order_id"] == int(awaiting_order["id"])
            assert "rozpracovaná zakázka" in exc.detail["message"].lower()
    finally:
        db.close()
        engine.dispose()
