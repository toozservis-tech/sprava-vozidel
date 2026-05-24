from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from .api_vin import decode_vin_api
from .database import SessionLocal
from .models import Vehicle as VehicleModel, ServiceRecord as ServiceRecordModel
from .ownership import get_customer_by_email, get_owned_vehicle_rows
from .schema_management import assert_module_ready


@dataclass
class Vehicle:
    vin: str
    plate: str
    name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    engine: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class ServiceRecord:
    vehicle_vin: str
    date: date
    odometer_km: Optional[int]
    price: Optional[float]
    description: str
    category: str


class VehicleHubService:
    """
    Služba pro správu vozidel a servisních záznamů.
    Používá databázi pro trvalé ukládání dat.
    """

    def __init__(self, user_email: Optional[str] = None) -> None:
        self.user_email = user_email

    def _get_db(self) -> Session:
        """Vrací databázovou session"""
        return SessionLocal()

    def _get_customer(self, db: Session):
        if not self.user_email:
            return None
        return get_customer_by_email(db, self.user_email)

    # ---------- VOZIDLA ----------

    def add_vehicle(self, vehicle: Vehicle) -> None:
        """
        Přidá nebo aktualizuje vozidlo v databázi.
        """
        if not self.user_email:
            raise ValueError("Uživatel není přihlášen")
        
        db = self._get_db()
        try:
            assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
            customer = self._get_customer(db)
            if customer is None:
                raise ValueError("Uživatel nebyl nalezen")
            vin = vehicle.vin.strip().upper() if vehicle.vin else None
            owned_rows = get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None))
            
            # Zkusíme najít existující vozidlo podle VIN nebo SPZ
            existing = None
            if vin:
                existing = next((row for row in owned_rows if row.vin == vin), None)
            
            if not existing and vehicle.plate:
                existing = next((row for row in owned_rows if row.plate == vehicle.plate), None)
            
            if existing:
                # Aktualizace existujícího vozidla
                existing.nickname = vehicle.name
                existing.brand = vehicle.brand
                existing.model = vehicle.model
                existing.year = vehicle.year
                existing.engine = vehicle.engine
                existing.vin = vin
                existing.plate = vehicle.plate
                existing.notes = vehicle.notes
            else:
                # Vytvoření nového vozidla
                db_vehicle = VehicleModel(
                    user_email=self.user_email,
                    nickname=vehicle.name,
                    brand=vehicle.brand,
                    model=vehicle.model,
                    year=vehicle.year,
                    engine=vehicle.engine,
                    vin=vin,
                    plate=vehicle.plate,
                    notes=vehicle.notes
                )
                db.add(db_vehicle)
            
            db.commit()
        finally:
            db.close()

    def get_all_vehicles(self) -> List[Vehicle]:
        """Vrací všechna vozidla aktuálního uživatele"""
        if not self.user_email:
            return []
        
        db = self._get_db()
        try:
            assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
            customer = self._get_customer(db)
            if customer is None:
                return []
            db_vehicles = get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None))
            
            vehicles = []
            for v in db_vehicles:
                vehicles.append(Vehicle(
                    vin=v.vin or "",
                    plate=v.plate or "",
                    name=v.nickname or "",
                    brand=v.brand,
                    model=v.model,
                    year=v.year,
                    engine=v.engine,
                    notes=v.notes
                ))
            return vehicles
        finally:
            db.close()

    def get_vehicle(self, vin: str) -> Optional[Vehicle]:
        """Vrací vozidlo podle VIN"""
        if not self.user_email:
            return None
        
        db = self._get_db()
        try:
            assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
            customer = self._get_customer(db)
            if customer is None:
                return None
            normalized_vin = vin.strip().upper()
            db_vehicle = next(
                (row for row in get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None)) if row.vin == normalized_vin),
                None,
            )
            
            if db_vehicle:
                return Vehicle(
                    vin=db_vehicle.vin or "",
                    plate=db_vehicle.plate or "",
                    name=db_vehicle.nickname or "",
                    brand=db_vehicle.brand,
                    model=db_vehicle.model,
                    year=db_vehicle.year,
                    engine=db_vehicle.engine,
                    notes=db_vehicle.notes
                )
            return None
        finally:
            db.close()

    # ---------- SERVISNÍ ZÁZNAMY ----------

    def add_service_record(self, record: ServiceRecord) -> None:
        """Přidá servisní záznam k vozidlu"""
        if not self.user_email:
            raise ValueError("Uživatel není přihlášen")
        
        db = self._get_db()
        try:
            assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
            customer = self._get_customer(db)
            if customer is None:
                raise ValueError("Uživatel nebyl nalezen")
            vin = record.vehicle_vin.strip().upper()
            vehicle = next(
                (row for row in get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None)) if row.vin == vin),
                None,
            )
            
            if not vehicle:
                raise ValueError(f"Unknown vehicle VIN: {vin}")
            
            db_record = ServiceRecordModel(
                tenant_id=vehicle.tenant_id or 1,
                vehicle_id=vehicle.id,
                performed_at=record.date,
                mileage=record.odometer_km,
                price=record.price,
                description=record.description,
                note=record.category
            )
            db.add(db_record)
            db.commit()
        finally:
            db.close()

    def get_records_for_vehicle(self, vin: str) -> List[ServiceRecord]:
        """Vrací servisní záznamy pro vozidlo"""
        if not self.user_email:
            return []
        
        db = self._get_db()
        try:
            assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
            customer = self._get_customer(db)
            if customer is None:
                return []
            normalized_vin = vin.strip().upper()
            vehicle = next(
                (row for row in get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None)) if row.vin == normalized_vin),
                None,
            )
            
            if not vehicle:
                return []
            
            db_records = db.query(ServiceRecordModel).filter(
                ServiceRecordModel.vehicle_id == vehicle.id
            ).all()
            
            records = []
            for r in db_records:
                records.append(ServiceRecord(
                    vehicle_vin=vin,
                    date=r.performed_at.date() if r.performed_at else date.today(),
                    odometer_km=r.mileage,
                    price=r.price,
                    description=r.description,
                    category=r.note or ""
                ))
            return records
        finally:
            db.close()

    # ---------- VIN DECODE ----------

    def decode_vin(self, vin: str) -> dict:
        """
        Dekóduje VIN pomocí API a vrací informace o vozidle.
        
        Args:
            vin: VIN kód vozidla
            
        Returns:
            dict s klíči: brand, model, year, engine, tyres (seznam)
            
        Raises:
            ValueError: Pokud je VIN neplatný
            Exception: Pokud API selže
        """
        vin = vin.strip().upper()
        try:
            return decode_vin_api(vin)
        except ValueError as e:
            # Přeposíláme ValueError beze změny
            raise
        except Exception as e:
            # Ostatní chyby zabalíme do obecné výjimky
            raise Exception(f"Chyba při dekódování VIN: {str(e)}") from e
