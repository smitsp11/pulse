"""
Nudge generator for creating context-aware re-engagement messages.

Uses Gemini 2.5 Flash to generate nudges that are:
- Specific to the friction type
- Adapted to the carrier's brand voice
- Under 160 characters (SMS limit)
"""

import os
import time
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from dotenv import load_dotenv

from .models import (
    TranscriptInput,
    ClassificationResult,
    NudgeResult,
    BrandPersona,
    BRAND_PERSONAS,
    StallCategory,
)

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


# Nudge generation prompt template
NUDGE_PROMPT = """You are writing an SMS follow-up for an insurance lead who got stuck.

Brand Voice: {brand_persona_name}
{brand_description}
Style rules: {style_rules}
Example of this voice: "{example}"

Friction type: {friction_type}
Last bot message: "{last_bot_message}"
User's last reply: "{last_user_message}"

Rules:
- MUST be under 160 characters (this is critical - SMS limit)
- Match the brand voice exactly
- Remove the specific blocker, don't just ask "are you there?"
- Offer an alternative or simplification
- No emojis
- Be helpful, not pushy

Write ONLY the nudge message, nothing else:"""


# Template library for common friction types
# These provide fallbacks and examples for the LLM
NUDGE_TEMPLATES = {
    StallCategory.HIGH_FRICTION: {
        BrandPersona.HELPFUL_NEIGHBOR: [
            "No stress on the {item}—a photo of your registration works too!",
            "Hey, if the {item} is hard to find, we can work with your registration instead.",
            "Totally get it! You can send the {item} later, or try a photo of your insurance card.",
        ],
        BrandPersona.PROFESSIONAL_ADVISOR: [
            "I understand the {item} can be inconvenient to locate. A photo of your registration document would work just as well.",
            "No rush on the {item}. When you have a moment, a copy of your registration is an acceptable alternative.",
            "I can see the {item} is difficult to access right now. Please feel free to send it when convenient, or we can use your registration instead.",
        ],
    },
    StallCategory.CONFUSION: {
        BrandPersona.HELPFUL_NEIGHBOR: [
            "Sorry if that was confusing! In simple terms: {explanation}",
            "Let me break that down differently: {explanation}",
            "Good question! Basically, {explanation}",
        ],
        BrandPersona.PROFESSIONAL_ADVISOR: [
            "I apologize for the confusion. To clarify: {explanation}",
            "Allow me to explain that more clearly: {explanation}",
            "That's a common question. Simply put: {explanation}",
        ],
    },
}


def generate_nudge(
    transcript: TranscriptInput,
    classification: ClassificationResult,
    brand_persona: BrandPersona = BrandPersona.HELPFUL_NEIGHBOR,
    model_name: str = "gemini-2.5-flash",
) -> NudgeResult:
    """
    Generate a context-aware nudge for a stalled conversation.
    
    Args:
        transcript: The conversation transcript
        classification: The classification result from the classifier
        brand_persona: The brand voice to use
        model_name: Gemini model to use
        
    Returns:
        NudgeResult with the generated nudge
    """
    start_time = time.time()
    
    # Get brand persona details
    persona_details = BRAND_PERSONAS[brand_persona]
    
    # Get last messages
    last_bot_message = transcript.last_bot_message or "No bot message"
    last_user_message = transcript.last_user_message or "No user response"
    
    # Build prompt
    prompt = NUDGE_PROMPT.format(
        brand_persona_name=brand_persona.value.replace("_", " ").title(),
        brand_description=persona_details["description"],
        style_rules=", ".join(persona_details["rules"]),
        example=persona_details["example"],
        friction_type=classification.reason,
        last_bot_message=last_bot_message,
        last_user_message=last_user_message,
    )
    
    # Call Gemini
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.7,  # Slightly higher for creative variation
            max_output_tokens=100,
        )
    )
    
    raw_response = response.text
    latency_ms = (time.time() - start_time) * 1000
    
    # Clean up the nudge
    nudge_text = raw_response.strip().strip('"').strip("'")
    
    # Ensure under 160 characters
    if len(nudge_text) > 160:
        # Try to truncate intelligently
        nudge_text = nudge_text[:157] + "..."
    
    return NudgeResult(
        chat_id=transcript.chat_id,
        classification=classification,
        brand_persona=brand_persona,
        nudge_text=nudge_text,
        raw_llm_response=raw_response,
        latency_ms=latency_ms,
    )


def generate_nudge_batch(
    transcripts_and_classifications: list[tuple[TranscriptInput, ClassificationResult]],
    brand_persona: BrandPersona = BrandPersona.HELPFUL_NEIGHBOR,
    model_name: str = "gemini-2.5-flash",
) -> list[NudgeResult]:
    """
    Generate nudges for multiple transcripts.
    
    Args:
        transcripts_and_classifications: List of (transcript, classification) tuples
        brand_persona: The brand voice to use
        model_name: Gemini model to use
        
    Returns:
        List of NudgeResults
    """
    results = []
    for transcript, classification in transcripts_and_classifications:
        # Skip benign classifications
        if classification.category == StallCategory.BENIGN:
            continue
            
        result = generate_nudge(
            transcript, classification, brand_persona, model_name
        )
        results.append(result)
    
    return results


def compare_brand_voices(
    transcript: TranscriptInput,
    classification: ClassificationResult,
    model_name: str = "gemini-2.5-flash",
) -> dict[BrandPersona, NudgeResult]:
    """
    Generate nudges in both brand voices for comparison.
    
    Args:
        transcript: The conversation transcript
        classification: The classification result
        model_name: Gemini model to use
        
    Returns:
        Dictionary mapping BrandPersona to NudgeResult
    """
    results = {}
    for persona in BrandPersona:
        results[persona] = generate_nudge(
            transcript, classification, persona, model_name
        )
    return results


# CLI interface for testing
if __name__ == "__main__":
    from .models import Message, MessageRole
    from .classifier import classify_transcript
    
    # Example usage
    sample_transcript = TranscriptInput(
        chat_id="test-001",
        history=[
            Message(role=MessageRole.BOT, text="Hi! I can help you get an auto insurance quote. To get started, I'll need your VIN number."),
            Message(role=MessageRole.USER, text="Ugh, I'm at work right now. I don't have that on me."),
            Message(role=MessageRole.BOT, text="No problem! You can usually find your VIN on your insurance card or registration document."),
        ]
    )
    
    print("Classifying transcript...")
    classification = classify_transcript(sample_transcript)
    print(f"Classification: {classification.category.value} (confidence: {classification.confidence:.2f})")
    
    print("\nGenerating nudges in both brand voices...")
    print("-" * 50)
    
    for persona in BrandPersona:
        result = generate_nudge(sample_transcript, classification, persona)
        print(f"\n{persona.value.replace('_', ' ').title()}:")
        print(f"  \"{result.nudge_text}\"")
        print(f"  Length: {len(result.nudge_text)} chars | Latency: {result.latency_ms:.0f}ms")
