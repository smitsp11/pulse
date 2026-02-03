# Product Requirements Document (PRD)

## Project Overview

**Project Name:** Pulse (Stalled Conversation Resurrection Engine)  
**Type:** Background Service / Intelligence Layer  
**Status:** MVP / Prototype Phase

---

## 1. Objective

To build a classification engine that detects stalled conversations, identifies the cause of friction, and generates a context-aware re-engagement message to recover the user.

---

## 2. User Stories

**As an Insurance Agent:**  
I want to know which of my 50 "waiting" conversations are actually at risk of churning so I can prioritize who to text back.

**As a Product Owner:**  
I want to measure friction points in our flow (e.g., "we lose 30% of users at the VIN request") to improve the core bot.

---

## 3. Functional Requirements (MVP)

### 3.1 The Trigger (Input)

- The system accepts a chat transcript (JSON format).
- The system is triggered when:
  - `last_message_sender = Bot`
  - `time_since_last_message > X minutes` (e.g., 60 minutes)

### 3.2 The Intelligence (Logic)

The system passes the transcript to an LLM (e.g., GPT-4o-mini) with a prompt to classify the **Silence Reason** into one of the following:

- High Friction Request (VIN, Driver License #)
- Privacy / Trust
- Confusion
- Pricing Shock
- Benign / Unknown

### 3.3 The Output (Action)

The system outputs a JSON object containing:

```json
{
  "status": "STALLED_HIGH_RISK",
  "reason": "High Friction Request (VIN)",
  "suggested_nudge": "A specific, casual text to unblock the user."
}
```

---

## 4. Technical Specifications (Demo)

- **Language:** Python 3.10+
- **Core Libraries:** openai, json, datetime

### Mock Data Structure

```json
{
  "chat_id": "101",
  "history": [
    {"role": "bot", "text": "To get you an accurate quote, I need your VIN."},
    {"role": "user", "text": "Ugh, I'm at work, I don't have it."},
    {"role": "bot", "text": "No problem! You can find it on your insurance card or registration."}
  ]
}
```

### Judge Prompt Strategy

- **Role:** You are a senior sales coach analyzing a stalled SMS thread.
- **Task:** Analyze the last turn. Did the user stop because of a hard constraint? Draft a text to remove that constraint.

---

## 5. Success Metrics (KPIs)

- **Accuracy:** Silence Reason matches human assessment (Target: >90%).
- **Resurrection Rate:** % of users who reply to the nudge vs. a control group.

---

## 6. Future Scope (Post-Internship)

- Dashboard integration showing at-risk leads
- Auto-send nudges for high-confidence scenarios
- Friction heatmap identifying high-dropoff questions
