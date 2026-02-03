"""
FastAPI webhook and API layer for Pulse.

This module provides:
- Webhook endpoint to receive transcripts from existing bot system
- API to return classification + approved nudge
- A/B test infrastructure for controlled experiments
"""

import os
import random
import hashlib
from datetime import datetime
from typing import Optional
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .models import (
    TranscriptInput,
    ClassificationResult,
    NudgeResult,
    NudgeDecision,
    BackendStatus,
    BrandPersona,
    StallCategory,
    Message,
    MessageRole,
)
from .classifier import classify_transcript
from .nudge_generator import generate_nudge
from .backend_status import check_backend_status, BackendStatusChecker
from .database import get_database
from .logger import PulseLogger

# Load environment
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Pulse API",
    description="Stalled Conversation Resurrection Engine",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
logger = PulseLogger()
backend_checker = BackendStatusChecker(mock_mode=True)


# ============== Request/Response Models ==============

class WebhookTranscriptMessage(BaseModel):
    """Message format from webhook."""
    role: str = Field(description="'bot' or 'user'")
    text: str
    timestamp: Optional[str] = None


class WebhookPayload(BaseModel):
    """Webhook payload from bot system."""
    chat_id: str
    carrier_id: Optional[str] = None
    history: list[WebhookTranscriptMessage]
    last_bot_message_timestamp: Optional[str] = None
    metadata: Optional[dict] = None


class ClassificationResponse(BaseModel):
    """Classification API response."""
    chat_id: str
    status: str
    category: str
    reason: str
    confidence: float
    evidence: str
    latency_ms: Optional[float] = None


class NudgeResponse(BaseModel):
    """Nudge API response."""
    chat_id: str
    action: str  # "SEND", "QUEUE_FOR_REVIEW", "SKIP"
    reason: str
    nudge_text: Optional[str] = None
    brand_persona: Optional[str] = None
    classification: Optional[ClassificationResponse] = None
    backend_status: Optional[dict] = None
    experiment_group: Optional[str] = None  # For A/B testing


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str


# ============== A/B Test Infrastructure ==============

class ExperimentGroup(str, Enum):
    """A/B test groups."""
    CONTROL = "control"  # No nudge
    TREATMENT = "treatment"  # Nudge enabled


class ABTestConfig(BaseModel):
    """A/B test configuration."""
    enabled: bool = True
    treatment_ratio: float = 0.5  # 50% treatment, 50% control
    experiment_id: str = "pulse_nudge_v1"


# Global A/B test config
ab_config = ABTestConfig()


def get_experiment_group(chat_id: str) -> ExperimentGroup:
    """
    Deterministically assign a chat to an experiment group.
    
    Uses hash of chat_id for consistent assignment - same chat
    always gets same group.
    """
    if not ab_config.enabled:
        return ExperimentGroup.TREATMENT
    
    # Hash chat_id for deterministic assignment
    hash_val = int(hashlib.md5(
        f"{ab_config.experiment_id}:{chat_id}".encode()
    ).hexdigest(), 16)
    
    # Assign based on treatment ratio
    if (hash_val % 100) / 100 < ab_config.treatment_ratio:
        return ExperimentGroup.TREATMENT
    return ExperimentGroup.CONTROL


# ============== Carrier Configuration ==============

class CarrierConfig(BaseModel):
    """Per-carrier configuration."""
    carrier_id: str
    brand_persona: BrandPersona = BrandPersona.HELPFUL_NEIGHBOR
    auto_send_enabled: bool = False
    confidence_threshold: float = 0.7
    ab_test_enabled: bool = True


# Default carrier configs (would come from database in production)
CARRIER_CONFIGS = {
    "lemonade": CarrierConfig(
        carrier_id="lemonade",
        brand_persona=BrandPersona.HELPFUL_NEIGHBOR,
        auto_send_enabled=False,
        confidence_threshold=0.7,
    ),
    "statefarm": CarrierConfig(
        carrier_id="statefarm",
        brand_persona=BrandPersona.PROFESSIONAL_ADVISOR,
        auto_send_enabled=False,
        confidence_threshold=0.8,
    ),
    "default": CarrierConfig(
        carrier_id="default",
        brand_persona=BrandPersona.HELPFUL_NEIGHBOR,
        auto_send_enabled=False,
        confidence_threshold=0.7,
    ),
}


def get_carrier_config(carrier_id: Optional[str]) -> CarrierConfig:
    """Get configuration for a carrier."""
    if carrier_id and carrier_id in CARRIER_CONFIGS:
        return CARRIER_CONFIGS[carrier_id]
    return CARRIER_CONFIGS["default"]


# ============== API Endpoints ==============

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="0.1.0",
    )


@app.post("/webhook/stalled", response_model=NudgeResponse)
async def process_stalled_conversation(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    x_carrier_id: Optional[str] = Header(None),
):
    """
    Webhook endpoint for processing stalled conversations.
    
    This is the main entry point for the bot system to send
    stalled conversations for analysis.
    """
    # Get carrier config
    carrier_id = x_carrier_id or payload.carrier_id
    carrier_config = get_carrier_config(carrier_id)
    
    # Build transcript
    transcript = TranscriptInput(
        chat_id=payload.chat_id,
        history=[
            Message(
                role=MessageRole(m.role),
                text=m.text,
            )
            for m in payload.history
        ],
    )
    
    # Log incoming transcript
    background_tasks.add_task(logger.log_transcript, transcript)
    
    # Check A/B test assignment
    experiment_group = get_experiment_group(payload.chat_id)
    
    if experiment_group == ExperimentGroup.CONTROL:
        return NudgeResponse(
            chat_id=payload.chat_id,
            action="SKIP",
            reason="Control group - no nudge",
            experiment_group=experiment_group.value,
        )
    
    # Check backend status (multi-channel awareness)
    backend_status = check_backend_status(
        payload.chat_id,
        mock_mode=True,  # Use real integration in production
    )
    
    # Log backend status
    background_tasks.add_task(logger.log_backend_status, backend_status)
    
    if not backend_status.safe_to_nudge:
        return NudgeResponse(
            chat_id=payload.chat_id,
            action="SKIP",
            reason=f"User active elsewhere: {backend_status.last_portal_activity}",
            backend_status=backend_status.model_dump(),
            experiment_group=experiment_group.value,
        )
    
    # Classify transcript
    classification = classify_transcript(transcript)
    
    # Log classification
    background_tasks.add_task(
        logger.log_classification,
        transcript,
        classification,
    )
    
    # Check if classification warrants a nudge
    if classification.category == StallCategory.BENIGN:
        return NudgeResponse(
            chat_id=payload.chat_id,
            action="SKIP",
            reason="Classification is BENIGN - no intervention needed",
            classification=ClassificationResponse(
                chat_id=classification.chat_id,
                status=classification.status.value,
                category=classification.category.value,
                reason=classification.reason,
                confidence=classification.confidence,
                evidence=classification.evidence,
                latency_ms=classification.latency_ms,
            ),
            experiment_group=experiment_group.value,
        )
    
    if classification.confidence < carrier_config.confidence_threshold:
        return NudgeResponse(
            chat_id=payload.chat_id,
            action="SKIP",
            reason=f"Confidence {classification.confidence:.2f} below threshold {carrier_config.confidence_threshold}",
            classification=ClassificationResponse(
                chat_id=classification.chat_id,
                status=classification.status.value,
                category=classification.category.value,
                reason=classification.reason,
                confidence=classification.confidence,
                evidence=classification.evidence,
                latency_ms=classification.latency_ms,
            ),
            experiment_group=experiment_group.value,
        )
    
    # Generate nudge with carrier's brand voice
    nudge = generate_nudge(
        transcript,
        classification,
        carrier_config.brand_persona,
    )
    
    # Log nudge
    background_tasks.add_task(logger.log_nudge, nudge)
    
    # Determine action based on config
    action = "SEND" if carrier_config.auto_send_enabled else "QUEUE_FOR_REVIEW"
    
    return NudgeResponse(
        chat_id=payload.chat_id,
        action=action,
        reason=f"Nudge generated for {classification.reason}",
        nudge_text=nudge.nudge_text,
        brand_persona=nudge.brand_persona.value,
        classification=ClassificationResponse(
            chat_id=classification.chat_id,
            status=classification.status.value,
            category=classification.category.value,
            reason=classification.reason,
            confidence=classification.confidence,
            evidence=classification.evidence,
            latency_ms=classification.latency_ms,
        ),
        backend_status=backend_status.model_dump(),
        experiment_group=experiment_group.value,
    )


@app.post("/classify", response_model=ClassificationResponse)
async def classify_only(payload: WebhookPayload):
    """
    Classification-only endpoint.
    
    Returns classification without generating a nudge.
    Useful for analytics and debugging.
    """
    transcript = TranscriptInput(
        chat_id=payload.chat_id,
        history=[
            Message(
                role=MessageRole(m.role),
                text=m.text,
            )
            for m in payload.history
        ],
    )
    
    classification = classify_transcript(transcript)
    
    return ClassificationResponse(
        chat_id=classification.chat_id,
        status=classification.status.value,
        category=classification.category.value,
        reason=classification.reason,
        confidence=classification.confidence,
        evidence=classification.evidence,
        latency_ms=classification.latency_ms,
    )


@app.get("/experiment/config")
async def get_experiment_config():
    """Get current A/B test configuration."""
    return {
        "enabled": ab_config.enabled,
        "treatment_ratio": ab_config.treatment_ratio,
        "experiment_id": ab_config.experiment_id,
    }


@app.post("/experiment/config")
async def update_experiment_config(
    enabled: Optional[bool] = None,
    treatment_ratio: Optional[float] = None,
):
    """Update A/B test configuration."""
    global ab_config
    
    if enabled is not None:
        ab_config.enabled = enabled
    if treatment_ratio is not None:
        if not 0 <= treatment_ratio <= 1:
            raise HTTPException(400, "treatment_ratio must be between 0 and 1")
        ab_config.treatment_ratio = treatment_ratio
    
    return {
        "enabled": ab_config.enabled,
        "treatment_ratio": ab_config.treatment_ratio,
        "experiment_id": ab_config.experiment_id,
    }


@app.get("/carriers")
async def list_carriers():
    """List configured carriers."""
    return {
        carrier_id: {
            "brand_persona": config.brand_persona.value,
            "auto_send_enabled": config.auto_send_enabled,
            "confidence_threshold": config.confidence_threshold,
        }
        for carrier_id, config in CARRIER_CONFIGS.items()
    }


# ============== Metrics Endpoints ==============

@app.get("/metrics/classifications")
async def get_classification_metrics():
    """Get classification statistics."""
    db = get_database()
    return db.get_classification_stats()


@app.get("/metrics/reviews")
async def get_review_metrics():
    """Get review statistics."""
    db = get_database()
    return db.get_review_stats()


# ============== Auto-Send & Multi-Tenant Endpoints ==============

from .autosend import get_auto_send_engine, get_tenant_manager, SendAction

@app.post("/process")
async def process_with_autosend(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """
    Process a conversation with the auto-send engine.
    
    This endpoint uses the full Phase 4 pipeline:
    - Multi-channel awareness
    - A/B testing
    - Confidence thresholds
    - Auto-send for high confidence
    """
    tenant_id = x_tenant_id or payload.carrier_id or "default"
    
    # Build transcript
    transcript = TranscriptInput(
        chat_id=payload.chat_id,
        history=[
            Message(
                role=MessageRole(m.role),
                text=m.text,
            )
            for m in payload.history
        ],
    )
    
    # Process with auto-send engine
    engine = get_auto_send_engine()
    decision = engine.process_conversation(transcript, tenant_id)
    
    return {
        "chat_id": payload.chat_id,
        "tenant_id": tenant_id,
        "action": decision.action.value,
        "reason": decision.reason,
        "nudge_text": decision.nudge_text,
        "confidence": decision.confidence,
        "classification_category": decision.classification_category,
        "experiment_group": decision.experiment_group,
        "should_send": decision.action == SendAction.AUTO_SEND,
    }


@app.get("/tenants")
async def list_tenants():
    """List all tenant configurations."""
    manager = get_tenant_manager()
    return {"tenants": manager.list_tenants()}


@app.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str):
    """Get a specific tenant configuration."""
    manager = get_tenant_manager()
    tenant = manager.get_tenant(tenant_id)
    return tenant.to_dict()


@app.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    auto_send_enabled: Optional[bool] = None,
    auto_send_confidence_threshold: Optional[float] = None,
    review_confidence_threshold: Optional[float] = None,
    max_nudges_per_day: Optional[int] = None,
):
    """Update tenant configuration."""
    manager = get_tenant_manager()
    
    updates = {}
    if auto_send_enabled is not None:
        updates["auto_send_enabled"] = auto_send_enabled
    if auto_send_confidence_threshold is not None:
        updates["auto_send_confidence_threshold"] = auto_send_confidence_threshold
    if review_confidence_threshold is not None:
        updates["review_confidence_threshold"] = review_confidence_threshold
    if max_nudges_per_day is not None:
        updates["max_nudges_per_day"] = max_nudges_per_day
    
    tenant = manager.update_tenant(tenant_id, **updates)
    return tenant.to_dict()


@app.get("/tenants/{tenant_id}/stats")
async def get_tenant_stats(tenant_id: str):
    """Get statistics for a tenant."""
    engine = get_auto_send_engine()
    return engine.get_tenant_stats(tenant_id)


# ============== Startup/Shutdown ==============

@app.on_event("startup")
async def startup():
    """Initialize on startup."""
    print("Pulse API starting up...")
    # Initialize database
    get_database()
    print("Database initialized")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    print("Pulse API shutting down...")


# Run with: uvicorn src.api:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
