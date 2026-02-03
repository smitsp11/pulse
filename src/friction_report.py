"""
Friction Heatmap Report Generator.

Analyzes classification results to identify which bot questions
cause the most user friction/drop-off.

This report delivers immediate product value even before nudges
are automated - it acts as a "debugger for your conversation flow."
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import json

from .models import (
    TranscriptInput,
    ClassificationResult,
    StallCategory,
    StallStatus,
)


@dataclass
class FrictionPoint:
    """A bot question that causes friction."""
    bot_question: str
    total_occurrences: int
    friction_count: int
    benign_count: int
    friction_rate: float
    categories: dict[str, int]  # Category -> count
    sample_chat_ids: list[str]


@dataclass
class FrictionReport:
    """Complete friction analysis report."""
    generated_at: datetime
    total_conversations: int
    total_friction: int
    total_benign: int
    overall_friction_rate: float
    top_friction_points: list[FrictionPoint]
    by_category: dict[str, int]
    by_status: dict[str, int]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "total_conversations": self.total_conversations,
            "total_friction": self.total_friction,
            "total_benign": self.total_benign,
            "overall_friction_rate": self.overall_friction_rate,
            "top_friction_points": [
                {
                    "bot_question": fp.bot_question,
                    "total_occurrences": fp.total_occurrences,
                    "friction_count": fp.friction_count,
                    "benign_count": fp.benign_count,
                    "friction_rate": fp.friction_rate,
                    "categories": fp.categories,
                    "sample_chat_ids": fp.sample_chat_ids[:5],  # Limit samples
                }
                for fp in self.top_friction_points
            ],
            "by_category": self.by_category,
            "by_status": self.by_status,
        }


def extract_bot_question(transcript: TranscriptInput) -> Optional[str]:
    """Extract the last bot message (question) from a transcript."""
    for msg in reversed(transcript.history):
        if msg.role.value == "bot":
            return msg.text
    return None


def normalize_question(question: str) -> str:
    """
    Normalize a question for grouping similar questions.
    
    This helps group questions that are semantically similar but
    have slight wording variations.
    """
    # Simple normalization - lowercase and remove extra whitespace
    normalized = " ".join(question.lower().split())
    
    # Could add more sophisticated normalization:
    # - Remove names/personalization
    # - Identify question types (VIN request, photo request, etc.)
    
    return normalized


def identify_question_type(question: str) -> str:
    """Identify the type of question for higher-level aggregation."""
    question_lower = question.lower()
    
    if "vin" in question_lower:
        return "VIN Request"
    elif "license" in question_lower and ("driver" in question_lower or "dl" in question_lower):
        return "Driver's License Request"
    elif "photo" in question_lower or "upload" in question_lower or "picture" in question_lower:
        return "Photo/Document Upload"
    elif "ssn" in question_lower or "social security" in question_lower:
        return "SSN Request"
    elif any(term in question_lower for term in ["deductible", "coverage", "premium", "liability"]):
        return "Coverage/Insurance Terms"
    elif "address" in question_lower:
        return "Address Request"
    elif "date" in question_lower and "birth" in question_lower:
        return "DOB Request"
    elif "spouse" in question_lower or "husband" in question_lower or "wife" in question_lower:
        return "Spouse Information"
    else:
        return "Other"


def generate_friction_report(
    transcripts: list[TranscriptInput],
    classifications: list[ClassificationResult],
    min_occurrences: int = 2,
    top_n: int = 10,
) -> FrictionReport:
    """
    Generate a friction analysis report from classification results.
    
    Args:
        transcripts: List of conversation transcripts
        classifications: Corresponding classification results
        min_occurrences: Minimum occurrences for a question to be included
        top_n: Number of top friction points to include
        
    Returns:
        FrictionReport with aggregated analysis
    """
    # Build mapping of chat_id to transcript
    transcript_map = {t.chat_id: t for t in transcripts}
    
    # Group by bot question
    by_question: dict[str, list[tuple[TranscriptInput, ClassificationResult]]] = defaultdict(list)
    
    for classification in classifications:
        transcript = transcript_map.get(classification.chat_id)
        if transcript:
            bot_question = extract_bot_question(transcript)
            if bot_question:
                # Use normalized question for grouping
                normalized = normalize_question(bot_question)
                by_question[normalized].append((transcript, classification))
    
    # Calculate friction rates
    friction_points = []
    total_friction = 0
    total_benign = 0
    by_category = defaultdict(int)
    by_status = defaultdict(int)
    
    for normalized_question, items in by_question.items():
        if len(items) < min_occurrences:
            continue
        
        # Get original question text (use first occurrence)
        original_question = extract_bot_question(items[0][0])
        
        friction_count = 0
        benign_count = 0
        categories = defaultdict(int)
        chat_ids = []
        
        for transcript, classification in items:
            chat_ids.append(classification.chat_id)
            categories[classification.category.value] += 1
            by_category[classification.category.value] += 1
            by_status[classification.status.value] += 1
            
            if classification.category != StallCategory.BENIGN:
                friction_count += 1
                total_friction += 1
            else:
                benign_count += 1
                total_benign += 1
        
        friction_rate = friction_count / len(items) if items else 0
        
        friction_points.append(FrictionPoint(
            bot_question=original_question or normalized_question,
            total_occurrences=len(items),
            friction_count=friction_count,
            benign_count=benign_count,
            friction_rate=friction_rate,
            categories=dict(categories),
            sample_chat_ids=chat_ids,
        ))
    
    # Sort by friction rate (descending)
    friction_points.sort(key=lambda x: (-x.friction_rate, -x.total_occurrences))
    
    total_conversations = len(classifications)
    overall_friction_rate = total_friction / total_conversations if total_conversations > 0 else 0
    
    return FrictionReport(
        generated_at=datetime.utcnow(),
        total_conversations=total_conversations,
        total_friction=total_friction,
        total_benign=total_benign,
        overall_friction_rate=overall_friction_rate,
        top_friction_points=friction_points[:top_n],
        by_category=dict(by_category),
        by_status=dict(by_status),
    )


def generate_friction_report_by_type(
    transcripts: list[TranscriptInput],
    classifications: list[ClassificationResult],
) -> dict[str, dict]:
    """
    Generate friction report aggregated by question type.
    
    This provides higher-level insights like "VIN requests cause 78% friction"
    rather than specific question wording.
    """
    # Build mapping
    transcript_map = {t.chat_id: t for t in transcripts}
    
    by_type: dict[str, dict] = defaultdict(lambda: {
        "total": 0,
        "friction": 0,
        "benign": 0,
        "questions": set(),
    })
    
    for classification in classifications:
        transcript = transcript_map.get(classification.chat_id)
        if transcript:
            bot_question = extract_bot_question(transcript)
            if bot_question:
                question_type = identify_question_type(bot_question)
                by_type[question_type]["total"] += 1
                by_type[question_type]["questions"].add(bot_question)
                
                if classification.category != StallCategory.BENIGN:
                    by_type[question_type]["friction"] += 1
                else:
                    by_type[question_type]["benign"] += 1
    
    # Calculate rates and convert sets to lists
    result = {}
    for qtype, data in by_type.items():
        result[qtype] = {
            "total": data["total"],
            "friction": data["friction"],
            "benign": data["benign"],
            "friction_rate": data["friction"] / data["total"] if data["total"] > 0 else 0,
            "example_questions": list(data["questions"])[:3],
        }
    
    return result


def print_friction_report(report: FrictionReport, show_samples: bool = False):
    """Print a formatted friction report to console."""
    print("\n" + "=" * 60)
    print("FRICTION HEATMAP REPORT")
    print("=" * 60)
    print(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"\nTotal Conversations Analyzed: {report.total_conversations}")
    print(f"Total Friction (non-benign): {report.total_friction} ({report.overall_friction_rate*100:.1f}%)")
    print(f"Total Benign: {report.total_benign}")
    
    print("\n" + "-" * 60)
    print("BY CATEGORY:")
    print("-" * 60)
    for category, count in sorted(report.by_category.items()):
        pct = count / report.total_conversations * 100 if report.total_conversations > 0 else 0
        print(f"  {category}: {count} ({pct:.1f}%)")
    
    print("\n" + "-" * 60)
    print("TOP FRICTION POINTS (Bot Questions Causing Drop-off):")
    print("-" * 60)
    
    if not report.top_friction_points:
        print("  No friction points found (need more data)")
        return
    
    # Table header
    print(f"\n{'Bot Question':<45} | {'Stalls':>6} | {'Rate':>6}")
    print("-" * 65)
    
    for fp in report.top_friction_points:
        # Truncate long questions
        question = fp.bot_question[:42] + "..." if len(fp.bot_question) > 45 else fp.bot_question
        print(f"{question:<45} | {fp.total_occurrences:>6} | {fp.friction_rate*100:>5.1f}%")
        
        if show_samples and fp.sample_chat_ids:
            print(f"  └─ Samples: {', '.join(fp.sample_chat_ids[:3])}")
    
    print("\n" + "=" * 60)
    print("ACTIONABLE INSIGHTS:")
    print("=" * 60)
    
    if report.top_friction_points:
        top = report.top_friction_points[0]
        print(f"\n🎯 Top Issue: \"{top.bot_question[:50]}...\"")
        print(f"   This question causes {top.friction_rate*100:.0f}% of users to stall.")
        print(f"   Consider: Offering alternatives, simplifying the ask, or making it optional.")
    
    print()


# CLI interface
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Add parent to path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    from src.models import Message, MessageRole
    
    # Create sample data for demonstration
    sample_transcripts = [
        TranscriptInput(
            chat_id=f"demo-{i}",
            history=[
                Message(role=MessageRole.BOT, text="I need your VIN to get a quote."),
                Message(role=MessageRole.USER, text="I don't have it with me."),
            ]
        )
        for i in range(5)
    ] + [
        TranscriptInput(
            chat_id=f"demo-{i}",
            history=[
                Message(role=MessageRole.BOT, text="What's your zip code?"),
                Message(role=MessageRole.USER, text="90210"),
            ]
        )
        for i in range(5, 8)
    ]
    
    sample_classifications = [
        ClassificationResult(
            chat_id=f"demo-{i}",
            status=StallStatus.STALLED_HIGH_RISK,
            category=StallCategory.HIGH_FRICTION,
            reason="HIGH_FRICTION:VIN_REQUEST",
            confidence=0.9,
            evidence="User said they don't have it",
        )
        for i in range(5)
    ] + [
        ClassificationResult(
            chat_id=f"demo-{i}",
            status=StallStatus.BENIGN,
            category=StallCategory.BENIGN,
            reason="BENIGN",
            confidence=0.8,
            evidence="Normal conversation flow",
        )
        for i in range(5, 8)
    ]
    
    report = generate_friction_report(sample_transcripts, sample_classifications, min_occurrences=1)
    print_friction_report(report, show_samples=True)
