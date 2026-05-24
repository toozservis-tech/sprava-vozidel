"""
Bezpečnostní modul pro Správu vozidel
- Hashování hesel pomocí bcrypt
- JWT tokeny pro autentizaci
"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional

# Pokusit se importovat bcrypt přímo (bez passlib)
try:
    import bcrypt

    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    bcrypt = None

try:
    import jwt
    from jwt import PyJWTError as JWTError

    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    JWTError = Exception
    jwt = None

from .config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY


def hash_password(password: str) -> str:
    """
    Hashuje heslo pomocí bcrypt (pokud je dostupný) nebo SHA256 jako fallback.

    Args:
        password: Heslo k hashování

    Returns:
        Hash hesla

    Raises:
        ValueError: Pokud je heslo prázdné nebo příliš krátké
    """
    if not password:
        raise ValueError("Heslo nemůže být prázdné")
    if len(password) < 6:
        raise ValueError("Heslo musí mít alespoň 6 znaků")

    if BCRYPT_AVAILABLE and bcrypt:
        # Použít bcrypt přímo
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode("utf-8")
    else:
        # Fallback na SHA256 (méně bezpečné, ale funkční)
        print("[SECURITY] WARNING: bcrypt není dostupný, používám SHA256")
        return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Ověří heslo proti hashi.

    Podporuje:
    - bcrypt hashe (začínají $2b$)
    - SHA256 hashe (64 znaků hex)

    Args:
        plain_password: Heslo v čitelné formě
        hashed_password: Hash hesla z databáze

    Returns:
        True pokud se hesla shodují
    """
    if not plain_password or not hashed_password:
        return False

    # Detekce typu hashe
    if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
        # bcrypt hash
        if BCRYPT_AVAILABLE and bcrypt:
            try:
                return bcrypt.checkpw(
                    plain_password.encode("utf-8"), hashed_password.encode("utf-8")
                )
            except Exception as e:
                print(f"[SECURITY] Chyba při ověřování bcrypt: {e}")
                return False
        else:
            print("[SECURITY] WARNING: bcrypt hash, ale bcrypt není dostupný")
            return False
    elif len(hashed_password) == 64:
        # SHA256 hash (legacy)
        sha256_hash = hashlib.sha256(plain_password.encode()).hexdigest()
        return sha256_hash == hashed_password
    else:
        # Neznámý formát
        return False


def needs_rehash(hashed_password: str) -> bool:
    """
    Zjistí, zda by heslo mělo být přehashováno (upgrade z SHA256 na bcrypt).

    Args:
        hashed_password: Hash hesla z databáze

    Returns:
        True pokud by heslo mělo být přehashováno
    """
    if not BCRYPT_AVAILABLE:
        return False

    # SHA256 hash (64 znaků hex) by měl být upgradován na bcrypt
    if len(hashed_password) == 64 and not hashed_password.startswith("$"):
        return True

    return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Vytvoří JWT access token.

    Args:
        data: Data k zakódování do tokenu (typicky {"sub": email})
        expires_delta: Doba platnosti tokenu (výchozí: JWT_EXPIRE_MINUTES)

    Returns:
        JWT token jako string
    """
    if not JWT_AVAILABLE or jwt is None:
        # Fallback - vrátit jednoduchý token (email)
        return data.get("sub", "")

    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)

    if "iat" not in to_encode:
        to_encode["iat"] = datetime.utcnow()
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[str]:
    """
    Dekóduje JWT token a vrátí email uživatele.

    Args:
        token: JWT token

    Returns:
        Email uživatele nebo None pokud je token neplatný
    """
    if not JWT_AVAILABLE or jwt is None:
        # Fallback - token je přímo email
        return token if "@" in token else None

    payload = decode_access_token_payload(token)
    if not payload:
        return None
    email: str = payload.get("sub")
    if email is None:
        return None
    return email


def decode_access_token_payload(token: str) -> Optional[dict]:
    """
    Dekóduje JWT token a vrátí celý payload.

    Returns:
        Dict payload nebo None pokud je token neplatný.
    """
    if not JWT_AVAILABLE or jwt is None:
        return {"sub": token} if "@" in token else None

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if not isinstance(payload, dict):
            return None
        return payload
    except JWTError:
        return None


def get_password_hash_type(hashed_password: str) -> str:
    """
    Zjistí typ hashe hesla.

    Returns:
        "bcrypt", "sha256" nebo "unknown"
    """
    if hashed_password.startswith("$2b$") or hashed_password.startswith("$2a$"):
        return "bcrypt"
    elif len(hashed_password) == 64:
        return "sha256"
    else:
        return "unknown"
