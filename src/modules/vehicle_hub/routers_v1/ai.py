"""
AI Endpoint v1.0 router (autopilot integrace)
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import date, datetime
import re
import json

from ..database import get_db
from ..models import ServiceRecord as ServiceRecordModel, Vehicle as VehicleModel, Customer
from ..ownership import get_owned_vehicle, get_owned_vehicle_rows
from .schemas import AIRecordRequestV1, AIRecordResponseV1
from src.core.config import AUTOPILOT_SHARED_SECRET

router = APIRouter(prefix="/ai", tags=["ai-v1"])


def parse_service_message(message: str) -> dict:
    """
    Jednoduchý parser pro textovou zprávu o servisu.
    Později může být nahrazen LLM voláním (OpenAI).
    
    Hledá:
    - Kilometry (číslo + "km")
    - Cenu (číslo + "Kč" nebo "CZK")
    - Kategorii (slovo jako "olej", "brzdy", atd.)
    - Datum (pokud je v textu)
    """
    parsed = {
        "odometer_km": None,
        "price": None,
        "category": None,
        "description": message,
        "date": date.today().isoformat()
    }
    
    message_lower = message.lower()
    
    # Hledat kilometry
    km_pattern = r'(\d+)\s*k[m]'
    km_match = re.search(km_pattern, message_lower)
    if km_match:
        try:
            parsed["odometer_km"] = int(km_match.group(1))
        except:
            pass
    
    # Hledat cenu
    price_patterns = [
        r'(\d+)\s*kč',
        r'(\d+)\s*czk',
        r'(\d+)\s*korun',
        r'za\s*(\d+)',
        r'(\d+)\s*,-'
    ]
    for pattern in price_patterns:
        price_match = re.search(pattern, message_lower)
        if price_match:
            try:
                parsed["price"] = float(price_match.group(1))
                break
            except:
                pass
    
    # Hledat kategorii
    category_keywords = {
        "OLEJ": ["olej", "oleje", "oil"],
        "BRZDY": ["brzdy", "brzd", "brake"],
        "PNEU": ["pneu", "pneumatiky", "guma", "gumy", "tire", "tyre"],
        "STK": ["stk", "technická", "technicka"],
        "DIAGNOSTIKA": ["diagnostika", "diagnostika", "diagnosis"]
    }
    
    for category, keywords in category_keywords.items():
        if any(keyword in message_lower for keyword in keywords):
            parsed["category"] = category
            break
    
    # Pokud není nalezena kategorie, použít "GENERAL"
    if not parsed["category"]:
        parsed["category"] = "GENERAL"
    
    return parsed


@router.post("/record", response_model=AIRecordResponseV1)
def create_record_from_ai(
    request: AIRecordRequestV1,
    db: Session = Depends(get_db)
):
    """
    Vytvoří servisní záznam z AI zprávy (autopilot integrace).
    
    Očekává:
    - shared_secret: pro autentizaci
    - user_id: ID uživatele
    - vehicle_id: (volitelné) ID vozidla
    - message: textová zpráva s informacemi o servisu
    """
    # 1. Ověřit shared_secret
    if not AUTOPILOT_SHARED_SECRET:
        raise HTTPException(status_code=500, detail="AUTOPILOT_SHARED_SECRET není nakonfigurován")
    
    if request.shared_secret != AUTOPILOT_SHARED_SECRET:
        raise HTTPException(status_code=401, detail="Neplatný shared_secret")
    
    # 2. Ověřit, že uživatel existuje
    user = db.query(Customer).filter(Customer.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    
    # 3. Najít vozidlo
    vehicle = None
    if request.vehicle_id:
        vehicle = get_owned_vehicle(
            db,
            user,
            int(request.vehicle_id),
            tenant_id=getattr(user, "tenant_id", None),
        )
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno nebo nepatří uživateli")
    else:
        # Pokusit se najít defaultní vozidlo (první vozidlo uživatele)
        owned_vehicles = get_owned_vehicle_rows(db, user, tenant_id=getattr(user, "tenant_id", None))
        vehicle = owned_vehicles[0] if owned_vehicles else None
        
        if not vehicle:
            raise HTTPException(
                status_code=400,
                detail="Uživatel nemá žádné vozidlo. Zadejte vehicle_id."
            )
    
    # 4. Parsovat zprávu
    parsed = parse_service_message(request.message)
    
    # 5. Vytvořit servisní záznam
    record = ServiceRecordModel(
        tenant_id=vehicle.tenant_id or getattr(user, "tenant_id", None) or 1,
        vehicle_id=vehicle.id,
        user_id=user.id,
        performed_at=datetime.now(),
        mileage=parsed.get("odometer_km"),
        description=parsed.get("description", request.message),
        price=parsed.get("price"),
        category=parsed.get("category"),
        note=f"Vytvořeno z AI: {request.message}"
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)
    
    # NAVÍC: Zaznamenat příkaz zákazníka do CustomerCommand (Command Bot v1)
    # Toto se provede asynchronně, aby neblokovalo odpověď
    try:
        from .customer_commands import CustomerCommandRequest
        from ..models import CustomerCommand
        from src.bot.command_engine import detect_intent
        
        # Vytvořit customer command záznam
        cc = CustomerCommand(
            source="autopilot",
            customer_name=user.name,
            customer_email=user.email,
            vehicle_id=vehicle.id,
            raw_text=request.message,
            intent_type=detect_intent(request.message).value,
            status="RECEIVED"
        )
        db.add(cc)
        db.commit()
        db.refresh(cc)
        
        # Pokusit se provést akci podle záměru (pokud to dává smysl)
        # Pro CREATE_BOOKING, CREATE_TASK, ADD_NOTE můžeme provést akci
        # Pro v1 to necháme na ruční zpracování, jen zaznamenáme
        cc.status = "RECEIVED"  # Pro v1 necháme na ruční zpracování
        cc.result_summary = "Zaznamenáno z AI endpointu - čeká na ruční zpracování"
        db.commit()
    except Exception as e:
        # Ignorovat chyby v customer command - nechceme rozbít hlavní funkcionalitu
        print(f"[AI] Warning: Customer command logging selhal: {e}")
    
    return AIRecordResponseV1(
        status="ok",
        record_id=record.id,
        vehicle_id=vehicle.id,
        parsed=parsed
    )
