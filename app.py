"""
AI Triage Nurse — Post-Op Recovery Agent
Streamlit app with two pages: Patient Chat and Nurse Dashboard.
"""

import datetime
import json
import os
import ssl
import threading
from pathlib import Path

# ─── Norton TLS Fix (local dev only) ───
# Norton AV intercepts HTTPS on local machine. Not needed on Streamlit Cloud.
CERT_PATH = Path.home() / "certs" / "cacert.pem"
if CERT_PATH.exists():
    os.environ["SSL_CERT_FILE"] = str(CERT_PATH)
    os.environ["REQUESTS_CA_BUNDLE"] = str(CERT_PATH)

import anthropic
import streamlit as st
from dotenv import load_dotenv

from src import db
from src.agents.conversationalist import run_turn
from src.agents.risk_assessor import assess_risk
from src.agents.escalator import escalate
from src.guardrails import check_emergency_bypass, run_guardrails_on_risk_assessment

load_dotenv(override=True)

# ─── API Key: support both .env (local) and st.secrets (Streamlit Cloud) ───
if not os.getenv("ANTHROPIC_API_KEY"):
    try:
        api_key_from_secrets = st.secrets.get("ANTHROPIC_API_KEY", "")
        if api_key_from_secrets:
            os.environ["ANTHROPIC_API_KEY"] = api_key_from_secrets
    except Exception:
        pass

# ─── Page Config ───
st.set_page_config(
    page_title="AI Triage Nurse",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Global CSS ───
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* Base */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 900px;
    }

    /* Hide default Streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] li {
        color: #e2e8f0 !important;
    }

    /* Page header */
    .page-header {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px 0 16px 0;
        border-bottom: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 20px;
    }
    .page-header .logo {
        width: 44px;
        height: 44px;
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 22px;
        flex-shrink: 0;
    }
    .page-header .title-group h1 {
        margin: 0;
        font-size: 22px;
        font-weight: 700;
        letter-spacing: -0.3px;
    }
    .page-header .title-group p {
        margin: 2px 0 0 0;
        font-size: 12px;
        color: #64748b;
    }

    /* Disclaimer */
    .disclaimer-bar {
        background: rgba(245, 158, 11, 0.1);
        border: 1px solid rgba(245, 158, 11, 0.2);
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 12px;
        color: #f59e0b;
        text-align: center;
        margin-bottom: 20px;
    }

    /* Scenario card */
    .scenario-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 16px;
    }
    .scenario-card .patient-name {
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 4px;
    }
    .scenario-card .patient-detail {
        font-size: 13px;
        color: #94a3b8;
        line-height: 1.5;
    }
    .scenario-card .patient-tag {
        display: inline-block;
        background: rgba(59,130,246,0.15);
        color: #60a5fa;
        font-size: 11px;
        font-weight: 500;
        padding: 3px 8px;
        border-radius: 4px;
        margin-right: 6px;
        margin-top: 8px;
    }

    /* Chat area */
    .chat-container {
        min-height: 400px;
    }

    /* Override Streamlit chat styling */
    [data-testid="stChatMessage"] {
        border-radius: 12px !important;
        padding: 12px 16px !important;
        margin-bottom: 8px !important;
    }

    /* User message */
    [data-testid="stChatMessage"][data-testid-role="user"] {
        background: rgba(59, 130, 246, 0.08) !important;
        border: 1px solid rgba(59, 130, 246, 0.15) !important;
    }

    /* Assistant message */
    [data-testid="stChatMessage"][data-testid-role="assistant"] {
        background: rgba(255, 255, 255, 0.04) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
    }

    /* Streamlit button override */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px;
        padding: 10px 24px !important;
        transition: all 0.2s ease;
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
    }

    /* ─── Nurse Dashboard Styles ─── */
    .alert-banner {
        padding: 16px 20px;
        border-radius: 12px;
        margin-bottom: 16px;
        color: white;
    }
    .alert-banner .alert-title { font-size: 16px; font-weight: 700; }
    .alert-banner .alert-body { font-size: 13px; margin-top: 4px; opacity: 0.9; }
    .alert-routine  { background: linear-gradient(135deg, #059669, #10b981); }
    .alert-monitor  { background: linear-gradient(135deg, #d97706, #f59e0b); color: #1a1a1a !important; }
    .alert-urgent   { background: linear-gradient(135deg, #ea580c, #f97316); }
    .alert-critical { background: linear-gradient(135deg, #dc2626, #ef4444); }
    .alert-911-now  { background: linear-gradient(135deg, #991b1b, #dc2626); }
    .alert-system-error { background: linear-gradient(135deg, #475569, #64748b); }

    .stat-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin: 16px 0;
    }
    .stat-card {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 14px 12px;
        text-align: center;
    }
    .stat-card .stat-value {
        font-size: 28px;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .stat-card .stat-label {
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #64748b;
        margin-top: 4px;
    }

    .section-title {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #475569;
        margin: 24px 0 10px 0;
        padding-bottom: 6px;
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }

    .tl-item {
        font-size: 13px;
        padding: 6px 0 6px 16px;
        border-left: 2px solid rgba(255,255,255,0.1);
        margin-left: 4px;
        line-height: 1.5;
    }
    .tl-red  { border-left-color: #ef4444; }
    .tl-yel  { border-left-color: #f59e0b; }
    .tl-grn  { border-left-color: #10b981; }

    .gap-pill {
        display: block;
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 12px;
        margin: 4px 0;
        line-height: 1.4;
    }
    .gap-high   { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.2); color: #fca5a5; }
    .gap-medium { background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.2); color: #fcd34d; }
    .gap-low    { background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.2); color: #6ee7b7; }

    .pipeline-card {
        background: rgba(255,255,255,0.02);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 14px 16px;
        font-size: 12px;
        color: #64748b;
        line-height: 1.8;
    }
    .pipeline-card strong { color: #94a3b8; }
    .pipeline-card .model-tag {
        display: inline-block;
        background: rgba(139,92,246,0.15);
        color: #a78bfa;
        font-size: 10px;
        font-weight: 500;
        padding: 1px 6px;
        border-radius: 3px;
    }

    /* Conclusion card */
    .conclusion-card {
        border-radius: 14px;
        padding: 20px 24px;
        margin: 12px 0;
        background: rgba(255,255,255,0.03);
    }
    .conclusion-card.sev-routine  { border: 2px solid #10b981; }
    .conclusion-card.sev-monitor  { border: 2px solid #f59e0b; }
    .conclusion-card.sev-urgent   { border: 2px solid #f97316; }
    .conclusion-card.sev-critical { border: 2px solid #ef4444; }
    .conclusion-header {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 14px;
    }
    .conclusion-header .sev-badge {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 4px 10px;
        border-radius: 6px;
    }
    .sev-badge.routine  { background: rgba(16,185,129,0.15); color: #34d399; }
    .sev-badge.monitor  { background: rgba(245,158,11,0.15); color: #fbbf24; }
    .sev-badge.urgent   { background: rgba(249,115,22,0.15); color: #fb923c; }
    .sev-badge.critical { background: rgba(239,68,68,0.15); color: #f87171; }
    .conclusion-section {
        margin: 10px 0;
    }
    .conclusion-section .label {
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #64748b;
        margin-bottom: 4px;
    }
    .conclusion-section .value {
        font-size: 14px;
        color: #e2e8f0;
        line-height: 1.5;
    }
    .conclusion-symptoms {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 6px;
    }
    .conclusion-symptoms .symptom-chip {
        display: inline-block;
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.1);
        font-size: 11px;
        padding: 3px 8px;
        border-radius: 4px;
        color: #94a3b8;
    }

    /* Conclusion CTAs */
    .conclusion-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 18px;
        padding-top: 16px;
        border-top: 1px solid rgba(255,255,255,0.08);
    }
    .conclusion-actions .cta-btn {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 10px 20px;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 600;
        text-decoration: none;
        cursor: pointer;
        transition: all 0.2s ease;
        border: none;
    }
    .cta-btn.cta-primary {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    .cta-btn.cta-primary:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(59,130,246,0.3);
    }
    .cta-btn.cta-secondary {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.12);
        color: #94a3b8;
    }
    .cta-btn.cta-secondary:hover {
        background: rgba(255,255,255,0.1);
        color: #e2e8f0;
    }
    .cta-btn.cta-urgent {
        background: linear-gradient(135deg, #ea580c, #f97316);
        color: white;
    }
    .cta-btn.cta-urgent:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(249,115,22,0.4);
    }
    .cta-btn.cta-critical {
        background: linear-gradient(135deg, #dc2626, #ef4444);
        color: white;
        font-size: 14px;
        padding: 12px 24px;
    }
    .cta-btn.cta-critical:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(239,68,68,0.4);
    }
    .conclusion-reassurance {
        font-size: 12px;
        color: #64748b;
        margin-top: 10px;
        text-align: center;
    }

    /* Turn counter */
    .turn-counter {
        text-align: center;
        padding: 6px 0;
        margin-bottom: 8px;
    }
    .turn-counter .dots {
        display: inline-flex;
        gap: 6px;
        align-items: center;
    }
    .turn-counter .dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: rgba(255,255,255,0.1);
        border: 1px solid rgba(255,255,255,0.15);
    }
    .turn-counter .dot.filled {
        background: linear-gradient(135deg, #3b82f6, #8b5cf6);
        border-color: transparent;
    }
    .turn-counter .dot.current {
        background: linear-gradient(135deg, #3b82f6, #8b5cf6);
        border-color: transparent;
        box-shadow: 0 0 8px rgba(59,130,246,0.4);
    }
    .turn-counter .turn-label {
        font-size: 11px;
        color: #64748b;
        margin-left: 10px;
    }

    /* Chat locked state */
    .chat-locked-msg {
        text-align: center;
        padding: 16px;
        color: #64748b;
        font-size: 13px;
        border: 1px dashed rgba(255,255,255,0.1);
        border-radius: 10px;
        margin-top: 12px;
    }

    /* Worklist */
    .worklist-item {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 14px 16px;
        border-radius: 10px;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        margin-bottom: 8px;
        transition: all 0.15s ease;
    }
    .worklist-item:hover {
        background: rgba(255,255,255,0.06);
        border-color: rgba(255,255,255,0.12);
    }
    .worklist-item.risk-high {
        border-left: 3px solid #ef4444;
    }
    .worklist-item.risk-moderate {
        border-left: 3px solid #f59e0b;
    }
    .worklist-item.risk-low {
        border-left: 3px solid #10b981;
    }
    .worklist-score {
        font-size: 22px;
        font-weight: 700;
        min-width: 48px;
        text-align: center;
    }
    .worklist-details {
        flex: 1;
    }
    .worklist-details .wl-name {
        font-size: 14px;
        font-weight: 600;
        color: #e2e8f0;
    }
    .worklist-details .wl-meta {
        font-size: 11px;
        color: #64748b;
        margin-top: 2px;
    }
    .worklist-details .wl-reasoning {
        font-size: 12px;
        color: #94a3b8;
        margin-top: 6px;
        line-height: 1.4;
    }
    .worklist-badge {
        font-size: 10px;
        font-weight: 600;
        padding: 3px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .worklist-badge.wb-urgent {
        background: rgba(239,68,68,0.15);
        color: #f87171;
    }
    .worklist-badge.wb-monitor {
        background: rgba(245,158,11,0.15);
        color: #fbbf24;
    }
    .worklist-badge.wb-routine {
        background: rgba(16,185,129,0.15);
        color: #34d399;
    }

    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 60px 20px;
    }
    .empty-state .empty-icon {
        font-size: 48px;
        margin-bottom: 12px;
        opacity: 0.5;
    }
    .empty-state p {
        color: #475569;
        font-size: 14px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Helpers ───
SCENARIOS_DIR = Path(__file__).parent / "src" / "scenarios"


def load_scenarios() -> dict[str, dict]:
    scenarios = {}
    if SCENARIOS_DIR.exists():
        for f in sorted(SCENARIOS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                scenarios[data["name"]] = data
            except (json.JSONDecodeError, KeyError):
                continue
    return scenarios


def get_client() -> anthropic.Anthropic | None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def _try_parse_conclusion(reply: str) -> dict | None:
    """Try to parse a conclusion JSON from the agent's reply.

    Handles: raw JSON, markdown code fences, JSON embedded in text.
    """
    if not reply:
        return None

    # Try raw JSON first
    text = reply.strip()
    for attempt in [
        text,                                          # raw
        text.strip("`").strip(),                       # backtick-wrapped
        _extract_json_block(text),                     # ```json ... ```
        _extract_json_object(text),                    # JSON embedded in text
    ]:
        if not attempt:
            continue
        try:
            data = json.loads(attempt)
            if isinstance(data, dict) and data.get("conclusion") is True:
                return data
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _extract_json_block(text: str) -> str | None:
    """Extract JSON from markdown code fences like ```json {...} ```."""
    import re
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    return match.group(1) if match else None


def _extract_json_object(text: str) -> str | None:
    """Extract a JSON object from text containing other content."""
    start = text.find('{')
    if start == -1:
        return None
    # Find matching closing brace
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _render_conclusion_card(data: dict) -> str:
    """Return a patient-friendly HTML conclusion card.

    The patient sees: a warm heading, guidance, what to do next, and CTAs.
    Clinical details (severity, symptom codes) go to the Nurse Dashboard only.
    """
    sev = data.get("severity", "routine")

    # Patient-friendly headings per severity
    heading_map = {
        "routine": ("✅", "You're doing great!", "Your recovery looks on track."),
        "monitor": ("👀", "Let's keep an eye on this", "A few things to watch, but nothing alarming right now."),
        "urgent": ("📞", "Please reach out to your care team", "Some of what you described needs a closer look from your doctor."),
        "critical": ("🚨", "Please seek care right away", "What you're describing needs immediate medical attention."),
    }
    icon, heading, subheading = heading_map.get(sev, heading_map["monitor"])

    # Severity-specific CTAs
    cta_map = {
        "routine": (
            '<span class="cta-btn cta-primary">📅 Schedule Follow-up Check-in</span>'
            '<span class="cta-btn cta-secondary">📖 View Recovery Tips</span>'
            '<div class="conclusion-reassurance">Keep resting and following your care plan. You\'re on the right path!</div>'
        ),
        "monitor": (
            '<span class="cta-btn cta-primary">⏰ Check Back in 4 Hours</span>'
            '<span class="cta-btn cta-secondary">🔄 Start New Check-in Now</span>'
            '<div class="conclusion-reassurance">We\'ve shared this with your care team. Check back soon so we can see how you\'re doing.</div>'
        ),
        "urgent": (
            '<span class="cta-btn cta-urgent">📞 Call Your Care Team Now</span>'
            '<span class="cta-btn cta-secondary">🔄 Start New Check-in</span>'
            '<div class="conclusion-reassurance">Your care team is ready to help. Please don\'t wait on this.</div>'
        ),
        "critical": (
            '<span class="cta-btn cta-critical">🚨 Call 911 Now</span>'
            '<span class="cta-btn cta-urgent">📞 Call Your Care Team</span>'
            '<div class="conclusion-reassurance">Your safety is the priority. Please get help immediately.</div>'
        ),
    }
    actions_html = cta_map.get(sev, cta_map["monitor"])

    return (
        f'<div class="conclusion-card sev-{sev}">'
        # Warm heading (no clinical jargon)
        f'<div class="conclusion-header">'
        f'<span style="font-size:28px;">{icon}</span>'
        f'<div>'
        f'<div style="font-size:18px;font-weight:700;color:#f1f5f9;">{heading}</div>'
        f'<div style="font-size:13px;color:#94a3b8;margin-top:2px;">{subheading}</div>'
        f'</div>'
        f'</div>'
        # What we found (patient-friendly summary)
        f'<div class="conclusion-section">'
        f'<div class="label">What We Noticed</div>'
        f'<div class="value">{data.get("summary", "")}</div>'
        f'</div>'
        # What to do (guidance)
        f'<div class="conclusion-section">'
        f'<div class="label">What You Can Do</div>'
        f'<div class="value">{data.get("guidance", "")}</div>'
        f'</div>'
        # Next step
        f'<div class="conclusion-section">'
        f'<div class="label">Next Step</div>'
        f'<div class="value">{data.get("next_step", "")}</div>'
        f'</div>'
        # CTAs
        f'<div class="conclusion-actions">{actions_html}</div>'
        f'</div>'
    )


def _save_session_to_history(session_id: str, conclusion: dict) -> None:
    """Save concluded session data to patient_history for longitudinal tracking."""
    try:
        session = db.get_session(session_id)
        if not session:
            return

        severity = conclusion.get("severity", "routine")
        risk_map = {"routine": "low", "monitor": "moderate", "urgent": "high", "critical": "critical"}
        risk_level = risk_map.get(severity, "moderate")

        symptoms_noted = conclusion.get("symptoms_noted", [])
        summary = conclusion.get("summary", "Check-in completed.")

        # Gather unresolved concerns from investigation gaps
        gaps = db.get_investigation_gaps(session_id, only_unaddressed=True)
        unresolved = [g["question"] for g in gaps]

        # Resolved = addressed gaps
        resolved_gaps = db.get_investigation_gaps(session_id, only_unaddressed=False)
        resolved = [g["question"] for g in resolved_gaps if g["addressed"]]

        db.save_patient_history(
            session_id=session_id,
            patient_name=session["patient_name"],
            surgery_type=session["surgery_type"],
            recovery_day=session["recovery_day"],
            key_findings=symptoms_noted,
            risk_level=risk_level,
            unresolved_concerns=unresolved,
            resolved_concerns=resolved,
            session_summary=summary,
        )
    except Exception:
        pass  # Don't crash the UI for history logging


def _render_turn_counter(current_turn: int, max_turns: int = 4) -> str:
    """Return HTML for a turn progress indicator."""
    dots = ""
    for i in range(1, max_turns + 1):
        if i < current_turn:
            dots += '<span class="dot filled"></span>'
        elif i == current_turn:
            dots += '<span class="dot current"></span>'
        else:
            dots += '<span class="dot"></span>'
    label = f"Question {min(current_turn, max_turns)} of {max_turns}"
    return (
        f'<div class="turn-counter">'
        f'<span class="dots">{dots}</span>'
        f'<span class="turn-label">{label}</span>'
        f'</div>'
    )


# ─── Init ───
db.init_db()
scenarios = load_scenarios()

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "session_concluded" not in st.session_state:
    st.session_state.session_concluded = False

# ─── Check API key ───
has_api_key = bool(os.getenv("ANTHROPIC_API_KEY"))
if not has_api_key:
    st.error(
        "**ANTHROPIC_API_KEY not found.** "
        "Create a `.env` file in the project root with:\n\n"
        "```\nANTHROPIC_API_KEY=sk-ant-your-key-here\n```"
    )
    st.stop()

# ─── Session state defaults ───
if "dashboard_view" not in st.session_state:
    st.session_state.dashboard_view = "worklist"  # "worklist" or "detail"
if "detail_session_id" not in st.session_state:
    st.session_state.detail_session_id = None

# ─── Sidebar Navigation ───
with st.sidebar:
    st.markdown("""
    <div style="padding: 16px 0 20px 0; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 16px;">
        <div style="display:flex; align-items:center; gap:10px;">
            <div style="width:36px;height:36px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;">🏥</div>
            <div>
                <div style="font-size:16px;font-weight:700;color:#f1f5f9;">AI Triage Nurse</div>
                <div style="font-size:11px;color:#64748b;">Post-Op Recovery Agent</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        ["💬 Patient Chat", "📊 Nurse Dashboard"],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Scenario selection in sidebar
    if not scenarios:
        st.warning("No scenarios found.")
        st.stop()

    scenario_name = st.selectbox(
        "Clinical Scenario",
        options=list(scenarios.keys()),
        key="scenario_select",
    )
    selected = scenarios[scenario_name]

    st.markdown(
        f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);'
        f'border-radius:8px;padding:10px 12px;margin:8px 0;font-size:12px;">'
        f'<div style="font-weight:600;color:#e2e8f0;">{selected["patient_name"]}</div>'
        f'<div style="color:#94a3b8;margin-top:2px;">{selected["surgery_type"]} &middot; Day {selected["recovery_day"]}</div>'
        f'<div style="color:#64748b;margin-top:6px;line-height:1.4;">{selected["description"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if st.button("▶ Start New Session", type="primary", use_container_width=True):
        session_id = db.create_session(
            surgery_type=selected["surgery_type"],
            recovery_day=selected["recovery_day"],
            patient_name=selected["patient_name"],
        )
        st.session_state.session_id = session_id
        st.session_state.chat_messages = []
        st.session_state.session_concluded = False
        st.rerun()

    st.markdown("---")

    # Pipeline info in sidebar
    st.markdown("""
    <div style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:#475569;margin-bottom:8px;font-weight:600;">Agent Pipeline</div>
    <div style="font-size:11px;color:#64748b;line-height:1.8;">
        <strong style="color:#94a3b8;">Conversationalist</strong> <span style="background:rgba(139,92,246,0.15);color:#a78bfa;font-size:9px;padding:1px 5px;border-radius:3px;">Sonnet</span><br>
        <strong style="color:#94a3b8;">Risk Assessor</strong> <span style="background:rgba(139,92,246,0.15);color:#a78bfa;font-size:9px;padding:1px 5px;border-radius:3px;">Sonnet</span><br>
        <strong style="color:#94a3b8;">Escalator</strong> <span style="background:rgba(59,130,246,0.15);color:#60a5fa;font-size:9px;padding:1px 5px;border-radius:3px;">Haiku</span><br>
        <span style="color:#475569;">5 guardrails &middot; 21 red flags</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🗑️ Reset Database", use_container_width=True, help="Delete all sessions and start fresh"):
        db_path = Path(__file__).parent / "triage.db"
        for suffix in ["", "-wal", "-shm"]:
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        db.init_db()
        st.session_state.session_id = None
        st.session_state.chat_messages = []
        st.session_state.session_concluded = False
        st.session_state.detail_session_id = None
        st.rerun()

    st.markdown("""
    <div style="font-size:10px;color:#334155;margin-top:16px;text-align:center;">
        Educational demo · Not medical advice
    </div>
    """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAGE: Patient Chat
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if page == "💬 Patient Chat":

    # Header
    st.markdown("""
    <div class="page-header">
        <div class="logo">💬</div>
        <div class="title-group">
            <h1>Patient Chat</h1>
            <p>Talk to us about how you're feeling after surgery</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        '<div class="disclaimer-bar">'
        '⚠️ <strong>Educational Demo</strong> — This is not medical advice. Do not use for real patient care.'
        '</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.session_id:
        session = db.get_session(st.session_state.session_id)

        if session:
            # Active session indicator
            st.markdown(
                f'<div class="scenario-card">'
                f'<div class="patient-name">{session["patient_name"]}</div>'
                f'<div class="patient-detail">{session["surgery_type"]} &middot; Recovery Day {session["recovery_day"]}</div>'
                f'<span class="patient-tag">Active Session</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Count current patient turns for progress indicator
            patient_turns = sum(1 for m in st.session_state.chat_messages if m["role"] == "user")

            # Turn counter (show after first message)
            if patient_turns > 0 and not st.session_state.session_concluded:
                st.markdown(_render_turn_counter(patient_turns), unsafe_allow_html=True)

            # Chat history — render conclusion cards, never show raw JSON
            for msg in st.session_state.chat_messages:
                if msg["role"] == "assistant":
                    conclusion = _try_parse_conclusion(msg["content"])
                    if conclusion:
                        st.markdown(_render_conclusion_card(conclusion), unsafe_allow_html=True)
                        continue
                    # Safety net: hide any JSON that slipped through
                    content = msg["content"]
                    if content.strip().startswith("{") or '"conclusion"' in content:
                        st.markdown(_render_conclusion_card({
                            "conclusion": True, "severity": "monitor",
                            "summary": "Thank you for this check-in. We've noted everything you shared.",
                            "guidance": "Continue following your care team's instructions and rest.",
                            "next_step": "Check back in a few hours, or contact your care team if anything changes.",
                            "symptoms_noted": [],
                        }), unsafe_allow_html=True)
                        continue
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            # Chat input (locked after conclusion)
            if st.session_state.session_concluded:
                st.markdown(
                    '<div class="chat-locked-msg">'
                    'This check-in session has ended. Use the actions above, or start a new check-in if your symptoms change.'
                    '</div>',
                    unsafe_allow_html=True,
                )
                if st.button("🔄 Start New Check-in", type="primary", use_container_width=True):
                    new_sid = db.create_session(
                        surgery_type=session["surgery_type"],
                        recovery_day=session["recovery_day"],
                        patient_name=session["patient_name"],
                    )
                    st.session_state.session_id = new_sid
                    st.session_state.chat_messages = []
                    st.session_state.session_concluded = False
                    st.rerun()
            elif user_input := st.chat_input("How are you feeling today?"):
                st.session_state.chat_messages.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.markdown(user_input)

                # GUARDRAIL Layer 1: Emergency keyword bypass
                emergency = check_emergency_bypass(user_input)
                if emergency:
                    db.write_alert(
                        st.session_state.session_id,
                        emergency["severity"],
                        emergency["summary"],
                        signals=emergency["signals"],
                        recommended_action=emergency["recommended_action"],
                    )

                # Conversationalist agent
                with st.spinner("Thinking..."):
                    try:
                        client = get_client()
                        reply = run_turn(client, st.session_state.session_id, user_input)
                    except Exception as e:
                        reply = "I'm having trouble responding right now. Please try again."
                        db.write_alert(
                            st.session_state.session_id,
                            "system-error",
                            f"Conversationalist failed: {type(e).__name__}",
                            signals=["agent_failure"],
                            recommended_action="Check API key and connection.",
                        )

                # Check if this is a conclusion
                conclusion = _try_parse_conclusion(reply)
                if conclusion:
                    st.markdown(_render_conclusion_card(conclusion), unsafe_allow_html=True)
                    st.session_state.session_concluded = True
                    _save_session_to_history(st.session_state.session_id, conclusion)
                elif reply.strip().startswith("{") or '"conclusion"' in reply:
                    # JSON-like but parsing failed -- never show raw JSON to patient
                    fallback_conclusion = {
                        "conclusion": True,
                        "severity": "monitor",
                        "summary": "Thank you for this check-in. We've noted everything you shared.",
                        "guidance": "Continue following your care team's instructions and rest.",
                        "next_step": "Check back in a few hours, or contact your care team if anything changes.",
                        "symptoms_noted": [],
                    }
                    st.markdown(_render_conclusion_card(fallback_conclusion), unsafe_allow_html=True)
                    st.session_state.session_concluded = True
                    _save_session_to_history(st.session_state.session_id, fallback_conclusion)
                else:
                    with st.chat_message("assistant"):
                        st.markdown(reply)

                st.session_state.chat_messages.append({"role": "assistant", "content": reply})

                # Background: Risk Assessor + Escalator
                def _background_assess(sid: str):
                    try:
                        bg_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                        assessment = assess_risk(bg_client, sid)
                        if assessment:
                            checked = run_guardrails_on_risk_assessment(sid, assessment)
                            if checked.get("guardrail_adjustments", {}).get("score_adjusted"):
                                db.write_risk_score(
                                    sid,
                                    score=checked["score"],
                                    triggered_signals=checked["triggered_signals"],
                                    reasoning=checked["reasoning"],
                                )
                                assessment = checked
                            escalate(bg_client, sid, assessment)
                    except Exception as e:
                        db.write_alert(
                            sid, "system-error",
                            f"Risk Assessor failed: {type(e).__name__}",
                            signals=["agent_failure"],
                            recommended_action="Manual review recommended.",
                        )

                threading.Thread(
                    target=_background_assess,
                    args=(st.session_state.session_id,),
                    daemon=True,
                ).start()

                # Force rerun to update turn counter and lock state
                if conclusion:
                    st.rerun()
    else:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">👈</div>
            <p>Select a scenario from the sidebar and click <strong>Start New Session</strong> to begin.</p>
        </div>
        """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PAGE: Nurse Dashboard
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "📊 Nurse Dashboard":

    # Determine which view to show: worklist or patient detail
    viewing_detail = st.session_state.get("detail_session_id") is not None

    # ──────────────────────────────────────────────
    # VIEW: Patient Detail (navigated from worklist)
    # ──────────────────────────────────────────────
    if viewing_detail:
        detail_sid = st.session_state.detail_session_id
        session = db.get_session(detail_sid)

        if not session:
            st.error("Session not found.")
            st.session_state.detail_session_id = None
            st.rerun()
        else:
            # Load data
            alerts = db.get_alerts(detail_sid)
            symptoms = db.get_symptoms(detail_sid)
            vitals = db.get_vitals(detail_sid)
            meds = db.get_meds(detail_sid)
            risk_scores = db.get_risk_scores(detail_sid)
            conclusion_record = db.get_session_conclusion(detail_sid)

            # Filter out system-error alerts for display
            clinical_alerts = [a for a in alerts if a["severity"] != "system-error"]

            score = risk_scores[-1]["score"] if risk_scores else 0
            s_color = "#10b981" if score <= 20 else "#f59e0b" if score <= 40 else "#f97316" if score <= 60 else "#ef4444"
            sev_label = "LOW" if score <= 20 else "MODERATE" if score <= 40 else "HIGH" if score <= 60 else "CRITICAL"
            is_concluded = conclusion_record is not None

            # ── Back Button + Title ──
            back_col, title_col = st.columns([1, 5])
            with back_col:
                if st.button("← Back", use_container_width=True):
                    st.session_state.detail_session_id = None
                    st.rerun()
            with title_col:
                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:16px;">
                    <div>
                        <span style="font-size:22px;font-weight:800;color:#f1f5f9;">{session["patient_name"]}</span>
                        <span style="font-size:12px;color:#64748b;margin-left:8px;">
                            {session["surgery_type"]} · Day {session["recovery_day"]}
                        </span>
                    </div>
                    <span style="font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px;
                                {'background:rgba(16,185,129,0.15);color:#34d399;' if is_concluded else 'background:rgba(59,130,246,0.15);color:#60a5fa;'}">
                        {'✅ Concluded' if is_concluded else '● Live'}</span>
                </div>
                """, unsafe_allow_html=True)

            # ── Top Row: Risk Score + Stats ──
            st.markdown("")
            r_col, s1_col, s2_col, s3_col, s4_col = st.columns([2, 1, 1, 1, 1])

            with r_col:
                st.markdown(f"""
                <div style="background:rgba(0,0,0,0.2);border:2px solid {s_color};border-radius:14px;
                            padding:20px;text-align:center;">
                    <div style="font-size:48px;font-weight:800;color:{s_color};line-height:1;">{score}</div>
                    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;
                                color:{s_color};margin-top:4px;">{sev_label} RISK</div>
                </div>
                """, unsafe_allow_html=True)
            with s1_col:
                unique_symptoms = len({s["name"] for s in symptoms})
                st.metric("Symptoms", unique_symptoms)
            with s2_col:
                st.metric("Vitals", len(vitals))
            with s3_col:
                st.metric("Meds", len(meds))
            with s4_col:
                st.metric("Alerts", len(clinical_alerts))

            # ── Alert Banner (only clinical alerts, not system errors) ──
            if clinical_alerts:
                latest = clinical_alerts[-1]
                sev = latest["severity"]
                alert_icons = {"routine": "✅", "monitor": "👁️", "urgent": "⚠️", "critical": "🚨", "911-now": "🆘"}
                st.markdown(
                    f'<div class="alert-banner alert-{sev}" style="margin-top:16px;">'
                    f'<div class="alert-title">{alert_icons.get(sev, "🔔")} {sev.upper()}</div>'
                    f'<div class="alert-body">{latest["summary"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if latest.get("recommended_action"):
                    st.caption(f"**Recommended:** {latest['recommended_action']}")

            st.markdown("---")

            # ── Two-Column Layout ──
            left_col, right_col = st.columns([3, 2])

            with left_col:
                # ── Symptoms ──
                st.markdown("#### 🩺 Symptoms")
                if symptoms:
                    # Deduplicate: keep only the LATEST entry per symptom name
                    latest_by_name: dict[str, dict] = {}
                    for s_item in symptoms:
                        latest_by_name[s_item["name"]] = s_item  # last write wins (chronological)
                    for s_item in latest_by_name.values():
                        sev_val = s_item["severity"]
                        sev_dot = "🔴" if sev_val >= 7 else "🟡" if sev_val >= 4 else "🟢"
                        txt = s_item.get("free_text", "")
                        detail_txt = f' — *"{txt}"*' if txt else ""
                        st.markdown(f"{sev_dot} **{s_item['name']}** ({sev_val}/10){detail_txt}")
                else:
                    st.caption("No symptoms reported yet.")

                # ── Vitals ──
                st.markdown("#### 📊 Vitals")
                if vitals:
                    for v in vitals:
                        st.markdown(f"• **{v['type']}**: {v['value']} {v['unit']}")
                else:
                    st.caption("No vitals recorded.")

                # ── Meds ──
                st.markdown("#### 💊 Medications")
                if meds:
                    for m in meds:
                        st.markdown(f"• **{m['med_name']}** ({m['dose']}) — taken {m['taken_at']}")
                else:
                    st.caption("No medications logged.")

            with right_col:
                # ── Risk Trend ──
                st.markdown("#### 📈 Risk Trend")
                if risk_scores:
                    scores_data = [r["score"] for r in risk_scores[-10:]]
                    st.line_chart(scores_data, height=150, use_container_width=True)
                    latest_risk = risk_scores[-1]
                    if latest_risk.get("triggered_signals"):
                        sigs = latest_risk["triggered_signals"]
                        if isinstance(sigs, str):
                            sigs = json.loads(sigs)
                        if sigs:
                            st.markdown("**Signals:** " + ", ".join(f"`{s}`" for s in sigs))
                else:
                    st.caption("Awaiting risk assessment...")

                # ── Conclusion ──
                if conclusion_record:
                    risk_level = conclusion_record["risk_level"]
                    rl_colors = {"low": "#10b981", "moderate": "#f59e0b", "high": "#f97316", "critical": "#ef4444"}
                    rl_color = rl_colors.get(risk_level, "#64748b")
                    st.markdown("#### 📝 Conclusion")
                    st.markdown(
                        f'<div style="border-left:3px solid {rl_color};padding:10px 14px;'
                        f'background:rgba(255,255,255,0.03);border-radius:0 8px 8px 0;font-size:13px;'
                        f'color:#e2e8f0;line-height:1.6;">'
                        f'{conclusion_record["session_summary"]}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            # ── Expandable Sections ──
            exp_left, exp_right = st.columns(2)

            with exp_left:
                # Conversation Transcript
                messages = db.get_messages(detail_sid, limit=50)
                with st.expander(f"💬 Conversation Transcript ({len(messages)} messages)", expanded=False):
                    if messages:
                        for msg in messages:
                            role_icon = "🧑" if msg["role"] == "user" else "🤖"
                            role_label = "Patient" if msg["role"] == "user" else "AI Nurse"
                            content = msg["content"]
                            if content.strip().startswith("{") and '"conclusion"' in content:
                                content = "[Session conclusion]"
                            ts = msg.get("created_at", "")[-8:]
                            st.markdown(f"**{role_icon} {role_label}** `{ts}`")
                            st.markdown(f"> {content}")
                            st.markdown("")
                    else:
                        st.caption("No messages yet.")

            with exp_right:
                # Alert History
                with st.expander(f"🔔 Alert History ({len(clinical_alerts)} alerts)", expanded=False):
                    if clinical_alerts:
                        for a in reversed(clinical_alerts):
                            a_sev = a["severity"]
                            a_icons = {"routine": "✅", "monitor": "👁️", "urgent": "⚠️", "critical": "🚨", "911-now": "🆘"}
                            st.markdown(f"**{a_icons.get(a_sev, '🔔')} {a_sev.upper()}** — {a['summary']}")
                            st.caption(a["created_at"])
                            st.markdown("")
                    else:
                        st.caption("No alerts.")

    # ──────────────────────────────────────────────
    # VIEW: Worklist (default dashboard view)
    # ──────────────────────────────────────────────
    else:
        st.markdown("""
        <div class="page-header">
            <div class="logo" style="background:linear-gradient(135deg,#059669,#10b981);">📊</div>
            <div class="title-group">
                <h1>Nurse Dashboard</h1>
                <p>Patient worklist — sorted by clinical risk</p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Refresh
        ref_left, ref_right = st.columns([4, 1])
        with ref_left:
            st.caption(f"🕐 {datetime.datetime.now().strftime('%H:%M:%S')}")
        with ref_right:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

        all_sessions = db.get_all_sessions_with_risk()

        if not all_sessions:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">⏳</div>
                <p>No patient sessions yet. Start one from the sidebar.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Summary stats
            total = len(all_sessions)
            high_risk = sum(1 for s in all_sessions if s["risk_score"] > 60)
            moderate_risk = sum(1 for s in all_sessions if 30 < s["risk_score"] <= 60)
            needs_review = sum(1 for s in all_sessions if s["urgent_alert_count"] > 0)

            sum_cols = st.columns(4)
            with sum_cols[0]:
                st.metric("Total Patients", total)
            with sum_cols[1]:
                st.metric("High Risk", high_risk, delta=None)
            with sum_cols[2]:
                st.metric("Moderate Risk", moderate_risk, delta=None)
            with sum_cols[3]:
                st.metric("Needs Review", needs_review, delta=None)

            st.markdown("")

            # Patient cards
            for s in all_sessions:
                r_score = s["risk_score"]
                s_color_wl = "#ef4444" if r_score > 60 else "#f59e0b" if r_score > 30 else "#10b981"
                risk_class = "risk-high" if r_score > 60 else "risk-moderate" if r_score > 30 else "risk-low"

                # Badge
                if s["urgent_alert_count"] > 0:
                    badge = "🔴 Needs Review"
                    badge_bg = "rgba(239,68,68,0.15)"
                    badge_color = "#f87171"
                elif r_score > 30:
                    badge = "🟡 Monitoring"
                    badge_bg = "rgba(245,158,11,0.15)"
                    badge_color = "#fbbf24"
                else:
                    badge = "🟢 Stable"
                    badge_bg = "rgba(16,185,129,0.15)"
                    badge_color = "#34d399"

                reasoning = s.get("risk_reasoning") or s.get("latest_alert") or "No assessment yet"
                if len(reasoning) > 120:
                    reasoning = reasoning[:117] + "..."

                # Card layout: info + button
                card_col, btn_col = st.columns([6, 1])

                with card_col:
                    st.markdown(f"""
                    <div style="display:flex;align-items:center;gap:16px;padding:16px 20px;
                                background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);
                                border-left:4px solid {s_color_wl};border-radius:10px;margin-bottom:4px;">
                        <div style="text-align:center;min-width:50px;">
                            <div style="font-size:28px;font-weight:800;color:{s_color_wl};">{r_score}</div>
                            <div style="font-size:8px;text-transform:uppercase;letter-spacing:1px;color:#475569;">RISK</div>
                        </div>
                        <div style="flex:1;">
                            <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
                                <span style="font-size:15px;font-weight:700;color:#e2e8f0;">{s["patient_name"]}</span>
                                <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:10px;
                                            background:{badge_bg};color:{badge_color};">{badge}</span>
                            </div>
                            <div style="font-size:12px;color:#64748b;">{s["surgery_type"]} · Day {s["recovery_day"]} · {s["symptom_count"]} symptoms</div>
                            <div style="font-size:12px;color:#94a3b8;margin-top:4px;line-height:1.4;">{reasoning}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with btn_col:
                    if st.button("View →", key=f"wl_{s['id']}", use_container_width=True):
                        st.session_state.detail_session_id = s["id"]
                        # Also switch the active session for chat
                        st.session_state.session_id = s["id"]
                        msgs = db.get_messages(s["id"], limit=50)
                        st.session_state.chat_messages = [
                            {"role": m["role"], "content": m["content"]} for m in msgs
                        ]
                        concluded = db.get_session_conclusion(s["id"])
                        st.session_state.session_concluded = concluded is not None
                        st.rerun()
