"""
Command Engine - jednoduchý intent detection pro Customer Command Bot v1

Tento modul obsahuje pravidlo-based rozpoznávání záměrů zákazníků.
V budoucnu může být nahrazeno AI modelem.
"""
from enum import Enum
from typing import Literal


class IntentType(str, Enum):
    """Typy záměrů, které bot rozpoznává"""
    CREATE_BOOKING = "CREATE_BOOKING"
    CREATE_TASK = "CREATE_TASK"
    ADD_NOTE = "ADD_NOTE"
    ADD_VEHICLE = "ADD_VEHICLE"
    QUESTION = "QUESTION"
    UNKNOWN = "UNKNOWN"


def detect_intent(raw_text: str) -> IntentType:
    """
    Jednoduché pravidlo-based rozpoznávání záměru z textu.
    
    Pravidla:
    - obsahuje slova typu: 'objednat', 'objednávka', 'termín', 'chci přijet', 
      'výměna oleje', 'pneuservis' -> CREATE_BOOKING
    - obsahuje slova: 'připomeň', 'připomínka', 'nezapomeň' -> CREATE_TASK
    - obsahuje slova: 'poznámka', 'zapiš si', 'zapsat' -> ADD_NOTE
    - pokud končí otazníkem, ale nesedí na nic výše -> QUESTION
    - jinak -> UNKNOWN
    
    Args:
        raw_text: Původní text od zákazníka
        
    Returns:
        IntentType: Rozpoznaný typ záměru
    """
    if not raw_text:
        return IntentType.UNKNOWN
    
    text_lower = raw_text.lower().strip()
    
    # Klíčová slova pro rezervaci/objednávku
    booking_keywords = [
        'objednat', 'objednávka', 'objednavka', 'objednávku', 'objednavku',
        'termín', 'termin', 'termínu', 'terminu',
        'chci přijet', 'chci prijet', 'přijet', 'prijet',
        'výměna oleje', 'vymena oleje', 'výměnu oleje', 'vymenu oleje',
        'pneuservis', 'pneuservisu',
        'servis', 'servisu', 'servisní', 'servisni',
        'rezervace', 'rezervaci', 'rezervovat', 'zarezervovat',
        'chci na', 'potřebuji', 'potrebuji', 'potřebuju', 'potrebuju',
        'chci se objednat', 'chci se prihlasit'
    ]
    
    # Klíčová slova pro úkol/připomínku
    task_keywords = [
        'připomeň', 'pripomen', 'připomínka', 'pripominka', 'připomínku', 'pripominku',
        'nezapomeň', 'nezapomen', 'nezapomeňte', 'nezapomente',
        'připomenout', 'pripomenout', 'připomínat', 'pripominat',
        'úkol', 'ukol', 'úkolu', 'ukolu', 'úkoly', 'ukoly',
        'udělat', 'udelat', 'udělej', 'udelej', 'udělejte', 'udelejte'
    ]
    
    # Klíčová slova pro poznámku
    note_keywords = [
        'poznámka', 'poznamka', 'poznámku', 'poznamku', 'poznámky', 'poznamky',
        'zapiš si', 'zapis si', 'zapište si', 'zapiste si',
        'zapsat', 'zapsat si', 'zapsat si to',
        'poznamenej', 'poznamenejte', 'poznamenat',
        'zaznamenej', 'zaznamenejte', 'zaznamenat'
    ]
    
    # Klíčová slova pro přidání vozidla
    vehicle_keywords = [
        'přidal vozidlo', 'pridal vozidlo', 'přidat vozidlo', 'pridat vozidlo',
        'přidej vozidlo', 'pridej vozidlo', 'přidejte vozidlo', 'pridejte vozidlo',
        'nové vozidlo', 'nove vozidlo', 'nové auto', 'nove auto',
        'přidat auto', 'pridat auto', 'přidej auto', 'pridej auto',
        'přidej vozidlo', 'pridej vozidlo',  # Duplicitní pro jistotu
        'vin', 'spz', 'registrační značka', 'registracni znacka',
        'přidat vozidlo s vin', 'pridat vozidlo s vin',  # Pro příkazy s VIN
        'přidal vozidlo s vin', 'pridal vozidlo s vin'
    ]
    
    # Kontrola přidání vozidla (nejdřív, protože může obsahovat i jiná klíčová slova)
    # Kontrola kombinace: (přidat/přidej/přidal) + (vozidlo/auto) nebo VIN/SPZ
    vehicle_words = ['vozidlo', 'auto', 'vin', 'spz']
    has_vehicle_word = any(word in text_lower for word in vehicle_words)
    
    # Kontrola slov obsahujících "prid" nebo "přid" (flexibilní pro diakritiku)
    # Použít jednoduchou kontrolu - hledat "p" následované "id" (přidat, pridat, přidej, pridej, atd.)
    import re
    # Regex pro "p" + nějaký znak + "id" (zachytí "prid", "přid", "přid", atd.)
    has_add_word = bool(re.search(r'p.{0,2}id', text_lower)) or 'prid' in text_lower or 'přid' in text_lower
    
    if has_add_word and has_vehicle_word:
        return IntentType.ADD_VEHICLE
    
    # Také zkontrolovat klíčová slova
    for keyword in vehicle_keywords:
        if keyword in text_lower:
            return IntentType.ADD_VEHICLE
    
    # Kontrola rezervace/objednávky
    for keyword in booking_keywords:
        if keyword in text_lower:
            return IntentType.CREATE_BOOKING
    
    # Kontrola úkolu/připomínky
    for keyword in task_keywords:
        if keyword in text_lower:
            return IntentType.CREATE_TASK
    
    # Kontrola poznámky
    for keyword in note_keywords:
        if keyword in text_lower:
            return IntentType.ADD_NOTE
    
    # Kontrola otázky (končí otazníkem a nesedí na nic výše)
    if text_lower.endswith('?') or text_lower.endswith('?'):
        return IntentType.QUESTION
    
    # Výchozí hodnota
    return IntentType.UNKNOWN


# TODO: Příprava na budoucí AI integraci
def call_ai_for_intent(raw_text: str) -> tuple[IntentType, dict]:
    """
    FUTURE: Funkce pro volání AI modelu pro rozpoznávání záměru.
    
    Tato funkce je připravena pro pozdější integraci s AI službou
    (např. OpenAI, Claude, nebo vlastní fine-tuned model).
    
    Prozatím není implementována a nepoužívá se.
    
    Args:
        raw_text: Původní text od zákazníka
        
    Returns:
        tuple[IntentType, dict]: Rozpoznaný záměr a metadata (confidence, entities, atd.)
        
    Příklad budoucí implementace:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{
                "role": "system",
                "content": "Rozpoznej záměr zákazníka z textu..."
            }, {
                "role": "user",
                "content": raw_text
            }]
        )
        # Parsování response a návrat IntentType + metadata
    """
    # Prozatím vracíme UNKNOWN - funkce není implementována
    return IntentType.UNKNOWN, {}







