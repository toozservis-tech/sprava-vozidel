"""
AI Feature Suggestion Engine - analyzuje použití a navrhuje nové funkce
"""
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, or_

from .models import (
    UsageAnalytics, FeatureSuggestion, FeatureDependency,
    FeatureVote, FeatureFeedback
)
from .analytics import AnalyticsCollector


class FeatureSuggestionEngine:
    """AI engine pro navrhování nových funkcí"""
    
    def __init__(self, db: Session):
        self.db = db
        self.analytics = AnalyticsCollector(db)
    
    def analyze_and_suggest(
        self,
        tenant_id: int,
        days: int = 30
    ) -> List[FeatureSuggestion]:
        """Analyzovat použití a navrhnout nové funkce"""
        
        # Získat statistiky použití
        stats = self.analytics.get_usage_stats(tenant_id, days=days)
        patterns = self.analytics.get_usage_patterns(tenant_id, days=days)
        
        suggestions = []
        
        # 1. Analýza nedostatečně používaných funkcí
        suggestions.extend(self._suggest_improvements_for_underused_features(stats, tenant_id))
        
        # 2. Analýza chybějících funkcí mezi často používanými moduly
        suggestions.extend(self._suggest_missing_integrations(stats, patterns, tenant_id))
        
        # 3. Analýza pomalých endpointů
        suggestions.extend(self._suggest_performance_improvements(stats, tenant_id))
        
        # 4. Analýza uživatelských vzorců
        suggestions.extend(self._suggest_workflow_improvements(patterns, tenant_id))
        
        # 5. Analýza chybových vzorců
        suggestions.extend(self._suggest_error_handling_improvements(stats, tenant_id))
        
        # 6. Analýza automatizace opakujících se úkolů
        suggestions.extend(self._suggest_automation_opportunities(patterns, tenant_id))
        
        return suggestions
    
    def _suggest_improvements_for_underused_features(
        self,
        stats: Dict[str, Any],
        tenant_id: int
    ) -> List[FeatureSuggestion]:
        """Navrhnout vylepšení pro málo používané funkce"""
        
        suggestions = []
        
        # Najít moduly s nízkým použitím, ale vysokým potenciálem
        # TODO: Implementovat logiku
        
        return suggestions
    
    def _suggest_missing_integrations(
        self,
        stats: Dict[str, Any],
        patterns: Dict[str, Any],
        tenant_id: int
    ) -> List[FeatureSuggestion]:
        """Navrhnout chybějící integrace mezi moduly"""
        
        suggestions = []
        
        # Analýza kombinací modulů používaných společně
        top_modules = [m["module"] for m in stats.get("top_modules", [])[:5]]
        
        # Mapování možných integrací
        integration_map = {
            ("vehicle_hub", "email_client"): {
                "title": "Automatické emailové notifikace o vozidlech",
                "description": "Automaticky posílat emaily při změnách vozidel, servisních záznamů nebo připomínek",
                "category": "integration",
                "priority": 85,
                "reasoning": "Uživatelé často používají vehicle_hub a email_client společně. Automatizace by ušetřila čas.",
                "dependencies": ["vehicle_hub", "email_client"],
                "implementation_complexity": "medium"
            },
            ("vehicle_hub", "pdf_manager"): {
                "title": "Generování PDF reportů o vozidlech",
                "description": "Automaticky generovat PDF reporty s informacemi o vozidle, servisních záznamech a historii",
                "category": "integration",
                "priority": 75,
                "reasoning": "Kombinace vehicle_hub a pdf_manager by umožnila snadné vytváření dokumentace.",
                "dependencies": ["vehicle_hub", "pdf_manager"],
                "implementation_complexity": "medium"
            },
            ("email_client", "pdf_manager"): {
                "title": "Odesílání PDF jako příloh emailů",
                "description": "Zjednodušit proces odesílání PDF souborů jako příloh v emailech",
                "category": "integration",
                "priority": 70,
                "reasoning": "Uživatelé často potřebují posílat PDF soubory emailem.",
                "dependencies": ["email_client", "pdf_manager"],
                "implementation_complexity": "low"
            }
        }
        
        # Zkontrolovat, které integrace chybí
        for module_pair, suggestion_data in integration_map.items():
            if all(m in top_modules for m in module_pair):
                # Ověřit, zda už není podobný návrh
                existing = self.db.query(FeatureSuggestion).filter(
                    and_(
                        FeatureSuggestion.tenant_id == tenant_id,
                        FeatureSuggestion.title.like(f"%{suggestion_data['title'][:30]}%"),
                        FeatureSuggestion.status.in_(["suggested", "approved", "implemented"])
                    )
                ).first()
                
                if not existing:
                    suggestion = FeatureSuggestion(
                        tenant_id=tenant_id,
                        **suggestion_data,
                        confidence_score=0.8,
                        usage_patterns={
                            "modules_used_together": list(module_pair),
                            "usage_frequency": "high"
                        },
                        auto_implementable=False
                    )
                    suggestions.append(suggestion)
        
        return suggestions
    
    def _suggest_performance_improvements(
        self,
        stats: Dict[str, Any],
        tenant_id: int
    ) -> List[FeatureSuggestion]:
        """Navrhnout vylepšení výkonu"""
        
        suggestions = []
        
        # Najít pomalé endpointy
        since = datetime.utcnow() - timedelta(days=30)
        slow_endpoints = self.db.query(
            UsageAnalytics.endpoint,
            func.avg(UsageAnalytics.response_time_ms).label('avg_time')
        ).filter(
            and_(
                UsageAnalytics.tenant_id == tenant_id,
                UsageAnalytics.timestamp >= since,
                UsageAnalytics.response_time_ms.isnot(None),
                UsageAnalytics.endpoint.isnot(None)
            )
        ).group_by(UsageAnalytics.endpoint).having(
            func.avg(UsageAnalytics.response_time_ms) > 1000  # Více než 1 sekunda
        ).order_by(desc('avg_time')).limit(5).all()
        
        for endpoint, avg_time in slow_endpoints:
            suggestion = FeatureSuggestion(
                tenant_id=tenant_id,
                title=f"Optimalizace výkonu: {endpoint}",
                description=f"Endpoint {endpoint} má průměrnou dobu odezvy {avg_time:.0f}ms. Doporučujeme optimalizaci.",
                category="performance",
                priority=60,
                reasoning=f"Endpoint je pomalý ({avg_time:.0f}ms), což ovlivňuje uživatelský zážitek.",
                usage_patterns={
                    "endpoint": endpoint,
                    "avg_response_time_ms": float(avg_time),
                    "calls_count": stats.get("total_requests", 0)
                },
                implementation_complexity="medium",
                auto_implementable=False
            )
            suggestions.append(suggestion)
        
        return suggestions
    
    def _suggest_workflow_improvements(
        self,
        patterns: Dict[str, Any],
        tenant_id: int
    ) -> List[FeatureSuggestion]:
        """Navrhnout vylepšení workflow"""
        
        suggestions = []
        
        # Analýza sekvenčních vzorců
        # TODO: Implementovat detekci opakujících se sekvencí akcí
        
        return suggestions
    
    def _suggest_error_handling_improvements(
        self,
        stats: Dict[str, Any],
        tenant_id: int
    ) -> List[FeatureSuggestion]:
        """Navrhnout vylepšení zpracování chyb"""
        
        suggestions = []
        
        if stats.get("error_rate_percent", 0) > 5:
            suggestion = FeatureSuggestion(
                tenant_id=tenant_id,
                title="Vylepšení zpracování chyb",
                description=f"Chybovost aplikace je {stats['error_rate_percent']:.1f}%. Doporučujeme zlepšit error handling.",
                category="reliability",
                priority=90,
                reasoning=f"Vysoká chybovost ({stats['error_rate_percent']:.1f}%) negativně ovlivňuje uživatelský zážitek.",
                usage_patterns={
                    "error_rate_percent": stats['error_rate_percent'],
                    "total_requests": stats['total_requests']
                },
                implementation_complexity="high",
                auto_implementable=False
            )
            suggestions.append(suggestion)
        
        return suggestions
    
    def _suggest_automation_opportunities(
        self,
        patterns: Dict[str, Any],
        tenant_id: int
    ) -> List[FeatureSuggestion]:
        """Navrhnout možnosti automatizace"""
        
        suggestions = []
        
        # Analýza opakujících se akcí
        # TODO: Implementovat detekci opakujících se sekvencí
        
        # Příklad: Automatické zálohování
        suggestion = FeatureSuggestion(
            tenant_id=tenant_id,
            title="Automatické zálohování dat",
            description="Automatické pravidelné zálohování databáze a důležitých souborů",
            category="automation",
            priority=80,
            reasoning="Zálohování je důležité pro bezpečnost dat. Automatizace by ušetřila čas.",
            usage_patterns={},
            implementation_complexity="medium",
            auto_implementable=True
        )
        suggestions.append(suggestion)
        
        return suggestions
    
    def save_suggestions(self, suggestions: List[FeatureSuggestion]) -> List[FeatureSuggestion]:
        """Uložit návrhy do databáze"""
        
        saved = []
        for suggestion in suggestions:
            # Zkontrolovat duplicity
            existing = self.db.query(FeatureSuggestion).filter(
                and_(
                    FeatureSuggestion.tenant_id == suggestion.tenant_id,
                    FeatureSuggestion.title == suggestion.title,
                    FeatureSuggestion.status.in_(["suggested", "approved", "implemented"])
                )
            ).first()
            
            if not existing:
                self.db.add(suggestion)
                saved.append(suggestion)
        
        self.db.commit()
        
        return saved
    
    def get_suggestions(
        self,
        tenant_id: int,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 50
    ) -> List[FeatureSuggestion]:
        """Získat návrhy funkcí"""
        
        query = self.db.query(FeatureSuggestion).filter(
            FeatureSuggestion.tenant_id == tenant_id
        )
        
        if status:
            query = query.filter(FeatureSuggestion.status == status)
        if category:
            query = query.filter(FeatureSuggestion.category == category)
        
        return query.order_by(desc(FeatureSuggestion.priority), desc(FeatureSuggestion.created_at)).limit(limit).all()
    
    def update_suggestion_priority(
        self,
        suggestion_id: int,
        tenant_id: int,
        new_priority: int
    ) -> Optional[FeatureSuggestion]:
        """Aktualizovat prioritu návrhu"""
        
        suggestion = self.db.query(FeatureSuggestion).filter(
            and_(
                FeatureSuggestion.id == suggestion_id,
                FeatureSuggestion.tenant_id == tenant_id
            )
        ).first()
        
        if suggestion:
            suggestion.priority = new_priority
            suggestion.updated_at = datetime.utcnow()
            self.db.commit()
        
        return suggestion

