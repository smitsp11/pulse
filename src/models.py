"""
Data models for Pulse classification and nudge generation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of the message sender."""
    BOT = "bot"
    USER = "user"


class Message(BaseModel):
    """A single message in a conversation."""
    role: MessageRole
    text: str
    timestamp: Optional[datetime] = None


class TranscriptInput(BaseModel):
    """Input format for conversation transcripts."""
    chat_id: str
    history: list[Message]
    last_bot_message_timestamp: Optional[datetime] = None
    
    @property
    def last_bot_message(self) -> Optional[str]:
        """Get the last message sent by the bot."""
        for msg in reversed(self.history):
            if msg.role == MessageRole.BOT:
                return msg.text
        return None
    
    @property
    def last_user_message(self) -> Optional[str]:
        """Get the last message sent by the user."""
        for msg in reversed(self.history):
            if msg.role == MessageRole.USER:
                return msg.text
        return None


class StallCategory(str, Enum):
    """Categories for classifying why a user stalled."""
    HIGH_FRICTION = "HIGH_FRICTION"
    CONFUSION = "CONFUSION"
    BENIGN = "BENIGN"


class StallStatus(str, Enum):
    """Status indicating risk level of the stall."""
    STALLED_HIGH_RISK = "STALLED_HIGH_RISK"
    STALLED_LOW_RISK = "STALLED_LOW_RISK"
    BENIGN = "BENIGN"


class ClassificationResult(BaseModel):
    """Output from the classification engine."""
    chat_id: str
    status: StallStatus
    category: StallCategory
    reason: str = Field(description="Detailed reason, e.g., 'HIGH_FRICTION:VIN_REQUEST'")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0-1")
    evidence: str = Field(description="Quote from transcript supporting classification")
    raw_llm_response: Optional[str] = None
    classified_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = None


class BackendStatus(BaseModel):
    """
    Status from backend systems for multi-channel awareness.
    
    Critical for avoiding the "Multi-Channel State Trap" where we nudge
    a user who has already completed the action on another channel.
    """
    chat_id: str
    user_active_elsewhere: bool = Field(
        default=False,
        description="True if user took action on portal/email"
    )
    last_portal_activity: Optional[datetime] = None
    pending_documents_received: bool = False
    safe_to_nudge: bool = True
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class BrandPersona(str, Enum):
    """Brand voice personas for enterprise customization."""
    HELPFUL_NEIGHBOR = "helpful_neighbor"
    PROFESSIONAL_ADVISOR = "professional_advisor"


BRAND_PERSONAS = {
    BrandPersona.HELPFUL_NEIGHBOR: {
        "description": "Casual, friendly, like texting a neighbor (Lemonade style)",
        "example": "No stress on the VIN—a photo of your registration works too!",
        "rules": [
            "Use contractions",
            "Keep it breezy",
            "OK to be slightly informal"
        ]
    },
    BrandPersona.PROFESSIONAL_ADVISOR: {
        "description": "Warm but professional, trustworthy advisor (State Farm style)",
        "example": "I understand getting the VIN can be inconvenient. A photo of your registration document would work just as well.",
        "rules": [
            "No slang",
            "Complete sentences", 
            "Empathetic but not casual"
        ]
    }
}


class NudgeResult(BaseModel):
    """Output from the nudge generator."""
    chat_id: str
    classification: ClassificationResult
    brand_persona: BrandPersona
    nudge_text: str
    raw_llm_response: Optional[str] = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    latency_ms: Optional[float] = None


class ReviewDecision(str, Enum):
    """Human review decisions for nudges."""
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class ReviewedNudge(BaseModel):
    """A nudge that has been reviewed by a human."""
    nudge: NudgeResult
    decision: ReviewDecision
    edited_text: Optional[str] = None
    reviewer_notes: Optional[str] = None
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)
    review_time_seconds: Optional[float] = None


class NudgeDecision(BaseModel):
    """Final decision on whether/how to nudge a user."""
    chat_id: str
    action: Literal["SEND", "QUEUE_FOR_REVIEW", "SKIP"]
    reason: str
    nudge: Optional[NudgeResult] = None
    backend_status: Optional[BackendStatus] = None
