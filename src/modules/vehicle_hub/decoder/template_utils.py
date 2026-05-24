"""
Utility funkce pro práci s šablonami vozidel
"""
import logging
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import VehicleTypeTemplate
from .models import VehicleDecodedData

logger = logging.getLogger(__name__)


def get_template_from_db(
    db: Session,
    make: Optional[str],
    model: Optional[str],
    engine_code: Optional[str],
    production_year: Optional[int],
    type_label: Optional[str]
) -> Optional[VehicleTypeTemplate]:
    """
    Načte šablonu z databáze podle klíče (make, model, engine_code, production_year, type_label).
    
    Args:
        db: Database session
        make: Tovární značka
        model: Model
        engine_code: Kód motoru
        production_year: Rok výroby
        type_label: Typ / Varianta / Verze
        
    Returns:
        VehicleTypeTemplate nebo None
    """
    if not make or not model:
        logger.debug("[TEMPLATE] Nemohu načíst šablonu - chybí make nebo model")
        return None
    
    try:
        # Vyhledat šablonu - nejpřesnější match je podle všech klíčů
        query = db.query(VehicleTypeTemplate).filter(
            VehicleTypeTemplate.make == make,
            VehicleTypeTemplate.model == model
        )
        
        # Přidat další filtry, pokud jsou dostupné
        if engine_code:
            query = query.filter(VehicleTypeTemplate.engine_code == engine_code)
        if production_year:
            query = query.filter(VehicleTypeTemplate.production_year == production_year)
        if type_label:
            query = query.filter(VehicleTypeTemplate.type_label == type_label)
        
        template = query.first()
        
        if template:
            logger.info(f"[TEMPLATE] ✅ Načtena šablona: {make} {model} ({production_year})")
            return template
        else:
            logger.debug(f"[TEMPLATE] Šablona nenalezena pro: {make} {model} ({production_year})")
            return None
            
    except Exception as e:
        logger.error(f"[TEMPLATE] Chyba při načítání šablony: {e}", exc_info=True)
        return None


def upsert_template(
    db: Session,
    make: str,
    model: str,
    engine_code: Optional[str],
    production_year: Optional[int],
    type_label: Optional[str],
    wheels_and_tyres: Optional[str],
    extra_records: Optional[str],
    default_notes: Optional[str]
) -> VehicleTypeTemplate:
    """
    Vytvoří nebo aktualizuje šablonu v databázi.
    
    Args:
        db: Database session
        make: Tovární značka
        model: Model
        engine_code: Kód motoru
        production_year: Rok výroby
        type_label: Typ / Varianta / Verze
        wheels_and_tyres: Kola a pneumatiky
        extra_records: Další záznamy
        default_notes: Výchozí poznámky
        
    Returns:
        VehicleTypeTemplate
    """
    if not make or not model:
        raise ValueError("make a model jsou povinné pro vytvoření šablony")
    
    try:
        # Hledat existující šablonu
        template = db.query(VehicleTypeTemplate).filter(
            VehicleTypeTemplate.make == make,
            VehicleTypeTemplate.model == model,
            VehicleTypeTemplate.engine_code == engine_code,
            VehicleTypeTemplate.production_year == production_year,
            VehicleTypeTemplate.type_label == type_label
        ).first()
        
        if template:
            # Aktualizovat existující
            logger.info(f"[TEMPLATE] Aktualizuji existující šablonu: {make} {model}")
            template.wheels_and_tyres = wheels_and_tyres
            template.extra_records = extra_records
            template.default_notes = default_notes
            template.updated_at = datetime.utcnow()
        else:
            # Vytvořit novou
            logger.info(f"[TEMPLATE] Vytvářím novou šablonu: {make} {model}")
            template = VehicleTypeTemplate(
                make=make,
                model=model,
                engine_code=engine_code,
                production_year=production_year,
                type_label=type_label,
                wheels_and_tyres=wheels_and_tyres,
                extra_records=extra_records,
                default_notes=default_notes
            )
            db.add(template)
        
        db.commit()
        db.refresh(template)
        
        logger.info(f"[TEMPLATE] ✅ Šablona uložena: {make} {model}")
        return template
        
    except Exception as e:
        logger.error(f"[TEMPLATE] Chyba při ukládání šablony: {e}", exc_info=True)
        db.rollback()
        raise


def apply_template_to_decoded_data(
    template: VehicleTypeTemplate,
    data: VehicleDecodedData
) -> VehicleDecodedData:
    """
    Aplikuje data z šablony na dekódovaná data.
    Pouze doplní None hodnoty, nepřepisuje existující.
    
    Args:
        template: VehicleTypeTemplate
        data: VehicleDecodedData
        
    Returns:
        VehicleDecodedData s doplněnými hodnotami ze šablony
    """
    logger.info(f"[TEMPLATE] Aplikuji šablonu na dekódovaná data")
    
    # Doplňovat pouze None hodnoty
    if not data.wheels_and_tyres and template.wheels_and_tyres:
        data.wheels_and_tyres = template.wheels_and_tyres
        logger.debug(f"[TEMPLATE] Doplněno wheels_and_tyres ze šablony")
    
    if not data.extra_records and template.extra_records:
        data.extra_records = template.extra_records
        logger.debug(f"[TEMPLATE] Doplněno extra_records ze šablony")
    
    # Poznámky - přidat na konec, ne přepsat
    if template.default_notes:
        if data.extra_records:
            data.extra_records += "\n\n" + template.default_notes
        else:
            data.extra_records = template.default_notes
        logger.debug(f"[TEMPLATE] Doplněno default_notes ze šablony")
    
    return data
import logging
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.models import VehicleTypeTemplate
from .models import VehicleDecodedData

logger = logging.getLogger(__name__)


def get_template_from_db(
    db: Session,
    make: Optional[str],
    model: Optional[str],
    engine_code: Optional[str],
    production_year: Optional[int],
    type_label: Optional[str]
) -> Optional[VehicleTypeTemplate]:
    """
    Načte šablonu z databáze podle klíče (make, model, engine_code, production_year, type_label).
    
    Args:
        db: Database session
        make: Tovární značka
        model: Model
        engine_code: Kód motoru
        production_year: Rok výroby
        type_label: Typ / Varianta / Verze
        
    Returns:
        VehicleTypeTemplate nebo None
    """
    if not make or not model:
        logger.debug("[TEMPLATE] Nemohu načíst šablonu - chybí make nebo model")
        return None
    
    try:
        # Vyhledat šablonu - nejpřesnější match je podle všech klíčů
        query = db.query(VehicleTypeTemplate).filter(
            VehicleTypeTemplate.make == make,
            VehicleTypeTemplate.model == model
        )
        
        # Přidat další filtry, pokud jsou dostupné
        if engine_code:
            query = query.filter(VehicleTypeTemplate.engine_code == engine_code)
        if production_year:
            query = query.filter(VehicleTypeTemplate.production_year == production_year)
        if type_label:
            query = query.filter(VehicleTypeTemplate.type_label == type_label)
        
        template = query.first()
        
        if template:
            logger.info(f"[TEMPLATE] ✅ Načtena šablona: {make} {model} ({production_year})")
            return template
        else:
            logger.debug(f"[TEMPLATE] Šablona nenalezena pro: {make} {model} ({production_year})")
            return None
            
    except Exception as e:
        logger.error(f"[TEMPLATE] Chyba při načítání šablony: {e}", exc_info=True)
        return None


def upsert_template(
    db: Session,
    make: str,
    model: str,
    engine_code: Optional[str],
    production_year: Optional[int],
    type_label: Optional[str],
    wheels_and_tyres: Optional[str],
    extra_records: Optional[str],
    default_notes: Optional[str]
) -> VehicleTypeTemplate:
    """
    Vytvoří nebo aktualizuje šablonu v databázi.
    
    Args:
        db: Database session
        make: Tovární značka
        model: Model
        engine_code: Kód motoru
        production_year: Rok výroby
        type_label: Typ / Varianta / Verze
        wheels_and_tyres: Kola a pneumatiky
        extra_records: Další záznamy
        default_notes: Výchozí poznámky
        
    Returns:
        VehicleTypeTemplate
    """
    if not make or not model:
        raise ValueError("make a model jsou povinné pro vytvoření šablony")
    
    try:
        # Hledat existující šablonu
        template = db.query(VehicleTypeTemplate).filter(
            VehicleTypeTemplate.make == make,
            VehicleTypeTemplate.model == model,
            VehicleTypeTemplate.engine_code == engine_code,
            VehicleTypeTemplate.production_year == production_year,
            VehicleTypeTemplate.type_label == type_label
        ).first()
        
        if template:
            # Aktualizovat existující
            logger.info(f"[TEMPLATE] Aktualizuji existující šablonu: {make} {model}")
            template.wheels_and_tyres = wheels_and_tyres
            template.extra_records = extra_records
            template.default_notes = default_notes
            template.updated_at = datetime.utcnow()
        else:
            # Vytvořit novou
            logger.info(f"[TEMPLATE] Vytvářím novou šablonu: {make} {model}")
            template = VehicleTypeTemplate(
                make=make,
                model=model,
                engine_code=engine_code,
                production_year=production_year,
                type_label=type_label,
                wheels_and_tyres=wheels_and_tyres,
                extra_records=extra_records,
                default_notes=default_notes
            )
            db.add(template)
        
        db.commit()
        db.refresh(template)
        
        logger.info(f"[TEMPLATE] ✅ Šablona uložena: {make} {model}")
        return template
        
    except Exception as e:
        logger.error(f"[TEMPLATE] Chyba při ukládání šablony: {e}", exc_info=True)
        db.rollback()
        raise


def apply_template_to_decoded_data(
    template: VehicleTypeTemplate,
    data: VehicleDecodedData
) -> VehicleDecodedData:
    """
    Aplikuje data z šablony na dekódovaná data.
    Pouze doplní None hodnoty, nepřepisuje existující.
    
    Args:
        template: VehicleTypeTemplate
        data: VehicleDecodedData
        
    Returns:
        VehicleDecodedData s doplněnými hodnotami ze šablony
    """
    logger.info(f"[TEMPLATE] Aplikuji šablonu na dekódovaná data")
    
    # Doplňovat pouze None hodnoty
    if not data.wheels_and_tyres and template.wheels_and_tyres:
        data.wheels_and_tyres = template.wheels_and_tyres
        logger.debug(f"[TEMPLATE] Doplněno wheels_and_tyres ze šablony")
    
    if not data.extra_records and template.extra_records:
        data.extra_records = template.extra_records
        logger.debug(f"[TEMPLATE] Doplněno extra_records ze šablony")
    
    # Poznámky - přidat na konec, ne přepsat
    if template.default_notes:
        if data.extra_records:
            data.extra_records += "\n\n" + template.default_notes
        else:
            data.extra_records = template.default_notes
        logger.debug(f"[TEMPLATE] Doplněno default_notes ze šablony")
    
    return data

