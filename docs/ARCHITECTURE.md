# AI Triage Nurse — Post-Op Recovery Agent

## Overview

A multi-agent AI system that simulates a post-operative recovery triage nurse. A patient chats naturally about how they're feeling; three Claude-powered agents collaborate behind the scenes to collect symptoms, assess risk, and escalate alerts to a real-time nurse dashboard.

Each agent is a **clinical reasoner**, not a checklist-follower. They form hypotheses, detect patterns, reason about trajectories, and make judgment calls — powered by clinical knowledge, synthetic reasoning examples, and a five-layer guardrail system.

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
| LAYER 1: Emergency Keyword Bypass                |
| 23 regex patterns (chest pain, can't breathe,    |
| uncontrolled bleeding, suicidal ideation, etc.)   |
| Triggers 911-NOW alert BEFORE agents run          |
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
|                          patient_history                                  |
+--------------------------------------------------------------------------+
       |
       v
+-------------------+
|  NURSE DASHBOARD  |
|  (Streamlit)      |
|  Auto-refresh 3s  |
|  - Alert banner   |
|  - Risk sparkline |
|  - Assessment     |
|    reasoning      |
|  - Triggered      |
|    signals        |
|  - Timeline       |
|  - Alert history  |
+-------------------+
```

### Agent Coordination

Agents don't talk to each other directly. They coordinate through SQLite as shared memory:

```
Conversationalist ──writes──> symptoms, vitals, meds, messages
                                      |
                                      v (reads all of it)
Risk Assessor     ──writes──> risk_scores
                                      |
                                      v (reads score + signals)
Escalator         ──writes──> alerts    [Evening 3 — planned]
                                      |
                                      v (reads alerts)
Nurse Dashboard   <──displays─────────┘
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

### 2. Risk Assessor (Complete)
- **Model:** Claude Sonnet
- **Role:** Background clinical analyst. Thinks like a nurse with 20 years of experience reviewing a chart.
- **Pattern:** Single API call (no tool loop). Returns structured JSON: `{score, triggered_signals, reasoning}`.
- **Runs:** In a background thread after the Conversationalist replies. Patient never waits.
- **Prompt caching:** `cache_control: {"type": "ephemeral"}` on the system prompt (red-flag matrix is static reference data).

**How it thinks:**
1. **Reads trajectories** — "Pain reversed from improving (3/10) to worsening (6/10)"
2. **Detects compounding patterns** — "Swelling + calf pain + tachycardia = DVT triad, not three mild findings"
3. **Accounts for medication masking** — "Patient on ibuprofen with temp 100.2F — true temperature may be higher"
4. **Notices what's MISSING** — "Day 5 post-knee, no mention of mobility = DVT risk factor"
5. **Calibrates to surgery and day** — "Day 1 appendectomy nausea is a 15, not a 50"
6. **Won't cry wolf** — over-scoring normal recovery erodes trust in the alert system

**Knowledge injected each assessment:**
- Full patient context with trend detection
- Surgery-specific clinical knowledge
- Vital sign interpretation guide with clinical reasoning
- Red-flag matrix (21 signals, surgery-specific filtering)
- 3 few-shot reasoning examples showing shallow vs deep clinical reasoning

### 3. Escalator (Evening 3 — Planned)
- **Model:** Claude Haiku (`claude-haiku-4-5-20251001`)
- **Role:** Translates risk assessment into actionable nurse alerts
- **Input:** Risk score + triggered signals + session context
- **Output:** Alert severity (`routine` | `monitor` | `urgent` | `911-now`) + summary + recommended action
- **Design rationale:** Haiku is fast and cheap — appropriate for a narrow classification task

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

Five layers of protection. Prompts are suggestions — guardrails are enforcement.

### Layer 1: Emergency Keyword Bypass
- **23 regex patterns** covering: respiratory distress, cardiac events, hemorrhage, loss of consciousness, suicidal ideation, anaphylaxis, etc.
- Runs **BEFORE** any agent — fastest path to escalation
- Creates `911-now` alert immediately, regardless of what agents think
- Examples: "can't breathe", "chest pain", "bleeding won't stop", "throat is swelling"

### Layer 2: Output Content Filter
- Scans Conversationalist's reply for three violation types:
  - **Diagnosis language:** "you probably have an infection", "this looks like DVT"
  - **Prescription language:** "you should take 800mg", "increase your dosage"
  - **Alarm language:** "go to the ER right now", "this is an emergency"
- Violating replies are replaced with safe alternatives that acknowledge concern without crossing the line
- Creates `system-error` alert so nurses see the agent attempted to diagnose/prescribe

### Layer 3: Hallucination Detector
- **15 signal-to-data mappings** that verify the Risk Assessor's claims against actual patient data
- Checks: Did the patient actually report this symptom? Is there a vital reading that supports this signal? Does the trend data actually show worsening?
- Hallucinated signals are removed from the assessment
- Examples caught: triggering "chest_pain" when no chest pain was reported, triggering "fever_persistent" when temperature is 99.5F

### Layer 4: Score Sanity Check
- **Floor:** Emergency symptoms (chest pain, breathing difficulty, uncontrolled bleeding) can never score below 70
- **Ceiling:** No reported symptoms/vitals can never score above 20
- **Consistency:** High score (>60) with no triggered signals is capped at 40
- **Consistency:** Low score (<30) with 3+ triggered signals is raised to 45

### Layer 5: Tool Input Validator
- Validates every tool call before execution:
  - `log_symptom`: name matches alphanumeric pattern, severity clamped 0-10, free_text max 1000 chars
  - `log_vital`: type must be in valid enum (temperature, heart_rate, blood_pressure, respiratory_rate, spo2), value 0-500
  - `log_med_taken`: name matches pattern, dose required, max lengths enforced
  - `ask_clarifying`: question required, max 500 chars
- Invalid inputs are rejected and returned to Claude as errors (it can retry)
- Clamped values (e.g., severity 15 -> 10) are accepted with a warning

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

### Schema (8 tables)

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

## UI: Streamlit Two-Column Layout

### Left Column -- Patient Chat
- Scenario selector dropdown (knee day 3, appendix day 1, hip day 5)
- "Start New Session" button creates a new DB session
- `st.chat_input` / `st.chat_message` for natural conversation
- Emergency bypass runs on every message before agents
- Error handling: agent failures surface as `system-error` alerts on the dashboard

### Right Column -- Nurse Dashboard
- `@st.fragment(run_every=3)` -- auto-refreshes every 3 seconds without disrupting chat
- **Alert banner:** Color-coded by severity (green/yellow/orange/red/grey)
- **Risk score sparkline:** Last 10 scores as a line chart
- **Latest assessment reasoning:** Shows the Risk Assessor's clinical reasoning
- **Triggered signals:** Lists which red flags matched
- **Recovery timeline:** Chronological log of symptoms, vitals, meds with emoji indicators
- **Alert history:** Expandable section showing all past alerts

---

## File Structure

```
post-op-triage/
  app.py                          # Streamlit entry point + pipeline orchestration
  pyproject.toml                  # Dependencies + project metadata
  .env.example                    # ANTHROPIC_API_KEY template
  .gitignore                      # Python + SQLite exclusions
  triage.db                       # SQLite DB (gitignored, created at runtime)
  docs/
    ARCHITECTURE.md               # This file
  src/
    __init__.py
    schema.sql                    # 8-table SQLite schema
    db.py                         # DB layer (WAL, thread-local, CRUD, context builder)
    tools.py                      # Tool definitions + executor
    guardrails.py                 # Five-layer safety system
    red_flags.py                  # 21 typed danger signals (dataclasses)
    clinical_knowledge.py         # Recovery timelines, drug info, vital interpretation
    synthetic_scenarios.py        # Few-shot reasoning examples for agents
    agents/
      __init__.py
      conversationalist.py        # Patient-facing reasoning agent (Sonnet, tool-use loop)
      risk_assessor.py            # Background pattern recognition agent (Sonnet)
      escalator.py                # [Evening 3] Alert severity + nurse text (Haiku)
    scenarios/
      knee_day3.json              # Day 3 post knee replacement (Alex)
      appendix_day1.json          # Day 1 post appendectomy (Jordan)
      hip_day5.json               # Day 5 post hip replacement (Sam)
  tests/
    __init__.py
    test_pipeline.py              # [Evening 5] Scenario-based pytest fixtures
```

---

## Build Plan (7 Evenings)

| Evening | Focus | Status |
|---------|-------|--------|
| 1 | Scaffold + Conversationalist agent + Streamlit UI | Done |
| 2 | Risk Assessor + clinical knowledge + memory + reasoning agents + guardrails | Done |
| 3 | Escalator agent (Haiku) + alert UI integration | Planned |
| 4 | Expand toolset + add more scenarios | Planned |
| 5 | Prompt caching (1-hour TTL) + pytest fixtures | Planned |
| 6 | README + demo recording | Planned |
| 7 | Buffer / voice input exploration | Planned |

---

## Key Design Decisions

### Why no agent framework?
Raw Anthropic SDK keeps the implementation transparent — interviewers can read every line. No magic, no abstraction layers. The tool-use loop is ~30 lines of Python.

### Why reasoning agents instead of rule engines?
A rule engine can check "temperature > 101.5 = flag." But it can't reason: "Temperature 100.2 on Day 7 in a patient taking ibuprofen (which suppresses fever) whose pain just reversed from improving to worsening = likely infection even though the temp alone looks borderline." The LLM's value is judgment, not classification.

### Why few-shot reasoning examples?
Prompts that say "think carefully" produce vague outputs. Prompts that show WRONG thinking vs RIGHT thinking with explicit reasoning teach the model the specific cognitive patterns we want. The examples encode clinical judgment that the model can generalize from.

### Why five guardrail layers?
Prompts are suggestions — the model can ignore them. Guardrails are code that runs after the model, enforcing constraints the model can't override. Each layer catches a different failure mode:
- Layer 1 catches emergencies the model might underreact to
- Layer 2 catches the model overstepping its role
- Layer 3 catches the model making things up
- Layer 4 catches the model being inconsistent
- Layer 5 catches malformed data before it enters the database

### Why SQLite instead of a message broker?
All three agents run in the same process. SQLite with WAL mode handles concurrent reads/writes cleanly. No infrastructure to deploy. The database IS the coordination layer — agents read each other's outputs directly.

### Why three agents instead of one?
Separation of concerns: the Conversationalist optimizes for empathy and investigation (Sonnet, conversational), the Risk Assessor optimizes for pattern recognition (Sonnet, analytical), and the Escalator optimizes for fast classification (Haiku, cheap). Each agent has a focused prompt, distinct knowledge injection, and can be tested independently.

### Why background risk assessment?
Without it, the patient waits 5-11 seconds per message (Conversationalist + Risk Assessor + Escalator in series). With background processing, perceived latency drops to 2-3 seconds (just the Conversationalist). The nurse dashboard picks up alerts asynchronously.

### Why cross-session memory?
A patient checking in on Day 5 shouldn't start from scratch. If they had swelling on Day 3 that was flagged as unresolved, the Day 5 agents should follow up on it. Memory transforms the system from "three conversations" into "one patient journey."

### Why thread-local DB connections?
Python's `sqlite3` module raises errors when connections are shared across threads. `threading.local()` gives each thread its own connection. Combined with WAL mode, this allows the main Streamlit thread and the background assessment thread to operate concurrently.

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

- **Five-layer guardrail system:** Emergency bypass, output filtering, hallucination detection, score validation, input sanitization
- **Prompt injection defense:** The Conversationalist system prompt explicitly instructs Claude to treat all patient input as clinical data, never as system instructions.
- **Output enforcement:** Even if the prompt fails, Layer 2 catches diagnosis/prescription language at the code level.
- **Hallucination prevention:** Layer 3 verifies every risk signal against actual data — the model can't invent symptoms.
- **Input validation:** Severity clamped to 0-10 in code + CHECK constraint in SQL. Vital types restricted to valid enum. Alert severity restricted to valid enum.
- **No real patient data:** Educational demo with fictional scenarios only.
- **API key handling:** `.env` file (gitignored) + `python-dotenv` for loading.

---

## Running the App

```bash
# 1. Clone and install
git clone <repo-url>
cd post-op-triage
pip install -e ".[dev]"

# 2. Set up API key
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 3. Launch
streamlit run app.py
```

The app opens at `http://localhost:8501`. Select a scenario, click "Start New Session", and chat as the patient. The nurse dashboard on the right updates automatically.

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `anthropic` | >=0.40 | Claude API SDK (tool use, prompt caching) |
| `streamlit` | >=1.33 | Web UI (chat, dashboard, fragments) |
| `python-dotenv` | >=1.0 | .env file loading |
| `pytest` | >=8.0 (dev) | Test runner |
| Python | >=3.11 | Type hints, match statements |
