"""
Databázové modely pro AI Feature Suggestion System
"""
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from src.modules.vehicle_hub.database import Base


class UsageAnalytics(Base):
    """Sledování použití aplikace - endpointy, funkce, uživatelské vzorce"""
    __tablename__ = "usage_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    user_email = Column(String, nullable=True, index=True)
    
    # Co bylo použito
    endpoint = Column(String, nullable=True, index=True)  # API endpoint
    module = Column(String, nullable=True, index=True)  # Modul (vehicle_hub, email_client, etc.)
    function = Column(String, nullable=True, index=True)  # Konkrétní funkce
    action = Column(String, nullable=True)  # Akce (create, read, update, delete)
    
    # Metadata
    request_method = Column(String, nullable=True)  # GET, POST, PUT, DELETE
    response_status = Column(Integer, nullable=True)
    response_time_ms = Column(Float, nullable=True)  # Doba odezvy v ms
    request_size = Column(Integer, nullable=True)  # Velikost requestu v bytech
    response_size = Column(Integer, nullable=True)  # Velikost response v bytech
    
    # Kontext
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    session_id = Column(String, nullable=True, index=True)
    
    # Časové údaje
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Další metadata (JSON)
    extra_metadata = Column(JSON, nullable=True)


class FeatureSuggestion(Base):
    """Navrhované funkce od AI systému"""
    __tablename__ = "feature_suggestions"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)
    
    # Základní informace
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String, nullable=True, index=True)  # vehicle, email, pdf, image, etc.
    priority = Column(Integer, default=0, index=True)  # 0-100, vyšší = důležitější
    
    # AI analýza
    reasoning = Column(Text, nullable=True)  # Proč byla funkce navržena
    confidence_score = Column(Float, default=0.0)  # 0.0-1.0, jistota AI
    usage_patterns = Column(JSON, nullable=True)  # Vzorce použití, které vedly k návrhu
    
    # Závislosti a kompatibilita
    dependencies = Column(JSON, nullable=True)  # Seznam závislostí (moduly, funkce)
    compatible_features = Column(JSON, nullable=True)  # Kompatibilní existující funkce
    conflicts = Column(JSON, nullable=True)  # Potenciální konflikty
    
    # Implementace
    implementation_complexity = Column(String, nullable=True)  # low, medium, high
    estimated_effort_hours = Column(Float, nullable=True)
    implementation_steps = Column(JSON, nullable=True)  # Krok za krokem implementace
    
    # Status
    status = Column(String, default="suggested", index=True)  # suggested, approved, rejected, implemented, testing
    approved_by = Column(String, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    # Automatická implementace
    auto_implementable = Column(Boolean, default=False)  # Může být automaticky implementováno?
    auto_implementation_code = Column(Text, nullable=True)  # Generovaný kód pro automatickou implementaci
    
    # Časové údaje
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    implemented_at = Column(DateTime, nullable=True)
    
    # Vztahy
    related_suggestions = Column(JSON, nullable=True)  # ID souvisejících návrhů
    votes = relationship("FeatureVote", back_populates="feature", cascade="all, delete-orphan")
    feedback = relationship("FeatureFeedback", back_populates="feature", cascade="all, delete-orphan")


class FeatureVote(Base):
    """Hlasování uživatelů o navrhovaných funkcích"""
    __tablename__ = "feature_votes"
    
    id = Column(Integer, primary_key=True, index=True)
    feature_id = Column(Integer, ForeignKey("feature_suggestions.id"), nullable=False, index=True)
    user_email = Column(String, nullable=False, index=True)
    vote = Column(Integer, nullable=False)  # 1 = pro, -1 = proti, 0 = neutrální
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    feature = relationship("FeatureSuggestion", back_populates="votes")


class FeatureFeedback(Base):
    """Zpětná vazba na implementované funkce"""
    __tablename__ = "feature_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    feature_id = Column(Integer, ForeignKey("feature_suggestions.id"), nullable=False, index=True)
    user_email = Column(String, nullable=False, index=True)
    
    rating = Column(Integer, nullable=True)  # 1-5 hvězdiček
    comment = Column(Text, nullable=True)
    usage_frequency = Column(String, nullable=True)  # daily, weekly, monthly, rarely, never
    issues = Column(JSON, nullable=True)  # Seznam problémů nebo vylepšení
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    feature = relationship("FeatureSuggestion", back_populates="feedback")


class FeatureDependency(Base):
    """Mapování závislostí mezi funkcemi"""
    __tablename__ = "feature_dependencies"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Funkce, která má závislost
    source_feature = Column(String, nullable=False, index=True)  # Název funkce/modulu
    source_type = Column(String, nullable=False)  # module, endpoint, function
    
    # Na čem závisí
    depends_on_feature = Column(String, nullable=False, index=True)
    depends_on_type = Column(String, nullable=False)
    
    # Typ závislosti
    dependency_type = Column(String, nullable=False)  # required, optional, recommended
    
    # Metadata
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Kompatibilita
    compatible = Column(Boolean, default=True)
    tested = Column(Boolean, default=False)
    tested_at = Column(DateTime, nullable=True)


class AutoImplementationLog(Base):
    """Log automatických implementací funkcí"""
    __tablename__ = "auto_implementation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    feature_id = Column(Integer, ForeignKey("feature_suggestions.id"), nullable=False, index=True)
    
    # Implementace
    implementation_type = Column(String, nullable=False)  # auto, manual, hybrid
    status = Column(String, nullable=False, index=True)  # started, completed, failed, rolled_back
    
    # Kód a změny
    code_generated = Column(Text, nullable=True)
    files_created = Column(JSON, nullable=True)  # Seznam vytvořených souborů
    files_modified = Column(JSON, nullable=True)  # Seznam upravených souborů
    
    # Výsledek
    success = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    test_results = Column(JSON, nullable=True)  # Výsledky testů
    
    # Časové údaje
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

