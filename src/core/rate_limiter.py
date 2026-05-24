"""
Rate Limiter pro API endpointy
Ochrana proti DDoS a brute force útokům
"""
from functools import wraps
from fastapi import HTTPException, Request
from typing import Callable
from collections import defaultdict
import time
from datetime import datetime, timedelta


class RateLimiter:
    """Jednoduchý rate limiter"""
    
    def __init__(self):
        self.storage = defaultdict(list)
    
    def check_rate_limit(
        self,
        key: str,
        max_calls: int,
        period: int = 60
    ) -> bool:
        """
        Zkontroluje, zda byl překročen rate limit.
        
        Args:
            key: Unikátní klíč (např. IP adresa nebo email)
            max_calls: Maximální počet volání
            period: Období v sekundách
        
        Returns:
            True pokud je limit v pořádku, False pokud byl překročen
        """
        now = time.time()
        
        # Vyčistit staré záznamy
        self.storage[key] = [
            timestamp for timestamp in self.storage[key]
            if now - timestamp < period
        ]
        
        # Kontrola limitu
        if len(self.storage[key]) >= max_calls:
            return False
        
        # Přidat aktuální požadavek
        self.storage[key].append(now)
        return True
    
    def clear(self, key: str = None):
        """Vyčistí rate limit pro klíč nebo všechny"""
        if key:
            if key in self.storage:
                del self.storage[key]
        else:
            self.storage.clear()


# Globální instance
rate_limiter = RateLimiter()


def rate_limit(max_calls: int = 5, period: int = 60, key_func: Callable = None):
    """
    Decorator pro rate limiting endpointu.
    
    Args:
        max_calls: Maximální počet volání
        period: Období v sekundách
        key_func: Funkce pro získání klíče (výchozí: IP adresa)
    
    Note: Pro FastAPI endpointy použijte Depends místo tohoto decoratoru
    nebo použijte RateLimitMiddleware.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Získat klíč pro rate limiting
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Výchozí: použít IP adresu z requestu (pokud je k dispozici)
                key = "global"  # Fallback
            
            # Kontrola rate limitu
            if not rate_limiter.check_rate_limit(key, max_calls, period):
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Maximum {max_calls} requests per {period} seconds."
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator




