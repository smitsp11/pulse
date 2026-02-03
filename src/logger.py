"""
Logging utilities for Pulse.

Logging is mandatory for:
- Debugging misclassifications
- Calibrating templates
- Measuring quality and training better prompts
- Proving business value
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from .models import (
    ClassificationResult,
    NudgeResult,
    ReviewedNudge,
    BackendStatus,
    TranscriptInput,
)


class PulseLogger:
    """
    Logger for Pulse operations.
    
    Logs all classifications, nudges, reviews, and outcomes to JSON files
    for analysis and debugging.
    """
    
    def __init__(self, log_dir: str = "logs"):
        """
        Initialize the logger.
        
        Args:
            log_dir: Directory to store log files
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for different log types
        (self.log_dir / "classifications").mkdir(exist_ok=True)
        (self.log_dir / "nudges").mkdir(exist_ok=True)
        (self.log_dir / "reviews").mkdir(exist_ok=True)
        (self.log_dir / "backend_status").mkdir(exist_ok=True)
        (self.log_dir / "transcripts").mkdir(exist_ok=True)
    
    def _write_log(self, subdir: str, filename: str, data: dict):
        """Write a log entry to a JSON file."""
        filepath = self.log_dir / subdir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def _append_to_daily_log(self, log_type: str, data: dict):
        """Append an entry to a daily aggregate log file."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        filepath = self.log_dir / f"{log_type}_{today}.jsonl"
        
        with open(filepath, "a") as f:
            f.write(json.dumps(data, default=str) + "\n")
    
    def log_transcript(self, transcript: TranscriptInput):
        """Log an input transcript."""
        filename = f"{transcript.chat_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        self._write_log("transcripts", filename, transcript.model_dump())
        self._append_to_daily_log("transcripts", {
            "chat_id": transcript.chat_id,
            "message_count": len(transcript.history),
            "logged_at": datetime.utcnow().isoformat(),
        })
    
    def log_classification(
        self,
        transcript: TranscriptInput,
        result: ClassificationResult
    ):
        """
        Log a classification result.
        
        Args:
            transcript: The input transcript
            result: The classification result
        """
        filename = f"{result.chat_id}_{result.classified_at.strftime('%Y%m%d_%H%M%S')}.json"
        
        log_data = {
            "transcript": transcript.model_dump(),
            "classification": result.model_dump(),
        }
        
        self._write_log("classifications", filename, log_data)
        self._append_to_daily_log("classifications", {
            "chat_id": result.chat_id,
            "status": result.status.value,
            "category": result.category.value,
            "confidence": result.confidence,
            "latency_ms": result.latency_ms,
            "classified_at": result.classified_at.isoformat(),
        })
    
    def log_backend_status(self, status: BackendStatus):
        """Log a backend status check."""
        filename = f"{status.chat_id}_{status.checked_at.strftime('%Y%m%d_%H%M%S')}.json"
        self._write_log("backend_status", filename, status.model_dump())
        self._append_to_daily_log("backend_status", {
            "chat_id": status.chat_id,
            "safe_to_nudge": status.safe_to_nudge,
            "user_active_elsewhere": status.user_active_elsewhere,
            "checked_at": status.checked_at.isoformat(),
        })
    
    def log_nudge(self, nudge: NudgeResult):
        """Log a generated nudge."""
        filename = f"{nudge.chat_id}_{nudge.generated_at.strftime('%Y%m%d_%H%M%S')}.json"
        self._write_log("nudges", filename, nudge.model_dump())
        self._append_to_daily_log("nudges", {
            "chat_id": nudge.chat_id,
            "brand_persona": nudge.brand_persona.value,
            "nudge_length": len(nudge.nudge_text),
            "latency_ms": nudge.latency_ms,
            "generated_at": nudge.generated_at.isoformat(),
        })
    
    def log_review(self, review: ReviewedNudge):
        """Log a human review decision."""
        filename = f"{review.nudge.chat_id}_{review.reviewed_at.strftime('%Y%m%d_%H%M%S')}.json"
        self._write_log("reviews", filename, review.model_dump())
        self._append_to_daily_log("reviews", {
            "chat_id": review.nudge.chat_id,
            "decision": review.decision.value,
            "review_time_seconds": review.review_time_seconds,
            "was_edited": review.edited_text is not None,
            "reviewed_at": review.reviewed_at.isoformat(),
        })


def load_daily_log(log_dir: str, log_type: str, date: Optional[str] = None) -> list[dict]:
    """
    Load entries from a daily log file.
    
    Args:
        log_dir: Directory containing log files
        log_type: Type of log (classifications, nudges, reviews, backend_status)
        date: Date string in YYYY-MM-DD format. Defaults to today.
        
    Returns:
        List of log entries
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    filepath = Path(log_dir) / f"{log_type}_{date}.jsonl"
    
    if not filepath.exists():
        return []
    
    entries = []
    with open(filepath, "r") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))
    
    return entries


def get_classification_stats(log_dir: str, date: Optional[str] = None) -> dict:
    """
    Get classification statistics for a given date.
    
    Args:
        log_dir: Directory containing log files
        date: Date string in YYYY-MM-DD format. Defaults to today.
        
    Returns:
        Dictionary with classification statistics
    """
    entries = load_daily_log(log_dir, "classifications", date)
    
    if not entries:
        return {"total": 0, "by_category": {}, "by_status": {}, "avg_confidence": 0}
    
    by_category = {}
    by_status = {}
    total_confidence = 0
    
    for entry in entries:
        category = entry.get("category", "UNKNOWN")
        status = entry.get("status", "UNKNOWN")
        confidence = entry.get("confidence", 0)
        
        by_category[category] = by_category.get(category, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        total_confidence += confidence
    
    return {
        "total": len(entries),
        "by_category": by_category,
        "by_status": by_status,
        "avg_confidence": total_confidence / len(entries) if entries else 0,
    }
