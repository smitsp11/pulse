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
# From the project root, with venv activated:
python -m streamlit run app.py
```

**If you see NumPy or pandas errors** (e.g. `numpy.dtype size changed`, `_ARRAY_API not found`), your shell is likely using Conda’s `streamlit` instead of the venv. Run with the venv’s Python explicitly:

```bash
# Linux / macOS
./venv/bin/python -m streamlit run app.py

# Windows (PowerShell)
.\venv\Scripts\python.exe -m streamlit run app.py
```

The app will open in your browser with three tabs:
1. **Classify & Nudge:** Paste a transcript and get instant classification + nudge
2. **Friction Heatmap:** Analyze batch transcripts for drop-off patterns
3. **Review Queue:** Approve/edit/reject generated nudges

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
```

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
