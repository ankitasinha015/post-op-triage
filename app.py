"""
AI Triage Nurse — Post-Op Recovery Agent
Streamlit entry point: two-column layout with patient chat (left) and nurse dashboard (right).
"""

import json
import os
import threading
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

from src import db
from src.agents.conversationalist import run_turn
from src.agents.risk_assessor import assess_risk
from src.agents.escalator import escalate
from src.guardrails import check_emergency_bypass, run_guardrails_on_risk_assessment

load_dotenv()

st.set_page_config(
    page_title="AI Triage Nurse — Post-Op Recovery",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Global Styles ───
st.markdown("""
<style>
    /* Tighter top padding */
    .block-container { padding-top: 1rem; }

    /* Chat message styling */
    .stChatMessage { border-radius: 12px; }

    /* Alert banner pulse animation for urgent+ */
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.85; } }
    .alert-urgent { animation: pulse 2s ease-in-out infinite; }

    /* Dashboard section headers */
    .dash-header {
        font-size: 13px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #666;
        margin-top: 16px;
        margin-bottom: 8px;
        border-bottom: 1px solid #eee;
        padding-bottom: 4px;
    }

    /* Timeline entry */
    .timeline-entry {
        font-size: 13px;
        padding: 4px 0;
        border-left: 2px solid #ddd;
        padding-left: 12px;
        margin-left: 4px;
    }
    .timeline-entry.severity-high { border-left-color: #dc3545; }
    .timeline-entry.severity-med  { border-left-color: #ffc107; }
    .timeline-entry.severity-low  { border-left-color: #28a745; }

    /* Investigation gap badges */
    .gap-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 12px;
        margin: 2px 0;
    }
    .gap-high   { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    .gap-medium { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
    .gap-low    { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }

    /* Metric cards */
    .metric-row {
        display: flex;
        gap: 8px;
        margin-bottom: 12px;
    }
    .metric-card {
        flex: 1;
        background: #f8f9fa;
        border-radius: 8px;
        padding: 12px;
        text-align: center;
    }
    .metric-card .value {
        font-size: 24px;
        font-weight: 700;
        line-height: 1.2;
    }
    .metric-card .label {
        font-size: 11px;
        color: #888;
        text-transform: uppercase;
    }

    /* Scenario description */
    .scenario-desc {
        font-size: 13px;
        color: #666;
        padding: 8px 12px;
        background: #f8f9fa;
        border-radius: 6px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Header ───
st.markdown("""
<div style="text-align:center; margin-bottom:4px;">
    <h2 style="margin-bottom:2px;">🏥 AI Triage Nurse</h2>
    <p style="color:#888; font-size:14px; margin-top:0;">Post-Operative Recovery Monitoring System</p>
</div>
<div style="background:#fff3cd;padding:6px 16px;border-radius:4px;margin-bottom:16px;
text-align:center;font-size:13px;color:#856404;">
⚠️ <strong>Educational Demo</strong> — Not medical advice. Do not use for real patient care.
</div>
""", unsafe_allow_html=True)

SCENARIOS_DIR = Path(__file__).parent / "src" / "scenarios"


def load_scenarios() -> dict[str, dict]:
    scenarios = {}
    for f in sorted(SCENARIOS_DIR.glob("*.json")):
        data = json.loads(f.read_text())
        scenarios[data["name"]] = data
    return scenarios


def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("Set ANTHROPIC_API_KEY in your .env file.")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)


db.init_db()
scenarios = load_scenarios()

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []
if "agent_status" not in st.session_state:
    st.session_state.agent_status = "idle"

left_col, right_col = st.columns([1, 1], gap="large")

# ━━━ LEFT COLUMN: Patient Chat ━━━
with left_col:
    st.markdown("### 💬 Patient Chat")

    scenario_name = st.selectbox(
        "Select scenario",
        options=list(scenarios.keys()),
        key="scenario_select",
    )

    # Show scenario description
    selected = scenarios[scenario_name]
    st.markdown(
        f'<div class="scenario-desc">{selected["description"]}</div>',
        unsafe_allow_html=True,
    )

    if st.button("Start New Session", type="primary", use_container_width=True):
        session_id = db.create_session(
            surgery_type=selected["surgery_type"],
            recovery_day=selected["recovery_day"],
            patient_name=selected["patient_name"],
        )
        st.session_state.session_id = session_id
        st.session_state.chat_messages = []
        st.session_state.agent_status = "idle"
        st.rerun()

    if st.session_state.session_id:
        session = db.get_session(st.session_state.session_id)
        if session:
            st.markdown(
                f"**{session['patient_name']}** · "
                f"`{session['surgery_type']}` · "
                f"Recovery Day **{session['recovery_day']}**"
            )

        # Chat history
        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Chat input
        if user_input := st.chat_input("How are you feeling today?"):
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)

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

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    try:
                        client = get_client()
                        reply = run_turn(client, st.session_state.session_id, user_input)
                    except Exception as e:
                        reply = f"I'm having trouble responding right now. (Error: {e})"
                        db.write_alert(
                            st.session_state.session_id,
                            "system-error",
                            f"Conversationalist agent failed: {e}",
                            signals=["agent_failure"],
                            recommended_action="Check API key and network connection.",
                        )
                st.write(reply)

            # Background: Risk Assessor + Escalator
            def _run_background_assessment(sid: str):
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
                        recommended_action="Risk assessment unavailable. Manual review recommended.",
                    )

            threading.Thread(
                target=_run_background_assessment,
                args=(st.session_state.session_id,),
                daemon=True,
            ).start()

            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
    else:
        st.markdown("""
        <div style="text-align:center; padding:40px 20px; color:#888;">
            <p style="font-size:48px; margin-bottom:8px;">👆</p>
            <p>Select a scenario and click <strong>Start New Session</strong> to begin.</p>
        </div>
        """, unsafe_allow_html=True)


# ━━━ RIGHT COLUMN: Nurse Dashboard ━━━
@st.fragment(run_every=3)
def nurse_dashboard():
    st.markdown("### 🩺 Nurse Dashboard")

    session_id = st.session_state.get("session_id")
    if not session_id:
        st.markdown("""
        <div style="text-align:center; padding:40px 20px; color:#888;">
            <p style="font-size:48px; margin-bottom:8px;">⏳</p>
            <p>Waiting for patient session...</p>
        </div>
        """, unsafe_allow_html=True)
        return

    alerts = db.get_alerts(session_id)
    symptoms = db.get_symptoms(session_id)
    vitals = db.get_vitals(session_id)
    meds = db.get_meds(session_id)
    risk_scores = db.get_risk_scores(session_id)
    investigation_gaps = db.get_investigation_gaps(session_id, only_unaddressed=True)

    # ── Alert Banner ──
    if alerts:
        latest = alerts[-1]
        severity = latest["severity"]
        color_map = {
            "routine": "#28a745",
            "monitor": "#ffc107",
            "urgent": "#fd7e14",
            "critical": "#dc3545",
            "911-now": "#dc3545",
            "system-error": "#6c757d",
        }
        icon_map = {
            "routine": "✅",
            "monitor": "👁️",
            "urgent": "⚠️",
            "critical": "🚨",
            "911-now": "🆘",
            "system-error": "⚙️",
        }
        text_color = "white" if severity != "monitor" else "#333"
        color = color_map.get(severity, "#6c757d")
        icon = icon_map.get(severity, "🔔")
        pulse_class = "alert-urgent" if severity in ("urgent", "critical", "911-now") else ""

        st.markdown(
            f"""<div class="{pulse_class}" style="background:{color};color:{text_color};
            padding:14px 18px;border-radius:10px;margin-bottom:8px;">
            <div style="font-size:20px;font-weight:700;">{icon} {severity.upper()}</div>
            <div style="font-size:14px;margin-top:4px;">{latest['summary']}</div>
            </div>""",
            unsafe_allow_html=True,
        )
        if latest.get("recommended_action"):
            st.caption(f"**Recommended:** {latest['recommended_action']}")
    else:
        st.markdown(
            """<div style="background:#28a745;color:white;padding:14px 18px;border-radius:10px;
            margin-bottom:8px;">
            <div style="font-size:20px;font-weight:700;">✅ ALL CLEAR</div>
            <div style="font-size:14px;margin-top:4px;">No alerts — routine monitoring</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # ── Quick Metrics ──
    latest_score = risk_scores[-1]["score"] if risk_scores else 0
    score_color = "#28a745" if latest_score <= 20 else "#ffc107" if latest_score <= 40 else "#fd7e14" if latest_score <= 60 else "#dc3545"

    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="value" style="color:{score_color}">{latest_score}</div>
            <div class="label">Risk Score</div>
        </div>
        <div class="metric-card">
            <div class="value">{len(symptoms)}</div>
            <div class="label">Symptoms</div>
        </div>
        <div class="metric-card">
            <div class="value">{len(vitals)}</div>
            <div class="label">Vitals</div>
        </div>
        <div class="metric-card">
            <div class="value">{len(meds)}</div>
            <div class="label">Meds</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Risk Score Trend ──
    if risk_scores:
        st.markdown('<div class="dash-header">Risk Score Trend</div>', unsafe_allow_html=True)
        scores = [r["score"] for r in risk_scores[-10:]]
        st.line_chart(scores, height=120, use_container_width=True)

        latest_risk = risk_scores[-1]
        if latest_risk.get("reasoning"):
            st.caption(f"**Assessment:** {latest_risk['reasoning']}")
        if latest_risk.get("triggered_signals"):
            signals = latest_risk["triggered_signals"]
            if isinstance(signals, str):
                signals = json.loads(signals)
            if signals:
                signal_badges = " ".join(
                    f'`{s}`' for s in signals
                )
                st.markdown(f"**Signals:** {signal_badges}")

    # ── Investigation Gaps ──
    if investigation_gaps:
        st.markdown('<div class="dash-header">Investigation Gaps</div>', unsafe_allow_html=True)
        st.caption("Risk Assessor flagged these for follow-up:")
        for g in investigation_gaps:
            css_class = f"gap-{g['priority']}"
            priority_label = g["priority"].upper()
            st.markdown(
                f'<div class="gap-badge {css_class}"><strong>[{priority_label}]</strong> {g["question"]}</div>',
                unsafe_allow_html=True,
            )

    # ── Clinical Timeline ──
    st.markdown('<div class="dash-header">Clinical Timeline</div>', unsafe_allow_html=True)

    timeline_items = []
    for s in symptoms:
        sev_class = "severity-high" if s["severity"] >= 7 else "severity-med" if s["severity"] >= 4 else "severity-low"
        icon = "🔴" if s["severity"] >= 7 else "🟡" if s["severity"] >= 4 else "🟢"
        detail = f' — "{s["free_text"]}"' if s.get("free_text") else ""
        timeline_items.append((
            s["logged_at"], sev_class,
            f'{icon} <strong>{s["name"]}</strong> ({s["severity"]}/10){detail}'
        ))
    for v in vitals:
        timeline_items.append((
            v["logged_at"], "severity-low",
            f'📊 <strong>{v["type"]}</strong>: {v["value"]} {v["unit"]}'
        ))
    for m in meds:
        timeline_items.append((
            m["logged_at"], "severity-low",
            f'💊 <strong>{m["med_name"]}</strong> ({m["dose"]}) — taken: {m["taken_at"]}'
        ))

    timeline_items.sort(key=lambda x: x[0])

    if timeline_items:
        for ts, sev_class, label in timeline_items:
            time_short = ts.split(" ")[-1][:5] if " " in ts else ts
            st.markdown(
                f'<div class="timeline-entry {sev_class}">'
                f'<span style="color:#999;font-size:11px;">{time_short}</span> {label}'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("No observations yet.")

    # ── Alert History ──
    if len(alerts) > 1:
        st.markdown('<div class="dash-header">Alert History</div>', unsafe_allow_html=True)
        with st.expander(f"View {len(alerts) - 1} previous alerts"):
            for a in reversed(alerts[:-1]):
                sev = a["severity"].upper()
                st.markdown(f"- **{sev}**: {a['summary']}  \n  _{a['created_at']}_")

    # ── Agent Pipeline Status ──
    st.markdown('<div class="dash-header">Agent Pipeline</div>', unsafe_allow_html=True)
    agent_count = 3
    tool_count = 10  # 4 conversationalist + 6 risk assessor
    st.markdown(f"""
    <div style="font-size:12px; color:#888; line-height:1.6;">
    <strong>Conversationalist</strong> (Sonnet) — 4 tools · patient-facing<br>
    <strong>Risk Assessor</strong> (Sonnet) — 6 tools · background investigator<br>
    <strong>Escalator</strong> (Haiku) — alert translator<br>
    <span style="color:#aaa;">Guardrails: 5 layers active · Red flags: 21 signals</span>
    </div>
    """, unsafe_allow_html=True)


with right_col:
    nurse_dashboard()
