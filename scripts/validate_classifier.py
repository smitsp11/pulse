#!/usr/bin/env python3
"""
Validation script for Pulse classifier.

This script runs the classifier against sample transcripts with known
expected categories and measures accuracy.

Phase 1 Exit Criteria:
- 50+ real transcripts classified
- Human-LLM agreement rate >80%
- At least 25% of stalls classified as non-benign
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import TranscriptInput, Message, MessageRole
from src.classifier import classify_transcript
from src.logger import PulseLogger


def load_transcripts(data_dir: str = "data") -> list[dict]:
    """Load all sample transcripts from data directory."""
    transcripts = []
    data_path = Path(data_dir)
    
    for json_file in data_path.glob("sample_transcripts*.json"):
        with open(json_file, "r") as f:
            data = json.load(f)
            transcripts.extend(data.get("transcripts", []))
    
    return transcripts


def run_validation(
    transcripts: list[dict],
    log_results: bool = True,
    verbose: bool = True
) -> dict:
    """
    Run validation against sample transcripts.
    
    Args:
        transcripts: List of transcript dictionaries with expected_category
        log_results: Whether to log results
        verbose: Whether to print detailed output
        
    Returns:
        Validation statistics
    """
    logger = PulseLogger() if log_results else None
    
    results = {
        "total": len(transcripts),
        "correct": 0,
        "incorrect": 0,
        "by_category": {
            "HIGH_FRICTION": {"total": 0, "correct": 0},
            "CONFUSION": {"total": 0, "correct": 0},
            "BENIGN": {"total": 0, "correct": 0},
        },
        "non_benign_rate": 0,
        "errors": [],
        "predictions": [],
    }
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"PULSE CLASSIFIER VALIDATION")
        print(f"{'='*60}")
        print(f"Total transcripts: {len(transcripts)}")
        print(f"{'='*60}\n")
    
    for i, t in enumerate(transcripts):
        chat_id = t.get("chat_id", f"unknown-{i}")
        expected = t.get("expected_category", "UNKNOWN")
        
        # Build transcript input
        history = [
            Message(
                role=MessageRole(m["role"]),
                text=m["text"]
            )
            for m in t.get("history", [])
        ]
        
        transcript = TranscriptInput(
            chat_id=chat_id,
            history=history,
        )
        
        try:
            # Classify
            result = classify_transcript(transcript)
            predicted = result.category.value
            
            # Log if enabled
            if logger:
                logger.log_classification(transcript, result)
            
            # Check correctness
            is_correct = predicted == expected
            
            results["by_category"][expected]["total"] += 1
            if is_correct:
                results["correct"] += 1
                results["by_category"][expected]["correct"] += 1
            else:
                results["incorrect"] += 1
                results["errors"].append({
                    "chat_id": chat_id,
                    "expected": expected,
                    "predicted": predicted,
                    "confidence": result.confidence,
                    "evidence": result.evidence,
                })
            
            results["predictions"].append({
                "chat_id": chat_id,
                "expected": expected,
                "predicted": predicted,
                "confidence": result.confidence,
                "correct": is_correct,
            })
            
            if verbose:
                status = "✓" if is_correct else "✗"
                print(f"[{status}] {chat_id}")
                print(f"    Expected: {expected}")
                print(f"    Predicted: {predicted} (confidence: {result.confidence:.2f})")
                if not is_correct:
                    print(f"    Evidence: {result.evidence[:80]}...")
                print()
                
        except Exception as e:
            results["errors"].append({
                "chat_id": chat_id,
                "error": str(e),
            })
            if verbose:
                print(f"[!] {chat_id} - ERROR: {e}\n")
    
    # Calculate metrics
    results["accuracy"] = results["correct"] / results["total"] if results["total"] > 0 else 0
    
    non_benign = sum(
        1 for p in results["predictions"]
        if p["predicted"] != "BENIGN"
    )
    results["non_benign_rate"] = non_benign / results["total"] if results["total"] > 0 else 0
    
    # Per-category accuracy
    for cat in results["by_category"]:
        cat_data = results["by_category"][cat]
        cat_data["accuracy"] = (
            cat_data["correct"] / cat_data["total"]
            if cat_data["total"] > 0 else 0
        )
    
    return results


def print_summary(results: dict):
    """Print validation summary."""
    print(f"\n{'='*60}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*60}")
    print(f"Total transcripts: {results['total']}")
    print(f"Correct: {results['correct']}")
    print(f"Incorrect: {results['incorrect']}")
    print(f"Overall Accuracy: {results['accuracy']*100:.1f}%")
    print(f"Non-benign rate: {results['non_benign_rate']*100:.1f}%")
    
    print(f"\nPer-Category Results:")
    print(f"-" * 40)
    for cat, data in results["by_category"].items():
        print(f"  {cat}:")
        print(f"    Total: {data['total']}")
        print(f"    Correct: {data['correct']}")
        print(f"    Accuracy: {data['accuracy']*100:.1f}%")
    
    # Exit criteria check
    print(f"\n{'='*60}")
    print(f"EXIT CRITERIA CHECK")
    print(f"{'='*60}")
    
    criteria = [
        ("50+ transcripts classified", results["total"] >= 50, f"{results['total']} transcripts"),
        ("Human-LLM agreement >80%", results["accuracy"] >= 0.80, f"{results['accuracy']*100:.1f}%"),
        ("Non-benign rate >25%", results["non_benign_rate"] >= 0.25, f"{results['non_benign_rate']*100:.1f}%"),
    ]
    
    all_passed = True
    for name, passed, value in criteria:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name} ({value})")
        if not passed:
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print("ALL EXIT CRITERIA MET - Ready for Phase 2!")
    else:
        print("Some criteria not met - continue validation")
    print(f"{'='*60}\n")
    
    # Show errors if any
    if results["errors"]:
        print(f"\nMisclassifications ({len([e for e in results['errors'] if 'predicted' in e])}):")
        print("-" * 40)
        for err in results["errors"]:
            if "predicted" in err:
                print(f"  {err['chat_id']}: expected {err['expected']}, got {err['predicted']}")


def main():
    """Run validation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate Pulse classifier")
    parser.add_argument("--data-dir", default="data", help="Directory containing sample transcripts")
    parser.add_argument("--no-log", action="store_true", help="Disable logging")
    parser.add_argument("--quiet", action="store_true", help="Only show summary")
    parser.add_argument("--output", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    # Load transcripts
    transcripts = load_transcripts(args.data_dir)
    
    if not transcripts:
        print(f"No transcripts found in {args.data_dir}/")
        print("Make sure sample_transcripts*.json files exist.")
        sys.exit(1)
    
    # Run validation
    results = run_validation(
        transcripts,
        log_results=not args.no_log,
        verbose=not args.quiet,
    )
    
    # Print summary
    print_summary(results)
    
    # Save results if requested
    if args.output:
        with open(args.output, "w") as f:
            # Remove non-serializable data
            output = {k: v for k, v in results.items() if k != "predictions"}
            output["predictions"] = results["predictions"]
            json.dump(output, f, indent=2, default=str)
        print(f"Results saved to {args.output}")
    
    # Exit with appropriate code
    if results["accuracy"] >= 0.80 and results["total"] >= 50:
        sys.exit(0)  # Success
    else:
        sys.exit(1)  # Criteria not met


if __name__ == "__main__":
    main()
