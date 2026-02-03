#!/usr/bin/env python3
"""
Batch Pre-computation Script for Pulse Demo

This script processes all sample transcripts and saves the results to
a JSON file that can be loaded instantly during the demo.

Usage:
    python scripts/batch_precompute.py [--live]

Options:
    --live    Use real API calls (default is mock mode for testing)

The script will:
1. Load all transcripts from data/sample_transcripts.json and data/sample_transcripts_extended.json
2. Classify each transcript (with rate limiting if using live API)
3. Generate friction analysis
4. Save results to data/friction_data.json
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import (
    TranscriptInput,
    Message,
    MessageRole,
    StallCategory,
    StallStatus,
)

# Default to mock mode for safety
USE_LIVE_API = "--live" in sys.argv

# Rate limiting for live API (Gemini free tier: ~60 requests/minute)
DELAY_BETWEEN_REQUESTS = 2.0 if USE_LIVE_API else 0.0


def load_all_transcripts() -> list[dict]:
    """Load all transcripts from data files."""
    transcripts = []
    
    data_files = [
        Path("data/sample_transcripts.json"),
        Path("data/sample_transcripts_extended.json"),
    ]
    
    for filepath in data_files:
        if filepath.exists():
            with open(filepath, "r") as f:
                data = json.load(f)
                transcripts.extend(data.get("transcripts", []))
            print(f"  Loaded {len(data.get('transcripts', []))} transcripts from {filepath}")
        else:
            print(f"  Warning: {filepath} not found")
    
    return transcripts


def detect_question_type(bot_message: str) -> str:
    """Detect the type of question being asked."""
    text = bot_message.lower()
    
    if "vin" in text:
        return "VIN_REQUEST"
    elif "license" in text or "driver's license" in text or "dl" in text:
        return "LICENSE_REQUEST"
    elif "photo" in text or "upload" in text or "picture" in text or "image" in text:
        return "DOCUMENT_UPLOAD"
    elif "social" in text or "ssn" in text or "security number" in text:
        return "SSN_REQUEST"
    elif "bank" in text or "routing" in text or "account" in text:
        return "BANKING_INFO"
    elif any(term in text for term in ["um/uim", "pip", "bi/pd", "csl", "tort", "plup"]):
        return "INSURANCE_JARGON"
    elif "deductible" in text or "coverage" in text or "premium" in text:
        return "COVERAGE_QUESTION"
    elif "odometer" in text or "mileage" in text:
        return "MILEAGE_REQUEST"
    elif "date" in text and ("birth" in text or "effective" in text or "purchase" in text):
        return "DATE_REQUEST"
    elif "address" in text:
        return "ADDRESS_REQUEST"
    else:
        return "OTHER"


def mock_classify(transcript_data: dict) -> dict:
    """Mock classification based on expected category."""
    expected = transcript_data.get("expected_category", "BENIGN")
    
    confidence_map = {
        "HIGH_FRICTION": 0.92,
        "CONFUSION": 0.85,
        "BENIGN": 0.70,
    }
    
    status_map = {
        "HIGH_FRICTION": "STALLED_HIGH_RISK",
        "CONFUSION": "STALLED_LOW_RISK",
        "BENIGN": "BENIGN",
    }
    
    # Get last bot message for evidence
    last_bot_msg = ""
    last_user_msg = ""
    for msg in transcript_data["history"]:
        if msg["role"] == "bot":
            last_bot_msg = msg["text"]
        else:
            last_user_msg = msg["text"]
    
    return {
        "chat_id": transcript_data["chat_id"],
        "status": status_map.get(expected, "BENIGN"),
        "category": expected,
        "reason": f"{expected}:{detect_question_type(last_bot_msg)}" if expected == "HIGH_FRICTION" else expected,
        "confidence": confidence_map.get(expected, 0.7),
        "evidence": f"User said: '{last_user_msg[:50]}...'" if len(last_user_msg) > 50 else f"User said: '{last_user_msg}'",
        "question_type": detect_question_type(last_bot_msg),
    }


def live_classify(transcript_data: dict) -> dict:
    """Classify using real API."""
    from src.classifier import classify_transcript
    
    transcript = TranscriptInput(
        chat_id=transcript_data["chat_id"],
        history=[
            Message(role=MessageRole(m["role"]), text=m["text"])
            for m in transcript_data["history"]
        ]
    )
    
    result = classify_transcript(transcript)
    
    # Get last bot message for question type
    last_bot_msg = ""
    for msg in transcript_data["history"]:
        if msg["role"] == "bot":
            last_bot_msg = msg["text"]
    
    return {
        "chat_id": result.chat_id,
        "status": result.status.value,
        "category": result.category.value,
        "reason": result.reason,
        "confidence": result.confidence,
        "evidence": result.evidence,
        "question_type": detect_question_type(last_bot_msg),
    }


def generate_friction_analysis(classifications: list[dict], transcripts: list[dict]) -> dict:
    """Generate comprehensive friction analysis."""
    
    # Summary stats
    total = len(classifications)
    by_category = defaultdict(int)
    by_status = defaultdict(int)
    by_question_type = defaultdict(lambda: {"total": 0, "friction_count": 0})
    
    friction_points = defaultdict(lambda: {"count": 0, "friction_count": 0, "examples": []})
    
    for i, result in enumerate(classifications):
        by_category[result["category"]] += 1
        by_status[result["status"]] += 1
        
        q_type = result.get("question_type", "OTHER")
        by_question_type[q_type]["total"] += 1
        
        if result["category"] in ["HIGH_FRICTION", "CONFUSION"]:
            by_question_type[q_type]["friction_count"] += 1
        
        # Track specific bot questions
        if i < len(transcripts):
            for msg in transcripts[i]["history"]:
                if msg["role"] == "bot":
                    last_bot = msg["text"]
            
            # Normalize the question
            normalized = last_bot[:100] if len(last_bot) > 100 else last_bot
            friction_points[normalized]["count"] += 1
            
            if result["category"] in ["HIGH_FRICTION", "CONFUSION"]:
                friction_points[normalized]["friction_count"] += 1
                friction_points[normalized]["examples"].append({
                    "chat_id": result["chat_id"],
                    "user_response": transcripts[i]["history"][-1]["text"] if transcripts[i]["history"][-1]["role"] == "user" else "No response",
                })
    
    # Calculate friction rates
    friction_count = by_category.get("HIGH_FRICTION", 0) + by_category.get("CONFUSION", 0)
    friction_rate = friction_count / total if total > 0 else 0
    
    for q_type in by_question_type:
        t = by_question_type[q_type]["total"]
        f = by_question_type[q_type]["friction_count"]
        by_question_type[q_type]["friction_rate"] = f / t if t > 0 else 0
    
    # Sort friction points by rate
    top_friction_points = []
    for question, data in friction_points.items():
        if data["count"] >= 1:  # Minimum occurrences
            rate = data["friction_count"] / data["count"]
            top_friction_points.append({
                "question": question,
                "total": data["count"],
                "friction_count": data["friction_count"],
                "friction_rate": rate,
                "examples": data["examples"][:2],  # Keep only 2 examples
            })
    
    top_friction_points.sort(key=lambda x: (-x["friction_rate"], -x["friction_count"]))
    
    return {
        "generated_at": datetime.now().isoformat(),
        "mode": "live_api" if USE_LIVE_API else "mock",
        "summary": {
            "total_analyzed": total,
            "friction_rate": friction_rate,
            "by_category": dict(by_category),
            "by_status": dict(by_status),
        },
        "by_friction_type": dict(by_question_type),
        "top_friction_points": top_friction_points[:15],
        "classifications": classifications,
    }


def main():
    print("=" * 60)
    print("Pulse Demo Pre-computation Script")
    print("=" * 60)
    print(f"\nMode: {'LIVE API (watch rate limits!)' if USE_LIVE_API else 'MOCK (using expected categories)'}")
    print(f"Delay between requests: {DELAY_BETWEEN_REQUESTS}s")
    print()
    
    # Load transcripts
    print("Loading transcripts...")
    transcripts = load_all_transcripts()
    print(f"Total: {len(transcripts)} transcripts\n")
    
    if not transcripts:
        print("Error: No transcripts found!")
        return
    
    # Classify each transcript
    print("Classifying transcripts...")
    classifications = []
    
    for i, t in enumerate(transcripts):
        if USE_LIVE_API:
            result = live_classify(t)
            if DELAY_BETWEEN_REQUESTS > 0:
                time.sleep(DELAY_BETWEEN_REQUESTS)
        else:
            result = mock_classify(t)
        
        classifications.append(result)
        
        # Progress indicator
        pct = (i + 1) / len(transcripts) * 100
        status_icon = "🔴" if result["category"] == "HIGH_FRICTION" else "🟡" if result["category"] == "CONFUSION" else "🟢"
        print(f"  [{pct:5.1f}%] {status_icon} {t['chat_id']}: {result['category']} ({result['confidence']:.0%})")
    
    print(f"\nClassified {len(classifications)} transcripts")
    
    # Generate analysis
    print("\nGenerating friction analysis...")
    analysis = generate_friction_analysis(classifications, transcripts)
    
    # Save results
    output_path = Path("data/friction_data.json")
    with open(output_path, "w") as f:
        json.dump(analysis, f, indent=2)
    
    print(f"\n✅ Saved results to {output_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    summary = analysis["summary"]
    print(f"Total Analyzed: {summary['total_analyzed']}")
    print(f"Friction Rate: {summary['friction_rate']:.0%}")
    print(f"\nBy Category:")
    for cat, count in summary["by_category"].items():
        print(f"  {cat}: {count}")
    
    print(f"\nTop Friction Types:")
    for q_type, data in sorted(analysis["by_friction_type"].items(), key=lambda x: -x[1]["friction_rate"])[:5]:
        print(f"  {q_type}: {data['friction_rate']:.0%} ({data['friction_count']}/{data['total']})")
    
    print(f"\nTop Friction Points:")
    for fp in analysis["top_friction_points"][:3]:
        print(f"  \"{fp['question'][:50]}...\"")
        print(f"    Rate: {fp['friction_rate']:.0%} ({fp['friction_count']}/{fp['total']})")
    
    print("\n✅ Pre-computation complete! You can now run the demo without API calls.")
    print("   Set USE_MOCK_DATA = True in app.py (default) to use this data.")


if __name__ == "__main__":
    main()
