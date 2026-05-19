"""
AI Triage Nurse — Post-Op Recovery Agent
Streamlit app with two pages: Patient Chat and Nurse Dashboard.
"""

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
    """Try to parse a conclusion JSON from the agent's reply."""
    try:
        data = json.loads(reply)
        if isinstance(data, dict) and data.get("conclusion") is True:
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _render_conclusion_card(data: dict) -> str:
    """Return HTML for an inline conclusion card with severity-specific CTAs."""
    sev = data.get("severity", "routine")
    icons = {"routine": "✅", "monitor": "👁️", "urgent": "⚠️", "critical": "🚨"}
    icon = icons.get(sev, "🔔")

    symptoms_html = ""
    noted = data.get("symptoms_noted", [])
    if noted:
        chips = "".join(f'<span class="symptom-chip">{s}</span>' for s in noted)
        symptoms_html = (
            f'<div class="conclusion-section">'
            f'<div class="label">Symptoms Noted</div>'
            f'<div class="conclusion-symptoms">{chips}</div>'
            f'</div>'
        )

    # Severity-specific CTAs
    cta_map = {
        "routine": (
            '<span class="cta-btn cta-primary">📅 Schedule Follow-up Check-in</span>'
            '<span class="cta-btn cta-secondary">📖 View Recovery Tips</span>'
            '<div class="conclusion-reassurance">Everything looks on track. Keep up the good work!</div>'
        ),
        "monitor": (
            '<span class="cta-btn cta-primary">⏰ Set Reminder (4 hours)</span>'
            '<span class="cta-btn cta-secondary">🔄 Start New Check-in</span>'
            '<div class="conclusion-reassurance">We\'ll keep an eye on this. Check back if anything changes.</div>'
        ),
        "urgent": (
            '<span class="cta-btn cta-urgent">📞 Call Care Team Now</span>'
            '<span class="cta-btn cta-secondary">🔄 Start New Check-in</span>'
            '<div class="conclusion-reassurance">Your care team is ready to help. Don\'t wait on this.</div>'
        ),
        "critical": (
            '<span class="cta-btn cta-critical">🚨 Call 911</span>'
            '<span class="cta-btn cta-urgent">📞 Call Care Team</span>'
            '<div class="conclusion-reassurance">Please seek immediate medical attention.</div>'
        ),
    }
    actions_html = cta_map.get(sev, cta_map["monitor"])

    return (
        f'<div class="conclusion-card sev-{sev}">'
        f'<div class="conclusion-header">'
        f'<span style="font-size:22px;">{icon}</span>'
        f'<span class="sev-badge {sev}">{sev}</span>'
        f'<span style="font-size:13px;color:#94a3b8;">Check-in Complete</span>'
        f'</div>'
        f'<div class="conclusion-section">'
        f'<div class="label">Summary</div>'
        f'<div class="value">{data.get("summary", "")}</div>'
        f'</div>'
        f'<div class="conclusion-section">'
        f'<div class="label">Guidance</div>'
        f'<div class="value">{data.get("guidance", "")}</div>'
        f'</div>'
        f'<div class="conclusion-section">'
        f'<div class="label">Next Step</div>'
        f'<div class="value">{data.get("next_step", "")}</div>'
        f'</div>'
        f'{symptoms_html}'
        f'<div class="conclusion-actions">{actions_html}</div>'
        f'</div>'
    )


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

    st.markdown("""
    <div style="position:absolute;bottom:16px;left:16px;right:16px;font-size:10px;color:#334155;">
        Educational demo &middot; Not medical advice
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

            # Chat history — render conclusion cards for JSON conclusions
            for msg in st.session_state.chat_messages:
                if msg["role"] == "assistant":
                    conclusion = _try_parse_conclusion(msg["content"])
                    if conclusion:
                        st.markdown(_render_conclusion_card(conclusion), unsafe_allow_html=True)
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
                            f"Conversationalist failed: {e}",
                            signals=["agent_failure"],
                            recommended_action="Check API key and connection.",
                        )

                # Check if this is a conclusion
                conclusion = _try_parse_conclusion(reply)
                if conclusion:
                    st.markdown(_render_conclusion_card(conclusion), unsafe_allow_html=True)
                    st.session_state.session_concluded = True
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
                            f"Risk Assessor failed: {e}",
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

    st.markdown("""
    <div class="page-header">
        <div class="logo" style="background:linear-gradient(135deg,#059669,#10b981);">📊</div>
        <div class="title-group">
            <h1>Nurse Dashboard</h1>
            <p>Real-time clinical monitoring and risk assessment</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    session_id = st.session_state.get("session_id")

    if not session_id:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">⏳</div>
            <p>Start a patient session from the sidebar to see clinical data here.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Refresh button
        if st.button("🔄 Refresh Dashboard", use_container_width=False):
            st.rerun()

        # Load all data
        alerts = db.get_alerts(session_id)
        symptoms = db.get_symptoms(session_id)
        vitals = db.get_vitals(session_id)
        meds = db.get_meds(session_id)
        risk_scores = db.get_risk_scores(session_id)
        gaps = db.get_investigation_gaps(session_id, only_unaddressed=True)

        # ── Alert Banner ──
        if alerts:
            latest = alerts[-1]
            sev = latest["severity"]
            icons = {
                "routine": "✅", "monitor": "👁️", "urgent": "⚠️",
                "critical": "🚨", "911-now": "🆘", "system-error": "⚙️",
            }
            st.markdown(
                f'<div class="alert-banner alert-{sev}">'
                f'<div class="alert-title">{icons.get(sev, "🔔")} {sev.upper()}</div>'
                f'<div class="alert-body">{latest["summary"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if latest.get("recommended_action"):
                st.caption(f"**Recommended:** {latest['recommended_action']}")
        else:
            st.markdown(
                '<div class="alert-banner alert-routine">'
                '<div class="alert-title">✅ ALL CLEAR</div>'
                '<div class="alert-body">No alerts — routine monitoring</div>'
                '</div>',
                unsafe_allow_html=True,
            )

        # ── Stats Grid ──
        score = risk_scores[-1]["score"] if risk_scores else 0
        s_color = "#10b981" if score <= 20 else "#f59e0b" if score <= 40 else "#f97316" if score <= 60 else "#ef4444"
        st.markdown(f"""
        <div class="stat-grid">
            <div class="stat-card"><div class="stat-value" style="color:{s_color}">{score}</div><div class="stat-label">Risk Score</div></div>
            <div class="stat-card"><div class="stat-value">{len(symptoms)}</div><div class="stat-label">Symptoms</div></div>
            <div class="stat-card"><div class="stat-value">{len(vitals)}</div><div class="stat-label">Vitals</div></div>
            <div class="stat-card"><div class="stat-value">{len(meds)}</div><div class="stat-label">Meds Taken</div></div>
        </div>
        """, unsafe_allow_html=True)

        # ── Risk Score Trend ──
        if risk_scores:
            st.markdown('<div class="section-title">Risk Score Trend</div>', unsafe_allow_html=True)
            scores_list = [r["score"] for r in risk_scores[-10:]]
            st.line_chart(scores_list, height=120, use_container_width=True)

            latest_risk = risk_scores[-1]
            if latest_risk.get("reasoning"):
                st.caption(latest_risk["reasoning"])
            if latest_risk.get("triggered_signals"):
                sigs = latest_risk["triggered_signals"]
                if isinstance(sigs, str):
                    sigs = json.loads(sigs)
                if sigs:
                    st.markdown("**Triggered Signals:** " + " ".join(f"`{s}`" for s in sigs))

        # ── Investigation Gaps ──
        if gaps:
            st.markdown('<div class="section-title">Investigation Gaps</div>', unsafe_allow_html=True)
            for g in gaps:
                p = g["priority"]
                st.markdown(
                    f'<div class="gap-pill gap-{p}">'
                    f'<strong>[{p.upper()}]</strong> {g["question"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # ── Clinical Timeline ──
        st.markdown('<div class="section-title">Clinical Timeline</div>', unsafe_allow_html=True)

        items = []
        for s in symptoms:
            cls = "tl-red" if s["severity"] >= 7 else "tl-yel" if s["severity"] >= 4 else "tl-grn"
            dot = "🔴" if s["severity"] >= 7 else "🟡" if s["severity"] >= 4 else "🟢"
            txt = s.get("free_text", "")
            detail = f' — <em>"{txt}"</em>' if txt else ""
            items.append((s["logged_at"], cls, f'{dot} <b>{s["name"]}</b> ({s["severity"]}/10){detail}'))
        for v in vitals:
            items.append((v["logged_at"], "tl-grn", f'📊 <b>{v["type"]}</b>: {v["value"]} {v["unit"]}'))
        for m in meds:
            items.append((m["logged_at"], "tl-grn", f'💊 <b>{m["med_name"]}</b> ({m["dose"]}) — taken {m["taken_at"]}'))

        items.sort(key=lambda x: x[0])

        if items:
            for ts, cls, label in items:
                t = ts.split(" ")[-1][:5] if " " in ts else ""
                st.markdown(
                    f'<div class="tl-item {cls}">'
                    f'<span style="color:#475569;font-size:10px;">{t}</span> {label}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No observations yet. Start chatting with the patient.")

        # ── Alert History ──
        if len(alerts) > 1:
            st.markdown('<div class="section-title">Alert History</div>', unsafe_allow_html=True)
            with st.expander(f"{len(alerts) - 1} previous alerts"):
                for a in reversed(alerts[:-1]):
                    st.markdown(f"**{a['severity'].upper()}**: {a['summary']}  \n_{a['created_at']}_")
