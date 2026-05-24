"""
API Router pro AI Feature Suggestion System
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from src.modules.vehicle_hub.database import get_db
from src.core.auth import get_current_user_email
from src.modules.vehicle_hub.routers_v1.auth import get_current_user, require_role
from src.modules.vehicle_hub.models import Customer
from .models import FeatureSuggestion, FeatureVote, FeatureFeedback
from .feature_engine import FeatureSuggestionEngine
from .dependency_checker import DependencyChecker
from .integration_manager import FeatureIntegrationManager
from .analytics import AnalyticsCollector

router = APIRouter(prefix="/api/v1/ai-features", tags=["AI Features"])


# ============= SCHEMAS =============

class FeatureSuggestionResponse(BaseModel):
    id: int
    title: str
    description: str
    category: Optional[str]
    priority: int
    confidence_score: float
    status: str
    implementation_complexity: Optional[str]
    estimated_effort_hours: Optional[float]
    created_at: datetime
    
    class Config:
        from_attributes = True


class FeatureSuggestionCreate(BaseModel):
    title: str
    description: str
    category: Optional[str] = None
    priority: Optional[int] = 50
    reasoning: Optional[str] = None
    dependencies: Optional[List[Dict[str, Any]]] = None


class FeatureVoteCreate(BaseModel):
    vote: int  # 1 = pro, -1 = proti, 0 = neutrální
    comment: Optional[str] = None


class FeatureFeedbackCreate(BaseModel):
    rating: Optional[int] = None  # 1-5
    comment: Optional[str] = None
    usage_frequency: Optional[str] = None
    issues: Optional[List[str]] = None


# ============= ENDPOINTS =============

@router.get("/suggestions", response_model=List[FeatureSuggestionResponse])
def get_suggestions(
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Získat seznam navrhovaných funkcí"""
    
    tenant_id = current_user.tenant_id
    
    engine = FeatureSuggestionEngine(db)
    suggestions = engine.get_suggestions(
        tenant_id=tenant_id,
        status=status,
        category=category,
        limit=limit
    )
    
    return suggestions


@router.get("/suggestions/{suggestion_id}", response_model=FeatureSuggestionResponse)
def get_suggestion_detail(
    suggestion_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Získat detail návrhu funkce"""
    
    tenant_id = current_user.tenant_id
    
    suggestion = db.query(FeatureSuggestion).filter(
        FeatureSuggestion.id == suggestion_id,
        FeatureSuggestion.tenant_id == tenant_id
    ).first()
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Návrh nenalezen")
    
    return suggestion


@router.post("/suggestions/analyze")
def analyze_and_suggest(
    days: int = 30,
    current_user: Customer = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Spustit analýzu a navrhnout nové funkce - pouze pro adminy"""
    
    tenant_id = current_user.tenant_id
    
    engine = FeatureSuggestionEngine(db)
    suggestions = engine.analyze_and_suggest(tenant_id=tenant_id, days=days)
    saved = engine.save_suggestions(suggestions)
    
    return {
        "analyzed": True,
        "suggestions_created": len(saved),
        "suggestions": [{"id": s.id, "title": s.title} for s in saved]
    }


@router.post("/suggestions", response_model=FeatureSuggestionResponse)
def create_suggestion(
    suggestion: FeatureSuggestionCreate,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvořit nový návrh funkce (manuálně)"""
    
    tenant_id = current_user.tenant_id
    
    new_suggestion = FeatureSuggestion(
        tenant_id=tenant_id,
        title=suggestion.title,
        description=suggestion.description,
        category=suggestion.category,
        priority=suggestion.priority or 50,
        reasoning=suggestion.reasoning,
        dependencies=suggestion.dependencies,
        status="suggested",
        confidence_score=0.5  # Manuální návrh má nižší confidence
    )
    
    db.add(new_suggestion)
    db.commit()
    db.refresh(new_suggestion)
    
    return new_suggestion


@router.post("/suggestions/{suggestion_id}/vote")
def vote_on_suggestion(
    suggestion_id: int,
    vote: FeatureVoteCreate,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Hlasovat o návrhu funkce"""
    
    tenant_id = current_user.tenant_id
    email = current_user.email
    
    suggestion = db.query(FeatureSuggestion).filter(
        FeatureSuggestion.id == suggestion_id,
        FeatureSuggestion.tenant_id == tenant_id
    ).first()
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Návrh nenalezen")
    
    # Zkontrolovat, zda uživatel už hlasoval
    existing_vote = db.query(FeatureVote).filter(
        FeatureVote.feature_id == suggestion_id,
        FeatureVote.user_email == email
    ).first()
    
    if existing_vote:
        existing_vote.vote = vote.vote
        existing_vote.comment = vote.comment
    else:
        new_vote = FeatureVote(
            feature_id=suggestion_id,
            user_email=current_user.email,
            vote=vote.vote,
            comment=vote.comment
        )
        db.add(new_vote)
    
    db.commit()
    
    return {"status": "ok", "message": "Hlas byl zaznamenán"}


@router.post("/suggestions/{suggestion_id}/approve")
def approve_suggestion(
    suggestion_id: int,
    current_user: Customer = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Schválit návrh funkce - pouze pro adminy"""
    
    tenant_id = current_user.tenant_id
    
    suggestion = db.query(FeatureSuggestion).filter(
        FeatureSuggestion.id == suggestion_id,
        FeatureSuggestion.tenant_id == tenant_id
    ).first()
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Návrh nenalezen")
    
    suggestion.status = "approved"
    suggestion.approved_by = current_user.email
    suggestion.approved_at = datetime.utcnow()
    
    db.commit()
    
    return {"status": "ok", "message": "Návrh byl schválen"}


@router.post("/suggestions/{suggestion_id}/reject")
def reject_suggestion(
    suggestion_id: int,
    current_user: Customer = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Odmítnout návrh funkce - pouze pro adminy"""
    
    tenant_id = current_user.tenant_id
    
    suggestion = db.query(FeatureSuggestion).filter(
        FeatureSuggestion.id == suggestion_id,
        FeatureSuggestion.tenant_id == tenant_id
    ).first()
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Návrh nenalezen")
    
    suggestion.status = "rejected"
    
    db.commit()
    
    return {"status": "ok", "message": "Návrh byl odmítnut"}


@router.get("/suggestions/{suggestion_id}/integration-plan")
def get_integration_plan(
    suggestion_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Získat plán integrace funkce"""
    
    tenant_id = current_user.tenant_id
    
    suggestion = db.query(FeatureSuggestion).filter(
        FeatureSuggestion.id == suggestion_id,
        FeatureSuggestion.tenant_id == tenant_id
    ).first()
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Návrh nenalezen")
    
    manager = FeatureIntegrationManager(db)
    plan = manager.prepare_integration_plan(suggestion)
    
    return plan


@router.get("/suggestions/{suggestion_id}/dependencies")
def check_dependencies(
    suggestion_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Zkontrolovat závislosti návrhu"""
    
    tenant_id = current_user.tenant_id
    
    suggestion = db.query(FeatureSuggestion).filter(
        FeatureSuggestion.id == suggestion_id,
        FeatureSuggestion.tenant_id == tenant_id
    ).first()
    
    if not suggestion:
        raise HTTPException(status_code=404, detail="Návrh nenalezen")
    
    checker = DependencyChecker(db)
    deps = checker.check_dependencies(suggestion)
    
    return deps


@router.get("/analytics/stats")
def get_analytics_stats(
    days: int = 30,
    current_user: Customer = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Získat statistiky použití aplikace - pouze pro adminy"""
    
    tenant_id = current_user.tenant_id
    
    collector = AnalyticsCollector(db)
    stats = collector.get_usage_stats(tenant_id=tenant_id, days=days)
    
    return stats


@router.get("/analytics/patterns")
def get_usage_patterns(
    days: int = 30,
    current_user: Customer = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Získat vzorce použití aplikace - pouze pro adminy"""
    
    tenant_id = current_user.tenant_id
    
    collector = AnalyticsCollector(db)
    patterns = collector.get_usage_patterns(tenant_id=tenant_id, days=days)
    
    return patterns

