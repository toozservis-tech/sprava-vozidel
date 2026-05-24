"""
Customer Commands API v1.0 router
API pro zpracování příkazů zákazníků (Command Bot v1)
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..database import get_db
from ..models import CustomerCommand, Vehicle as VehicleModel, Customer, Reservation, Reminder, ServiceRecord as ServiceRecordModel
from ..ownership import (
    ensure_vehicle_owner_assignment,
    get_customer_by_email,
    get_owned_vehicle_rows,
)
from src.bot.command_engine import detect_intent, IntentType

router = APIRouter(prefix="/api/customer-commands", tags=["customer-commands"])


# Pydantic modely pro request/response
class CustomerCommandRequest(BaseModel):
    source: str  # např. "web_chat", "autopilot", "internal"
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    vehicle_id: Optional[int] = None
    message: str


class CustomerCommandResponse(BaseModel):
    intent_type: str
    status: str
    result_summary: Optional[str] = None
    command_id: int
    requires_vehicle_selection: bool = False
    available_vehicles: Optional[List[dict]] = None


def _get_customer_owned_vehicles(db: Session, customer_email: str) -> List[VehicleModel]:
    customer = get_customer_by_email(db, customer_email)
    if customer is None:
        return []
    return get_owned_vehicle_rows(db, customer, tenant_id=getattr(customer, "tenant_id", None))


def find_vehicles_by_text(text: str, customer_email: str, db: Session) -> List[dict]:
    """
    Najde vozidla uživatele podle textu v příkazu.
    
    Args:
        text: Text příkazu (např. "eviduj výměnu oleje na vozidle škoda superb")
        customer_email: Email zákazníka
        db: Database session
        
    Returns:
        List[dict]: Seznam vozidel s id, nickname, brand, model, plate
    """
    if not customer_email:
        return []
    
    # Získat všechna vozidla uživatele
    vehicles = _get_customer_owned_vehicles(db, customer_email)
    
    if not vehicles:
        return []
    
    # Normalizovat text pro hledání (malá písmena, odstranit diakritiku)
    import unicodedata
    def normalize_text(t):
        t = t.lower()
        t = unicodedata.normalize('NFKD', t)
        t = ''.join(c for c in t if not unicodedata.combining(c))
        return t
    
    text_normalized = normalize_text(text)
    
    # Klíčová slova pro hledání vozidel
    vehicle_keywords = []
    for vehicle in vehicles:
        keywords = []
        if vehicle.nickname:
            keywords.append(normalize_text(vehicle.nickname))
        if vehicle.brand:
            keywords.append(normalize_text(vehicle.brand))
        if vehicle.model:
            keywords.append(normalize_text(vehicle.model))
        if vehicle.plate:
            keywords.append(normalize_text(vehicle.plate))
        # Kombinace brand + model
        if vehicle.brand and vehicle.model:
            keywords.append(normalize_text(f"{vehicle.brand} {vehicle.model}"))
        
        vehicle_keywords.append((vehicle, keywords))
    
    # Najít vozidla, která se shodují s textem
    matched_vehicles = []
    for vehicle, keywords in vehicle_keywords:
        for keyword in keywords:
            if keyword and keyword in text_normalized:
                matched_vehicles.append({
                    "id": vehicle.id,
                    "nickname": vehicle.nickname or "",
                    "brand": vehicle.brand or "",
                    "model": vehicle.model or "",
                    "plate": vehicle.plate or "",
                    "display_name": f"{vehicle.nickname or vehicle.brand or 'Vozidlo'} {vehicle.model or ''} {vehicle.plate or ''}".strip()
                })
                break  # Každé vozidlo přidat jen jednou
    
    return matched_vehicles


def execute_customer_command(command: CustomerCommand, db: Session) -> str:
    """
    Provede akci podle typu záměru příkazu.
    
    Args:
        command: CustomerCommand objekt s rozpoznaným intent_type
        db: Database session
        
    Returns:
        str: Textový popis výsledku (pro result_summary)
    """
    try:
        if command.intent_type == IntentType.CREATE_BOOKING:
            # Vytvořit rezervaci (pro v1 jen záznam "Čeká na ruční potvrzení")
            # Pro v1 vytvoříme rezervaci se statusem PENDING
            
            # Zkontrolovat, zda máme customer_id
            customer_id = None
            if command.customer_email:
                customer = db.query(Customer).filter(Customer.email == command.customer_email).first()
                if customer:
                    customer_id = customer.id
            
            if not customer_id:
                # Pokud nemáme customer_id, nemůžeme vytvořit rezervaci
                # Vytvoříme jen záznam v CustomerCommand s poznámkou
                return "Rezervace vyžaduje přihlášeného zákazníka. Příkaz byl zaznamenán a čeká na ruční zpracování."
            
            if not command.vehicle_id:
                return "Rezervace vyžaduje vozidlo. Příkaz byl zaznamenán a čeká na ruční zpracování."
            
            # Vytvořit rezervaci
            # Pro v1 použijeme výchozí servis (můžeme později rozšířit)
            # Zkusit najít servis (Customer s role='service')
            service = db.query(Customer).filter(Customer.role == 'service').first()
            if not service:
                return "Rezervace vyžaduje nakonfigurovaný servis. Příkaz byl zaznamenán a čeká na ruční zpracování."
            
            # Vytvořit rezervaci s výchozím termínem (např. za týden)
            from datetime import timedelta
            start_datetime = datetime.utcnow() + timedelta(days=7)
            
            reservation = Reservation(
                service_id=service.id,
                customer_id=customer_id,
                vehicle_id=command.vehicle_id,
                service_type="Obecný servis",
                note=f"Vytvořeno z příkazu zákazníka: {command.raw_text[:100]}",
                start_datetime=start_datetime,
                status="PENDING"
            )
            db.add(reservation)
            db.commit()
            db.refresh(reservation)
            
            return f"Vytvořena rezervace ID {reservation.id} – čeká na potvrzení."
            
        elif command.intent_type == IntentType.CREATE_TASK:
            # Vytvořit interní task/připomínku
            # Použijeme Reminder model pro v1
            
            # Zkontrolovat, zda máme customer_id
            customer_id = None
            if command.customer_email:
                customer = db.query(Customer).filter(Customer.email == command.customer_email).first()
                if customer:
                    customer_id = customer.id
            
            if not customer_id:
                return "Úkol vyžaduje přihlášeného zákazníka. Příkaz byl zaznamenán a čeká na ruční zpracování."
            
            # Vytvořit připomínku
            # Pro v1 použijeme výchozí datum (za týden)
            from datetime import timedelta
            reminder_date = datetime.utcnow() + timedelta(days=7)
            
            reminder = Reminder(
                customer_id=customer_id,
                vehicle_id=command.vehicle_id,
                reminder_type="GENERAL",
                title=f"Úkol z příkazu zákazníka",
                description=command.raw_text[:500],
                due_date=reminder_date.date(),
                is_completed=False
            )
            db.add(reminder)
            db.commit()
            db.refresh(reminder)
            
            return f"Vytvořen úkol ID {reminder.id} – čeká na zpracování."
            
        elif command.intent_type == IntentType.ADD_NOTE:
            # Přidat poznámku k vozidlu nebo vytvořit interní poznámku
            if command.vehicle_id:
                # Přidat poznámku k vozidlu
                vehicle = db.query(VehicleModel).filter(VehicleModel.id == command.vehicle_id).first()
                if vehicle:
                    # Aktualizovat poznámku vozidla (pokud existuje pole notes)
                    # Pro v1 použijeme pole note, pokud existuje
                    if hasattr(vehicle, 'note'):
                        existing_note = vehicle.note or ""
                        new_note = f"{existing_note}\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] {command.raw_text[:500]}"
                        vehicle.note = new_note.strip()
                    else:
                        # Pokud nemáme pole note, vytvoříme servisní záznam jako poznámku
                        service_record = ServiceRecordModel(
                            tenant_id=vehicle.tenant_id or command.tenant_id or 1,
                            vehicle_id=command.vehicle_id,
                            performed_at=datetime.utcnow(),
                            description=f"Poznámka: {command.raw_text[:500]}",
                            category="JINE",
                            note=command.raw_text[:500]
                        )
                        db.add(service_record)
                    db.commit()
                    return f"Poznámka byla přidána k vozidlu ID {command.vehicle_id}."
                else:
                    return "Vozidlo nenalezeno. Příkaz byl zaznamenán a čeká na ruční zpracování."
            else:
                # Interní poznámka (jen záznam v CustomerCommand)
                return "Poznámka byla zaznamenána. (Pro interní poznámky použijte vozidlo.)"
            
        elif command.intent_type == IntentType.ADD_VEHICLE:
            # Přidat vozidlo s interaktivním dotazováním
            # Zkontrolovat, zda máme customer_id
            customer_id = None
            tenant_id = 1
            if command.customer_email:
                customer = db.query(Customer).filter(Customer.email == command.customer_email).first()
                if customer:
                    customer_id = customer.id
                    if hasattr(customer, 'tenant_id') and customer.tenant_id:
                        tenant_id = customer.tenant_id
            
            if not customer_id:
                return "Přidání vozidla vyžaduje přihlášeného zákazníka. Příkaz byl zaznamenán a čeká na ruční zpracování."
            
            # Parsovat VIN z textu (hledat 17 znaků alfanumerických)
            import re
            import json
            vin_match = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', command.raw_text.upper())
            vin = vin_match.group(1) if vin_match else None
            
            # Zkontrolovat, zda už máme uložený kontext (dotazování)
            context_data = None
            if command.normalized_text:
                try:
                    context_data = json.loads(command.normalized_text)
                except:
                    pass
            
            # Pokud nemáme VIN a nemáme kontext, požádat o VIN
            if not vin and not context_data:
                return "Pro přidání vozidla potřebuji VIN kód (17 znaků). Zadejte prosím VIN vozidla."
            
            # Pokud máme VIN ale nemáme kontext, načíst data z MDČR a pak vytvořit kontext
            if vin and not context_data:
                # Nejdřív načíst data z MDČR API, abychom mohli zobrazit informace o vozidle
                brand = None
                model = None
                year = None
                
                try:
                    from src.modules.vehicle_hub.decoder.mdcr_client import fetch_vehicle_by_vin_from_mdcr
                    import asyncio
                    
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    mdcr_data = loop.run_until_complete(fetch_vehicle_by_vin_from_mdcr(vin))
                    
                    if mdcr_data:
                        brand = mdcr_data.make
                        model = mdcr_data.model
                        if mdcr_data.production_year:
                            year = int(mdcr_data.production_year)
                        print(f"[COMMAND] MDČR data načtena: {brand} {model} ({year})")
                    
                    # Fallback na lokální dekódování
                    if not brand or not model:
                        from src.modules.vehicle_hub.decoder.vin_decoder import decode_vin_local
                        local_data, _ = decode_vin_local(vin)
                        if local_data:
                            if not brand:
                                brand = local_data.make
                            if not model:
                                model = local_data.model
                            if not year and local_data.model_year:
                                year = int(local_data.model_year)
                except Exception as e:
                    print(f"[COMMAND] VIN decode failed: {e}")
                
                # Vytvořit kontext s načtenými daty
                context_data = {
                    "step": "waiting_for_info",
                    "vin": vin,
                    "brand": brand,
                    "model": model,
                    "year": year
                }
                # Uložit kontext do normalized_text
                command.normalized_text = json.dumps(context_data)
                command.status = "REQUIRES_INFO"
                db.commit()
                
                # Vytvořit zprávu s informacemi o vozidle
                vehicle_preview = ""
                if brand and model:
                    vehicle_preview = f"✅ Našel jsem vozidlo: **{brand} {model}" + (f" ({year})" if year else "") + "**\n\n"
                else:
                    vehicle_preview = f"✅ VIN kód je platný.\n\n"
                
                # Vrátit zprávu s požadavkem na další údaje - NEPOKRAČOVAT dál
                return f"{vehicle_preview}⚠️ Pro dokončení přidání vozidla potřebuji ještě:\n• SPZ (registrační značka) - POVINNÉ\n• název vozidla (jak chcete vozidlo pojmenovat) - POVINNÉ\n\nZadejte prosím chybějící údaje (např. 'SPZ: 1A2 3456, název: Moje škoda')."
            
            # Pokud máme kontext, zkusit extrahovat informace z aktuální zprávy
            if context_data and context_data.get("step") == "waiting_for_info":
                vin = context_data.get("vin")  # Použít VIN z kontextu
                
                # Zkusit najít SPZ v textu (různé formáty: 1A2 3456, 1A23456, ABC-1234)
                plate_match = re.search(r'\b([A-Z0-9]{1,3}[-\s]?[A-Z0-9]{4,6})\b', command.raw_text.upper())
                plate = plate_match.group(1).replace(" ", "").replace("-", "") if plate_match else None
                
                # Název vozidla - hledat po klíčových slovech
                name_keywords = ["název", "nazev", "jméno", "jmeno", "pojmenuj", "pojmenovat", "chci", "chce", "chceme", "nazvu", "nazvu"]
                nickname = None
                for keyword in name_keywords:
                    pattern = rf'{keyword}[:\s]+([^\n,]+?)(?:,|\n|$)'
                    name_match = re.search(pattern, command.raw_text, re.IGNORECASE)
                    if name_match:
                        nickname = name_match.group(1).strip()
                        # Odstranit případné uvozovky
                        nickname = nickname.strip('"\'')
                        break
                
                # Pokud nemáme název, zkusit najít něco po "SPZ" nebo před "SPZ"
                if not nickname and plate:
                    # Zkusit najít text před nebo po SPZ
                    parts = re.split(re.escape(plate), command.raw_text, flags=re.IGNORECASE)
                    for part in parts:
                        part = part.strip()
                        # Odstranit běžná slova
                        part = re.sub(r'\b(spz|registrační|znacka|značka|plate)\b', '', part, flags=re.IGNORECASE).strip()
                        if part and len(part) > 2 and len(part) < 50:
                            # Ověřit, že to není jen číslo nebo SPZ
                            if not re.match(r'^[\d\s-]+$', part):
                                nickname = part.strip(' ,:')
                                break
                
                # Aktualizovat kontext
                if plate:
                    context_data["plate"] = plate
                if nickname:
                    context_data["nickname"] = nickname
                
                # Použít data z kontextu
                brand = context_data.get("brand")
                model = context_data.get("model")
                year = context_data.get("year")
            else:
                # Pokud nemáme kontext, musíme mít VIN
                if not vin:
                    return "VIN nebyl nalezen v příkazu. Zadejte VIN (17 znaků)."
            
            # Pokud stále nemáme VIN, požádat o něj
            if not vin:
                return "VIN nebyl nalezen v příkazu. Zadejte VIN (17 znaků)."
            
            # Zkontrolovat, zda vozidlo s tímto VIN už neexistuje
            customer = get_customer_by_email(db, command.customer_email)
            existing = None
            if customer is not None:
                existing = next(
                    (
                        vehicle
                        for vehicle in _get_customer_owned_vehicles(db, command.customer_email)
                        if str(getattr(vehicle, "vin", None) or "").strip().upper() == vin
                    ),
                    None,
                )
            
            if existing:
                return f"Vozidlo s VIN {vin} již existuje (ID: {existing.id})."
            
            # Dekódovat VIN pomocí MDČR API a lokálního dekodéru (pouze pokud nemáme data z kontextu)
            if not brand or not model:
                engine = None
                engine_code = None
                plate_from_api = None
                stk_valid_until = None
                tyres_info = None
                notes_parts = [f"Přidáno přes Command Bot: {command.raw_text[:200]}"]
                
                try:
                    # Použít MDČR API (async, ale můžeme použít sync wrapper)
                    from src.modules.vehicle_hub.decoder.mdcr_client import fetch_vehicle_by_vin_from_mdcr
                    import asyncio
                    
                    # Zkusit načíst z MDČR API
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    mdcr_data = loop.run_until_complete(fetch_vehicle_by_vin_from_mdcr(vin))
                    
                    if mdcr_data:
                        if not brand:
                            brand = mdcr_data.make
                        if not model:
                            model = mdcr_data.model
                        if not year and mdcr_data.production_year:
                            year = int(mdcr_data.production_year)
                        if mdcr_data.engine_code:
                            engine_code = mdcr_data.engine_code
                        if mdcr_data.engine_displacement_cc and mdcr_data.engine_power_kw:
                            engine = f"{mdcr_data.engine_displacement_cc}cm³ / {mdcr_data.engine_power_kw}kW"
                            if engine_code:
                                engine += f" / {engine_code}"
                        elif mdcr_data.engine_code:
                            engine = engine_code
                        if mdcr_data.plate:
                            plate_from_api = mdcr_data.plate
                        if mdcr_data.stk_valid_until:
                            stk_valid_until = mdcr_data.stk_valid_until
                        if mdcr_data.tyres_raw:
                            tyres_info = mdcr_data.tyres_raw
                        if mdcr_data.extra_records:
                            notes_parts.append(f"\n\nData z MDČR:\n{mdcr_data.extra_records}")
                        
                        print(f"[COMMAND] MDČR data načtena: {brand} {model} ({year})")
                    
                    # Fallback na lokální dekódování, pokud MDČR nevrátilo data
                    if not brand or not model:
                        from src.modules.vehicle_hub.decoder.vin_decoder import decode_vin_local
                        local_data, _ = decode_vin_local(vin)
                        if local_data:
                            if not brand:
                                brand = local_data.make
                            if not model:
                                model = local_data.model
                            if not year and local_data.model_year:
                                year = int(local_data.model_year)
                        print(f"[COMMAND] Lokální VIN data načtena: {brand} {model} ({year})")
                except Exception as e:
                    print(f"[COMMAND] VIN decode failed: {e}")
                    import traceback
                    traceback.print_exc()
                    # Pokračovat bez dekódování
                    engine = None
                    engine_code = None
                    plate_from_api = None
                    stk_valid_until = None
                    tyres_info = None
                    notes_parts = [f"Přidáno přes Command Bot: {command.raw_text[:200]}"]
            else:
                # Máme data z kontextu, ale potřebujeme načíst další údaje z MDČR (motor, STK, atd.)
                engine = None
                engine_code = None
                plate_from_api = None
                stk_valid_until = None
                tyres_info = None
                notes_parts = [f"Přidáno přes Command Bot: {command.raw_text[:200]}"]
                
                try:
                    from src.modules.vehicle_hub.decoder.mdcr_client import fetch_vehicle_by_vin_from_mdcr
                    import asyncio
                    
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    mdcr_data = loop.run_until_complete(fetch_vehicle_by_vin_from_mdcr(vin))
                    
                    if mdcr_data:
                        if mdcr_data.engine_code:
                            engine_code = mdcr_data.engine_code
                        if mdcr_data.engine_displacement_cc and mdcr_data.engine_power_kw:
                            engine = f"{mdcr_data.engine_displacement_cc}cm³ / {mdcr_data.engine_power_kw}kW"
                            if engine_code:
                                engine += f" / {engine_code}"
                        elif mdcr_data.engine_code:
                            engine = engine_code
                        if mdcr_data.plate:
                            plate_from_api = mdcr_data.plate
                        if mdcr_data.stk_valid_until:
                            stk_valid_until = mdcr_data.stk_valid_until
                        if mdcr_data.tyres_raw:
                            tyres_info = mdcr_data.tyres_raw
                        if mdcr_data.extra_records:
                            notes_parts.append(f"\n\nData z MDČR:\n{mdcr_data.extra_records}")
                except Exception as e:
                    print(f"[COMMAND] VIN decode failed: {e}")
            
            # Získat SPZ a název z kontextu nebo z API
            plate = context_data.get("plate") if context_data else None
            if not plate:
                plate = plate_from_api
            
            nickname = context_data.get("nickname") if context_data else None
            
            # Pokud nemáme SPZ nebo název, MUSÍME se zeptat - NIKDY nevytvářet vozidlo bez těchto údajů
            # SPZ je vždy povinná, název je povinný
            if not plate or not nickname:
                # Uložit kontext pro další dotazování
                context = {
                    "step": "waiting_for_info",
                    "vin": vin,
                    "brand": brand,
                    "model": model,
                    "year": year
                }
                if plate:
                    context["plate"] = plate
                if nickname and nickname != f"Vozidlo {vin[:8]}":
                    context["nickname"] = nickname
                
                command.normalized_text = json.dumps(context)
                command.status = "REQUIRES_INFO"
                db.commit()
                
                missing = []
                if not plate:
                    missing.append("SPZ (registrační značka) - POVINNÉ")
                if not nickname:
                    # Navrhnout výchozí název, ale stále se zeptat
                    suggested_name = ""
                    if brand and model:
                        suggested_name = f"{brand} {model}"
                        if year:
                            suggested_name += f" ({year})"
                    else:
                        suggested_name = f"Vozidlo {vin[:8]}"
                    missing.append(f"název vozidla (např. '{suggested_name}') - POVINNÉ")
                
                vehicle_preview = ""
                if brand and model:
                    vehicle_preview = f"✅ Našel jsem vozidlo: **{brand} {model}" + (f" ({year})" if year else "") + "**\n\n"
                else:
                    vehicle_preview = f"✅ VIN kód je platný.\n\n"
                
                return f"{vehicle_preview}⚠️ Pro dokončení přidání vozidla potřebuji ještě:\n• {chr(10) + '• '.join(missing)}\n\nZadejte prosím chybějící údaje (např. 'SPZ: 1A2 3456, název: Moje škoda')."
            
            # Vytvořit vozidlo se všemi daty
            vehicle = VehicleModel(
                user_email=command.customer_email,
                tenant_id=tenant_id,
                nickname=nickname,
                brand=brand,
                model=model,
                year=year,
                engine=engine,
                vin=vin,
                plate=plate,
                stk_valid_until=stk_valid_until,
                tyres_info=tyres_info,
                notes="\n".join(notes_parts)
            )
            db.add(vehicle)
            db.flush()
            if customer is not None:
                ensure_vehicle_owner_assignment(
                    db,
                    vehicle=vehicle,
                    owner=customer,
                    assigned_by_customer_id=customer.id,
                )
            db.commit()
            db.refresh(vehicle)
            
            vehicle_info = f"{vehicle.nickname}"
            if vehicle.brand and vehicle.model:
                vehicle_info = f"{vehicle.brand} {vehicle.model}"
            if vehicle.year:
                vehicle_info += f" ({vehicle.year})"
            
            result_msg = f"✅ Vozidlo bylo úspěšně přidáno!\n\n"
            result_msg += f"**{vehicle_info}**\n"
            result_msg += f"• VIN: {vin}\n"
            if plate:
                result_msg += f"• SPZ: {plate}\n"
            if engine:
                result_msg += f"• Motor: {engine}\n"
            if stk_valid_until:
                result_msg += f"• STK platná do: {stk_valid_until.strftime('%d.%m.%Y')}\n"
            result_msg += f"• ID: {vehicle.id}"
            
            return result_msg
            
        elif command.intent_type in [IntentType.QUESTION, IntentType.UNKNOWN]:
            # Pro otázky a neznámé příkazy nic automaticky nevykonáváme
            return "Příkaz byl zaznamenán a čeká na ruční zpracování."
        
        else:
            return "Neznámý typ záměru. Příkaz byl zaznamenán a čeká na ruční zpracování."
            
    except Exception as e:
        # V případě chyby vrátit chybovou zprávu
        return f"Chyba při zpracování příkazu: {str(e)}"


@router.post("", response_model=CustomerCommandResponse)
def create_customer_command(
    request: CustomerCommandRequest,
    db: Session = Depends(get_db)
):
    """
    Vytvoří nový zákaznický příkaz a pokusí se ho zpracovat.
    
    Tento endpoint přijímá příkazy z různých zdrojů (web chat, autopilot, atd.)
    a automaticky je zpracovává podle rozpoznaného záměru.
    """
    # Získat tenant_id z uživatele (pokud existuje)
    tenant_id = 1  # Výchozí tenant_id
    if request.customer_email:
        customer = db.query(Customer).filter(Customer.email == request.customer_email).first()
        if customer and hasattr(customer, 'tenant_id') and customer.tenant_id:
            tenant_id = customer.tenant_id
    
    # Zkontrolovat, zda existuje předchozí příkaz s REQUIRES_INFO statusem
    # Pokud ano, pokračovat v dotazování místo vytváření nového příkazu
    if request.customer_email:
        pending_command = db.query(CustomerCommand).filter(
            CustomerCommand.customer_email == request.customer_email,
            CustomerCommand.status == "REQUIRES_INFO",
            CustomerCommand.intent_type == IntentType.ADD_VEHICLE.value
        ).order_by(CustomerCommand.created_at.desc()).first()
        
        if pending_command:
            # Pokračovat v dotazování - použít existující příkaz
            try:
                result_summary = execute_customer_command(pending_command, db)
                
                # Zkontrolovat, zda execute_customer_command nastavil status na REQUIRES_INFO
                db.refresh(pending_command)
                if pending_command.status == "REQUIRES_INFO":
                    # Status už je nastaven na REQUIRES_INFO, nechat ho
                    pending_command.result_summary = result_summary
                elif "⚠️" in result_summary or "potřebuji ještě" in result_summary.lower() or "POVINNÉ" in result_summary:
                    # Pokud zpráva obsahuje požadavek na další údaje, nastavit REQUIRES_INFO
                    pending_command.status = "REQUIRES_INFO"
                    pending_command.result_summary = result_summary
                else:
                    # Jinak nastavit podle výsledku
                    pending_command.status = "EXECUTED" if "✅" in result_summary and "úspěšně" in result_summary.lower() else "REQUIRES_INFO"
                    pending_command.result_summary = result_summary
                    pending_command.processed_at = datetime.utcnow()
                
                # Aktualizovat raw_text s novou zprávou
                pending_command.raw_text = f"{pending_command.raw_text}\n\n[Pokračování] {request.message}"
                
                db.commit()
                db.refresh(pending_command)
                
                return CustomerCommandResponse(
                    intent_type=pending_command.intent_type,
                    status=pending_command.status,
                    result_summary=pending_command.result_summary,
                    command_id=pending_command.id,
                    requires_vehicle_selection=False,
                    available_vehicles=None
                )
            except Exception as e:
                import traceback
                error_traceback = traceback.format_exc()
                print(f"[CUSTOMER_COMMAND ERROR] Chyba při pokračování dotazování: {str(e)}")
                print(f"[CUSTOMER_COMMAND ERROR] Traceback:\n{error_traceback}")
                
                pending_command.status = "FAILED"
                pending_command.error_message = str(e)
                pending_command.processed_at = datetime.utcnow()
                db.commit()
                
                return CustomerCommandResponse(
                    intent_type=pending_command.intent_type,
                    status="FAILED",
                    result_summary=f"Chyba: {str(e)}",
                    command_id=pending_command.id,
                    requires_vehicle_selection=False,
                    available_vehicles=None
                )
    
    # Rozpoznat záměr
    try:
        intent = detect_intent(request.message)
    except Exception as e:
        print(f"[CUSTOMER_COMMAND] Chyba při rozpoznávání záměru: {e}")
        intent = IntentType.UNKNOWN
    
    # Pokud příkaz vyžaduje vozidlo a není zadáno, zkusit najít podle textu
    requires_vehicle = intent in [IntentType.CREATE_BOOKING, IntentType.CREATE_TASK, IntentType.ADD_NOTE]
    available_vehicles = None
    
    if requires_vehicle and not request.vehicle_id and request.customer_email:
        try:
            # Zkusit najít vozidla podle textu
            matched_vehicles = find_vehicles_by_text(request.message, request.customer_email, db)
            
            if len(matched_vehicles) == 1:
                # Jednoznačná shoda - použít toto vozidlo
                request.vehicle_id = matched_vehicles[0]["id"]
            elif len(matched_vehicles) > 1:
                # Více shod - vrátit seznam k výběru
                available_vehicles = matched_vehicles
            else:
                # Žádná shoda - zobrazit všechna vozidla uživatele
                try:
                    all_vehicles = _get_customer_owned_vehicles(db, request.customer_email)
                    available_vehicles = [
                        {
                            "id": v.id,
                            "nickname": v.nickname or "",
                            "brand": v.brand or "",
                            "model": v.model or "",
                            "plate": v.plate or "",
                            "display_name": f"{v.nickname or v.brand or 'Vozidlo'} {v.model or ''} {v.plate or ''}".strip()
                        }
                        for v in all_vehicles
                    ]
                except Exception as e:
                    print(f"[CUSTOMER_COMMAND] Chyba při načítání vozidel: {e}")
                    available_vehicles = []
        except Exception as e:
            print(f"[CUSTOMER_COMMAND] Chyba při hledání vozidel: {e}")
            available_vehicles = []
    
    # Pokud potřebujeme výběr vozidla, vrátit speciální response
    if requires_vehicle and not request.vehicle_id:
        if not available_vehicles or len(available_vehicles) == 0:
            # Uživatel nemá žádná vozidla
            command = CustomerCommand(
                tenant_id=tenant_id,
                source=request.source,
                customer_name=request.customer_name,
                customer_email=request.customer_email,
                vehicle_id=None,
                raw_text=request.message,
                status="RECEIVED",
                intent_type=intent.value
            )
            db.add(command)
            db.commit()
            db.refresh(command)
            
            return CustomerCommandResponse(
                intent_type=command.intent_type,
                status="FAILED",
                result_summary="Nemáte žádná vozidla v systému. Nejdříve přidejte vozidlo.",
                command_id=command.id,
                requires_vehicle_selection=False,
                available_vehicles=None
            )
        
        # Vytvořit záznam CustomerCommand (bez vehicle_id)
        command = CustomerCommand(
            tenant_id=tenant_id,
            source=request.source,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            vehicle_id=None,
            raw_text=request.message,
            status="RECEIVED",
            intent_type=intent.value
        )
        db.add(command)
        db.commit()
        db.refresh(command)
        
        return CustomerCommandResponse(
            intent_type=command.intent_type,
            status="REQUIRES_VEHICLE_SELECTION",
            result_summary="Prosím vyberte vozidlo:",
            command_id=command.id,
            requires_vehicle_selection=True,
            available_vehicles=available_vehicles
        )
    
    # Vytvořit záznam CustomerCommand
    command = CustomerCommand(
        tenant_id=tenant_id,
        source=request.source,
        customer_name=request.customer_name,
        customer_email=request.customer_email,
        vehicle_id=request.vehicle_id,
        raw_text=request.message,
        status="RECEIVED",
        intent_type=intent.value
    )
    
    # Uložit do DB
    db.add(command)
    db.commit()
    db.refresh(command)
    
    # Pokusit se provést akci podle záměru
    try:
        result_summary = execute_customer_command(command, db)
        
        # Zkontrolovat, zda příkaz vyžaduje další informace
        # Pokud execute_customer_command nastavil status na REQUIRES_INFO, zachovat ho
        db.refresh(command)
        if command.status == "REQUIRES_INFO":
            # Status už je nastaven na REQUIRES_INFO, nechat ho
            command.result_summary = result_summary
        else:
            # Jinak nastavit na EXECUTED
            command.status = "EXECUTED"
            command.result_summary = result_summary
            command.processed_at = datetime.utcnow()
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"[CUSTOMER_COMMAND ERROR] Chyba při zpracování příkazu: {str(e)}")
        print(f"[CUSTOMER_COMMAND ERROR] Traceback:\n{error_traceback}")
        
        command.status = "FAILED"
        command.error_message = str(e)
        command.processed_at = datetime.utcnow()
        result_summary = f"Chyba: {str(e)}"
    
    try:
        db.commit()
        db.refresh(command)
    except Exception as e:
        print(f"[CUSTOMER_COMMAND ERROR] Chyba při ukládání do DB: {str(e)}")
        db.rollback()
        # Vrátit response i když se nepodařilo uložit do DB
        return CustomerCommandResponse(
            intent_type=command.intent_type,
            status="FAILED",
            result_summary=f"Chyba při ukládání: {str(e)}",
            command_id=None,
            requires_vehicle_selection=False,
            available_vehicles=None
        )
    
    # Vrátit úspěšnou odpověď
    return CustomerCommandResponse(
        intent_type=command.intent_type or "UNKNOWN",
        status=command.status or "RECEIVED",
        result_summary=command.result_summary or "Příkaz byl zpracován.",
        command_id=command.id,
        requires_vehicle_selection=False,
        available_vehicles=None
    )


@router.get("")
def get_customer_commands(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    intent_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Získá seznam zákaznických příkazů.
    
    Používá se v admin UI pro zobrazení příkazů zákazníků.
    """
    query = db.query(CustomerCommand)
    
    # Filtrování podle statusu
    if status:
        query = query.filter(CustomerCommand.status == status)
    
    # Filtrování podle typu záměru
    if intent_type:
        query = query.filter(CustomerCommand.intent_type == intent_type)
    
    # Seřadit podle data (nejnovější první)
    query = query.order_by(CustomerCommand.created_at.desc())
    
    # Limit a offset
    total = query.count()
    commands = query.offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "commands": [
            {
                "id": cmd.id,
                "created_at": cmd.created_at.isoformat() if cmd.created_at else None,
                "source": cmd.source,
                "customer_name": cmd.customer_name,
                "customer_email": cmd.customer_email,
                "vehicle_id": cmd.vehicle_id,
                "raw_text": cmd.raw_text,
                "intent_type": cmd.intent_type,
                "status": cmd.status,
                "result_summary": cmd.result_summary,
                "error_message": cmd.error_message
            }
            for cmd in commands
        ]
    }


@router.get("/{command_id}")
def get_customer_command(
    command_id: int,
    db: Session = Depends(get_db)
):
    """
    Získá detail konkrétního zákaznického příkazu.
    """
    command = db.query(CustomerCommand).filter(CustomerCommand.id == command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Příkaz nenalezen")
    
    return {
        "id": command.id,
        "created_at": command.created_at.isoformat() if command.created_at else None,
        "source": command.source,
        "customer_name": command.customer_name,
        "customer_email": command.customer_email,
        "vehicle_id": command.vehicle_id,
        "raw_text": command.raw_text,
        "normalized_text": command.normalized_text,
        "intent_type": command.intent_type,
        "status": command.status,
        "result_summary": command.result_summary,
        "error_message": command.error_message,
        "processed_at": command.processed_at.isoformat() if command.processed_at else None
    }




