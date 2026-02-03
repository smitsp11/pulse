"""
SQLite database for storing transcripts, classifications, nudges, and reviews.

This provides persistence for the review queue and analytics.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from .models import (
    TranscriptInput,
    ClassificationResult,
    NudgeResult,
    ReviewedNudge,
    ReviewDecision,
    BackendStatus,
    Message,
    MessageRole,
    StallCategory,
    StallStatus,
    BrandPersona,
)


class PulseDatabase:
    """SQLite database for Pulse data."""
    
    def __init__(self, db_path: str = "data/pulse.db"):
        """Initialize database connection."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Transcripts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcripts (
                    chat_id TEXT PRIMARY KEY,
                    history TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Classifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS classifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    category TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence TEXT,
                    raw_llm_response TEXT,
                    classified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    latency_ms REAL,
                    FOREIGN KEY (chat_id) REFERENCES transcripts(chat_id)
                )
            """)
            
            # Nudges table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS nudges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    classification_id INTEGER NOT NULL,
                    brand_persona TEXT NOT NULL,
                    nudge_text TEXT NOT NULL,
                    raw_llm_response TEXT,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    latency_ms REAL,
                    FOREIGN KEY (chat_id) REFERENCES transcripts(chat_id),
                    FOREIGN KEY (classification_id) REFERENCES classifications(id)
                )
            """)
            
            # Reviews table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nudge_id INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    edited_text TEXT,
                    reviewer_notes TEXT,
                    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    review_time_seconds REAL,
                    FOREIGN KEY (nudge_id) REFERENCES nudges(id)
                )
            """)
            
            # Backend status checks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backend_status_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    user_active_elsewhere BOOLEAN NOT NULL,
                    last_portal_activity TIMESTAMP,
                    pending_documents_received BOOLEAN,
                    safe_to_nudge BOOLEAN NOT NULL,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_classifications_chat_id ON classifications(chat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_classifications_category ON classifications(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_nudges_chat_id ON nudges(chat_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_nudge_id ON reviews(nudge_id)")
    
    # Transcript operations
    def save_transcript(self, transcript: TranscriptInput):
        """Save a transcript to the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            history_json = json.dumps([
                {"role": m.role.value, "text": m.text}
                for m in transcript.history
            ])
            cursor.execute(
                "INSERT OR REPLACE INTO transcripts (chat_id, history) VALUES (?, ?)",
                (transcript.chat_id, history_json)
            )
    
    def get_transcript(self, chat_id: str) -> Optional[TranscriptInput]:
        """Get a transcript by chat_id."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM transcripts WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            if row:
                history = json.loads(row["history"])
                return TranscriptInput(
                    chat_id=row["chat_id"],
                    history=[
                        Message(role=MessageRole(m["role"]), text=m["text"])
                        for m in history
                    ]
                )
        return None
    
    # Classification operations
    def save_classification(self, classification: ClassificationResult) -> int:
        """Save a classification result. Returns the classification ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO classifications 
                (chat_id, status, category, reason, confidence, evidence, raw_llm_response, classified_at, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                classification.chat_id,
                classification.status.value,
                classification.category.value,
                classification.reason,
                classification.confidence,
                classification.evidence,
                classification.raw_llm_response,
                classification.classified_at,
                classification.latency_ms,
            ))
            return cursor.lastrowid
    
    def get_classifications(
        self,
        category: Optional[StallCategory] = None,
        min_confidence: Optional[float] = None,
        limit: int = 100
    ) -> list[ClassificationResult]:
        """Get classifications with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM classifications WHERE 1=1"
            params = []
            
            if category:
                query += " AND category = ?"
                params.append(category.value)
            
            if min_confidence:
                query += " AND confidence >= ?"
                params.append(min_confidence)
            
            query += " ORDER BY classified_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            results = []
            for row in cursor.fetchall():
                results.append(ClassificationResult(
                    chat_id=row["chat_id"],
                    status=StallStatus(row["status"]),
                    category=StallCategory(row["category"]),
                    reason=row["reason"],
                    confidence=row["confidence"],
                    evidence=row["evidence"],
                    raw_llm_response=row["raw_llm_response"],
                    classified_at=datetime.fromisoformat(row["classified_at"]) if row["classified_at"] else datetime.utcnow(),
                    latency_ms=row["latency_ms"],
                ))
            
            return results
    
    # Nudge operations
    def save_nudge(self, nudge: NudgeResult, classification_id: int) -> int:
        """Save a nudge. Returns the nudge ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO nudges 
                (chat_id, classification_id, brand_persona, nudge_text, raw_llm_response, generated_at, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                nudge.chat_id,
                classification_id,
                nudge.brand_persona.value,
                nudge.nudge_text,
                nudge.raw_llm_response,
                nudge.generated_at,
                nudge.latency_ms,
            ))
            return cursor.lastrowid
    
    def get_nudges_for_review(self, limit: int = 50) -> list[dict]:
        """Get nudges that haven't been reviewed yet."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT n.*, c.category, c.confidence, c.reason, t.history
                FROM nudges n
                JOIN classifications c ON n.classification_id = c.id
                JOIN transcripts t ON n.chat_id = t.chat_id
                LEFT JOIN reviews r ON n.id = r.nudge_id
                WHERE r.id IS NULL
                ORDER BY n.generated_at DESC
                LIMIT ?
            """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "nudge_id": row["id"],
                    "chat_id": row["chat_id"],
                    "nudge_text": row["nudge_text"],
                    "brand_persona": row["brand_persona"],
                    "category": row["category"],
                    "confidence": row["confidence"],
                    "reason": row["reason"],
                    "history": json.loads(row["history"]),
                    "generated_at": row["generated_at"],
                })
            
            return results
    
    # Review operations
    def save_review(
        self,
        nudge_id: int,
        decision: ReviewDecision,
        edited_text: Optional[str] = None,
        reviewer_notes: Optional[str] = None,
        review_time_seconds: Optional[float] = None,
    ):
        """Save a review decision."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reviews 
                (nudge_id, decision, edited_text, reviewer_notes, review_time_seconds)
                VALUES (?, ?, ?, ?, ?)
            """, (
                nudge_id,
                decision.value,
                edited_text,
                reviewer_notes,
                review_time_seconds,
            ))
    
    def get_review_stats(self) -> dict:
        """Get review statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN decision = 'approved' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN decision = 'edited' THEN 1 ELSE 0 END) as edited,
                    SUM(CASE WHEN decision = 'rejected' THEN 1 ELSE 0 END) as rejected,
                    AVG(review_time_seconds) as avg_review_time
                FROM reviews
            """)
            
            row = cursor.fetchone()
            return {
                "total": row["total"] or 0,
                "approved": row["approved"] or 0,
                "edited": row["edited"] or 0,
                "rejected": row["rejected"] or 0,
                "avg_review_time": row["avg_review_time"] or 0,
                "approval_rate": (row["approved"] or 0) / (row["total"] or 1),
            }
    
    # Analytics
    def get_classification_stats(self) -> dict:
        """Get classification statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT category, COUNT(*) as count
                FROM classifications
                GROUP BY category
            """)
            
            by_category = {row["category"]: row["count"] for row in cursor.fetchall()}
            
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM classifications
                GROUP BY status
            """)
            
            by_status = {row["status"]: row["count"] for row in cursor.fetchall()}
            
            cursor.execute("SELECT COUNT(*) as total, AVG(confidence) as avg_confidence FROM classifications")
            row = cursor.fetchone()
            
            return {
                "total": row["total"] or 0,
                "avg_confidence": row["avg_confidence"] or 0,
                "by_category": by_category,
                "by_status": by_status,
            }


# Singleton instance
_db_instance: Optional[PulseDatabase] = None


def get_database(db_path: str = "data/pulse.db") -> PulseDatabase:
    """Get or create database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = PulseDatabase(db_path)
    return _db_instance
