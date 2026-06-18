# AI Triage Nurse — Post-Op Recovery Agent

## Overview

A multi-agent AI system that simulates a post-operative recovery triage nurse. A patient chats naturally about how they're feeling; three Claude-powered agents collaborate behind the scenes to collect symptoms, assess risk, and escalate alerts to a real-time nurse dashboard.

Each agent is a **clinical reasoner**, not a checklist-follower. They form hypotheses, detect patterns, reason about trajectories, and make judgment calls — powered by clinical knowledge, synthetic reasoning examples, and an eight-layer guardrail system.

**Purpose:** Portfolio project demonstrating multi-agent orchestration, Anthropic SDK tool use, LLM guardrails, and structured clinical data extraction — built for technical interviewer audiences.

**Disclaimer:** Educational demo only. Not medical advice. Not for real patient care.

---

## Architecture

### Full Pipeline with Guardrails

```
Patient Message
       |
       v
+--------------------------------------------------+
| LAYER 1a: Emergency Keyword Bypass               |
| 23 regex patterns (chest pain, can't breathe,    |
| uncontrolled bleeding, suicidal ideation, etc.)   |
| Triggers 911-NOW alert BEFORE agents run          |
| Cost: Free, 0ms                                   |
+--------------------------------------------------+
       |
       v
+--------------------------------------------------+
| LAYER 1b: Semantic Emergency Classifier          |
| Haiku LLM classifier catches natural-language    |
| emergencies regex misses ("everything is going   |
| dark", "I took all my pills at once")            |
| Cost: ~$0.001, ~500ms                             |
+--------------------------------------------------+
       |
       v
+--------------------------------------------------+
| LAYER 6: Manipulation / Off-Topic Detector       |
| 13 regex patterns for prompt injection +          |
| Haiku LLM classifier for off-topic abuse          |
| Blocks: "ignore your instructions", "write a poem"|
| Cost: Free (regex) + ~$0.001 (Haiku fallback)    |
+--------------------------------------------------+
       |
       v
+-------------------+
| CONVERSATIONALIST |  <-- Clinical reasoning agent (Claude Sonnet)
| (Patient-facing)  |
|                   |      Injected knowledge:
| Forms hypotheses  |      - Surgery-specific recovery timelines
| Asks targeted     |      - Medication pharmacology
| questions         |      - 4 few-shot reasoning examples
| Logs via tools    |      - Full patient context with trends
|                   |      - Cross-session history
|   +----------------------------------+
|   | LAYER 5: Tool Input Validator    |
|   | Sanitizes severity (0-10 clamp)  |
|   | Rejects invalid vital types      |
|   | Validates medication names       |
|   +----------------------------------+
|                   |
+-------------------+
       |
       v
+--------------------------------------------------+
| LAYER 2: Output Content Filter                   |
| Blocks diagnosis language ("you have an          |
| infection"), prescription language ("take 800mg"),|
| and alarm language ("go to the ER now")          |
| Replaces with safe alternatives                   |
+--------------------------------------------------+
       |
       v
  Patient sees clean reply (2-3s latency)
       |
       v  (background thread — patient doesn't wait)
+-------------------+
| RISK ASSESSOR     |  <-- Pattern recognition agent (Claude Sonnet)
| (Background)      |
|                   |      Injected knowledge:
| Reads trajectories|      - Surgery-specific clinical knowledge
| Detects compound  |      - Vital sign interpretation guide
| patterns          |      - Red-flag matrix (21 signals)
| Considers med     |      - 3 few-shot reasoning examples
| masking           |      - Full patient context with trends
| Notices what's    |
| missing           |
+-------------------+
       |
       v
+--------------------------------------------------+
| LAYER 3: Hallucination Detector                  |
| Verifies each triggered signal against actual    |
| patient data. Removes signals not supported by   |
| reported symptoms/vitals (15 checkable mappings) |
+--------------------------------------------------+
       |
       v
+--------------------------------------------------+
| LAYER 4: Score Sanity Check                      |
| Emergency symptoms floor: score >= 70            |
| No-data ceiling: score <= 20                     |
| High score + no signals: capped at 40            |
| Low score + many signals: raised to 45           |
+--------------------------------------------------+
       |
       v
+--------------------------------------------------------------------------+
|                         SQLite (WAL mode)                                 |
| sessions | symptoms | vitals | meds | messages | alerts | risk_scores   |
|                   patient_history | investigation_gaps                    |
+--------------------------------------------------------------------------+
       |
       v
+--------------------------------------------------+
| LAYER 7: Data Completeness Check                 |
| On session conclusion, scores data quality 0-100  |
| Checks: symptoms, vitals, meds, message count    |
| Flags insufficient data for nurse review          |
| Cost: Free                                        |
+--------------------------------------------------+
       |
       v
+-------------------+
|  NURSE DASHBOARD  |
|  (React SPA +     |
|   FastAPI backend) |
|  - Risk score with |
|    5-level colors  |
|  - Symptom bars   |
|  - Medication     |
|    tracking       |
|  - CTA cards      |
|  - Recovery       |
|    timeline       |
+-------------------+
```

### Agent Coordination

Agents don't talk to each other directly. They coordinate through SQLite as shared memory:

```
Conversationalist ──writes──> symptoms, vitals, meds, messages
                                      |
                                      v (reads all of it)
Risk Assessor     ──writes──> risk_scores, investigation_gaps
                                      |
                                      v (reads score + signals + gaps)
Escalator         ──writes──> alerts
                                      |
                                      v (reads alerts)
Nurse Dashboard   <──displays─────────┘

Conversationalist ◄──reads── investigation_gaps (async feedback loop)
```

---

## Agents

### 1. Conversationalist (Complete)
- **Model:** Claude Sonnet (`claude-sonnet-4-20250514`)
- **Role:** Patient-facing clinical reasoner. NOT a data collector with a checklist.
- **Tools:** `log_symptom`, `log_vital`, `log_med_taken`, `ask_clarifying`
- **Pattern:** Anthropic SDK tool-use loop — Claude calls tools, we execute them (after validation), feed results back until Claude produces a text response.

**How it thinks:**
1. **Forms hypotheses** — "Unilateral leg swelling after hip surgery = suspect DVT"
2. **Calibrates to timeline** — "Day 1 nausea = anesthesia (normal). Day 5 nausea = possible abscess (concerning)"
3. **Notices patterns** — "Swelling + warmth + redness = infection cluster, not three independent findings"
4. **Asks the ONE discriminating question** — "Is it one leg or both?" not "rate your swelling 1-10"
5. **References prior data** — "You mentioned your pain was about a 5 earlier — has it changed?"
6. **Follows unresolved threads** — checks cross-session history for concerns that weren't resolved

**Knowledge injected each turn:**
- Surgery-specific recovery timeline (expected pain curve, milestones, red-flag context)
- Medication pharmacology (onset, peak, duration, clinical notes)
- 4 few-shot reasoning examples showing right vs wrong clinical thinking
- Full patient context with symptom trend detection
- Cross-session history (prior key findings, unresolved/resolved concerns)

### 2. Risk Assessor (Complete — Upgraded to Agentic Investigator)
- **Model:** Claude Sonnet
- **Role:** Background clinical investigator. Actively examines patient data through tool calls.
- **Pattern:** Tool-use loop with 6 investigation tools, capped at 6 iterations. Falls back to single-shot if loop fails.
- **Runs:** In a background thread after the Conversationalist replies. Patient never waits.
- **Prompt caching:** `cache_control: {"type": "ephemeral"}` on the system prompt.
- **Tools:** `get_symptom_trend`, `get_vital_trend`, `check_med_context`, `get_time_since_last`, `flag_investigation_gap`, `write_risk_alert`

**How it investigates:**
1. **Checks trends** — Uses `get_symptom_trend` and `get_vital_trend` to detect worsening, improvement, or reversal
2. **Detects medication masking** — Uses `check_med_context` to see if NSAIDs/opioids are hiding true severity
3. **Notices what's missing** — Uses `get_time_since_last` to find gaps (no mobility report = DVT risk)
4. **Flags gaps for Conversationalist** — Uses `flag_investigation_gap` to request specific questions on the next turn
5. **Writes final assessment** — Uses `write_risk_alert` with score, signals, and clinical reasoning

**Inter-agent feedback loop:**
- Risk Assessor writes to `investigation_gaps` table
- Conversationalist reads unaddressed gaps on next turn, works them naturally into conversation
- Gaps are marked as addressed (audit trail preserved)

**Error handling:**
- Aborts after 3+ tool failures, falls back to single-shot assessment
- Max 6 iterations prevents runaway loops
- Nurse dashboard always gets a score (fallback guarantees this)

**Knowledge injected each assessment:**
- Full patient context with trend detection
- Surgery-specific clinical knowledge
- Vital sign interpretation guide with clinical reasoning
- Red-flag matrix (21 signals, surgery-specific filtering)
- 5 few-shot examples: 3 reasoning patterns + 2 investigation sequences

### 3. Escalator (Complete)
- **Model:** Claude Haiku (`claude-haiku-4-5-20251001`)
- **Role:** Translates risk assessment into actionable nurse alerts
- **Input:** Risk score + triggered signals + reasoning + investigation gaps
- **Output:** JSON: `{severity, headline, actions[], reassess_in, rationale}`
- **Runs:** In background thread after Risk Assessor completes
- **Optimization:** Skips Haiku API call for very low-risk scores (≤15) — generates alert locally
- **Safety:** Validates that Haiku doesn't under-escalate — enforces minimum severity based on score
- **Design rationale:** Haiku is fast (~$0.001/call) and cheap — appropriate for a focused translation task

---

## Clinical Knowledge System

### Knowledge Base (`src/clinical_knowledge.py`)

**Recovery Timelines** — for each surgery type:
- Expected pain curve by recovery day (what's normal vs concerning)
- Recovery milestones (when to walk, when to reduce meds, when to drive)
- Surgery-specific red-flag context (DVT risk profile, infection patterns, etc.)

**Medication Pharmacology** — for common post-op meds:
- Drug class, onset, peak effect, duration, max daily dose
- Clinical reasoning notes (e.g., "ibuprofen suppresses fever — reported temp may be falsely low")

**Vital Sign Interpretation** — for each vital type:
- Normal ranges, concerning thresholds
- Clinical reasoning guidance (e.g., "HR 110 with 8/10 pain = pain-driven. HR 110 with mild pain + dyspnea = think PE")

### Red-Flag Matrix (`src/red_flags.py`)

21 typed dataclasses covering:
- **Infection:** persistent fever, high fever, wound redness, purulent discharge, wound warmth
- **Cardiovascular/DVT:** leg swelling, calf pain, tachycardia, chest pain
- **Respiratory:** shortness of breath, low SpO2, persistent cough
- **Neurological:** confusion, new numbness
- **Pain:** worsening pain, uncontrolled pain, medication ineffectiveness
- **GI:** persistent vomiting, no bowel function
- **Wound:** uncontrolled bleeding
- **Mobility:** inability to bear weight

Each flag has: signal name, description, base weight (0-100), category, urgency level, applicable surgeries, day range, and a human-readable condition for the LLM to evaluate. Validated at import time.

### Synthetic Reasoning Examples (`src/synthetic_scenarios.py`)

**Conversationalist examples** (4 scenarios) — each shows:
- What the patient says
- The WRONG response (checklist approach: log it, ask generic next question)
- The RIGHT response (hypothesis-driven: form theory, ask discriminating question)
- WHY the right approach is better (clinical reasoning explanation)

**Risk Assessor examples** (3 scenarios) — each shows:
- Patient data snapshot
- The WRONG assessment (shallow: individual findings, no pattern recognition)
- The RIGHT assessment (deep: trajectory analysis, pattern compounding, contextual scoring)

---

## Guardrail System (`src/guardrails.py`)

Eight layers of protection — 6 deterministic + 2 LLM-powered. Prompts are suggestions — guardrails are enforcement.

### Layer 1a: Emergency Keyword Bypass
- **23 regex patterns** covering: respiratory distress, cardiac events, hemorrhage, loss of consciousness, suicidal ideation, anaphylaxis, etc.
- Runs **BEFORE** any agent — fastest path to escalation
- Creates `911-now` alert immediately, regardless of what agents think
- Examples: "can't breathe", "chest pain", "bleeding won't stop", "throat is swelling"
- **Cost:** Free, 0ms

### Layer 1b: Semantic Emergency Classifier
- **Haiku LLM classifier** catches natural-language emergencies that regex misses
- Catches phrases like: "everything is going dark", "I took all my pills at once", "my heart feels like it's stopping"
- Triggers at ≥0.85 confidence threshold
- Creates `911-now` alert with LLM-generated reasoning
- **Cost:** ~$0.001, ~500ms

### Layer 2: Output Content Filter
- Scans Conversationalist's reply for three violation types:
  - **Diagnosis language:** "you probably have an infection", "this looks like DVT"
  - **Prescription language:** "you should take 800mg", "increase your dosage"
  - **Alarm language:** "go to the ER right now", "this is an emergency"
- Violating replies are replaced with safe alternatives that acknowledge concern without crossing the line
- Creates `system-error` alert so nurses see the agent attempted to diagnose/prescribe
- **Cost:** Free

### Layer 3: Hallucination Detector
- **15 signal-to-data mappings** that verify the Risk Assessor's claims against actual patient data
- Checks: Did the patient actually report this symptom? Is there a vital reading that supports this signal? Does the trend data actually show worsening?
- Hallucinated signals are removed from the assessment
- Examples caught: triggering "chest_pain" when no chest pain was reported, triggering "fever_persistent" when temperature is 99.5F
- **Cost:** Free

### Layer 4: Score Sanity Check (Expected-Symptom Cap)
- **Floor:** Emergency symptoms (chest pain, breathing difficulty, uncontrolled bleeding) can never score below 70
- **Ceiling:** No reported symptoms/vitals can never score above 20
- **Consistency:** High score (>60) with no triggered signals is capped at 40
- **Consistency:** Low score (<30) with 3+ triggered signals is raised to 45
- **Expected-symptom cap:** Day 1 normal symptoms scored as urgent; caps score at 25 when all symptoms are within expected ranges for surgery type + recovery day
- **Cost:** Free

### Layer 5: Tool Input Validator
- Validates every tool call before execution:
  - `log_symptom`: name matches alphanumeric pattern, severity clamped 0-10, free_text max 1000 chars
  - `log_vital`: type must be in valid enum (temperature, heart_rate, blood_pressure, respiratory_rate, spo2), value 0-500
  - `log_med_taken`: name matches pattern, dose required, max lengths enforced
  - `ask_clarifying`: question required, max 500 chars
- Invalid inputs are rejected and returned to Claude as errors (it can retry)
- Clamped values (e.g., severity 15 -> 10) are accepted with a warning
- **Cost:** Free

### Layer 6: Manipulation / Off-Topic Detector
- **Two-tier detection:** 13 regex patterns for prompt injection + Haiku LLM classifier for off-topic abuse
- Regex catches: "ignore your instructions", "you are now", "system prompt", role-play attempts
- Haiku catches: off-topic requests ("write me a poem", "help me with homework"), social engineering
- Returns a safe redirect reply without engaging with the manipulation
- **Cost:** Free (regex) + ~$0.001 (Haiku fallback)

### Layer 7: Data Completeness Check
- Runs on session conclusion to ensure sufficient clinical data was collected
- Scores sessions 0-100 based on: symptoms (+40), vitals (+25), medications (+15), message count (+10), severity ratings (+10)
- Creates a `monitor` alert if data is insufficient, flagging gaps for nurse review
- **Cost:** Free

---

## Memory System

### Within-Session Memory (`db.build_patient_context()`)

Every turn, each agent receives a structured clinical context string containing:
- **Session info:** Patient name, surgery type, recovery day
- **Symptom timeline:** Chronological log with timestamps and patient quotes
- **Symptom trends:** Automatic detection of WORSENING, IMPROVING, or STABLE patterns
- **Vital signs:** All measurements with timestamps
- **Medications:** What was taken and when
- **Prior alerts:** What the system has already flagged this session
- **Risk score history:** Trajectory of risk assessments

### Cross-Session Memory (`patient_history` table)

When a session ends, key findings are saved:
- Key findings (list of clinical observations)
- Risk level (low/moderate/high/critical)
- Unresolved concerns (things to follow up on)
- Resolved concerns (things that got better)
- Session summary

On the next session for the same patient, this history is injected into the context. The agents can say: "I see from your last check-in that you had some swelling. Has that gotten better?"

---

## Data Model

### SQLite with WAL Mode

All agents share state through a single SQLite database (`triage.db`). WAL (Write-Ahead Logging) mode enables concurrent reads while one writer commits. Thread-local connections (`threading.local()`) ensure Python thread safety.

### Schema (9 tables)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `session` | One per patient encounter | `surgery_type`, `recovery_day`, `patient_name` |
| `symptoms` | Logged by Conversationalist tools | `name`, `severity` (0-10), `free_text` |
| `vitals` | Temperature, HR, BP, SpO2 | `type`, `value`, `unit` |
| `meds` | Medication intake tracking | `med_name`, `dose`, `taken_at` |
| `messages` | Chat history (sliding window) | `role` (user/assistant), `content` |
| `alerts` | Escalator output for nurse | `severity`, `summary`, `recommended_action` |
| `risk_scores` | Risk Assessor output | `score` (0-100), `triggered_signals`, `reasoning` |
| `patient_history` | Cross-session memory | `key_findings`, `risk_level`, `unresolved_concerns` |
| `investigation_gaps` | Risk Assessor → Conversationalist feedback | `question`, `priority`, `addressed` |

### Constraints
- `severity` on symptoms: CHECK 0-10
- `score` on risk_scores: CHECK 0-100
- `role` on messages: CHECK IN ('user', 'assistant')
- Alert `severity`: CHECK IN ('routine', 'monitor', 'urgent', '911-now', 'system-error')
- `risk_level` on patient_history: CHECK IN ('low', 'moderate', 'high', 'critical')
- Foreign keys enforced via `PRAGMA foreign_keys=ON`

---

## Tool System

Tools are defined once in `src/tools.py` (single source of truth) and passed directly to the Anthropic SDK via the `tools` parameter. No agent framework — raw SDK.

### Available Tools

| Tool | Trigger | Fields | Guardrail |
|------|---------|--------|-----------|
| `log_symptom` | Patient describes any physical complaint | `name`, `severity` (0-10), `free_text` | Name validated, severity clamped |
| `log_vital` | Patient mentions a measurement | `type` (enum), `value`, `unit` | Type must be valid enum, value 0-500 |
| `log_med_taken` | Patient mentions taking medication | `med_name`, `dose`, `time` | Name validated, dose required |
| `ask_clarifying` | Vague symptom needs specifics | `question` | Max 500 chars |

### Tool-Use Loop

```python
while True:
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        tools=TOOL_DEFINITIONS,
        messages=messages,
    )
    tool_calls = [b for b in response.content if b.type == "tool_use"]
    if not tool_calls:
        # GUARDRAIL: Check output before returning to patient
        violation = check_output_content(reply)
        if violation:
            reply = sanitize_reply(reply, violation)
        return reply
    # GUARDRAIL: Validate inputs before execution
    for tc in tool_calls:
        validation = validate_tool_input(tc.name, tc.input)
        if not validation["valid"]:
            # Return error to Claude — it can retry
            tool_results.append({"content": f"Rejected: {errors}", "is_error": True})
        else:
            result = execute_tool(session_id, tc.name, validation["sanitized"])
            tool_results.append({"content": result})
```

---

## UI: React SPA + FastAPI Backend

### Patient Chat (`frontend/src/pages/Chat.jsx`)
- Scenario selector creates a new DB session via REST API
- Real-time chat with typing indicators and smooth scrolling
- Emergency lockout: chat input disabled after 911-now alert, red warning displayed
- Conclusion card: shows session summary, key findings, and "Start new check-in" button
- Progress bar shows conversation turn count
- JSON conclusion responses parsed and rendered as structured cards

### Nurse Dashboard (`frontend/src/pages/Dashboard.jsx`)
- Worklist view: all patient sessions with risk score, surgery type, recovery day
- Color-coded risk indicators (5-level: routine → 911-now)
- Click-through to patient detail view

### Patient Detail (`frontend/src/pages/PatientDetail.jsx`)
- **Risk score** with 5-level color coding and clinical reasoning
- **Symptom bars** with severity visualization
- **Medication tracking** with smart display
- **CTA cards** with numbered action items from Escalator
- **Recovery timeline** with chronological symptom/vital/med log
- **Alert history** with severity-coded entries

### FastAPI Backend (`api/main.py`)
- REST API serving React SPA + JSON endpoints
- Static file mounting for production (Vite build output)
- WebSocket support for real-time updates
- Background thread for risk pipeline (patient doesn't wait)
- CORS middleware for development mode

---

## File Structure

```
post-op-triage/
  api/
    main.py                       # FastAPI backend, serves React SPA + REST API
  frontend/
    src/
      pages/
        Chat.jsx                  # Patient chat interface with emergency lockout
        Dashboard.jsx             # Nurse worklist view
        PatientDetail.jsx         # Nurse detail view with risk, symptoms, CTAs
      components/
        Layout.jsx                # App shell with sidebar navigation
        NewSessionModal.jsx       # Scenario selector modal
    vite.config.js                # Vite build configuration
  src/
    __init__.py
    schema.sql                    # 9-table SQLite schema
    db.py                         # DB layer (WAL, thread-local, CRUD, context builder)
    tools.py                      # Tool definitions + executor
    guardrails.py                 # Eight-layer safety system (regex + LLM + deterministic)
    red_flags.py                  # 21 typed danger signals (dataclasses)
    clinical_knowledge.py         # Recovery timelines, drug info, vital interpretation
    synthetic_scenarios.py        # Few-shot reasoning examples for agents
    agents/
      __init__.py
      conversationalist.py        # Patient-facing reasoning agent (Sonnet, tool-use loop)
      risk_assessor.py            # Background pattern recognition agent (Sonnet, 6 tools)
      escalator.py                # Alert severity + nurse text (Haiku)
    scenarios/
      knee_day3.json              # 7 clinical scenarios covering
      knee_day7_infection.json    # all 3 surgery types, routine
      knee_day1_routine.json      # through emergency presentations
      hip_day5.json
      hip_day4_dvt.json
      appendix_day1.json
      appendix_day5_abscess.json
  tests/                          # 139 tests, all run without API calls
  docs/
    ARCHITECTURE.md               # This file
  render.yaml                     # Render deployment config
  pyproject.toml                  # Dependencies + project metadata
  .env.example                    # ANTHROPIC_API_KEY template
  triage.db                       # SQLite DB (gitignored, created at runtime)
```

---

## Build History

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | Scaffold + Conversationalist agent + initial UI | Done |
| 2 | Risk Assessor + clinical knowledge + memory + reasoning agents + 5-layer guardrails | Done |
| 3 | Risk Assessor upgrade to agentic investigator (6 tools, feedback loop) | Done |
| 4 | Escalator agent (Haiku) + 4 new scenarios (7 total) | Done |
| 5 | 139 tests + React/FastAPI rewrite + Render deployment | Done |
| 6 | 3 new guardrail layers (semantic emergency, manipulation detector, data completeness) | Done |
| 7 | Documentation + demo preparation | Done |

---

## Key Design Decisions

### Why no agent framework?
Raw Anthropic SDK keeps the implementation transparent — interviewers can read every line. No magic, no abstraction layers. The tool-use loop is ~30 lines of Python.

### Why reasoning agents instead of rule engines?
A rule engine can check "temperature > 101.5 = flag." But it can't reason: "Temperature 100.2 on Day 7 in a patient taking ibuprofen (which suppresses fever) whose pain just reversed from improving to worsening = likely infection even though the temp alone looks borderline." The LLM's value is judgment, not classification.

### Why few-shot reasoning examples?
Prompts that say "think carefully" produce vague outputs. Prompts that show WRONG thinking vs RIGHT thinking with explicit reasoning teach the model the specific cognitive patterns we want. The examples encode clinical judgment that the model can generalize from.

### Why eight guardrail layers?
Prompts are suggestions — the model can ignore them. Guardrails are code that runs after the model, enforcing constraints the model can't override. Each layer catches a different failure mode:
- Layer 1a catches emergencies the model might underreact to (regex, instant)
- Layer 1b catches natural-language emergencies regex misses (Haiku LLM, ~500ms)
- Layer 2 catches the model overstepping its role
- Layer 3 catches the model making things up
- Layer 4 catches the model being inconsistent
- Layer 5 catches malformed data before it enters the database
- Layer 6 catches prompt injection and off-topic abuse (regex + Haiku LLM)
- Layer 7 ensures sufficient clinical data was collected before session ends

### Why SQLite instead of a message broker?
All three agents run in the same process. SQLite with WAL mode handles concurrent reads/writes cleanly. No infrastructure to deploy. The database IS the coordination layer — agents read each other's outputs directly.

### Why three agents instead of one?
Separation of concerns: the Conversationalist optimizes for empathy and investigation (Sonnet, conversational), the Risk Assessor optimizes for pattern recognition (Sonnet, analytical), and the Escalator optimizes for fast classification (Haiku, cheap). Each agent has a focused prompt, distinct knowledge injection, and can be tested independently.

### Why background risk assessment?
Without it, the patient waits 5-11 seconds per message (Conversationalist + Risk Assessor + Escalator in series). With background processing, perceived latency drops to 2-3 seconds (just the Conversationalist). The nurse dashboard picks up alerts asynchronously.

### Why cross-session memory?
A patient checking in on Day 5 shouldn't start from scratch. If they had swelling on Day 3 that was flagged as unresolved, the Day 5 agents should follow up on it. Memory transforms the system from "three conversations" into "one patient journey."

### Why thread-local DB connections?
Python's `sqlite3` module raises errors when connections are shared across threads. `threading.local()` gives each thread its own connection. Combined with WAL mode, this allows the FastAPI request thread and the background assessment thread to operate concurrently.

### Why sliding window (20 messages)?
Unbounded conversation history grows the context window every turn, increasing latency and cost. 20 messages (~10 turns) keeps enough context for clinical continuity without degrading performance.

---

## Error Handling Strategy

- **Fail open, not silent:** If any agent crashes, the error surfaces as a `system-error` alert on the nurse dashboard with the failure details and recommended action.
- **Pipeline isolation:** Each agent call is wrapped in try/catch. A Risk Assessor failure doesn't block the Conversationalist reply — the patient still gets their response.
- **Tool errors:** `execute_tool` catches exceptions and returns error strings to Claude, which can retry or acknowledge gracefully.
- **Guardrail transparency:** When guardrails adjust an assessment, the adjustment is appended to the reasoning field so nurses can see what was changed and why.

---

## Security Considerations

- **Eight-layer guardrail system:** Emergency bypass (regex + LLM), output filtering, hallucination detection, score validation, input sanitization, manipulation detection (regex + LLM), data completeness
- **Prompt injection defense:** Layer 6 detects prompt injection attempts with 13 regex patterns + Haiku LLM classifier for off-topic abuse. The Conversationalist system prompt explicitly instructs Claude to treat all patient input as clinical data, never as system instructions.
- **Two-tier emergency detection:** Fast regex (0ms) + Haiku semantic classifier (~500ms) catches both keyword and natural-language emergencies.
- **Output enforcement:** Even if the prompt fails, Layer 2 catches diagnosis/prescription language at the code level.
- **Hallucination prevention:** Layer 3 verifies every risk signal against actual data — the model can't invent symptoms.
- **Input validation:** Severity clamped to 0-10 in code + CHECK constraint in SQL. Vital types restricted to valid enum. Alert severity restricted to valid enum.
- **No real patient data:** Educational demo with fictional scenarios only.
- **API key handling:** `.env` file (gitignored) + `python-dotenv` for loading.

---

## Running the App

```bash
# 1. Clone and install
git clone https://github.com/ankitasinha015/post-op-triage.git
cd post-op-triage
pip install -e ".[dev]"

# 2. Set up API key
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 3. Build the frontend
cd frontend && npm install && npm run build && cd ..

# 4. Launch
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

The app opens at `http://localhost:8000`. The React SPA serves as both the patient chat interface and the nurse dashboard. Select a scenario, start a new check-in, and chat as the patient. The nurse dashboard updates as risk assessments complete in the background.

**Live demo:** https://ai-triage-nurse.onrender.com

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `anthropic` | >=0.40 | Claude API SDK (tool use, prompt caching) |
| `fastapi` | >=0.100 | REST API + WebSocket backend |
| `uvicorn` | >=0.20 | ASGI server |
| `python-dotenv` | >=1.0 | .env file loading |
| `react` | 18 | Frontend SPA framework |
| `tailwindcss` | 3 | Utility-first CSS |
| `vite` | 5 | Frontend build tool |
| `pytest` | >=8.0 (dev) | Test runner (139 tests) |
| Python | >=3.11 | Type hints, match statements |
| Node.js | >=18 | Frontend build |
