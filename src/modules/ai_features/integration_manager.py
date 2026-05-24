"""
Feature Integration Manager - zajišťuje správnou integraci nových funkcí
"""
import json
import ast
from typing import List, Dict, Any, Optional
from pathlib import Path
from sqlalchemy.orm import Session

from .models import FeatureSuggestion, AutoImplementationLog
from .dependency_checker import DependencyChecker


class FeatureIntegrationManager:
    """Správa integrace nových funkcí do aplikace"""
    
    def __init__(self, db: Session, project_root: Optional[Path] = None):
        self.db = db
        self.dependency_checker = DependencyChecker(db)
        self.project_root = project_root or Path(__file__).parent.parent.parent.parent
    
    def prepare_integration_plan(
        self,
        suggestion: FeatureSuggestion
    ) -> Dict[str, Any]:
        """Připravit plán integrace funkce"""
        
        # Zkontrolovat závislosti
        deps_check = self.dependency_checker.check_dependencies(suggestion)
        
        if not deps_check["can_implement"]:
            return {
                "can_implement": False,
                "reason": "Chybějící závislosti",
                "missing_dependencies": deps_check["missing"]
            }
        
        # Identifikovat soubory, které budou ovlivněny
        affected_files = self._identify_affected_files(suggestion)
        
        # Vytvořit kroky implementace
        implementation_steps = self._create_implementation_steps(suggestion, affected_files)
        
        # Odhadnout složitost
        complexity = self._estimate_complexity(suggestion, implementation_steps)
        
        return {
            "can_implement": True,
            "affected_files": affected_files,
            "implementation_steps": implementation_steps,
            "estimated_complexity": complexity,
            "estimated_hours": suggestion.estimated_effort_hours or complexity.get("hours", 0),
            "dependencies": deps_check
        }
    
    def _identify_affected_files(
        self,
        suggestion: FeatureSuggestion
    ) -> List[Dict[str, Any]]:
        """Identifikovat soubory, které budou ovlivněny"""
        
        files = []
        
        # Na základě kategorie a závislostí
        category = suggestion.category
        dependencies = suggestion.dependencies or []
        
        # Mapování kategorií na moduly
        category_module_map = {
            "vehicle": "vehicle_hub",
            "email": "email_client",
            "pdf": "pdf_manager",
            "image": "image_tools",
            "voice": "voice",
            "integration": "server"
        }
        
        module = category_module_map.get(category, "server")
        
        # Identifikovat soubory v modulu
        module_path = self.project_root / "src" / "modules" / module
        
        if module_path.exists():
            # Controller
            controller_file = module_path / "controller.py"
            if controller_file.exists():
                files.append({
                    "path": str(controller_file.relative_to(self.project_root)),
                    "type": "controller",
                    "action": "modify"
                })
            
            # Service
            service_file = module_path / "service.py"
            if service_file.exists():
                files.append({
                    "path": str(service_file.relative_to(self.project_root)),
                    "type": "service",
                    "action": "modify"
                })
            
            # Router (pokud existuje)
            router_dir = module_path / "routers_v1"
            if router_dir.exists():
                files.append({
                    "path": str(router_dir),
                    "type": "router",
                    "action": "modify_or_create"
                })
        
        # Server main.py (pro nové endpointy)
        if category == "integration":
            files.append({
                "path": "src/server/main.py",
                "type": "server",
                "action": "modify"
            })
        
        # Web interface (pro UI)
        files.append({
            "path": "web/index.html",
            "type": "frontend",
            "action": "modify"
        })
        
        return files
    
    def _create_implementation_steps(
        self,
        suggestion: FeatureSuggestion,
        affected_files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Vytvořit kroky implementace"""
        
        steps = []
        
        # Krok 1: Databázové modely (pokud je potřeba)
        if "database" in (suggestion.metadata or {}):
            steps.append({
                "step": 1,
                "title": "Vytvořit databázové modely",
                "description": "Přidat nové modely do databáze",
                "files": ["src/modules/ai_features/models.py"],
                "complexity": "low"
            })
        
        # Krok 2: Backend logika
        backend_files = [f for f in affected_files if f["type"] in ["service", "controller"]]
        if backend_files:
            steps.append({
                "step": 2,
                "title": "Implementovat backend logiku",
                "description": "Přidat business logiku do service a controller",
                "files": [f["path"] for f in backend_files],
                "complexity": "medium"
            })
        
        # Krok 3: API endpointy
        router_files = [f for f in affected_files if f["type"] == "router"]
        if router_files:
            steps.append({
                "step": 3,
                "title": "Vytvořit API endpointy",
                "description": "Přidat nové endpointy do routeru",
                "files": [f["path"] for f in router_files],
                "complexity": "medium"
            })
        
        # Krok 4: Frontend UI
        frontend_files = [f for f in affected_files if f["type"] == "frontend"]
        if frontend_files:
            steps.append({
                "step": 4,
                "title": "Vytvořit UI komponenty",
                "description": "Přidat uživatelské rozhraní",
                "files": [f["path"] for f in frontend_files],
                "complexity": "medium"
            })
        
        # Krok 5: Testy
        steps.append({
            "step": len(steps) + 1,
            "title": "Vytvořit testy",
            "description": "Přidat unit a integrační testy",
            "files": ["tests/"],
            "complexity": "medium"
        })
        
        # Krok 6: Dokumentace
        steps.append({
            "step": len(steps) + 1,
            "title": "Aktualizovat dokumentaci",
            "description": "Aktualizovat README a API dokumentaci",
            "files": ["README.md", "docs/"],
            "complexity": "low"
        })
        
        return steps
    
    def _estimate_complexity(
        self,
        suggestion: FeatureSuggestion,
        steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Odhadnout složitost implementace"""
        
        total_hours = 0
        complexity_scores = {"low": 2, "medium": 4, "high": 8}
        
        for step in steps:
            complexity = step.get("complexity", "medium")
            total_hours += complexity_scores.get(complexity, 4)
        
        # Upravit podle kategorie
        category_multipliers = {
            "integration": 1.5,
            "performance": 1.3,
            "automation": 1.2
        }
        
        multiplier = category_multipliers.get(suggestion.category, 1.0)
        total_hours = int(total_hours * multiplier)
        
        # Určit celkovou složitost
        if total_hours <= 4:
            overall_complexity = "low"
        elif total_hours <= 12:
            overall_complexity = "medium"
        else:
            overall_complexity = "high"
        
        return {
            "overall": overall_complexity,
            "hours": total_hours,
            "steps_count": len(steps)
        }
    
    def generate_integration_code(
        self,
        suggestion: FeatureSuggestion,
        plan: Dict[str, Any]
    ) -> Dict[str, str]:
        """Generovat kód pro integraci (základní šablony)"""
        
        code_snippets = {}
        
        # Generovat základní strukturu podle typu funkce
        if suggestion.category == "integration":
            # Integrace mezi moduly
            code_snippets["service_integration"] = self._generate_service_integration_code(suggestion)
            code_snippets["router_endpoint"] = self._generate_router_endpoint_code(suggestion)
        
        elif suggestion.category == "automation":
            # Automatizace
            code_snippets["automation_task"] = self._generate_automation_code(suggestion)
        
        # Frontend komponenta
        code_snippets["frontend_component"] = self._generate_frontend_code(suggestion)
        
        return code_snippets
    
    def _generate_service_integration_code(
        self,
        suggestion: FeatureSuggestion
    ) -> str:
        """Generovat kód pro integraci služeb"""
        
        return f'''"""
{suggestion.title}
{suggestion.description}
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

# TODO: Implementovat {suggestion.title}
def {self._function_name_from_title(suggestion.title)}(
    db: Session,
    # TODO: Přidat parametry
) -> Dict[str, Any]:
    """
    {suggestion.description}
    """
    # TODO: Implementovat logiku
    pass
'''
    
    def _generate_router_endpoint_code(
        self,
        suggestion: FeatureSuggestion
    ) -> str:
        """Generovat kód pro API endpoint"""
        
        return f'''from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src.modules.vehicle_hub.database import get_db

router = APIRouter(prefix="/api/v1", tags=["{suggestion.category}"])

@router.post("/{self._endpoint_name_from_title(suggestion.title)}")
async def {self._function_name_from_title(suggestion.title)}(
    db: Session = Depends(get_db),
    # TODO: Přidat request model
):
    """
    {suggestion.description}
    """
    # TODO: Implementovat endpoint
    pass
'''
    
    def _generate_automation_code(
        self,
        suggestion: FeatureSuggestion
    ) -> str:
        """Generovat kód pro automatizaci"""
        
        return f'''"""
Automatizace: {suggestion.title}
{suggestion.description}
"""
import schedule
import time
from datetime import datetime

def {self._function_name_from_title(suggestion.title)}():
    """
    {suggestion.description}
    """
    # TODO: Implementovat automatizaci
    pass

# Naplánovat spuštění
# schedule.every().day.at("02:00").do({self._function_name_from_title(suggestion.title)})
'''
    
    def _generate_frontend_code(
        self,
        suggestion: FeatureSuggestion
    ) -> str:
        """Generovat kód pro frontend"""
        
        return f'''<!-- {suggestion.title} -->
<div class="feature-{self._css_class_from_title(suggestion.title)}">
    <h3>{suggestion.title}</h3>
    <p>{suggestion.description}</p>
    <!-- TODO: Implementovat UI -->
</div>

<script>
// {suggestion.title} - JavaScript
function init{suggestion.title.replace(" ", "")}() {{
    // TODO: Implementovat funkcionalitu
}}
</script>
'''
    
    def _function_name_from_title(self, title: str) -> str:
        """Převést název na název funkce"""
        return title.lower().replace(" ", "_").replace("-", "_")
    
    def _endpoint_name_from_title(self, title: str) -> str:
        """Převést název na název endpointu"""
        return title.lower().replace(" ", "-").replace("_", "-")
    
    def _css_class_from_title(self, title: str) -> str:
        """Převést název na CSS třídu"""
        return title.lower().replace(" ", "-").replace("_", "-")

