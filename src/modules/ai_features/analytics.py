"""
Analytics systém pro sledování použití aplikace
"""
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from fastapi import Request

from .models import UsageAnalytics
from src.modules.vehicle_hub.database import get_db


class AnalyticsCollector:
    """Sběr dat o použití aplikace"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def record_usage(
        self,
        tenant_id: int,
        endpoint: Optional[str] = None,
        module: Optional[str] = None,
        function: Optional[str] = None,
        action: Optional[str] = None,
        request_method: Optional[str] = None,
        response_status: Optional[int] = None,
        response_time_ms: Optional[float] = None,
        user_email: Optional[str] = None,
        request: Optional[Request] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Zaznamenat použití funkce/endpointu"""
        
        # Extrahovat informace z requestu
        user_agent = None
        ip_address = None
        session_id = None
        request_size = None
        response_size = None
        
        if request:
            user_agent = request.headers.get("user-agent")
            ip_address = request.client.host if request.client else None
            session_id = request.cookies.get("session_id")
            
            # Velikost requestu
            if hasattr(request, "_body"):
                request_size = len(request._body) if request._body else 0
        
        # Vytvořit záznam
        analytics = UsageAnalytics(
            tenant_id=tenant_id,
            user_email=user_email,
            endpoint=endpoint,
            module=module,
            function=function,
            action=action,
            request_method=request_method,
            response_status=response_status,
            response_time_ms=response_time_ms,
            request_size=request_size,
            response_size=response_size,
            user_agent=user_agent,
            ip_address=ip_address,
            session_id=session_id,
            extra_metadata=metadata or {},
            timestamp=datetime.utcnow()
        )
        
        self.db.add(analytics)
        self.db.commit()
        
        return analytics
    
    def get_usage_stats(
        self,
        tenant_id: int,
        days: int = 30,
        module: Optional[str] = None,
        endpoint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Získat statistiky použití"""
        
        since = datetime.utcnow() - timedelta(days=days)
        
        query = self.db.query(UsageAnalytics).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since
            )
        )
        
        if module:
            query = query.filter(UsageAnalytics.module == module)
        if endpoint:
            query = query.filter(UsageAnalytics.endpoint == endpoint)
        
        total_requests = query.count()
        
        # Nejčastěji používané endpointy
        top_endpoints = self.db.query(
            UsageAnalytics.endpoint,
            func.count(UsageAnalytics.id).label('count')
        ).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since,
                UsageAnalytics.endpoint.isnot(None)
            )
        ).group_by(UsageAnalytics.endpoint).order_by(desc('count')).limit(10).all()
        
        # Nejčastěji používané moduly
        top_modules = self.db.query(
            UsageAnalytics.module,
            func.count(UsageAnalytics.id).label('count')
        ).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since,
                UsageAnalytics.module.isnot(None)
            )
        ).group_by(UsageAnalytics.module).order_by(desc('count')).limit(10).all()
        
        # Průměrná doba odezvy
        avg_response_time = self.db.query(
            func.avg(UsageAnalytics.response_time_ms)
        ).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since,
                UsageAnalytics.response_time_ms.isnot(None)
            )
        ).scalar() or 0
        
        # Chybovost
        error_count = query.filter(UsageAnalytics.response_status >= 400).count()
        error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0
        
        # Aktivní uživatelé
        active_users = self.db.query(
            func.count(func.distinct(UsageAnalytics.user_email))
        ).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since,
                UsageAnalytics.user_email.isnot(None)
            )
        ).scalar() or 0
        
        return {
            "total_requests": total_requests,
            "top_endpoints": [{"endpoint": e, "count": c} for e, c in top_endpoints],
            "top_modules": [{"module": m, "count": c} for m, c in top_modules],
            "avg_response_time_ms": round(avg_response_time, 2),
            "error_rate_percent": round(error_rate, 2),
            "active_users": active_users,
            "period_days": days
        }
    
    def get_usage_patterns(
        self,
        tenant_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """Analyzovat vzorce použití pro AI"""
        
        since = datetime.utcnow() - timedelta(days=days)
        
        # Kombinace modulů používané společně (v rámci stejné session)
        session_modules = self.db.query(
            UsageAnalytics.session_id,
            func.group_concat(UsageAnalytics.module.distinct()).label('modules')
        ).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since,
                UsageAnalytics.session_id.isnot(None),
                UsageAnalytics.module.isnot(None)
            )
        ).group_by(UsageAnalytics.session_id).all()
        
        # Časové vzorce (kdy se co používá)
        hourly_usage = self.db.query(
            func.extract('hour', UsageAnalytics.timestamp).label('hour'),
            UsageAnalytics.module,
            func.count(UsageAnalytics.id).label('count')
        ).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since,
                UsageAnalytics.module.isnot(None)
            )
        ).group_by('hour', UsageAnalytics.module).all()
        
        # Funkce, které se používají společně
        sequential_patterns = []
        # TODO: Implementovat detekci sekvenčních vzorců
        
        return {
            "session_modules": [{"session": s, "modules": m} for s, m in session_modules[:100]],
            "hourly_usage": [{"hour": h, "module": m, "count": c} for h, m, c in hourly_usage],
            "sequential_patterns": sequential_patterns
        }


class AnalyticsMiddleware:
    """Middleware pro automatické sledování API požadavků"""
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # Získat tenant_id z requestu (pokud je k dispozici)
        # TODO: Implementovat extrakci tenant_id z JWT tokenu nebo headers
        
        start_time = time.time()
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Zaznamenat response status
                status = message.get("status")
                # TODO: Zaznamenat do analytics
                pass
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)
        
        # Zaznamenat dobu odezvy
        response_time = (time.time() - start_time) * 1000  # v ms
        # TODO: Zaznamenat do analytics

