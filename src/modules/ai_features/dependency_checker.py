"""
Dependency Checker - kontroluje závislosti a kompatibilitu funkcí
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from .models import FeatureSuggestion, FeatureDependency
from src.modules.vehicle_hub.database import get_db


class DependencyChecker:
    """Kontrola závislostí a kompatibility funkcí"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_dependencies(
        self,
        suggestion: FeatureSuggestion
    ) -> Dict[str, Any]:
        """Zkontrolovat závislosti návrhu"""
        
        dependencies = suggestion.dependencies or []
        missing = []
        available = []
        conflicts = []
        
        for dep in dependencies:
            dep_name = dep.get("name") if isinstance(dep, dict) else str(dep)
            dep_type = dep.get("type", "module") if isinstance(dep, dict) else "module"
            
            # Zkontrolovat, zda závislost existuje
            if not self._check_dependency_exists(dep_name, dep_type):
                missing.append({
                    "name": dep_name,
                    "type": dep_type,
                    "required": dep.get("required", True) if isinstance(dep, dict) else True
                })
            else:
                available.append({
                    "name": dep_name,
                    "type": dep_type
                })
                
                # Zkontrolovat kompatibilitu
                compat = self._check_compatibility(dep_name, dep_type, suggestion)
                if not compat["compatible"]:
                    conflicts.append({
                        "dependency": dep_name,
                        "issue": compat["issue"]
                    })
        
        return {
            "missing": missing,
            "available": available,
            "conflicts": conflicts,
            "can_implement": len([d for d in missing if d.get("required", True)]) == 0
        }
    
    def _check_dependency_exists(
        self,
        name: str,
        dep_type: str
    ) -> bool:
        """Zkontrolovat, zda závislost existuje"""
        
        # Mapování modulů v aplikaci
        available_modules = {
            "vehicle_hub": True,
            "email_client": True,
            "pdf_manager": True,
            "image_tools": True,
            "voice": True,
            "auth": True
        }
        
        if dep_type == "module":
            return available_modules.get(name, False)
        
        # TODO: Implementovat kontrolu pro endpointy, funkce, atd.
        
        return False
    
    def _check_compatibility(
        self,
        dependency_name: str,
        dependency_type: str,
        suggestion: FeatureSuggestion
    ) -> Dict[str, Any]:
        """Zkontrolovat kompatibilitu závislosti s návrhem"""
        
        # TODO: Implementovat komplexní kontrolu kompatibility
        # Např. kontrola verzí, konfliktů funkcí, atd.
        
        return {
            "compatible": True,
            "issue": None
        }
    
    def find_related_features(
        self,
        suggestion: FeatureSuggestion
    ) -> List[FeatureSuggestion]:
        """Najít související funkce"""
        
        related = []
        
        # Najít funkce se stejnou kategorií
        same_category = self.db.query(FeatureSuggestion).filter(
            and_(
                FeatureSuggestion.tenant_id == suggestion.tenant_id,
                FeatureSuggestion.category == suggestion.category,
                FeatureSuggestion.id != suggestion.id,
                FeatureSuggestion.status.in_(["suggested", "approved", "implemented"])
            )
        ).limit(5).all()
        
        related.extend(same_category)
        
        # Najít funkce se stejnými závislostmi
        if suggestion.dependencies:
            dep_names = [
                d.get("name") if isinstance(d, dict) else str(d)
                for d in suggestion.dependencies
            ]
            
            # TODO: Implementovat vyhledávání podle závislostí
        
        return related
    
    def build_dependency_graph(
        self,
        tenant_id: int
    ) -> Dict[str, Any]:
        """Vytvořit graf závislostí všech funkcí"""
        
        suggestions = self.db.query(FeatureSuggestion).filter(
            and_(
                FeatureSuggestion.tenant_id == tenant_id,
                FeatureSuggestion.status.in_(["suggested", "approved", "implemented"])
            )
        ).all()
        
        nodes = []
        edges = []
        
        for suggestion in suggestions:
            nodes.append({
                "id": suggestion.id,
                "title": suggestion.title,
                "category": suggestion.category,
                "status": suggestion.status
            })
            
            if suggestion.dependencies:
                for dep in suggestion.dependencies:
                    dep_name = dep.get("name") if isinstance(dep, dict) else str(dep)
                    edges.append({
                        "from": dep_name,
                        "to": suggestion.id,
                        "type": "depends_on"
                    })
        
        return {
            "nodes": nodes,
            "edges": edges
        }
    
    def validate_implementation_order(
        self,
        suggestion_ids: List[int],
        tenant_id: int
    ) -> Tuple[bool, List[str], List[int]]:
        """Validovat pořadí implementace funkcí"""
        
        suggestions = self.db.query(FeatureSuggestion).filter(
            and_(
                FeatureSuggestion.id.in_(suggestion_ids),
                FeatureSuggestion.tenant_id == tenant_id
            )
        ).all()
        
        errors = []
        correct_order = []
        
        # Topologické řazení podle závislostí
        implemented = set()
        
        while len(correct_order) < len(suggestions):
            progress = False
            
            for suggestion in suggestions:
                if suggestion.id in correct_order:
                    continue
                
                # Zkontrolovat, zda jsou všechny závislosti implementované
                deps_check = self.check_dependencies(suggestion)
                missing_required = [
                    d for d in deps_check["missing"]
                    if d.get("required", True)
                ]
                
                # Zkontrolovat, zda jsou závislosti v seznamu k implementaci
                missing_in_list = []
                if suggestion.dependencies:
                    for dep in suggestion.dependencies:
                        dep_name = dep.get("name") if isinstance(dep, dict) else str(dep)
                        # Pokud je to modul, není to problém
                        if dep.get("type", "module") == "module":
                            continue
                        # Pokud je to jiná funkce, musí být v seznamu
                        # TODO: Implementovat kontrolu
        
                if len(missing_required) == 0:
                    correct_order.append(suggestion.id)
                    implemented.add(suggestion.id)
                    progress = True
            
            if not progress:
                # Cyklická závislost nebo chybějící závislosti
                remaining = [s.id for s in suggestions if s.id not in correct_order]
                errors.append(f"Cyklická závislost nebo chybějící závislosti u funkcí: {remaining}")
                break
        
        return len(errors) == 0, errors, correct_order

