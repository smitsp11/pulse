# Pulse - Stalled Conversation Resurrection Engine

Pulse is a classification engine that detects stalled conversations, identifies the cause of friction, and generates context-aware re-engagement messages to recover users in insurance SMS workflows.

## The Problem

In SMS-based insurance workflows, silence is the default state. When a policyholder stops replying, the current system treats all silence equally as "Waiting for Customer." But not all silence is the same:

- **Scenario A (Benign):** User is looking for their credit card. *Action: Wait.*
- **Scenario B (Friction):** User was asked for a VIN, doesn't have it, feels blocked. *Action: Intervene.*
- **Scenario C (Confusion):** Bot used jargon the user didn't understand. *Action: Clarify.*

Scenarios B and C are invisible revenue leaks. Pulse detects them and enables targeted recovery.

## Features

### 1. Classification Engine
- Analyzes conversation transcripts to classify stall reasons
- Three categories: `HIGH_FRICTION`, `CONFUSION`, `BENIGN`
- Confidence scores for each classification
- Uses Gemini 2.5 Flash for fast, accurate classification

### 2. Nudge Generator
- Generates context-aware re-engagement messages
- **Brand Voice Support:** Adapts to carrier's brand (casual vs professional)
- SMS-optimized (under 160 characters)
- Template library for common friction types

### 3. Multi-Channel Awareness
- Checks if user has been active on other channels (portal, email)
- Prevents annoying users who already completed the action elsewhere
- Critical for enterprise deployment

### 4. Friction Heatmap
- Analyzes which bot questions cause the most drop-off
- Immediate value even without nudge automation
- "Debugger for your conversation flow"

### 5. Review Queue
- Human-in-the-loop review for generated nudges
- Approve, edit, or reject nudges before sending
- Tracks approval rates and review times

## Quick Start

### Prerequisites
- Python 3.10+
- Google AI API key (for Gemini 2.5 Flash)

### Installation

```bash
# Clone the repository
cd pulse

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

### Running the App

```bash
# Start the Streamlit app
streamlit run app.py
```

The app will open in your browser with three tabs:
1. **Classify & Nudge:** Paste a transcript and get instant classification + nudge
2. **Friction Heatmap:** Analyze batch transcripts for drop-off patterns
3. **Review Queue:** Approve/edit/reject generated nudges

### Running Validation

```bash
# Validate classifier against sample transcripts
python scripts/validate_classifier.py

# With detailed output
python scripts/validate_classifier.py --data-dir data --output results.json
```

## Project Structure

```
pulse/
├── app.py                    # Streamlit application
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template
├── src/
│   ├── __init__.py
│   ├── models.py             # Data models (Pydantic)
│   ├── classifier.py         # Classification engine
│   ├── nudge_generator.py    # Nudge generation
│   ├── backend_status.py     # Multi-channel awareness
│   ├── friction_report.py    # Friction heatmap analysis
│   ├── database.py           # SQLite persistence
│   └── logger.py             # Logging utilities
├── scripts/
│   └── validate_classifier.py # Validation script
├── data/
│   ├── sample_transcripts.json
│   └── sample_transcripts_extended.json
└── info/
    ├── Document_1_Vision_and_Strategic_Context.md
    └── Document_2_PRD_Pulse.md
```

## Brand Voice Configuration

Pulse supports multiple brand voices for enterprise clients:

```python
from src.models import BrandPersona
from src.nudge_generator import generate_nudge

# Casual voice (Lemonade style)
nudge = generate_nudge(transcript, classification, BrandPersona.HELPFUL_NEIGHBOR)
# Output: "No stress on the VIN—a photo of your registration works too!"

# Professional voice (State Farm style)
nudge = generate_nudge(transcript, classification, BrandPersona.PROFESSIONAL_ADVISOR)
# Output: "I understand getting the VIN can be inconvenient. A photo of your registration would work just as well."
```

## API Usage

### Classification

```python
from src.models import TranscriptInput, Message, MessageRole
from src.classifier import classify_transcript

transcript = TranscriptInput(
    chat_id="test-001",
    history=[
        Message(role=MessageRole.BOT, text="I need your VIN to get a quote."),
        Message(role=MessageRole.USER, text="I'm at work, don't have it on me."),
    ]
)

result = classify_transcript(transcript)
print(f"Category: {result.category.value}")  # HIGH_FRICTION
print(f"Confidence: {result.confidence:.2f}")  # 0.92
```

### Backend Status Check

```python
from src.backend_status import check_backend_status

status = check_backend_status("chat-123")
if not status.safe_to_nudge:
    print("User active elsewhere - do not nudge!")
```

## Success Metrics

- **Classification Accuracy:** >80% agreement with human labels
- **Nudge Approval Rate:** >70% approved without edits
- **Resurrection Rate:** 2x response rate vs control group
- **Review Time:** <30 seconds per nudge

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Transcript     │────>│  Backend     │────>│ Classifier  │
│  Ingestion      │     │  Status      │     │ (Gemini)    │
└─────────────────┘     │  Check       │     └─────────────┘
                        └──────────────┘            │
                               │                    v
                    safe_to_nudge?           ┌─────────────┐
                               │             │   Nudge     │
                               v             │ Generator   │
                        ┌──────────┐         │ (Gemini)    │
                        │  SKIP    │         └─────────────┘
                        │  if not  │               │
                        │  safe    │               v
                        └──────────┘         ┌─────────────┐
                                             │  Review     │
                                             │  Queue      │
                                             └─────────────┘
```

## License

Proprietary - General Magic, Inc.
