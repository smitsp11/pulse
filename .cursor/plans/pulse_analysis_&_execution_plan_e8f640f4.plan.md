---
name: Pulse Analysis & Execution Plan
overview: "A two-mode analysis of Pulse (Stalled Conversation Resurrection Engine): first aligning engineering mindset with business context, then creating a phased execution plan for incremental delivery."
todos:
  - id: phase1-classifier
    content: "Phase 1: Build classification engine (classifier.py) with 3 categories, confidence scores, and JSON logging"
    status: completed
  - id: phase1-backend-status
    content: "Phase 1: Add check_backend_status() placeholder for multi-channel state awareness"
    status: completed
  - id: phase1-validation
    content: "Phase 1: Validate classifier on 50+ transcripts, achieve >80% human agreement"
    status: completed
  - id: phase2-nudge-gen
    content: "Phase 2: Build nudge generator with brand_persona parameter and template library"
    status: completed
  - id: phase2-friction-report
    content: "Phase 2: Build Friction Heatmap report showing drop-off by bot question (high standalone value)"
    status: completed
  - id: phase2-review-ui
    content: "Phase 2: Build Streamlit app with Classify/Nudge, Heatmap, and Review Queue tabs"
    status: completed
  - id: phase3-integration
    content: "Phase 3: Build webhook integration, real backend status check, and A/B test infrastructure"
    status: completed
  - id: phase4-autosend
    content: "Phase 4: Enable auto-send with confidence thresholds and multi-tenant configuration"
    status: completed
isProject: false
---

# Pulse: Engineering Analysis & Execution Plan

---

## Mode 1: Engineer Mindset Alignment

### Engineering North Star

**"Turn dead air into data, and data into recovered revenue—without annoying anyone."**

The system must be *helpful*, not *persistent*. The difference between a save and a churn is whether the nudge feels like a friend removing a blocker or a salesperson demanding attention.

---

### What the Company Actually Cares About

**The real business pain:**

- Qualified leads are dying in a "Waiting for Customer" graveyard because the system cannot distinguish *blocked* users from *busy* users
- Revenue is leaking invisibly—there's no signal that a lead is at risk until it's already cold
- The current generic re-engagement ("Hey, are you still there?") is worse than nothing because it signals the bot doesn't understand context

**Emotionally unacceptable failure modes:**

1. **False urgency on benign silence** — Texting a user who's genuinely busy makes the brand feel desperate
2. **Missing obvious recoveries** — A user who said "I don't have my VIN" and got a useless response represents a *winnable* conversion that was lost to bad UX
3. **Building analytics that don't change behavior** — If this becomes a dashboard nobody looks at, it's wasted effort

**Disproportionate wins (high leverage, low effort):**

- Proving that 2-3 friction categories account for 80% of recoverable stalls (focus beats coverage)
- A single well-crafted nudge template per friction type that outperforms generic follow-ups
- Data that tells product *which bot question* causes the most churn (fixes the root cause)

---

### What Must Be True for This Product to Matter

**Implicit assumptions:**

1. Users stall for *classifiable* reasons, not random life noise
2. The conversation transcript contains enough context to infer the reason
3. LLMs can reliably classify silence intent from short SMS exchanges
4. Users who receive a *contextual* nudge respond better than those who receive a generic one
5. The insurance sales funnel has enough friction-caused churn to justify intervention

**What would collapse the idea:**

- If >70% of silence is truly benign (no signal to recover)
- If LLM classification accuracy is <80% (noise overwhelms signal)
- If users find *any* follow-up annoying regardless of context (nudges become spam)
- If the real friction is in insurance requirements (VIN is *required*), not bot UX (making nudges useless)

---

### Constraints That Should Shape Engineering Decisions


| Dimension                              | Lean Toward                                                          | Avoid                                    |
| -------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------- |
| **Speed vs Correctness**               | Fast classification (<2s), tolerant of occasional misses             | Perfect taxonomy that delays shipping    |
| **Automation vs Human-in-Loop**        | Human review for first 500 nudges; auto-send only after calibration  | Full automation on day 1                 |
| **False Positives vs False Negatives** | **Under-nudge** is safer than over-nudge; brand damage compounds     | Aggressive recovery that feels spammy    |
| **Precision vs Recall**                | High precision on "High Friction" (act confidently); lower recall OK | Catching every stall at cost of accuracy |


---

### Non-Negotiables

1. **Every nudge must be human-reviewable before send for Phase 1** — No auto-send until accuracy is proven
2. **Classification must include confidence score** — Low-confidence classifications should default to no action
3. **Logging is mandatory** — Every transcript, classification, nudge, and outcome must be stored for calibration
4. **The "Benign" category must be the default** — System should only act when confident something is wrong
5. **Nudges must feel human-written** — No corporate tone, no exclamation points overload
6. **Multi-channel state must be checked before nudging** — A user silent on SMS but active on portal/email is NOT stalled; nudging them is a brand-damaging error

---

### Explicit Tradeoffs

1. **Fewer categories > More categories** — Start with 3 (High Friction, Confusion, Benign). Add Pricing Shock and Privacy later if data supports them
2. **Template-based nudges > Fully generative nudges** — Safer, testable, and faster; LLM picks template, not freeform text
3. **Batch processing > Real-time** — MVP can run hourly; sub-minute latency is premature optimization
4. **Agent-facing > User-facing** — First version surfaces to human agents, doesn't auto-text users
5. **Accuracy on high-value stalls > Coverage of all stalls** — A lead asking for a quote is worth more than a lead in early browsing

---

## Mode 2: Execution Planning

### Strategic Refinements (Enterprise Context)

The following refinements address real enterprise insurance concerns that elevate this from "smart intern project" to "production-ready architecture":

**1. Multi-Channel State Awareness**

- **Problem:** Users often complete actions on other channels (web portal, email, phone) while silent on SMS
- **Risk:** Nudging them ("Don't forget the VIN!") when they already submitted it is a brand-damaging error
- **Solution:** `check_backend_status()` gate that queries CRM/portal before any nudge decision
- **Included in:** Phase 1 (placeholder), Phase 3 (real integration)

**2. Brand Voice Parameter**

- **Problem:** General Magic sells to enterprises with different brand personalities (Lemonade-casual vs State Farm-professional)
- **Risk:** A "No stress!" nudge violates conservative insurer brand guidelines
- **Solution:** `brand_persona` parameter in nudge generation; prompt adapts to carrier's voice
- **Included in:** Phase 2 (template library), all subsequent phases

**3. Friction Heatmap Moved to Phase 2**

- **Problem:** Original plan had analytics in Phase 4—too late for a startup that needs to know NOW why their bot is failing
- **Risk:** Building nudge automation before understanding friction patterns is premature optimization
- **Solution:** Friction Heatmap is a core Phase 2 deliverable, not a Phase 4 enhancement
- **Value:** "Even before we automate nudges, this tool is a debugger for your conversation flow"

**4. Streamlit over Next.js**

- **Problem:** Custom React/Next.js frontend adds complexity (auth, state, API glue) without AI value
- **Risk:** Solo engineer spends weekend on plumbing instead of prompts
- **Solution:** Streamlit for all internal tooling—builds in 2 hours, pure Python, professional enough for demos

### Phase 1: Classification Proof-of-Concept

**Goal:** Prove the LLM can reliably classify silence reasons on real transcripts.

**What is built:**

- Python CLI script that accepts a transcript JSON and returns classification
- Single LLM call (Gemini 2.5 Flash) with structured output
- 3 categories: `HIGH_FRICTION`, `CONFUSION`, `BENIGN`
- Confidence score (0-1)
- Simple logging to local JSON file

**Data structures:**

```python
# Input
TranscriptInput = {
    "chat_id": str,
    "history": list[{"role": str, "text": str}],
    "last_bot_message_timestamp": datetime
}

# Output  
ClassificationResult = {
    "chat_id": str,
    "status": "STALLED_HIGH_RISK" | "STALLED_LOW_RISK" | "BENIGN",
    "reason": str,  # e.g., "HIGH_FRICTION:VIN_REQUEST"
    "confidence": float,
    "raw_llm_response": str  # for debugging
}

# Backend State Check (critical for multi-channel awareness)
BackendStatus = {
    "chat_id": str,
    "user_active_elsewhere": bool,  # True if user took action on portal/email
    "last_portal_activity": datetime | None,
    "pending_documents_received": bool,
    "safe_to_nudge": bool
}
```

**Multi-Channel State Check (Negative Signal):**

Before classifying a conversation as stalled, the system must call `check_backend_status(chat_id)` to verify the user hasn't completed the requested action on another channel.

```python
def check_backend_status(chat_id: str) -> BackendStatus:
    """
    Placeholder for backend integration.
    
    In production, this queries the CRM/portal to check:
    - Did user upload requested document via web portal?
    - Did user email the agent directly?
    - Did user call the agency?
    
    If any of these are true, DO NOT nudge—the silence is resolved.
    """
    # TODO: Integrate with General Magic backend
    return BackendStatus(
        chat_id=chat_id,
        user_active_elsewhere=False,  # Default: assume not active elsewhere
        last_portal_activity=None,
        pending_documents_received=False,
        safe_to_nudge=True
    )
```

**Why this matters:** A user who stopped texting because they uploaded their VIN photo via the web portal is NOT stalled. Nudging them ("Don't forget the VIN!") turns a helpful system into an annoying one.

**LLM Prompt Strategy (Phase 1):**

```
You are a senior insurance sales coach reviewing a stalled SMS conversation.

The customer has stopped replying. Analyze why.

Categories:
- HIGH_FRICTION: Bot asked for something hard to get (VIN, license #, specific docs)
- CONFUSION: Bot used jargon or gave unclear instructions  
- BENIGN: User is likely busy, distracted, or naturally paused

Respond in JSON:
{"category": "...", "confidence": 0.0-1.0, "evidence": "quote from transcript"}

Transcript:
{transcript}
```

**What is intentionally NOT built:**

- No nudge generation yet
- No database integration
- No API layer
- No UI

**What this phase validates:**

- *Technical:* LLM can parse SMS transcripts and output structured classifications
- *Product:* The 3-category taxonomy captures most real stall reasons
- *Business:* There exists a meaningful population of non-benign stalls (>20%)

**Exit criteria:**

- 50+ real transcripts classified
- Human-LLM agreement rate >80%
- At least 25% of stalls classified as non-benign

---

### Phase 2: Nudge Generation, Review Queue & Friction Analytics

**Goal:** Prove that generated nudges are high-quality enough for human approval AND deliver immediate diagnostic value via friction analytics.

**What is built:**

- Nudge generation LLM call (separate from classification)
- Template library (3-5 templates per friction type)
- **Brand Voice parameter** for enterprise customization
- **Streamlit UI** (not Next.js—faster to build, pure Python) showing:
  - Stalled conversation
  - Classification + confidence
  - Suggested nudge
  - Approve / Edit / Reject buttons
- SQLite database for transcripts, classifications, nudges, and human decisions
- **Friction Heatmap Report** — shows which bot questions cause the most stalls (immediate product value even without sending nudges)

**Components:**

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│  Transcript     │────>│ Classifier   │────>│   Nudge     │
│  Ingestion      │     │ (LLM #1)     │     │ Generator   │
└─────────────────┘     └──────────────┘     │ (LLM #2)    │
                                              └─────────────┘
                                                    │
                          ┌─────────────────────────┼─────────────────────────┐
                          v                         v                         v
                   ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
                   │  Review     │          │  Friction   │          │   Brand     │
                   │  Queue      │          │  Heatmap    │          │   Voice     │
                   │ (Streamlit) │          │  Report     │          │  Templates  │
                   └─────────────┘          └─────────────┘          └─────────────┘
```

**Brand Voice Parameter (Enterprise Requirement):**

General Magic sells to insurance carriers with different brand personalities. The nudge generator must adapt:

```python
BrandPersona = Literal["helpful_neighbor", "professional_advisor"]

# Persona definitions
BRAND_PERSONAS = {
    "helpful_neighbor": {
        "description": "Casual, friendly, like texting a neighbor (Lemonade style)",
        "example": "No stress on the VIN—a photo of your registration works too!",
        "rules": ["Use contractions", "Keep it breezy", "OK to be slightly informal"]
    },
    "professional_advisor": {
        "description": "Warm but professional, trustworthy advisor (State Farm style)", 
        "example": "I understand getting the VIN can be inconvenient. A photo of your registration document would work just as well.",
        "rules": ["No slang", "Complete sentences", "Empathetic but not casual"]
    }
}
```

**LLM Prompt Strategy (Phase 2 - Nudge Generation with Brand Voice):**

```
You are writing an SMS follow-up for an insurance lead who got stuck.

Brand Voice: {brand_persona}
{BRAND_PERSONAS[brand_persona]["description"]}
Style rules: {BRAND_PERSONAS[brand_persona]["rules"]}
Example of this voice: {BRAND_PERSONAS[brand_persona]["example"]}

Friction type: {classification.reason}
Last bot message: {last_bot_message}
User's last reply: {last_user_message}

Rules:
- Max 160 characters
- Match the brand voice exactly
- Remove the specific blocker, don't just ask "are you there?"
- No emojis

Write the nudge:
```

**Friction Heatmap (Immediate Product Value):**

Even before a single nudge is sent, the classification data answers: "Which bot questions are killing our conversion?"

```python
def generate_friction_report(classifications: list[ClassificationResult]) -> FrictionReport:
    """
    Aggregates classifications to show:
    - Total stalls by category (pie chart)
    - Drop-off rate by bot question (bar chart)
    - Top 5 "killer questions" (table)
    
    This report is valuable to the Product Team even if nudges never ship.
    """
    # Group by the bot's last question
    by_bot_question = defaultdict(list)
    for c in classifications:
        last_bot_msg = c.transcript[-2]["text"]  # Bot's last message
        by_bot_question[last_bot_msg].append(c)
    
    # Rank by friction rate
    friction_rates = {
        q: sum(1 for c in cs if c.status != "BENIGN") / len(cs)
        for q, cs in by_bot_question.items()
    }
    return sorted(friction_rates.items(), key=lambda x: -x[1])
```

**Demo output (Streamlit):**

```
FRICTION HEATMAP - Top Drop-off Points
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bot Question                          | Stalls | Friction Rate
──────────────────────────────────────|────────|──────────────
"I need your VIN to get a quote"      |   47   |    78%
"Please upload a photo of your car"   |   31   |    62%
"What's your driver's license #?"     |   28   |    54%
"Do you have any at-fault accidents?" |   12   |    23%
"What's your zip code?"               |    8   |     9%
```

**The Pitch:** "Even before we automate nudges, Pulse acts as a debugger for your conversation flow. This report tells you exactly which questions are killing your conversion rates—so you can fix the bot, not just patch over it."

**What is intentionally NOT built:**

- Auto-send functionality
- CRM/bot integration
- Real-time streaming

**What this phase validates:**

- *Technical:* Two-stage LLM pipeline is reliable; brand voice parameter works
- *Product:* Human reviewers approve >70% of nudges without edits; friction report is actionable
- *Business:* The effort to review nudges is low enough to scale; product team finds friction data valuable

**Exit criteria:**

- 100+ nudges generated and reviewed
- Approval rate >70% (without edits)
- Average review time <30 seconds per nudge
- Friction report identifies at least 1 bot question to improve

---

### Phase 3: Integration & Controlled Experiment

**Goal:** Prove nudges actually resurrect stalled conversations.

**What is built:**

- Webhook endpoint to receive transcripts from existing bot system
- **Backend status integration** — real `check_backend_status()` implementation that queries CRM/portal
- API to return classification + approved nudge
- A/B test infrastructure: 50% get nudge, 50% control (no nudge)
- Basic metrics tracking: response rate, time-to-response

**Architecture:**

```
┌─────────────┐     Webhook      ┌─────────────┐
│  Existing   │ ──────────────>  │   Pulse     │
│  Bot System │                  │   Service   │
└─────────────┘                  └─────────────┘
                                       │
                                       v
                              ┌─────────────────┐
                              │ Backend Status  │ ◄── CRM/Portal API
                              │ Check           │
                              │ (Multi-Channel) │
                              └─────────────────┘
                                       │
                          safe_to_nudge = True?
                                       │
                   ┌───────────────────┼───────────────────┐
                   v                   v                   v
            ┌──────────┐        ┌──────────┐        ┌──────────┐
            │ Classify │ ────>  │ Generate │ ────>  │  Queue   │
            │          │        │  Nudge   │        │  or Send │
            │          │        │ (w/brand │        │          │
            │          │        │  voice)  │        │          │
            └──────────┘        └──────────┘        └──────────┘
```

**Multi-Channel Gate Logic:**

```python
def process_stalled_conversation(chat_id: str, transcript: dict) -> NudgeDecision:
    # CRITICAL: Check backend BEFORE classification
    backend_status = check_backend_status(chat_id)
    
    if not backend_status.safe_to_nudge:
        return NudgeDecision(
            action="SKIP",
            reason=f"User active elsewhere: {backend_status.last_portal_activity}"
        )
    
    # Only classify if safe to nudge
    classification = classify_transcript(transcript)
    
    if classification.status == "BENIGN" or classification.confidence < 0.7:
        return NudgeDecision(action="SKIP", reason="Benign or low confidence")
    
    # Generate nudge with carrier's brand voice
    nudge = generate_nudge(classification, brand_persona=carrier.brand_voice)
    
    return NudgeDecision(action="QUEUE_FOR_REVIEW", nudge=nudge)
```

**What is intentionally NOT built:**

- Full analytics dashboard
- Multi-tenant support
- Automatic threshold tuning

**What this phase validates:**

- *Technical:* Integration with production bot is stable
- *Product:* Nudged users respond at higher rate than control
- *Business:* Revenue impact is measurable and positive

**Exit criteria:**

- 500+ stalls processed in production
- Nudged users respond at 2x+ rate vs control (statistically significant)
- No increase in opt-out/block rate

---

### Phase 4: Auto-Send & Operational Scaling

**Goal:** Remove human review bottleneck and scale to full production volume.

**What is built:**

- Auto-send for high-confidence classifications (confidence >0.9, `safe_to_nudge=True`)
- Confidence threshold tuning based on outcome data
- Enhanced dashboard showing:
  - Stall volume by category over time (time series)
  - Resurrection rate by friction type and brand persona
  - A/B test results visualization
  - Nudge performance by template
- Multi-tenant configuration (different carriers, different brand voices, different thresholds)

**Note:** Friction Heatmap was moved to Phase 2—it delivers immediate value and shouldn't wait for production automation.

**What this phase validates:**

- *Technical:* System scales to full conversation volume without human bottleneck
- *Product:* Auto-send maintains quality without human review (no increase in opt-outs)
- *Business:* Pulse is ROI-positive at scale

**Exit criteria:**

- Auto-send enabled for >50% of nudges
- Auto-send opt-out rate within 10% of human-reviewed nudge rate
- Resurrection rate sustained at target levels (2x control)

---

### Minimal First Demo Plan

**Deliverable:** A Streamlit app where you paste a transcript and see classification + nudge in <5 seconds, plus a Friction Heatmap from batch-processed transcripts.

**Why Streamlit (not Next.js):** For a solo engineer, a custom React/Next.js frontend is a time sink. It adds complexity (auth, state management, API glue) without adding "AI value." Streamlit builds the same UI in 2 hours using pure Python—spend your time on prompts, not plumbing.

**Build order (can be done in ~2 days):**

1. `classifier.py` — Function that takes transcript, returns classification JSON
2. `nudge_generator.py` — Function that takes classification + brand_persona, returns nudge text
3. `backend_status.py` — Placeholder for `check_backend_status()` with mock implementation
4. `friction_report.py` — Function that aggregates classifications into heatmap data
5. `app.py` — Streamlit app with three tabs:
  - **Classify & Nudge:** Paste transcript, select brand voice, see results
  - **Friction Heatmap:** Upload batch of transcripts, see drop-off analysis
  - **Review Queue:** Approve/Edit/Reject nudges (Phase 2)
6. 10+ sample transcripts covering each friction type

**Demo script:**

1. **Single Transcript Demo:**
  - Show a "High Friction" transcript (VIN request)
  - Run through classifier → show output with confidence score
  - Toggle brand voice: "Helpful Neighbor" vs "Professional Advisor"
  - Run through nudge generator → show contextual nudge in both voices
  - Compare to generic "Hey, are you still there?"
2. **Friction Heatmap Demo:**
  - Load 50 sample transcripts
  - Show bar chart: "Top 5 Bot Questions Causing Stalls"
  - Pitch: "This tells you which questions to fix in your bot—before you even send a single nudge"
3. **Multi-Channel Awareness Demo:**
  - Show transcript where user went silent after VIN request
  - Show mock `check_backend_status()` returning `user_active_elsewhere=True`
  - System says: "User uploaded document via portal. Safe to nudge: NO"
  - Pitch: "We don't nudge users who already took action elsewhere"

---

### Where Human Review or Logging is Critical


| Stage              | What to Log                                                         | Why                                            |
| ------------------ | ------------------------------------------------------------------- | ---------------------------------------------- |
| Backend Status     | chat_id, user_active_elsewhere, last_portal_activity, safe_to_nudge | Debug false nudges; measure multi-channel rate |
| Classification     | Full transcript, raw LLM response, parsed output, latency           | Debug misclassifications                       |
| Nudge Generation   | Input context, brand_persona, raw LLM response, final nudge         | Calibrate templates by brand voice             |
| Human Review       | Decision (approve/edit/reject), edit diff, time spent               | Measure quality, train better prompts          |
| User Response      | Whether user replied, what they said, time to response              | Measure resurrection rate                      |
| Friction Analytics | Aggregated drop-off rates by bot question, by time of day           | Identify bot improvements                      |


**Logging is not optional.** Without it, you cannot calibrate the system or prove business value.

**Critical insight from multi-channel logging:** If you discover that 40% of "stalled" users actually completed the action on another channel, that changes the entire product strategy—the Friction Heatmap becomes more valuable than the nudge automation.

---

## Final Synthesis

### How Document 1 Should Influence Every Engineering Decision

**Every feature should be evaluated by asking: "Does this help us confidently distinguish *blocked* users from *busy* users, and take helpful action without annoying anyone?"** If a feature doesn't serve classification accuracy, nudge quality, or outcome measurement, it's premature.

**Addendum after strategic refinements:** The bar for "annoying" is higher in enterprise B2B than consumer. A nudge that annoys a user also annoys the carrier who trusted you with their brand. Multi-channel awareness and brand voice compliance are not nice-to-haves—they are table stakes for enterprise deployment.

### The Single Most Dangerous Assumption

**"Users who receive contextual nudges will respond at higher rates than users who receive no follow-up."**

This is dangerous because the entire ROI depends on it. If users find *any* follow-up annoying (regardless of context), or if the friction is inherent to insurance requirements (not removable by clever wording), the product creates cost without value.

**Secondary dangerous assumption (revealed by multi-channel analysis):** "SMS silence means user inaction." If a significant percentage of "stalled" users have actually completed the action on another channel, the addressable market for nudges shrinks dramatically—and the Friction Heatmap becomes the primary value proposition.

### The Fastest Possible Experiment to Test That Assumption

**Manual A/B test with 50 real stalled conversations:**

1. Pull 50 stalled conversations where the bot asked for VIN and user expressed friction ("I don't have it")
2. **NEW:** Manually verify in the CRM/portal that these users did NOT complete the action elsewhere
3. Manually classify them to confirm they're recoverable (not benign)
4. Split into two groups of 25:
  - **Control:** No follow-up
  - **Treatment:** Human agent sends a contextual nudge (e.g., "No stress on the VIN—a photo of your registration works too")
5. Measure response rate after 24 hours

**Time to run:** 1 day to identify transcripts + verify backend status, 24-48 hours for results.

**Success threshold:** Treatment group responds at 2x rate of control.

**If this fails:** Pivot to analytics-only (Friction Heatmap for product team) rather than nudge automation. The Friction Heatmap has standalone value regardless of whether nudges work—it tells the product team which bot questions to fix.

### Fallback Value Proposition

Even if the nudge automation hypothesis fails completely, Pulse delivers value as a **conversation flow debugger**:

- "40% of users drop off at the VIN request" → Product team redesigns that question
- "Users in the 'Professional Advisor' carrier convert 20% better than 'Helpful Neighbor'" → Insights for brand strategy
- "Most stalls happen between 6-8pm" → Staffing optimization for human agents

**The Friction Heatmap is the safety net that ensures Pulse is valuable even if the nudge ROI never materializes.**