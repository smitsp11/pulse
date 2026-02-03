#!/usr/bin/env python3
"""
Demo script for Pulse.

Demonstrates the full pipeline:
1. Classification
2. Nudge generation with brand voice
3. Multi-channel awareness
4. A/B testing
5. Auto-send decisions
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models import TranscriptInput, Message, MessageRole, BrandPersona
from src.classifier import classify_transcript
from src.nudge_generator import generate_nudge, compare_brand_voices
from src.backend_status import check_backend_status
from src.autosend import get_auto_send_engine, get_tenant_manager


def print_header(text: str):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def demo_classification():
    """Demo the classification engine."""
    print_header("CLASSIFICATION DEMO")
    
    transcripts = [
        # High Friction - VIN
        TranscriptInput(
            chat_id="demo-hf-vin",
            history=[
                Message(role=MessageRole.BOT, text="I need your VIN to get a quote."),
                Message(role=MessageRole.USER, text="I'm at work, don't have it with me."),
                Message(role=MessageRole.BOT, text="You can find it on your registration."),
            ]
        ),
        # Confusion - Jargon
        TranscriptInput(
            chat_id="demo-confusion",
            history=[
                Message(role=MessageRole.BOT, text="Would you like UM/UIM coverage with your policy?"),
                Message(role=MessageRole.USER, text="What is UM/UIM? I don't understand."),
            ]
        ),
        # Benign - Just busy
        TranscriptInput(
            chat_id="demo-benign",
            history=[
                Message(role=MessageRole.BOT, text="What's your zip code?"),
                Message(role=MessageRole.USER, text="90210"),
                Message(role=MessageRole.BOT, text="Great! And what year is your vehicle?"),
            ]
        ),
    ]
    
    for transcript in transcripts:
        print(f"\n--- Chat: {transcript.chat_id} ---")
        print("Conversation:")
        for msg in transcript.history:
            role = "BOT" if msg.role == MessageRole.BOT else "USER"
            print(f"  {role}: {msg.text}")
        
        result = classify_transcript(transcript)
        print(f"\nClassification:")
        print(f"  Category: {result.category.value}")
        print(f"  Confidence: {result.confidence:.0%}")
        print(f"  Reason: {result.reason}")
        print(f"  Evidence: {result.evidence[:60]}...")


def demo_nudge_generation():
    """Demo nudge generation with brand voices."""
    print_header("NUDGE GENERATION DEMO")
    
    transcript = TranscriptInput(
        chat_id="demo-nudge",
        history=[
            Message(role=MessageRole.BOT, text="I need your VIN to get a quote."),
            Message(role=MessageRole.USER, text="I'm at work, don't have it with me."),
        ]
    )
    
    print("Transcript:")
    for msg in transcript.history:
        role = "BOT" if msg.role == MessageRole.BOT else "USER"
        print(f"  {role}: {msg.text}")
    
    # Classify first
    classification = classify_transcript(transcript)
    print(f"\nClassification: {classification.category.value} ({classification.confidence:.0%})")
    
    # Generate nudges in both voices
    print("\nNudges by Brand Voice:")
    print("-" * 40)
    
    nudges = compare_brand_voices(transcript, classification)
    for persona, nudge in nudges.items():
        print(f"\n{persona.value.replace('_', ' ').title()}:")
        print(f"  \"{nudge.nudge_text}\"")
        print(f"  Length: {len(nudge.nudge_text)} chars")


def demo_multi_channel():
    """Demo multi-channel awareness."""
    print_header("MULTI-CHANNEL AWARENESS DEMO")
    
    print("\nScenario: User silent on SMS, but active on portal")
    print("-" * 40)
    
    # Simulate user active elsewhere
    status = check_backend_status(
        "demo-multi-channel",
        mock_mode=True,
        mock_active_elsewhere_rate=1.0  # 100% chance of being active elsewhere
    )
    
    print(f"\nBackend Status Check:")
    print(f"  User active elsewhere: {status.user_active_elsewhere}")
    print(f"  Last portal activity: {status.last_portal_activity}")
    print(f"  Documents received: {status.pending_documents_received}")
    print(f"  Safe to nudge: {status.safe_to_nudge}")
    
    if not status.safe_to_nudge:
        print("\n⚠️  DECISION: Do NOT send nudge - user completed action elsewhere!")
    else:
        print("\n✓ DECISION: Safe to send nudge")


def demo_autosend():
    """Demo the auto-send engine with different tenants."""
    print_header("AUTO-SEND ENGINE DEMO")
    
    transcript = TranscriptInput(
        chat_id="demo-autosend",
        history=[
            Message(role=MessageRole.BOT, text="I need your VIN to get a quote."),
            Message(role=MessageRole.USER, text="I'm at work, don't have it with me."),
        ]
    )
    
    engine = get_auto_send_engine()
    tenant_manager = get_tenant_manager()
    
    print("\nProcessing same conversation with different tenant configs:")
    print("-" * 50)
    
    for tenant_id in ["lemonade", "statefarm", "default"]:
        config = tenant_manager.get_tenant(tenant_id)
        print(f"\n--- Tenant: {tenant_id} ---")
        print(f"  Brand: {config.brand_persona.value}")
        print(f"  Auto-send: {'Enabled' if config.auto_send_enabled else 'Disabled'}")
        print(f"  Confidence threshold: {config.auto_send_confidence_threshold}")
        
        decision = engine.process_conversation(transcript, tenant_id)
        
        print(f"\n  Decision: {decision.action.value.upper()}")
        print(f"  Reason: {decision.reason}")
        if decision.nudge_text:
            print(f"  Nudge: \"{decision.nudge_text[:50]}...\"")


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("       PULSE - Stalled Conversation Resurrection Engine")
    print("                         DEMO")
    print("=" * 60)
    
    try:
        demo_classification()
        demo_nudge_generation()
        demo_multi_channel()
        demo_autosend()
        
        print_header("DEMO COMPLETE")
        print("\nTo run the full app:")
        print("  streamlit run app.py")
        print("\nTo run the API server:")
        print("  python scripts/run_api.py")
        print("\nTo validate the classifier:")
        print("  python scripts/validate_classifier.py")
        
    except Exception as e:
        print(f"\n❌ Error running demo: {e}")
        print("\nMake sure you have:")
        print("  1. Set GOOGLE_API_KEY in .env")
        print("  2. Installed dependencies: pip install -r requirements.txt")
        raise


if __name__ == "__main__":
    main()
