"""
A/B Testing infrastructure for Pulse experiments.

Provides controlled experiments to measure the impact of nudges
on user response rates.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict

from .models import NudgeResult, ClassificationResult


class ExperimentGroup(str, Enum):
    """Experiment group assignments."""
    CONTROL = "control"  # No nudge sent
    TREATMENT = "treatment"  # Nudge sent


@dataclass
class ExperimentOutcome:
    """Outcome for a single conversation in an experiment."""
    chat_id: str
    group: ExperimentGroup
    nudge_sent: bool
    user_responded: bool
    response_time_seconds: Optional[float] = None
    classification_category: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExperimentResults:
    """Aggregated results for an experiment."""
    experiment_id: str
    start_date: datetime
    end_date: Optional[datetime]
    
    # Sample sizes
    control_count: int = 0
    treatment_count: int = 0
    
    # Response rates
    control_responses: int = 0
    treatment_responses: int = 0
    
    # Computed metrics
    @property
    def control_response_rate(self) -> float:
        return self.control_responses / self.control_count if self.control_count > 0 else 0
    
    @property
    def treatment_response_rate(self) -> float:
        return self.treatment_responses / self.treatment_count if self.treatment_count > 0 else 0
    
    @property
    def lift(self) -> float:
        """Relative improvement from treatment."""
        if self.control_response_rate == 0:
            return 0
        return (self.treatment_response_rate - self.control_response_rate) / self.control_response_rate
    
    @property
    def is_significant(self) -> bool:
        """
        Check if results are statistically significant.
        
        Simple approximation using sample sizes.
        For production, use proper statistical tests.
        """
        min_samples = 100
        return (
            self.control_count >= min_samples and
            self.treatment_count >= min_samples
        )
    
    def to_dict(self) -> dict:
        return {
            "experiment_id": self.experiment_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "control": {
                "count": self.control_count,
                "responses": self.control_responses,
                "response_rate": self.control_response_rate,
            },
            "treatment": {
                "count": self.treatment_count,
                "responses": self.treatment_responses,
                "response_rate": self.treatment_response_rate,
            },
            "lift": self.lift,
            "is_significant": self.is_significant,
        }


class ABTestManager:
    """
    Manages A/B testing for Pulse experiments.
    
    Features:
    - Deterministic group assignment (same chat always gets same group)
    - Configurable treatment ratios
    - Outcome tracking and analysis
    """
    
    def __init__(
        self,
        experiment_id: str = "pulse_nudge_v1",
        treatment_ratio: float = 0.5,
        enabled: bool = True,
    ):
        """
        Initialize A/B test manager.
        
        Args:
            experiment_id: Unique identifier for this experiment
            treatment_ratio: Fraction of traffic to send to treatment (0-1)
            enabled: Whether A/B testing is enabled
        """
        self.experiment_id = experiment_id
        self.treatment_ratio = treatment_ratio
        self.enabled = enabled
        
        # In-memory outcome storage (use database in production)
        self.outcomes: list[ExperimentOutcome] = []
        self.start_date = datetime.utcnow()
    
    def get_group(self, chat_id: str) -> ExperimentGroup:
        """
        Deterministically assign a chat to an experiment group.
        
        Uses hash of chat_id + experiment_id for consistent assignment.
        The same chat_id will always get the same group within an experiment.
        
        Args:
            chat_id: The conversation ID
            
        Returns:
            ExperimentGroup.CONTROL or ExperimentGroup.TREATMENT
        """
        if not self.enabled:
            return ExperimentGroup.TREATMENT
        
        # Create deterministic hash
        hash_input = f"{self.experiment_id}:{chat_id}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        
        # Map to 0-1 range and compare to treatment ratio
        normalized = (hash_val % 10000) / 10000
        
        if normalized < self.treatment_ratio:
            return ExperimentGroup.TREATMENT
        return ExperimentGroup.CONTROL
    
    def record_outcome(
        self,
        chat_id: str,
        group: ExperimentGroup,
        nudge_sent: bool,
        user_responded: bool,
        response_time_seconds: Optional[float] = None,
        classification_category: Optional[str] = None,
    ):
        """
        Record the outcome for a conversation.
        
        Args:
            chat_id: The conversation ID
            group: The experiment group
            nudge_sent: Whether a nudge was sent
            user_responded: Whether the user responded
            response_time_seconds: Time to response (if responded)
            classification_category: The classification category
        """
        outcome = ExperimentOutcome(
            chat_id=chat_id,
            group=group,
            nudge_sent=nudge_sent,
            user_responded=user_responded,
            response_time_seconds=response_time_seconds,
            classification_category=classification_category,
        )
        self.outcomes.append(outcome)
    
    def get_results(self) -> ExperimentResults:
        """
        Get aggregated experiment results.
        
        Returns:
            ExperimentResults with metrics
        """
        results = ExperimentResults(
            experiment_id=self.experiment_id,
            start_date=self.start_date,
            end_date=datetime.utcnow(),
        )
        
        for outcome in self.outcomes:
            if outcome.group == ExperimentGroup.CONTROL:
                results.control_count += 1
                if outcome.user_responded:
                    results.control_responses += 1
            else:
                results.treatment_count += 1
                if outcome.user_responded:
                    results.treatment_responses += 1
        
        return results
    
    def get_results_by_category(self) -> dict[str, ExperimentResults]:
        """
        Get experiment results broken down by classification category.
        
        Returns:
            Dictionary mapping category to ExperimentResults
        """
        by_category: dict[str, ExperimentResults] = {}
        
        for outcome in self.outcomes:
            category = outcome.classification_category or "UNKNOWN"
            
            if category not in by_category:
                by_category[category] = ExperimentResults(
                    experiment_id=f"{self.experiment_id}_{category}",
                    start_date=self.start_date,
                    end_date=datetime.utcnow(),
                )
            
            results = by_category[category]
            
            if outcome.group == ExperimentGroup.CONTROL:
                results.control_count += 1
                if outcome.user_responded:
                    results.control_responses += 1
            else:
                results.treatment_count += 1
                if outcome.user_responded:
                    results.treatment_responses += 1
        
        return by_category
    
    def should_continue_experiment(self, min_samples: int = 500) -> bool:
        """
        Check if experiment should continue.
        
        Args:
            min_samples: Minimum samples needed per group
            
        Returns:
            True if more samples needed
        """
        results = self.get_results()
        return (
            results.control_count < min_samples or
            results.treatment_count < min_samples
        )
    
    def get_recommended_action(self) -> str:
        """
        Get recommended action based on results.
        
        Returns:
            Recommendation string
        """
        results = self.get_results()
        
        if not results.is_significant:
            return f"Continue experiment - need more samples (control: {results.control_count}, treatment: {results.treatment_count})"
        
        if results.lift > 0.5:  # >50% lift
            return f"Strong positive signal! Treatment shows {results.lift:.0%} lift. Consider rolling out."
        elif results.lift > 0.1:  # >10% lift
            return f"Moderate positive signal. Treatment shows {results.lift:.0%} lift. Continue monitoring."
        elif results.lift < -0.1:  # <-10% lift
            return f"Negative signal! Treatment shows {results.lift:.0%} change. Consider stopping."
        else:
            return f"No significant difference detected ({results.lift:.0%} lift)."


# Global experiment manager instance
_experiment_manager: Optional[ABTestManager] = None


def get_experiment_manager(
    experiment_id: str = "pulse_nudge_v1",
    treatment_ratio: float = 0.5,
) -> ABTestManager:
    """Get or create experiment manager singleton."""
    global _experiment_manager
    
    if _experiment_manager is None:
        _experiment_manager = ABTestManager(
            experiment_id=experiment_id,
            treatment_ratio=treatment_ratio,
        )
    
    return _experiment_manager


# Example usage and testing
if __name__ == "__main__":
    import random
    
    # Create experiment
    manager = ABTestManager(
        experiment_id="test_experiment",
        treatment_ratio=0.5,
    )
    
    # Simulate 200 conversations
    print("Simulating A/B test with 200 conversations...\n")
    
    for i in range(200):
        chat_id = f"chat-{i:04d}"
        group = manager.get_group(chat_id)
        
        # Simulate different response rates
        # Treatment has higher response rate (this is what we'd hope to see)
        if group == ExperimentGroup.TREATMENT:
            response_prob = 0.35  # 35% response rate with nudge
        else:
            response_prob = 0.15  # 15% response rate without nudge
        
        responded = random.random() < response_prob
        
        manager.record_outcome(
            chat_id=chat_id,
            group=group,
            nudge_sent=(group == ExperimentGroup.TREATMENT),
            user_responded=responded,
            classification_category=random.choice(["HIGH_FRICTION", "CONFUSION"]),
        )
    
    # Print results
    results = manager.get_results()
    print("=" * 50)
    print("EXPERIMENT RESULTS")
    print("=" * 50)
    print(f"Experiment: {results.experiment_id}")
    print(f"\nControl Group:")
    print(f"  Sample size: {results.control_count}")
    print(f"  Responses: {results.control_responses}")
    print(f"  Response rate: {results.control_response_rate:.1%}")
    print(f"\nTreatment Group:")
    print(f"  Sample size: {results.treatment_count}")
    print(f"  Responses: {results.treatment_responses}")
    print(f"  Response rate: {results.treatment_response_rate:.1%}")
    print(f"\nLift: {results.lift:.0%}")
    print(f"Statistically significant: {results.is_significant}")
    print(f"\nRecommendation: {manager.get_recommended_action()}")
