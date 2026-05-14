# AI Triage Nurse — Post-Op Recovery Agent

## Overview

A multi-agent AI system that simulates a post-operative recovery triage nurse. A patient chats naturally about how they're feeling; three Claude-powered agents collaborate behind the scenes to collect symptoms, assess risk, and escalate alerts to a real-time nurse dashboard.

**Purpose:** Portfolio project demonstrating multi-agent orchestration, Anthropic SDK tool use, and structured clinical data extraction — built for technical interviewer audiences.

**Disclaimer:** Educational demo only. Not medical advice. Not for real patient care.

---

## Architecture

### Three-Agent Pipeline

```
Patient Chat Input
       |
       v
+-------------------+       +-----------------------+       +-------------------+
| CONVERSATIONALIST |  -->  |    RISK ASSESSOR      |  -->  |    ESCALATOR      |
| (Claude Sonnet)   |       |    (Claude Sonnet)    |       |    (Claude Haiku) |
|                   |       |                       |       |                   |
| - Empathetic chat |       | - Red-flag matrix     |       | - Alert severity  |
| - Symptom logging |       | - Risk score 0-100    |       | - Action text     |
| - Tool use loop   |       | - Signal detection    |       | - Nurse summary   |
+-------------------+       +-----------------------+       +-------------------+
       |                            |                              |
       v                            v                              v
+--------------------------------------------------------------------------+
|                         SQLite (WAL mode)                                 |
|  sessions | symptoms | vitals | meds | messages | alerts | risk_scores   |
+--------------------------------------------------------------------------+
       |
       v
+-------------------+
|  NURSE DASHBOARD  |
|  (Streamlit)      |
|  - Alert banner   |
|  - Risk sparkline |
|  - Timeline       |
+-------------------+
```

### Agent Responsibilities

#### 1. Conversationalist (Evening 1 — Complete)
- **Model:** Claude Sonnet (`claude-sonnet-4-20250514`)
- **Role:** Patient-facing. Warm, empathetic conversation. Collects symptoms via structured tool calls.
- **Tools:** `log_symptom`, `log_vital`, `log_med_taken`, `ask_clarifying`
- **Pattern:** Anthropic SDK tool-use loop — Claude calls tools, we execute them, feed results back until Claude produces a text response.
- **Context window:** Sliding window of last 20 messages to cap growth.
- **Safety:** System prompt treats all patient input as clinical data, never as instructions (prompt injection defense).

#### 2. Risk Assessor (Evening 2 — Planned)
- **Model:** Claude Sonnet
- **Role:** Background evaluation. Runs after each Conversationalist turn.
- **Input:** Full session state (symptoms, vitals, meds) + red-flag matrix
- **Output:** Risk score (0-100) + list of triggered signals + reasoning
- **Red-flag matrix:** Typed dataclasses in `src/red_flags.py`, validated at import time
- **Prompt caching:** 1-hour TTL on the red-flag matrix (static reference data)

#### 3. Escalator (Evening 3 — Planned)
- **Model:** Claude Haiku (`claude-haiku-4-5-20251001`)
- **Role:** Translates risk assessment into actionable nurse alerts
- **Input:** Risk score + triggered signals + session context
- **Output:** Alert severity (`routine` | `monitor` | `urgent` | `911-now`) + summary + recommended action
- **Design rationale:** Haiku is fast and cheap — appropriate for a narrow classification task

### Background Processing

The Conversationalist streams its reply to the patient first (~2-3s perceived latency). The Risk Assessor and Escalator run in a background thread afterward, so the patient never waits for the full pipeline (5-11s). The nurse dashboard picks up new alerts on its next auto-refresh cycle (every 3 seconds).

---

## Data Model

### SQLite with WAL Mode

All agents share state through a single SQLite database (`triage.db`). WAL (Write-Ahead Logging) mode enables concurrent reads while one writer commits. Thread-local connections (`threading.local()`) ensure Python thread safety.

### Schema (7 tables)

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `session` | One per patient encounter | `surgery_type`, `recovery_day`, `patient_name` |
| `symptoms` | Logged by Conversationalist tools | `name`, `severity` (0-10), `free_text` |
| `vitals` | Temperature, HR, BP, SpO2 | `type`, `value`, `unit` |
| `meds` | Medication intake tracking | `med_name`, `dose`, `taken_at` |
| `messages` | Chat history (sliding window) | `role` (user/assistant), `content` |
| `alerts` | Escalator output for nurse | `severity`, `summary`, `recommended_action` |
| `risk_scores` | Risk Assessor output | `score` (0-100), `triggered_signals`, `reasoning` |

### Constraints
- `severity` on symptoms: CHECK 0-10
- `score` on risk_scores: CHECK 0-100
- `role` on messages: CHECK IN ('user', 'assistant')
- Alert `severity`: CHECK IN ('routine', 'monitor', 'urgent', '911-now', 'system-error')
- Foreign keys enforced via `PRAGMA foreign_keys=ON`

---

## Tool System

Tools are defined once in `src/tools.py` (single source of truth) and passed directly to the Anthropic SDK via the `tools` parameter. No agent framework — raw SDK.

### Available Tools

| Tool | Trigger | Fields |
|------|---------|--------|
| `log_symptom` | Patient describes any physical complaint | `name`, `severity` (0-10), `free_text` |
| `log_vital` | Patient mentions a measurement | `type` (enum), `value`, `unit` |
| `log_med_taken` | Patient mentions taking medication | `med_name`, `dose`, `time` |
| `ask_clarifying` | Vague symptom needs specifics | `question` |

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
        # Claude produced a text reply — we're done
        return text_reply
    # Execute tools, append results, loop back
    for tc in tool_calls:
        result = execute_tool(session_id, tc.name, tc.input)
        tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})
    messages.append({"role": "user", "content": tool_results})
```

---

## UI: Streamlit Two-Column Layout

### Left Column — Patient Chat
- Scenario selector dropdown (knee day 3, appendix day 1, hip day 5)
- "Start New Session" button creates a new DB session
- `st.chat_input` / `st.chat_message` for natural conversation
- Error handling: agent failures surface as `system-error` alerts on the dashboard

### Right Column — Nurse Dashboard
- `@st.fragment(run_every=3)` — auto-refreshes every 3 seconds without disrupting chat
- **Alert banner:** Color-coded by severity (green/yellow/orange/red/grey)
- **Risk score sparkline:** Last 10 scores as a line chart
- **Recovery timeline:** Chronological log of symptoms, vitals, meds with emoji indicators
- **Alert history:** Expandable section showing all past alerts

---

## File Structure

```
post-op-triage/
  app.py                          # Streamlit entry point
  pyproject.toml                  # Dependencies + project metadata
  .env.example                    # ANTHROPIC_API_KEY template
  .gitignore                      # Python + SQLite exclusions
  triage.db                       # SQLite DB (gitignored, created at runtime)
  docs/
    ARCHITECTURE.md               # This file
  src/
    __init__.py
    schema.sql                    # 7-table SQLite schema
    db.py                         # DB layer (WAL, thread-local, CRUD)
    tools.py                      # Tool definitions + executor
    red_flags.py                  # [Evening 2] Red-flag matrix (typed dataclasses)
    agents/
      __init__.py
      conversationalist.py        # Patient-facing agent (Sonnet, tool-use loop)
      risk_assessor.py            # [Evening 2] Background risk evaluation
      escalator.py                # [Evening 3] Alert severity + nurse text
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
| 2 | Risk Assessor agent + red-flag matrix (`red_flags.py`) | Planned |
| 3 | Escalator agent (Haiku) + alert UI integration | Planned |
| 4 | Expand toolset + add more scenarios | Planned |
| 5 | Prompt caching (1-hour TTL) + pytest fixtures | Planned |
| 6 | README + demo recording | Planned |
| 7 | Buffer / voice input exploration | Planned |

---

## Key Design Decisions

### Why no agent framework?
Raw Anthropic SDK keeps the implementation transparent — interviewers can read every line. No magic, no abstraction layers. The tool-use loop is ~30 lines of Python.

### Why SQLite instead of a message broker?
All three agents run in the same process. SQLite with WAL mode handles concurrent reads/writes cleanly. No infrastructure to deploy. The database IS the coordination layer — agents read each other's outputs directly.

### Why three agents instead of one?
Separation of concerns: the Conversationalist optimizes for empathy and data collection (Sonnet, conversational), the Risk Assessor optimizes for clinical accuracy (Sonnet, analytical), and the Escalator optimizes for fast classification (Haiku, cheap). Each agent has a focused prompt and can be tested independently.

### Why background risk assessment?
Without it, the patient waits 5-11 seconds per message (Conversationalist + Risk Assessor + Escalator in series). With background processing, perceived latency drops to 2-3 seconds (just the Conversationalist). The nurse dashboard picks up alerts asynchronously.

### Why thread-local DB connections?
Python's `sqlite3` module raises errors when connections are shared across threads. `threading.local()` gives each thread its own connection. Combined with WAL mode, this allows the main Streamlit thread and the background assessment thread to operate concurrently.

### Why sliding window (20 messages)?
Unbounded conversation history grows the context window every turn, increasing latency and cost. 20 messages (~10 turns) keeps enough context for clinical continuity without degrading performance.

---

## Error Handling Strategy

- **Fail open, not silent:** If any agent crashes, the error surfaces as a `system-error` alert on the nurse dashboard with the failure details and recommended action.
- **Pipeline isolation:** Each agent call is wrapped in try/catch. A Risk Assessor failure doesn't block the Conversationalist reply — the patient still gets their response.
- **Tool errors:** `execute_tool` catches exceptions and returns error strings to Claude, which can retry or acknowledge gracefully.

---

## Security Considerations

- **Prompt injection defense:** The Conversationalist system prompt explicitly instructs Claude to treat all patient input as clinical data, never as system instructions.
- **Input validation:** Severity clamped to 0-10 in code + CHECK constraint in SQL. Alert severity restricted to enum values via CHECK constraint.
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
| `anthropic` | >=0.40 | Claude API SDK (tool use, streaming) |
| `streamlit` | >=1.33 | Web UI (chat, dashboard, fragments) |
| `python-dotenv` | >=1.0 | .env file loading |
| `pytest` | >=8.0 (dev) | Test runner |
| Python | >=3.11 | Type hints, match statements |
