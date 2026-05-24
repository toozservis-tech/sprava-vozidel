"""
VIN validátor podle ISO 3779 a EU standardů
"""
import re
from typing import List, Tuple


# Mapování znaků VIN na číselné hodnoty pro checksum výpočet
VIN_CHAR_VALUES = {
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
    'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
    'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9,
    'S': 2, 'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
}

# Váhy pro checksum výpočet (pozice v VIN)
VIN_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


def validate_vin(vin: str) -> Tuple[bool, List[str]]:
    """
    Zvaliduje VIN podle EU/ISO 3779 standardů.
    
    Args:
        vin: VIN kód k validaci
        
    Returns:
        Tuple[bool, List[str]]: (ok, errors) - True pokud je VIN platný, jinak False + seznam chyb
    """
    errors: List[str] = []
    
    if not vin:
        errors.append("VIN není zadán")
        return False, errors
    
    # Normalizace - uppercase, odstranění mezer
    vin = vin.strip().upper()
    
    # 1. Kontrola délky
    if len(vin) != 17:
        errors.append(f"VIN musí mít přesně 17 znaků (zadáno: {len(vin)})")
        return False, errors
    
    # 2. Kontrola povolených znaků (bez I, O, Q)
    allowed_pattern = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')
    if not allowed_pattern.match(vin):
        invalid_chars = [char for char in vin if char in 'IOQ']
        if invalid_chars:
            errors.append(f"VIN obsahuje nepovolené znaky: {', '.join(set(invalid_chars))} (I, O, Q nejsou povoleny)")
        else:
            errors.append("VIN obsahuje nepovolené znaky (povolené jsou pouze A-H, J-N, P, R-Z, 0-9)")
        return False, errors
    
    # 3. Validace checksum podle ISO 3779 (9. znak)
    checksum_valid, checksum_error = _validate_checksum(vin)
    if not checksum_valid:
        errors.append(checksum_error)
        # Checksum není kritický - některé starší VINy ho nemají správně
        # Přidáme jen warning, ale nepovažujeme to za fatální chybu
        # errors.append(checksum_error)
    
    # 4. Kontrola struktury (volitelné)
    # WMI (1-3): musí být alfanumerický
    wmi = vin[0:3]
    if not re.match(r'^[A-HJ-NPR-Z0-9]{3}$', wmi):
        errors.append(f"WMI (World Manufacturer Identifier) není platný: {wmi}")
    
    # VDS (4-9): Vehicle Descriptor Section
    # VIS (10-17): Vehicle Identifier Section
    
    # Pokud jsou všechny kontroly OK
    if not errors:
        return True, []
    
    return False, errors


def _validate_checksum(vin: str) -> Tuple[bool, str]:
    """
    Validuje checksum VIN podle ISO 3779.
    
    Args:
        vin: VIN kód (17 znaků, normalizovaný)
        
    Returns:
        Tuple[bool, str]: (ok, error_message)
    """
    try:
        # 9. znak je checksum (pozice 8, 0-indexed)
        checksum_char = vin[8]
        
        # Pokud je checksum 'X', je to speciální případ
        if checksum_char == 'X':
            calculated_checksum = 10
        else:
            calculated_checksum = VIN_CHAR_VALUES.get(checksum_char)
            if calculated_checksum is None:
                return False, f"Neplatný checksum znak: {checksum_char}"
        
        # Výpočet checksum
        total = 0
        for i, char in enumerate(vin):
            if i == 8:  # Přeskočit checksum pozici při výpočtu
                continue
            char_value = VIN_CHAR_VALUES.get(char)
            if char_value is None:
                return False, f"Neplatný znak v pozici {i+1}: {char}"
            total += char_value * VIN_WEIGHTS[i]
        
        # Checksum je zbytek po dělení 11
        remainder = total % 11
        expected_checksum = remainder if remainder < 10 else 'X'
        
        if isinstance(expected_checksum, str):
            is_valid = checksum_char == expected_checksum
        else:
            is_valid = calculated_checksum == expected_checksum
        
        if not is_valid:
            expected_char = str(expected_checksum) if not isinstance(expected_checksum, str) else expected_checksum
            return False, f"Checksum není platný (očekáváno: {expected_char}, zadáno: {checksum_char})"
        
        return True, ""
    
    except Exception as e:
        return False, f"Chyba při validaci checksum: {str(e)}"


def normalize_vin(vin: str) -> str:
    """
    Normalizuje VIN (uppercase, bez mezer).
    
    Args:
        vin: VIN kód
        
    Returns:
        Normalizovaný VIN
    """
    return vin.strip().upper().replace(" ", "").replace("-", "")














