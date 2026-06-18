# AI Triage Nurse — Post-Op Recovery Agent

A multi-agent AI system that simulates a post-operative recovery triage nurse. Patients chat naturally about how they're feeling; three Claude-powered agents collaborate behind the scenes to collect symptoms, investigate clinical patterns, and escalate alerts to a real-time nurse dashboard.

**Live demo:** https://ai-triage-nurse.onrender.com

**This is not medical advice.** It's a portfolio project demonstrating multi-agent architecture, clinical reasoning patterns, and AI safety guardrails.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Anthropic](https://img.shields.io/badge/Claude-Sonnet%204.5%20%2B%20Haiku%204.5-purple)
![React](https://img.shields.io/badge/React-18-61dafb)
![Tests](https://img.shields.io/badge/Tests-139%20passing-brightgreen)

---

## What Makes This Interesting

Most LLM projects wire up a single model to a prompt. This one coordinates **three specialized agents** that communicate through shared state, investigate autonomously, and influence each other's behavior across conversation turns.

**The architectural centerpiece:** The Risk Assessor doesn't just score data — it actively investigates through tool calls, detects medication masking, notices missing data, and flags questions for the Conversationalist to ask on the next turn. Two agents that make each other smarter through a shared database, not hardcoded handoffs.

### Key Technical Decisions

| Decision | Why |
|----------|-----|
| **Raw Anthropic SDK** (no LangChain/LangGraph) | Full visibility into tool-use loops, state management, and guardrails. Frameworks abstract the parts I wanted to understand. |
| **SQLite as coordination layer** | Agents read each other's outputs through DB queries. No message bus, no direct calls. Simple, auditable, concurrent (WAL mode). |
| **No vector database** | Knowledge base is ~6,800 tokens (3 surgeries, 4 drugs, 21 red flags). That's 3.4% of Claude's 200K context. RAG would add complexity with zero benefit at this scale. |
| **Hybrid risk scoring** | LLM proposes a score, deterministic guardrails enforce expected ranges per surgery type and recovery day. Prevents both over- and under-scoring. |
| **Three models, not one** | Conversationalist (Sonnet) for empathy. Risk Assessor (Sonnet) for pattern detection. Escalator (Haiku) for fast, cheap alert translation. Each has a focused prompt and can be tested independently. |

---

## Architecture

```
Patient message arrives
       |
       v
  [Layer 1a: Emergency Bypass] ──── 23 regex patterns, instant, free
       |
       v
  [Layer 1b: Semantic Emergency] ── Haiku classifier, catches natural language
       |
       v
  [Layer 6: Manipulation Detector] ── blocks prompt injection + off-topic
       |
       v
  CONVERSATIONALIST (Claude Sonnet 4.5, tool-use loop)
  - Forms hypotheses about symptoms
  - Asks discriminating questions (not checklists)
  - Reads investigation gaps from Risk Assessor
  - Logs structured data via 4 tools
  - Greets returning patients with prior session context
       |
       |  (background thread, async)
       v
  RISK ASSESSOR (Claude Sonnet 4.5, tool-use loop)
  - 6 investigation tools: trends, medication masking, gap detection
  - Autonomously decides what to examine
  - Flags questions for Conversationalist via investigation_gaps table
  - Writes risk score + clinical reasoning
       |
       v
  GUARDRAILS (8 layers, 6 deterministic + 2 LLM)
  - Hallucination detector removes unsupported signals
  - Expected-symptom cap prevents over-scoring normal recovery
  - Data completeness check on session conclusion
  - Writes adjusted score back to DB
       |
       v
  ESCALATOR (Claude Haiku 4.5)
  - Translates risk assessment into nurse-facing alert
  - CTA matrix: specific actions per severity tier
  - Reassessment windows (routine=next shift, critical=30min, 911=continuous)
       |
       v
  NURSE DASHBOARD (React SPA, FastAPI backend)
  - Risk score with 5-level color coding
  - Symptom bars with severity visualization
  - Medication tracking with smart display
  - CTA cards with numbered action items
  - Recovery timeline
```

### Inter-Agent Feedback Loop

```
Risk Assessor ──writes──> investigation_gaps table
                                    |
                                    v (next patient message)
Conversationalist ──reads──> works gaps naturally into conversation
```

The Risk Assessor might flag: *"Ask about wound drainage character — is it serous or purulent?"*

The Conversationalist picks this up and asks naturally: *"You mentioned some drainage from your incision. Can you describe what it looks like — is it thin and watery, or thicker?"*

The patient never knows there are two agents collaborating.

### Cross-Session Patient History

Returning patients are greeted with context from prior sessions. The system tracks unresolved concerns, compares symptom trajectories across visits, and avoids re-asking the same generic opening questions. A patient checking in for the second time feels continuity, not repetition.

---

## Safety: Eight-Layer Guardrail System

Six layers are free and instant (regex, DB lookups, range checks). Two use Haiku for semantic classification (~$0.001 each, ~500ms). Defense in depth: if the prompt fails, deterministic guardrails catch it.

| Layer | What it catches | When it runs | Cost |
|-------|----------------|-------------|------|
| **1a. Emergency Bypass** | "can't breathe", "chest pain", "bleeding won't stop" (23 regex patterns) | Before any agent | Free, 0ms |
| **1b. Semantic Emergency** | "everything is going dark", "I took all my pills at once" — natural language emergencies regex misses | Before any agent | ~$0.001, ~500ms |
| **2. Output Filter** | Diagnosis language ("you have DVT"), prescription language ("take 800mg") | After Conversationalist reply | Free |
| **3. Hallucination Detector** | Risk Assessor claims signals not supported by patient data | After Risk Assessor | Free |
| **4. Expected-Symptom Cap** | Day 1 normal symptoms scored as urgent; caps score at 25 when all symptoms are within expected ranges for surgery type + recovery day | After Risk Assessor | Free |
| **5. Tool Input Validator** | Severity of 50/10, SQL injection in symptom names | Before tool execution | Free |
| **6. Manipulation Detector** | Prompt injection ("ignore your instructions"), off-topic abuse ("write me a poem") | Before Conversationalist | ~$0.001 |
| **7. Data Completeness** | Session ends with no symptoms, no vitals, or no actionable clinical data collected | On session conclusion | Free |

### Nurse CTA Matrix

The Escalator maps severity tiers to specific nurse actions:

| Tier | Actions | Reassess |
|------|---------|----------|
| **Routine** | Continue monitoring, encourage ambulation | Next shift |
| **Monitor** | Document, increase monitoring frequency, educate patient | 4-8 hours |
| **Urgent** | Focused assessment, full vitals, notify attending with SBAR | 1-2 hours |
| **Critical** | Assess immediately, call surgeon NOW with SBAR, continuous monitoring | 30 minutes |
| **911-Now** | Call 911/rapid response, maintain airway, crash cart | Continuous |

---

## Clinical Knowledge System

Not a rule engine. Reference knowledge that agents use to reason — the same way a nurse consults training.

- **3 surgery types** with expected pain curves, milestones, and surgery-specific red flags
- **Expected symptom ranges** per surgery type and recovery day (Day 1-7) for deterministic guardrail scoring
- **4 medications** with pharmacology, masking effects, and clinical reasoning notes
- **4 vital sign types** with interpretation guides and contextual reasoning
- **21 red-flag signals** filtered by surgery type and recovery day
- **7 few-shot examples** teaching hypothesis-driven thinking (not checklist behavior)

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/ankitasinha015/post-op-triage.git
cd post-op-triage
pip install -e ".[dev]"

# Set your API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Build the frontend
cd frontend && npm install && npm run build && cd ..

# Run the app
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000

# Run tests (no API key needed)
pytest tests/ -v
```

### Requirements
- Python 3.11+
- Node.js 18+ (for frontend build)
- Anthropic API key (Claude Sonnet 4.5 + Haiku 4.5 access)
- ~$0.25 per full conversation (10 patient messages)

---

## Project Structure

```
post-op-triage/
  api/
    main.py                         # FastAPI backend, serves React SPA + API
  frontend/
    src/
      pages/
        Chat.jsx                    # Patient chat interface
        PatientDetail.jsx           # Nurse detail view with risk score, symptoms, CTAs
      components/
        Layout.jsx                  # App shell with sidebar navigation
  src/
    db.py                           # SQLite layer, thread-local connections, WAL mode
    schema.sql                      # 9 tables including investigation_gaps
    tools.py                        # Conversationalist tool definitions + execution
    red_flags.py                    # 21-signal red flag matrix (typed dataclasses)
    clinical_knowledge.py           # Surgery timelines, med pharmacology, expected symptom ranges
    guardrails.py                   # Eight-layer safety system (regex + LLM + deterministic)
    synthetic_scenarios.py          # Few-shot reasoning examples for agents
    agents/
      conversationalist.py          # Patient-facing agent (Sonnet 4.5, tool-use loop)
      risk_assessor.py              # Clinical investigator (Sonnet 4.5, 6 tools, tool-use loop)
      escalator.py                  # Alert translator (Haiku 4.5) with CTA matrix
    scenarios/
      knee_day3.json                # 7 clinical scenarios covering
      knee_day7_infection.json      # all 3 surgery types, routine
      knee_day1_routine.json        # through emergency presentations
      hip_day5.json
      hip_day4_dvt.json
      appendix_day1.json
      appendix_day5_abscess.json
  tests/                            # 139 tests, all run without API calls
  docs/
    ARCHITECTURE.md                 # Full technical architecture document
```

---

## Test Coverage

**139 tests**, all running without API calls (pure logic, DB operations, tool execution):

```
tests/test_db.py                    15 tests  — CRUD, investigation gaps, patient context
tests/test_clinical_knowledge.py    21 tests  — surgery knowledge, med masking, vitals
tests/test_guardrails.py            12 tests  — emergency bypass, output filter, validation
tests/test_risk_assessor_tools.py   16 tests  — all 6 investigation tools
tests/test_conversationalist.py     11 tests  — gaps injection, tool execution
tests/test_red_flags.py             10 tests  — matrix integrity, filtering, formatting
tests/test_scenarios.py              7 tests  — scenario file validation
tests/test_escalator.py              6 tests  — severity mapping, low-score shortcut
tests/test_synthetic_scenarios.py    8 tests  — example structure and formatting
```

---

## Cost Analysis

| Component | Cost per message | Notes |
|-----------|-----------------|-------|
| Conversationalist | ~$0.01 | Sonnet, 2-4 tool calls per turn |
| Risk Assessor | ~$0.01-0.03 | Sonnet, 3-5 investigation calls |
| Escalator | ~$0.001 | Haiku, single call (skipped for low-risk) |
| Semantic Emergency (Layer 1b) | ~$0.001 | Haiku, runs every message |
| Manipulation Detector (Layer 6) | ~$0.001 | Haiku, only if regex doesn't match |
| **Total per message** | **~$0.02-0.04** | |
| **Per conversation (10 msgs)** | **~$0.25** | |

Prompt caching (`cache_control: ephemeral`) on Risk Assessor system prompts reduces cost on repeated assessments.

---

## What I'd Change at Scale

| Current | At Scale |
|---------|----------|
| Dict lookup for clinical knowledge | Vector DB (ChromaDB prototype, Pinecone production) |
| SQLite with WAL mode | PostgreSQL with connection pooling |
| 3 surgery types | 50+ with retrieval-augmented knowledge |
| Background thread | Task queue (Celery/Redis) |
| Expected-symptom ranges in code | Clinical rules engine with version control |
| Raw SDK | LangGraph for state machines + Agent SDK for tool loops |

The architecture is designed for this swap: `get_surgery_knowledge()` changes from dict lookup to vector search. Agent code stays the same. Only the retrieval layer changes.

---

## Built With

- [Anthropic Claude API](https://docs.anthropic.com/) — Claude Sonnet 4.5 + Haiku 4.5
- [FastAPI](https://fastapi.tiangolo.com/) — Backend API serving React SPA
- [React](https://react.dev/) + [Tailwind CSS](https://tailwindcss.com/) — Nurse dashboard and chat UI
- [SQLite](https://sqlite.org/) — Shared agent state with WAL mode
- [pytest](https://pytest.org/) — 139 tests, no API mocking needed

---

*Built as a portfolio project demonstrating multi-agent architecture, clinical reasoning, and AI safety patterns.*
