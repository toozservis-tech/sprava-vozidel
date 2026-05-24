"""
Auth Service - služba pro autentizaci a správu uživatelů
"""
from __future__ import annotations

import requests
from typing import Optional
from src.core.config import BASE_API_URL


class AuthService:
    """Služba pro autentizaci a správu uživatelů"""
    
    def __init__(self):
        self.current_user_email: Optional[str] = None
        self.access_token: Optional[str] = None
        self.current_user: Optional[dict] = None
    
    def _get_headers(self) -> dict:
        """Vrací HTTP hlavičky pro API volání"""
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self.current_user_email:
            headers["X-User-Email"] = self.current_user_email
        return headers
    
    def login(self, email: str, password: str) -> bool:
        """
        Přihlásí uživatele.
        
        Args:
            email: Email uživatele
            password: Heslo
            
        Returns:
            True pokud přihlášení proběhlo úspěšně
        """
        normalized_email = email.strip().lower()
        try:
            url = f"{BASE_API_URL}/user/login"
            data = {"email": normalized_email, "password": password}
            headers = {}
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                self.access_token = result.get("access_token")
                user = result.get("user", {})
                self.current_user_email = user.get("email") or normalized_email
                self.current_user = user
                return True
            return False
        except requests.exceptions.ConnectionError:
            print(f"[AUTH] Backend není dostupný ({BASE_API_URL}), používá se lokální režim")
            # Fallback - pro testování bez serveru
            self.current_user_email = normalized_email
            self.current_user = {"email": normalized_email}
            return True
        except Exception as e:
            print(f"[AUTH] Chyba při přihlášení: {e}")
            return False
    
    def register(self, email: str, password: str, customer_data: dict) -> bool:
        """
        Zaregistruje nového uživatele.
        
        Args:
            email: Email uživatele
            password: Heslo
            customer_data: Dict s údaji o zákazníkovi (name, ico, street, city, zip, phone)
            
        Returns:
            True pokud registrace proběhla úspěšně
        """
        normalized_email = email.strip().lower()
        try:
            url = f"{BASE_API_URL}/user/register"
            data = {
                "email": normalized_email,
                "password": password,
                **customer_data
            }
            headers = {}
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("verification_required"):
                    self.access_token = None
                    user = result.get("user") or {}
                    self.current_user_email = user.get("email") or normalized_email
                    self.current_user = user
                    print("[AUTH] Registrace čeká na ověření e-mailu (odkaz v e-mailu).")
                    return True
                self.access_token = result.get("access_token")
                user = result.get("user", {})
                self.current_user_email = user.get("email") or normalized_email
                self.current_user = user
                return True
            return False
        except requests.exceptions.ConnectionError:
            print(f"[AUTH] Backend není dostupný ({BASE_API_URL}), používá se lokální režim")
            self.current_user_email = normalized_email
            self.current_user = {"email": normalized_email}
            return True
        except Exception as e:
            print(f"[AUTH] Chyba při registraci: {e}")
            return False
    
    def fetch_ares_data(self, ico: str) -> Optional[dict]:
        """
        Načte data z ARES podle IČO.
        
        Args:
            ico: IČO firmy (8 číslic)
            
        Returns:
            Dict s údaji o firmě nebo None při chybě
        """
        # 1. Pokus o získání dat z backendu
        try:
            url = f"{BASE_API_URL}/user/ares"
            params = {"ico": ico}
            headers = self._get_headers()
            
            response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_ares_data(data, ico)
        except requests.exceptions.RequestException:
            print(f"[ARES] Backend není dostupný, zkouším veřejné ARES API...")
        
        # 2. Fallback na veřejné ARES API
        try:
            url = f"https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/{ico}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return self._normalize_ares_data(data, ico)
        except requests.exceptions.RequestException as e:
            print(f"[ARES] Chyba při volání veřejného API: {e}")
        
        return None
    
    def _normalize_ares_data(self, data: dict, ico: str) -> dict:
        """Normalizuje data z ARES do jednotného formátu"""
        result = {"ico": ico}
        
        # Extrakce názvu
        if "obchodniJmeno" in data:
            result["nazev"] = data["obchodniJmeno"]
        elif "nazev" in data:
            result["nazev"] = data["nazev"]
        
        # Extrakce sídla
        if "sidlo" in data:
            sidlo = data["sidlo"]
            
            if "nazevUlice" in sidlo:
                result["ulice"] = sidlo["nazevUlice"]
            elif "nazevObce" in sidlo:
                result["ulice"] = sidlo["nazevObce"]
            
            if "cisloDomovni" in sidlo:
                cislo = str(sidlo["cisloDomovni"])
                if "cisloOrientacni" in sidlo:
                    cislo += "/" + str(sidlo["cisloOrientacni"])
                result["cislo_popisne"] = cislo
            
            if "nazevObce" in sidlo:
                result["mesto"] = sidlo["nazevObce"]
            
            if "psc" in sidlo:
                result["psc"] = str(sidlo["psc"])
        
        # DIČ
        if "dic" in data:
            result["dic"] = data["dic"]
        
        return result
    
    def logout(self):
        """Odhlásí aktuálního uživatele"""
        self.current_user_email = None
        self.access_token = None
        self.current_user = None
    
    def is_logged_in(self) -> bool:
        """Vrací True pokud je uživatel přihlášen"""
        return self.current_user_email is not None
    
    def get_current_user_email(self) -> Optional[str]:
        """Vrací email aktuálně přihlášeného uživatele"""
        return self.current_user_email
    
    def get_access_token(self) -> Optional[str]:
        """Vrací JWT token"""
        return self.access_token
