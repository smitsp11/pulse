"""
Classification engine for detecting stalled conversation reasons.

Uses Gemini 2.5 Flash to analyze SMS transcripts and classify why
a user stopped responding.
"""

import json
import os
import time
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

from .models import (
    TranscriptInput,
    ClassificationResult,
    StallCategory,
    StallStatus,
    Message,
)

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Classification prompt template
CLASSIFICATION_PROMPT = """You are a senior insurance sales coach reviewing a stalled SMS conversation.

The customer has stopped replying. Analyze why.

Categories:
- HIGH_FRICTION: Bot asked for something hard to get (VIN, license #, specific docs, photos). User expressed difficulty, frustration, or inability to provide it.
- CONFUSION: Bot used jargon, gave unclear instructions, or user expressed confusion about what was being asked.
- BENIGN: User is likely busy, distracted, or naturally paused. No clear friction or confusion signals.

Important rules:
1. Default to BENIGN if unsure - we prefer to under-nudge rather than over-nudge
2. HIGH_FRICTION requires clear evidence the user hit a blocker (e.g., "I don't have that", "I'm at work", "where do I find that?")
3. CONFUSION requires evidence the user didn't understand (e.g., "what do you mean?", "huh?", or no response after jargon)
4. Look at the LAST exchange specifically - what was the bot's last question and how did the user respond (or not respond)?

Respond ONLY with valid JSON in this exact format:
{{"category": "HIGH_FRICTION" | "CONFUSION" | "BENIGN", "confidence": 0.0-1.0, "evidence": "exact quote from transcript"}}

Transcript:
{transcript}"""


def format_transcript_for_llm(transcript: TranscriptInput) -> str:
    """Format transcript into readable string for LLM."""
    lines = []
    for msg in transcript.history:
        role_label = "BOT" if msg.role.value == "bot" else "USER"
        lines.append(f"{role_label}: {msg.text}")
    return "\n".join(lines)


def parse_llm_response(response_text: str) -> dict:
    """Parse LLM JSON response, handling common issues."""
    # Try to extract JSON from response
    text = response_text.strip()
    
    # Handle markdown code blocks
    if text.startswith("```"):
        # Remove ```json and ``` markers
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```"):
                in_block = not in_block
                continue
            if in_block or not line.startswith("```"):
                json_lines.append(line)
        text = "\n".join(json_lines).strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Return default if parsing fails
        return {
            "category": "BENIGN",
            "confidence": 0.3,
            "evidence": f"Failed to parse LLM response: {str(e)}"
        }


def classify_transcript(
    transcript: TranscriptInput,
    model_name: str = "gemini-2.5-flash-preview-05-20"
) -> ClassificationResult:
    """
    Classify why a conversation stalled.
    
    Args:
        transcript: The conversation transcript to analyze
        model_name: Gemini model to use
        
    Returns:
        ClassificationResult with category, confidence, and evidence
    """
    start_time = time.time()
    
    # Format transcript for LLM
    transcript_text = format_transcript_for_llm(transcript)
    prompt = CLASSIFICATION_PROMPT.format(transcript=transcript_text)
    
    # Call Gemini
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.1,  # Low temperature for consistent classification
            max_output_tokens=256,
        )
    )
    
    raw_response = response.text
    latency_ms = (time.time() - start_time) * 1000
    
    # Parse response
    parsed = parse_llm_response(raw_response)
    
    # Map category to status
    category = StallCategory(parsed.get("category", "BENIGN"))
    confidence = float(parsed.get("confidence", 0.5))
    
    if category == StallCategory.HIGH_FRICTION and confidence >= 0.7:
        status = StallStatus.STALLED_HIGH_RISK
    elif category in [StallCategory.HIGH_FRICTION, StallCategory.CONFUSION] and confidence >= 0.5:
        status = StallStatus.STALLED_LOW_RISK
    else:
        status = StallStatus.BENIGN
    
    # Build detailed reason
    reason = f"{category.value}"
    if category == StallCategory.HIGH_FRICTION:
        # Try to identify specific friction type
        evidence = parsed.get("evidence", "").lower()
        if "vin" in evidence:
            reason = f"{category.value}:VIN_REQUEST"
        elif "license" in evidence or "dl" in evidence:
            reason = f"{category.value}:LICENSE_REQUEST"
        elif "photo" in evidence or "picture" in evidence or "upload" in evidence:
            reason = f"{category.value}:DOCUMENT_UPLOAD"
        else:
            reason = f"{category.value}:GENERAL"
    
    return ClassificationResult(
        chat_id=transcript.chat_id,
        status=status,
        category=category,
        reason=reason,
        confidence=confidence,
        evidence=parsed.get("evidence", "No evidence provided"),
        raw_llm_response=raw_response,
        latency_ms=latency_ms,
    )


def classify_transcript_batch(
    transcripts: list[TranscriptInput],
    model_name: str = "gemini-2.5-flash-preview-05-20"
) -> list[ClassificationResult]:
    """
    Classify multiple transcripts.
    
    Args:
        transcripts: List of transcripts to classify
        model_name: Gemini model to use
        
    Returns:
        List of ClassificationResults
    """
    results = []
    for transcript in transcripts:
        result = classify_transcript(transcript, model_name)
        results.append(result)
    return results


# CLI interface for testing
if __name__ == "__main__":
    import sys
    
    # Example usage
    sample_transcript = TranscriptInput(
        chat_id="test-001",
        history=[
            Message(role="bot", text="Hi! I can help you get an auto insurance quote. To get started, I'll need your VIN number."),
            Message(role="user", text="Ugh, I'm at work right now. I don't have that on me."),
            Message(role="bot", text="No problem! You can usually find your VIN on your insurance card or registration document."),
        ]
    )
    
    print("Classifying sample transcript...")
    result = classify_transcript(sample_transcript)
    print(f"\nResult:")
    print(f"  Status: {result.status.value}")
    print(f"  Category: {result.category.value}")
    print(f"  Reason: {result.reason}")
    print(f"  Confidence: {result.confidence:.2f}")
    print(f"  Evidence: {result.evidence}")
    print(f"  Latency: {result.latency_ms:.0f}ms")
