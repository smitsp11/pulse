"""
Auto-send system for high-confidence nudges.

Phase 4 features:
- Auto-send for high-confidence classifications
- Configurable confidence thresholds
- Multi-tenant configuration (different carriers, different settings)
- Safety guardrails
"""

from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
from dataclasses import dataclass, field
import json

from .models import (
    TranscriptInput,
    ClassificationResult,
    NudgeResult,
    NudgeDecision,
    BrandPersona,
    StallCategory,
    StallStatus,
)
from .classifier import classify_transcript
from .nudge_generator import generate_nudge
from .backend_status import check_backend_status
from .ab_testing import ABTestManager, ExperimentGroup, get_experiment_manager


class SendAction(str, Enum):
    """Possible actions for a nudge decision."""
    AUTO_SEND = "auto_send"
    QUEUE_FOR_REVIEW = "queue_for_review"
    SKIP = "skip"


@dataclass
class TenantConfig:
    """
    Configuration for a single tenant (carrier/agency).
    
    Different carriers have different requirements:
    - Brand voice (casual vs professional)
    - Risk tolerance (confidence thresholds)
    - Automation level (auto-send vs review)
    """
    tenant_id: str
    tenant_name: str
    
    # Brand configuration
    brand_persona: BrandPersona = BrandPersona.HELPFUL_NEIGHBOR
    
    # Auto-send configuration
    auto_send_enabled: bool = False
    auto_send_confidence_threshold: float = 0.9
    
    # Review queue configuration
    review_confidence_threshold: float = 0.7  # Below this, skip entirely
    
    # A/B testing
    ab_test_enabled: bool = True
    ab_test_treatment_ratio: float = 0.5
    
    # Safety guardrails
    max_nudges_per_day: int = 100
    cooldown_hours: int = 24  # Min hours between nudges to same user
    
    # Categories to handle
    enabled_categories: list[StallCategory] = field(
        default_factory=lambda: [StallCategory.HIGH_FRICTION, StallCategory.CONFUSION]
    )
    
    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "tenant_name": self.tenant_name,
            "brand_persona": self.brand_persona.value,
            "auto_send_enabled": self.auto_send_enabled,
            "auto_send_confidence_threshold": self.auto_send_confidence_threshold,
            "review_confidence_threshold": self.review_confidence_threshold,
            "ab_test_enabled": self.ab_test_enabled,
            "ab_test_treatment_ratio": self.ab_test_treatment_ratio,
            "max_nudges_per_day": self.max_nudges_per_day,
            "cooldown_hours": self.cooldown_hours,
            "enabled_categories": [c.value for c in self.enabled_categories],
        }


@dataclass
class SendDecision:
    """Decision about whether and how to send a nudge."""
    action: SendAction
    reason: str
    nudge_text: Optional[str] = None
    confidence: Optional[float] = None
    classification_category: Optional[str] = None
    experiment_group: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "nudge_text": self.nudge_text,
            "confidence": self.confidence,
            "classification_category": self.classification_category,
            "experiment_group": self.experiment_group,
            "timestamp": self.timestamp.isoformat(),
        }


class TenantManager:
    """
    Manages multi-tenant configurations.
    
    In production, this would load from a database.
    """
    
    def __init__(self):
        self.tenants: dict[str, TenantConfig] = {}
        self._load_default_tenants()
    
    def _load_default_tenants(self):
        """Load default tenant configurations."""
        # Example tenants
        self.tenants = {
            "lemonade": TenantConfig(
                tenant_id="lemonade",
                tenant_name="Lemonade Insurance",
                brand_persona=BrandPersona.HELPFUL_NEIGHBOR,
                auto_send_enabled=True,
                auto_send_confidence_threshold=0.9,
                review_confidence_threshold=0.6,
                max_nudges_per_day=200,
            ),
            "statefarm": TenantConfig(
                tenant_id="statefarm",
                tenant_name="State Farm",
                brand_persona=BrandPersona.PROFESSIONAL_ADVISOR,
                auto_send_enabled=False,  # More conservative
                auto_send_confidence_threshold=0.95,
                review_confidence_threshold=0.8,
                max_nudges_per_day=50,
            ),
            "default": TenantConfig(
                tenant_id="default",
                tenant_name="Default Configuration",
                brand_persona=BrandPersona.HELPFUL_NEIGHBOR,
                auto_send_enabled=False,
                auto_send_confidence_threshold=0.9,
                review_confidence_threshold=0.7,
            ),
        }
    
    def get_tenant(self, tenant_id: str) -> TenantConfig:
        """Get tenant configuration."""
        return self.tenants.get(tenant_id, self.tenants["default"])
    
    def list_tenants(self) -> list[dict]:
        """List all tenant configurations."""
        return [t.to_dict() for t in self.tenants.values()]
    
    def update_tenant(self, tenant_id: str, **kwargs) -> TenantConfig:
        """Update tenant configuration."""
        if tenant_id not in self.tenants:
            raise ValueError(f"Unknown tenant: {tenant_id}")
        
        tenant = self.tenants[tenant_id]
        
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)
        
        return tenant
    
    def create_tenant(self, config: TenantConfig) -> TenantConfig:
        """Create a new tenant."""
        if config.tenant_id in self.tenants:
            raise ValueError(f"Tenant already exists: {config.tenant_id}")
        
        self.tenants[config.tenant_id] = config
        return config


class AutoSendEngine:
    """
    Engine for processing conversations and making send decisions.
    
    Implements the full pipeline:
    1. Check backend status (multi-channel awareness)
    2. Classify conversation
    3. Check A/B test assignment
    4. Apply confidence thresholds
    5. Generate nudge if appropriate
    6. Make send decision (auto, queue, or skip)
    """
    
    def __init__(self, tenant_manager: Optional[TenantManager] = None):
        self.tenant_manager = tenant_manager or TenantManager()
        self._nudge_counts: dict[str, dict[str, int]] = {}  # tenant_id -> {date -> count}
        self._user_last_nudge: dict[str, datetime] = {}  # user_id -> last nudge time
    
    def _check_rate_limits(
        self,
        tenant_id: str,
        user_id: str,
        config: TenantConfig,
    ) -> Optional[str]:
        """
        Check rate limits and cooldowns.
        
        Returns reason string if rate limited, None if OK.
        """
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        # Check daily limit for tenant
        tenant_counts = self._nudge_counts.get(tenant_id, {})
        today_count = tenant_counts.get(today, 0)
        
        if today_count >= config.max_nudges_per_day:
            return f"Daily limit reached ({config.max_nudges_per_day})"
        
        # Check user cooldown
        last_nudge = self._user_last_nudge.get(user_id)
        if last_nudge:
            cooldown = timedelta(hours=config.cooldown_hours)
            if datetime.utcnow() - last_nudge < cooldown:
                return f"User in cooldown (last nudge: {last_nudge})"
        
        return None
    
    def _record_nudge_sent(self, tenant_id: str, user_id: str):
        """Record that a nudge was sent."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        
        if tenant_id not in self._nudge_counts:
            self._nudge_counts[tenant_id] = {}
        
        self._nudge_counts[tenant_id][today] = (
            self._nudge_counts[tenant_id].get(today, 0) + 1
        )
        
        self._user_last_nudge[user_id] = datetime.utcnow()
    
    def process_conversation(
        self,
        transcript: TranscriptInput,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
    ) -> SendDecision:
        """
        Process a stalled conversation and make a send decision.
        
        Args:
            transcript: The conversation transcript
            tenant_id: The tenant/carrier ID
            user_id: The user ID (defaults to chat_id)
            
        Returns:
            SendDecision with action and details
        """
        user_id = user_id or transcript.chat_id
        config = self.tenant_manager.get_tenant(tenant_id)
        
        # Step 1: Check backend status (multi-channel awareness)
        backend_status = check_backend_status(transcript.chat_id, mock_mode=True)
        
        if not backend_status.safe_to_nudge:
            return SendDecision(
                action=SendAction.SKIP,
                reason="User active on another channel",
            )
        
        # Step 2: Check A/B test assignment
        experiment_group = None
        if config.ab_test_enabled:
            ab_manager = get_experiment_manager(
                experiment_id=f"pulse_{tenant_id}",
                treatment_ratio=config.ab_test_treatment_ratio,
            )
            group = ab_manager.get_group(transcript.chat_id)
            experiment_group = group.value
            
            if group == ExperimentGroup.CONTROL:
                return SendDecision(
                    action=SendAction.SKIP,
                    reason="A/B test control group",
                    experiment_group=experiment_group,
                )
        
        # Step 3: Classify conversation
        classification = classify_transcript(transcript)
        
        # Skip benign classifications
        if classification.category == StallCategory.BENIGN:
            return SendDecision(
                action=SendAction.SKIP,
                reason="Classification is BENIGN",
                confidence=classification.confidence,
                classification_category=classification.category.value,
                experiment_group=experiment_group,
            )
        
        # Check if category is enabled for this tenant
        if classification.category not in config.enabled_categories:
            return SendDecision(
                action=SendAction.SKIP,
                reason=f"Category {classification.category.value} not enabled for tenant",
                confidence=classification.confidence,
                classification_category=classification.category.value,
                experiment_group=experiment_group,
            )
        
        # Step 4: Apply confidence thresholds
        if classification.confidence < config.review_confidence_threshold:
            return SendDecision(
                action=SendAction.SKIP,
                reason=f"Confidence {classification.confidence:.2f} below review threshold {config.review_confidence_threshold}",
                confidence=classification.confidence,
                classification_category=classification.category.value,
                experiment_group=experiment_group,
            )
        
        # Step 5: Check rate limits
        rate_limit_reason = self._check_rate_limits(tenant_id, user_id, config)
        if rate_limit_reason:
            return SendDecision(
                action=SendAction.SKIP,
                reason=rate_limit_reason,
                confidence=classification.confidence,
                classification_category=classification.category.value,
                experiment_group=experiment_group,
            )
        
        # Step 6: Generate nudge
        nudge = generate_nudge(
            transcript,
            classification,
            config.brand_persona,
        )
        
        # Step 7: Determine action based on confidence and config
        if (
            config.auto_send_enabled and
            classification.confidence >= config.auto_send_confidence_threshold
        ):
            # Auto-send for high confidence
            self._record_nudge_sent(tenant_id, user_id)
            return SendDecision(
                action=SendAction.AUTO_SEND,
                reason=f"High confidence ({classification.confidence:.2f}) - auto-sending",
                nudge_text=nudge.nudge_text,
                confidence=classification.confidence,
                classification_category=classification.category.value,
                experiment_group=experiment_group,
            )
        else:
            # Queue for review
            return SendDecision(
                action=SendAction.QUEUE_FOR_REVIEW,
                reason=f"Confidence {classification.confidence:.2f} - queuing for review",
                nudge_text=nudge.nudge_text,
                confidence=classification.confidence,
                classification_category=classification.category.value,
                experiment_group=experiment_group,
            )
    
    def get_tenant_stats(self, tenant_id: str) -> dict:
        """Get statistics for a tenant."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        tenant_counts = self._nudge_counts.get(tenant_id, {})
        
        return {
            "tenant_id": tenant_id,
            "nudges_today": tenant_counts.get(today, 0),
            "nudges_by_date": tenant_counts,
        }


# Singleton instances
_tenant_manager: Optional[TenantManager] = None
_auto_send_engine: Optional[AutoSendEngine] = None


def get_tenant_manager() -> TenantManager:
    """Get or create tenant manager singleton."""
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager


def get_auto_send_engine() -> AutoSendEngine:
    """Get or create auto-send engine singleton."""
    global _auto_send_engine
    if _auto_send_engine is None:
        _auto_send_engine = AutoSendEngine(get_tenant_manager())
    return _auto_send_engine


# CLI testing
if __name__ == "__main__":
    from .models import Message, MessageRole
    
    # Create test transcript
    transcript = TranscriptInput(
        chat_id="test-001",
        history=[
            Message(role=MessageRole.BOT, text="I need your VIN to get a quote."),
            Message(role=MessageRole.USER, text="I'm at work, don't have it on me."),
            Message(role=MessageRole.BOT, text="You can find it on your registration."),
        ]
    )
    
    # Test with different tenants
    engine = get_auto_send_engine()
    
    print("=" * 60)
    print("AUTO-SEND ENGINE TEST")
    print("=" * 60)
    
    for tenant_id in ["lemonade", "statefarm", "default"]:
        print(f"\n--- Testing with tenant: {tenant_id} ---")
        config = get_tenant_manager().get_tenant(tenant_id)
        print(f"Auto-send enabled: {config.auto_send_enabled}")
        print(f"Confidence threshold: {config.auto_send_confidence_threshold}")
        print(f"Brand persona: {config.brand_persona.value}")
        
        decision = engine.process_conversation(transcript, tenant_id)
        print(f"\nDecision: {decision.action.value}")
        print(f"Reason: {decision.reason}")
        if decision.nudge_text:
            print(f"Nudge: \"{decision.nudge_text}\"")
        print()
