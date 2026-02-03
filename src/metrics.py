"""
Metrics and analytics for Pulse.

Provides:
- Classification performance metrics
- Nudge performance metrics
- A/B test analysis
- Operational health metrics
"""

from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from collections import defaultdict

from .models import (
    ClassificationResult,
    NudgeResult,
    ReviewedNudge,
    ReviewDecision,
    StallCategory,
)
from .database import get_database


@dataclass
class ClassificationMetrics:
    """Classification performance metrics."""
    total: int = 0
    by_category: dict[str, int] = None
    by_status: dict[str, int] = None
    avg_confidence: float = 0.0
    avg_latency_ms: float = 0.0
    
    def __post_init__(self):
        if self.by_category is None:
            self.by_category = {}
        if self.by_status is None:
            self.by_status = {}
    
    @property
    def non_benign_rate(self) -> float:
        """Percentage of classifications that are non-benign."""
        if self.total == 0:
            return 0
        benign = self.by_category.get("BENIGN", 0)
        return (self.total - benign) / self.total
    
    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "by_category": self.by_category,
            "by_status": self.by_status,
            "avg_confidence": self.avg_confidence,
            "avg_latency_ms": self.avg_latency_ms,
            "non_benign_rate": self.non_benign_rate,
        }


@dataclass
class NudgeMetrics:
    """Nudge generation and performance metrics."""
    total_generated: int = 0
    total_reviewed: int = 0
    approved: int = 0
    edited: int = 0
    rejected: int = 0
    avg_review_time_seconds: float = 0.0
    by_brand_persona: dict[str, int] = None
    by_category: dict[str, int] = None
    
    def __post_init__(self):
        if self.by_brand_persona is None:
            self.by_brand_persona = {}
        if self.by_category is None:
            self.by_category = {}
    
    @property
    def approval_rate(self) -> float:
        """Percentage of reviewed nudges that were approved (without edits)."""
        if self.total_reviewed == 0:
            return 0
        return self.approved / self.total_reviewed
    
    @property
    def acceptance_rate(self) -> float:
        """Percentage of reviewed nudges that were approved or edited (not rejected)."""
        if self.total_reviewed == 0:
            return 0
        return (self.approved + self.edited) / self.total_reviewed
    
    @property
    def rejection_rate(self) -> float:
        """Percentage of reviewed nudges that were rejected."""
        if self.total_reviewed == 0:
            return 0
        return self.rejected / self.total_reviewed
    
    def to_dict(self) -> dict:
        return {
            "total_generated": self.total_generated,
            "total_reviewed": self.total_reviewed,
            "approved": self.approved,
            "edited": self.edited,
            "rejected": self.rejected,
            "approval_rate": self.approval_rate,
            "acceptance_rate": self.acceptance_rate,
            "rejection_rate": self.rejection_rate,
            "avg_review_time_seconds": self.avg_review_time_seconds,
            "by_brand_persona": self.by_brand_persona,
            "by_category": self.by_category,
        }


@dataclass
class ResurrectionMetrics:
    """Metrics for conversation resurrection (Phase 3+)."""
    total_nudges_sent: int = 0
    total_responses: int = 0
    avg_response_time_hours: float = 0.0
    response_rate: float = 0.0
    by_category: dict[str, dict] = None
    
    def __post_init__(self):
        if self.by_category is None:
            self.by_category = {}
    
    def to_dict(self) -> dict:
        return {
            "total_nudges_sent": self.total_nudges_sent,
            "total_responses": self.total_responses,
            "response_rate": self.response_rate,
            "avg_response_time_hours": self.avg_response_time_hours,
            "by_category": self.by_category,
        }


class MetricsCollector:
    """
    Collects and computes metrics from database.
    """
    
    def __init__(self, db_path: str = "data/pulse.db"):
        self.db = get_database(db_path)
    
    def get_classification_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> ClassificationMetrics:
        """Get classification metrics for a date range."""
        stats = self.db.get_classification_stats()
        
        return ClassificationMetrics(
            total=stats.get("total", 0),
            by_category=stats.get("by_category", {}),
            by_status=stats.get("by_status", {}),
            avg_confidence=stats.get("avg_confidence", 0),
        )
    
    def get_nudge_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> NudgeMetrics:
        """Get nudge metrics for a date range."""
        review_stats = self.db.get_review_stats()
        
        return NudgeMetrics(
            total_reviewed=review_stats.get("total", 0),
            approved=review_stats.get("approved", 0),
            edited=review_stats.get("edited", 0),
            rejected=review_stats.get("rejected", 0),
            avg_review_time_seconds=review_stats.get("avg_review_time", 0),
        )
    
    def get_dashboard_summary(self) -> dict:
        """Get a summary of all metrics for dashboard display."""
        classification = self.get_classification_metrics()
        nudge = self.get_nudge_metrics()
        
        return {
            "classification": classification.to_dict(),
            "nudge": nudge.to_dict(),
            "health": {
                "status": "healthy",
                "last_updated": datetime.utcnow().isoformat(),
            },
        }
    
    def get_friction_heatmap_data(self) -> dict:
        """Get data for friction heatmap visualization."""
        # This would query the database for aggregated friction data
        # For now, return structure that the frontend expects
        return {
            "by_question_type": {},
            "by_category": {},
            "top_friction_points": [],
        }


class ExitCriteriaChecker:
    """
    Checks exit criteria for each phase.
    
    Based on the execution plan:
    - Phase 1: 50+ transcripts, >80% accuracy, >25% non-benign
    - Phase 2: 100+ nudges, >70% approval, <30s review time
    - Phase 3: 500+ stalls, 2x response rate, no opt-out increase
    - Phase 4: >50% auto-send, sustained resurrection rate
    """
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics = metrics_collector
    
    def check_phase1(self) -> dict:
        """Check Phase 1 exit criteria."""
        class_metrics = self.metrics.get_classification_metrics()
        
        criteria = {
            "transcripts_classified": {
                "target": 50,
                "actual": class_metrics.total,
                "met": class_metrics.total >= 50,
            },
            "accuracy": {
                "target": 0.80,
                "actual": None,  # Requires human evaluation
                "met": None,
            },
            "non_benign_rate": {
                "target": 0.25,
                "actual": class_metrics.non_benign_rate,
                "met": class_metrics.non_benign_rate >= 0.25,
            },
        }
        
        return {
            "phase": 1,
            "criteria": criteria,
            "all_met": all(
                c["met"] for c in criteria.values() 
                if c["met"] is not None
            ),
        }
    
    def check_phase2(self) -> dict:
        """Check Phase 2 exit criteria."""
        nudge_metrics = self.metrics.get_nudge_metrics()
        
        criteria = {
            "nudges_reviewed": {
                "target": 100,
                "actual": nudge_metrics.total_reviewed,
                "met": nudge_metrics.total_reviewed >= 100,
            },
            "approval_rate": {
                "target": 0.70,
                "actual": nudge_metrics.approval_rate,
                "met": nudge_metrics.approval_rate >= 0.70,
            },
            "avg_review_time": {
                "target": 30,  # seconds
                "actual": nudge_metrics.avg_review_time_seconds,
                "met": nudge_metrics.avg_review_time_seconds <= 30,
            },
        }
        
        return {
            "phase": 2,
            "criteria": criteria,
            "all_met": all(c["met"] for c in criteria.values()),
        }
    
    def check_phase3(self) -> dict:
        """Check Phase 3 exit criteria."""
        # These require A/B test data which isn't available yet
        return {
            "phase": 3,
            "criteria": {
                "stalls_processed": {
                    "target": 500,
                    "actual": 0,
                    "met": False,
                },
                "resurrection_lift": {
                    "target": 2.0,  # 2x response rate
                    "actual": None,
                    "met": None,
                },
                "opt_out_rate": {
                    "target": "no increase",
                    "actual": None,
                    "met": None,
                },
            },
            "all_met": False,
        }
    
    def check_all_phases(self) -> dict:
        """Check exit criteria for all phases."""
        return {
            "phase1": self.check_phase1(),
            "phase2": self.check_phase2(),
            "phase3": self.check_phase3(),
            "current_phase": self._determine_current_phase(),
        }
    
    def _determine_current_phase(self) -> int:
        """Determine which phase we're currently in."""
        p1 = self.check_phase1()
        if not p1["all_met"]:
            return 1
        
        p2 = self.check_phase2()
        if not p2["all_met"]:
            return 2
        
        p3 = self.check_phase3()
        if not p3["all_met"]:
            return 3
        
        return 4


# Convenience functions
def get_metrics_collector(db_path: str = "data/pulse.db") -> MetricsCollector:
    """Get metrics collector instance."""
    return MetricsCollector(db_path)


def get_exit_criteria_checker(db_path: str = "data/pulse.db") -> ExitCriteriaChecker:
    """Get exit criteria checker instance."""
    return ExitCriteriaChecker(get_metrics_collector(db_path))


if __name__ == "__main__":
    # Test metrics collection
    collector = get_metrics_collector()
    
    print("=" * 60)
    print("PULSE METRICS DASHBOARD")
    print("=" * 60)
    
    summary = collector.get_dashboard_summary()
    
    print("\nClassification Metrics:")
    for key, value in summary["classification"].items():
        print(f"  {key}: {value}")
    
    print("\nNudge Metrics:")
    for key, value in summary["nudge"].items():
        print(f"  {key}: {value}")
    
    # Check exit criteria
    checker = get_exit_criteria_checker()
    criteria = checker.check_all_phases()
    
    print("\n" + "=" * 60)
    print("EXIT CRITERIA STATUS")
    print("=" * 60)
    print(f"Current Phase: {criteria['current_phase']}")
    
    for phase_key in ["phase1", "phase2", "phase3"]:
        phase = criteria[phase_key]
        status = "✓" if phase["all_met"] else "○"
        print(f"\n{status} Phase {phase['phase']}:")
        for name, c in phase["criteria"].items():
            met = "✓" if c["met"] else "✗" if c["met"] is False else "?"
            print(f"    [{met}] {name}: {c['actual']} (target: {c['target']})")
