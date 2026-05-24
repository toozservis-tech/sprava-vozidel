"""
Config Validator - validace konfigurace při startu aplikace
Loguje pouze existenci klíčů, nikdy ne jejich hodnoty
"""
import os
from pathlib import Path
from typing import Dict, List, Tuple
from src.core.config import (
    ENVIRONMENT,
    JWT_SECRET_KEY,
    DATAOVO_API_KEY,
    SMTP_HOST,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM,
    ENABLE_AI_FEATURES,
    ENABLE_CUSTOMER_COMMANDS,
    ENABLE_AUTOPILOT_API
)

# Výchozí hodnoty pro detekci, zda je klíč nastaven
DEFAULT_JWT_SECRET = "sprava-vozidel-dev-secret-change-in-production"
DEFAULT_SMTP_HOST = "smtp.mail.webnode.com"


def validate_config() -> Tuple[bool, Dict[str, any], List[str]]:
    """
    Validuje konfiguraci aplikace.
    
    Returns:
        Tuple[is_valid, config_status, missing_keys]
        - is_valid: True pokud jsou všechny kritické klíče nastaveny
        - config_status: Dict s informacemi o konfiguraci (bez hodnot)
        - missing_keys: Seznam chybějících klíčů
    """
    missing_keys = []
    config_status = {
        "environment": ENVIRONMENT,
        "jwt_configured": False,
        "dataovo_configured": False,
        "smtp_configured": False,
        "ai_features_enabled": ENABLE_AI_FEATURES,
        "customer_commands_enabled": ENABLE_CUSTOMER_COMMANDS,
        "autopilot_api_enabled": ENABLE_AUTOPILOT_API,
        "env_file_path": None,
        "env_file_exists": False,
        "env_file_readable": False
    }
    
    # Zkontrolovat .env soubor
    env_path = Path(__file__).parent.parent.parent / ".env"
    config_status["env_file_path"] = str(env_path)
    config_status["env_file_exists"] = env_path.exists()
    config_status["env_file_readable"] = env_path.is_file() and os.access(env_path, os.R_OK)
    
    # JWT Secret Key
    if JWT_SECRET_KEY and JWT_SECRET_KEY != DEFAULT_JWT_SECRET:
        config_status["jwt_configured"] = True
    else:
        missing_keys.append("JWT_SECRET_KEY")
        if ENVIRONMENT == "production":
            # V PROD je JWT kritický
            pass
    
    # DATAOVO API Key
    if DATAOVO_API_KEY and DATAOVO_API_KEY.strip():
        config_status["dataovo_configured"] = True
    else:
        missing_keys.append("DATAOVO_API_KEY")
    
    # SMTP Configuration
    smtp_configured = bool(
        SMTP_HOST and SMTP_HOST != DEFAULT_SMTP_HOST or SMTP_HOST == DEFAULT_SMTP_HOST and SMTP_USER and SMTP_PASSWORD
    )
    if SMTP_USER and SMTP_PASSWORD:
        config_status["smtp_configured"] = True
    else:
        if not SMTP_USER:
            missing_keys.append("SMTP_USER")
        if not SMTP_PASSWORD:
            missing_keys.append("SMTP_PASSWORD")
    
    # V PROD jsou některé klíče kritické
    is_valid = True
    if ENVIRONMENT == "production":
        if not config_status["jwt_configured"]:
            is_valid = False
        # DATAOVO a SMTP jsou volitelné, ale doporučené
    
    return is_valid, config_status, missing_keys


def log_config_status():
    """
    Loguje stav konfigurace při startu aplikace.
    NIKDY neloguje hodnoty klíčů, pouze jejich existenci.
    """
    is_valid, config_status, missing_keys = validate_config()
    
    print("\n" + "=" * 60)
    print("[CONFIG] Konfigurace aplikace")
    print("=" * 60)
    print(f"[CONFIG] Environment: {config_status['environment']}")
    print(f"[CONFIG] .env file path: {config_status['env_file_path']}")
    print(f"[CONFIG] .env file exists: {config_status['env_file_exists']}")
    print(f"[CONFIG] .env file readable: {config_status['env_file_readable']}")
    print("")
    print(f"[CONFIG] JWT_SECRET_KEY: {'FOUND' if config_status['jwt_configured'] else 'NOT FOUND'}")
    print(f"[CONFIG] DATAOVO_API_KEY: {'FOUND' if config_status['dataovo_configured'] else 'NOT FOUND'}")
    print(f"[CONFIG] SMTP configured: {'YES' if config_status['smtp_configured'] else 'NO'}")
    print(f"[CONFIG] ENABLE_AI_FEATURES: {config_status['ai_features_enabled']}")
    print(f"[CONFIG] ENABLE_CUSTOMER_COMMANDS: {config_status['customer_commands_enabled']}")
    print(f"[CONFIG] ENABLE_AUTOPILOT_API: {config_status['autopilot_api_enabled']}")
    if not config_status['smtp_configured']:
        if 'SMTP_USER' in missing_keys:
            print(f"[CONFIG]   └─ SMTP_USER: NOT FOUND")
        if 'SMTP_PASSWORD' in missing_keys:
            print(f"[CONFIG]   └─ SMTP_PASSWORD: NOT FOUND")
    
    if missing_keys:
        print("")
        print(f"[CONFIG] ⚠️  Missing keys: {', '.join(missing_keys)}")
        if ENVIRONMENT == "production":
            if "JWT_SECRET_KEY" in missing_keys:
                print("[CONFIG] ❌ KRITICKÁ CHYBA: JWT_SECRET_KEY není nastaven v PRODUKCI!")
            if "DATAOVO_API_KEY" in missing_keys:
                print("[CONFIG] ⚠️  WARNING: DATAOVO_API_KEY není nastaven - VIN lookup nebude fungovat")
    else:
        print("")
        print("[CONFIG] ✅ Všechny klíče jsou nastaveny")
    
    print("=" * 60 + "\n")
    
    return is_valid, config_status, missing_keys
