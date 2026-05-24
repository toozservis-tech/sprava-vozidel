"""
AI Asistent Bot Router pro Správu vozidel

Tento router poskytuje endpointy pro komunikaci s AI asistentem.
Bot přijímá textové příkazy, zpracovává je a provádí akce v systému.

ARCHITEKTURA:
- POST /api/bot/command - přijme příkaz od uživatele
- Příkazy se ukládají do BotCommand tabulky
- Intent detection určuje typ akce
- Akce se provádějí bezpečně podle intent_type

BEZPEČNOST:
- Bot může provádět pouze explicitně naprogramované akce
- Všechny akce jsou logovány v BotCommand tabulce
- Každá akce má zjistitelný intent_type a status

ROZŠÍŘENÍ:
- TODO: Napojit na OpenAI/Claude API pro lepší intent detection
- TODO: Přidat více typů akcí (update_vehicle, delete_record, atd.)
- TODO: Přidat kontext z předchozích zpráv v session
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import re

from ..database import get_db
from ..models import BotCommand, Customer, Vehicle, ServiceRecord, Reminder
from ..ownership import get_customer_by_email, get_owned_vehicle_rows
from .auth import get_current_user, get_current_user_optional

router = APIRouter(prefix="/bot", tags=["bot"])


# ============= PYDANTIC MODELY =============

class BotCommandRequest(BaseModel):
    """Request model pro příkaz bota"""
    session_id: Optional[str] = None  # Session ID pro spojení zpráv
    user_role: Optional[str] = "owner"  # Role uživatele
    message: str  # Text příkazu od uživatele


class BotCommandResponse(BaseModel):
    """Response model pro odpověď bota"""
    reply_text: str  # Odpověď bota
    intent_type: Optional[str] = None  # Typ záměru
    status: str  # Status zpracování
    command_id: int  # ID záznamu v databázi


# ============= INTENT DETECTION (Placeholder) =============

def detect_intent(message: str) -> tuple[str, dict]:
    """
    Detekuje záměr z textu příkazu
    
    TODO: V budoucnu nahradit AI modelem (OpenAI/Claude)
    Prozatím jednoduchý rule-based parser
    
    Returns:
        tuple: (intent_type, extracted_data)
    """
    message_lower = message.lower()
    
    # Klíčová slova pro různé typy akcí
    if any(word in message_lower for word in ["úkol", "task", "připomínka", "reminder"]):
        # Detekce typu připomínky
        if any(word in message_lower for word in ["servis", "service", "servisní"]):
            return "create_service_reminder", {}
        elif any(word in message_lower for word in ["stk", "technická", "technicka"]):
            return "create_stk_reminder", {}
        elif any(word in message_lower for word in ["olej", "oil"]):
            return "create_oil_reminder", {}
        else:
            return "create_reminder", {}
    
    if any(word in message_lower for word in ["servisní úkon", "servisni ukon", "servis", "service record"]):
        return "create_service_record", {}
    
    if any(word in message_lower for word in ["poznámka", "poznamka", "note"]):
        return "add_note", {}
    
    if any(word in message_lower for word in ["vozidlo", "auto", "vehicle", "car"]):
        if any(word in message_lower for word in ["přidat", "pridat", "add", "nové", "nove", "new"]):
            return "create_vehicle", {}
    
    # Neznámý záměr
    return "unknown", {}


def extract_vehicle_info(message: str, db: Session, user_email: str) -> Optional[Vehicle]:
    """
    Pokusí se najít vozidlo z textu (podle názvu, SPZ, atd.)
    
    Returns:
        Vehicle nebo None
    """
    customer = get_customer_by_email(db, user_email)
    if customer is None:
        return None
    vehicles = get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None))

    # Hledání SPZ v textu (český formát: 1A2 3456 nebo 1A23456)
    spz_pattern = r'\b[A-Z0-9]{1,3}\s?[0-9]{4}\b'
    spz_match = re.search(spz_pattern, message.upper())
    if spz_match:
        spz = spz_match.group().replace(" ", "")
        for vehicle in vehicles:
            if str(getattr(vehicle, "plate", "") or "").strip().upper() == spz:
                return vehicle
    
    # Hledání podle názvu vozidla (nickname)
    for vehicle in vehicles:
        if vehicle.nickname and vehicle.nickname.lower() in message.lower():
            return vehicle
    
    # Pokud má uživatel jen jedno vozidlo, použij ho
    if len(vehicles) == 1:
        return vehicles[0]
    
    return None


def extract_datetime(message: str) -> Optional[datetime]:
    """
    Pokusí se extrahovat datum/čas z textu
    
    TODO: V budoucnu použít lepší NLP parser (např. dateparser)
    
    Returns:
        datetime nebo None
    """
    # Jednoduché klíčové slova
    message_lower = message.lower()
    
    if "zítra" in message_lower or "zitra" in message_lower:
        from datetime import timedelta
        return datetime.utcnow() + timedelta(days=1)
    
    if "dnes" in message_lower or "dneska" in message_lower:
        return datetime.utcnow()
    
    if "pozítří" in message_lower or "pozitri" in message_lower:
        from datetime import timedelta
        return datetime.utcnow() + timedelta(days=2)
    
    # TODO: Parsování konkrétních dat (např. "15.12.2024 10:00")
    
    return None


# ============= AI ASSISTANT PLACEHOLDER =============

def call_ai_assistant(message: str, context: Optional[dict] = None) -> str:
    """
    Placeholder funkce pro volání AI asistenta
    
    TODO: V budoucnu napojit na OpenAI/Claude API
    Prozatím vrací statickou odpověď
    
    Args:
        message: Text příkazu od uživatele
        context: Kontext (např. předchozí zprávy, data vozidla, atd.)
    
    Returns:
        Odpověď AI asistenta
    """
    # TODO: Implementovat skutečné volání AI API
    # Např.:
    # response = openai.ChatCompletion.create(
    #     model="gpt-4",
    #     messages=[{"role": "user", "content": message}]
    # )
    # return response.choices[0].message.content
    
    return "Příkaz byl přijat a zpracován."


# ============= ACTION EXECUTORS =============

def execute_action(
    intent_type: str,
    message: str,
    db: Session,
    user_email: str,
    user_id: Optional[int] = None
) -> tuple[str, bool]:
    """
    Provede akci podle intent_type
    
    Returns:
        tuple: (result_message, success)
    """
    try:
        if intent_type == "create_service_record":
            # Vytvoření servisního záznamu
            vehicle = extract_vehicle_info(message, db, user_email)
            if not vehicle:
                return "Nepodařilo se najít vozidlo. Zadejte prosím SPZ nebo název vozidla.", False
            
            # Extrahovat popis
            description = message
            # Odstranit klíčová slova
            for word in ["servisní úkon", "servisni ukon", "servis", "service record", "přidej", "pridaj", "add"]:
                description = re.sub(word, "", description, flags=re.IGNORECASE)
            description = description.strip()
            
            if not description:
                description = "Servisní úkon"
            
            # Extrahovat datum
            performed_at = extract_datetime(message) or datetime.utcnow()
            
            # Vytvořit záznam
            record = ServiceRecord(
                vehicle_id=vehicle.id,
                user_id=user_id,
                performed_at=performed_at,
                description=description,
                note="Vytvořeno AI asistentem",
                created_by_ai=True  # Označit jako vytvořené AI
            )
            db.add(record)
            db.commit()
            
            return f"Servisní úkon byl přidán k vozidlu {vehicle.nickname or vehicle.plate or 'bez názvu'}.", True
        
        elif intent_type in ["create_reminder", "create_service_reminder", "create_stk_reminder", "create_oil_reminder"]:
            # Vytvoření připomínky
            vehicle = extract_vehicle_info(message, db, user_email)
            customer = get_customer_by_email(db, user_email)
            
            if not customer:
                return "Uživatel nebyl nalezen.", False
            
            # Určit typ připomínky
            reminder_type = "GENERAL"
            if intent_type == "create_service_reminder":
                reminder_type = "SERVIS"
            elif intent_type == "create_stk_reminder":
                reminder_type = "STK"
            elif intent_type == "create_oil_reminder":
                reminder_type = "OLEJ"
            
            # Extrahovat text a datum
            text = message
            for word in ["úkol", "task", "připomínka", "pripominka", "reminder", "přidej", "pridaj", "add"]:
                text = re.sub(word, "", text, flags=re.IGNORECASE)
            text = text.strip()
            
            if not text:
                text = "Připomínka"
            
            due_date = extract_datetime(message)
            if due_date:
                from datetime import date
                due_date = due_date.date()
            
            # Vytvořit připomínku
            reminder = Reminder(
                customer_id=customer.id,
                vehicle_id=vehicle.id if vehicle else None,
                type=reminder_type,
                text=text,
                due_date=due_date,
                is_manual=True
            )
            db.add(reminder)
            db.commit()
            
            vehicle_name = vehicle.nickname or vehicle.plate if vehicle else "všechna vozidla"
            return f"Připomínka byla vytvořena pro {vehicle_name}.", True
        
        elif intent_type == "add_note":
            # Přidání poznámky k vozidlu
            vehicle = extract_vehicle_info(message, db, user_email)
            if not vehicle:
                return "Nepodařilo se najít vozidlo. Zadejte prosím SPZ nebo název vozidla.", False
            
            # Extrahovat poznámku
            note = message
            for word in ["poznámka", "poznamka", "note", "přidej", "pridaj", "add"]:
                note = re.sub(word, "", note, flags=re.IGNORECASE)
            note = note.strip()
            
            if not note:
                return "Zadejte prosím text poznámky.", False
            
            # Přidat k existující poznámce
            if vehicle.notes:
                vehicle.notes = f"{vehicle.notes}\n\n{note}"
            else:
                vehicle.notes = note
            
            db.commit()
            
            return f"Poznámka byla přidána k vozidlu {vehicle.nickname or vehicle.plate or 'bez názvu'}.", True
        
        elif intent_type == "unknown":
            return "Nerozumím příkazu. Zkuste například: 'přidej servisní úkon na Fabii zítra výměna oleje' nebo 'vytvoř připomínku na STK'.", False
        
        else:
            return f"Akce typu '{intent_type}' zatím není implementována.", False
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Chyba při provádění akce: {str(e)}", False


# ============= ENDPOINT =============

@router.post("/command", response_model=BotCommandResponse)
def process_bot_command(
    request: BotCommandRequest,
    db: Session = Depends(get_db),
    current_user: Optional[Customer] = Depends(get_current_user_optional)
):
    """
    Zpracuje příkaz od uživatele a provede odpovídající akci
    
    Flow:
    1. Uloží příkaz do BotCommand s status="received"
    2. Detekuje intent z textu
    3. Provede akci podle intent_type
    4. Uloží výsledek zpět do BotCommand
    5. Vrátí odpověď uživateli
    """
    # Získat informace o uživateli
    user_email = current_user.email if current_user else None
    user_id = current_user.id if current_user else None
    user_role = request.user_role or (current_user.role if current_user else "guest")
    
    # Generovat session_id, pokud není zadán
    session_id = request.session_id or str(uuid.uuid4())
    
    # Vytvořit záznam v databázi
    bot_command = BotCommand(
        user_id=user_id,
        user_email=user_email,
        user_role=user_role,
        session_id=session_id,
        raw_text=request.message,
        status="received"
    )
    db.add(bot_command)
    db.commit()
    db.refresh(bot_command)
    
    try:
        # Detekovat intent
        intent_type, extracted_data = detect_intent(request.message)
        bot_command.intent_type = intent_type
        bot_command.status = "processing"
        db.commit()
        
        # Provedit akci
        result_message, success = execute_action(
            intent_type=intent_type,
            message=request.message,
            db=db,
            user_email=user_email or "",
            user_id=user_id
        )
        
        # TODO: V budoucnu použít AI pro generování odpovědi
        # ai_response = call_ai_assistant(request.message, context={...})
        # result_message = ai_response
        
        # Aktualizovat záznam
        bot_command.status = "processed" if success else "failed"
        bot_command.result_message = result_message
        bot_command.processed_at = datetime.utcnow()
        
        if not success:
            bot_command.error_message = result_message
        
        db.commit()
        
        return BotCommandResponse(
            reply_text=result_message,
            intent_type=intent_type,
            status=bot_command.status,
            command_id=bot_command.id
        )
    
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        
        # Aktualizovat záznam s chybou
        bot_command.status = "failed"
        bot_command.error_message = error_msg
        bot_command.processed_at = datetime.utcnow()
        db.commit()
        
        raise HTTPException(
            status_code=500,
            detail=f"Chyba při zpracování příkazu: {error_msg}"
        )


@router.get("/history")
def get_bot_history(
    session_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: Optional[Customer] = Depends(get_current_user_optional)
):
    """
    Vrátí historii příkazů pro danou session nebo uživatele
    """
    query = db.query(BotCommand)
    
    if session_id:
        query = query.filter(BotCommand.session_id == session_id)
    elif current_user:
        query = query.filter(BotCommand.user_id == current_user.id)
    else:
        raise HTTPException(status_code=401, detail="Musíte být přihlášeni nebo zadat session_id")
    
    commands = query.order_by(BotCommand.created_at.desc()).limit(limit).all()
    
    return {
        "commands": [
            {
                "id": cmd.id,
                "raw_text": cmd.raw_text,
                "result_message": cmd.result_message,
                "intent_type": cmd.intent_type,
                "status": cmd.status,
                "created_at": cmd.created_at.isoformat() if cmd.created_at else None
            }
            for cmd in commands
        ]
    }






