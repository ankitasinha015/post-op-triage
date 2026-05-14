"""
AI Triage Nurse — Post-Op Recovery Agent
Streamlit entry point: two-column layout with patient chat (left) and nurse dashboard (right).
"""

import json
import os
import time
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

from src import db
from src.agents.conversationalist import run_turn

load_dotenv()

st.set_page_config(
    page_title="AI Triage Nurse — Post-Op Recovery",
    page_icon="🏥",
    layout="wide",
)

st.markdown(
    """<div style="background:#fff3cd;padding:8px 16px;border-radius:4px;margin-bottom:16px;
    text-align:center;font-size:14px;color:#856404;">
    ⚠️ <strong>Educational Demo</strong> — Not medical advice. Do not use for real patient care.
    </div>""",
    unsafe_allow_html=True,
)

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

left_col, right_col = st.columns([1, 1], gap="large")

# ─── LEFT COLUMN: Patient Chat ───
with left_col:
    st.subheader("💬 Patient Chat")

    scenario_name = st.selectbox(
        "Select scenario",
        options=list(scenarios.keys()),
        key="scenario_select",
    )

    if st.button("Start New Session", type="primary"):
        scenario = scenarios[scenario_name]
        session_id = db.create_session(
            surgery_type=scenario["surgery_type"],
            recovery_day=scenario["recovery_day"],
            patient_name=scenario["patient_name"],
        )
        st.session_state.session_id = session_id
        st.session_state.chat_messages = []
        st.rerun()

    if st.session_state.session_id:
        session = db.get_session(st.session_state.session_id)
        if session:
            st.caption(
                f"**{session['patient_name']}** · {session['surgery_type']} · Day {session['recovery_day']}"
            )

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        if user_input := st.chat_input("How are you feeling?"):
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)

            with st.chat_message("assistant"):
                with st.spinner("Listening..."):
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

            st.session_state.chat_messages.append({"role": "assistant", "content": reply})
    else:
        st.info("Select a scenario and click **Start New Session** to begin.")


# ─── RIGHT COLUMN: Nurse Dashboard ───
@st.fragment(run_every=3)
def nurse_dashboard():
    st.subheader("🩺 Nurse Dashboard")

    session_id = st.session_state.get("session_id")
    if not session_id:
        st.info("Waiting for patient session...")
        return

    alerts = db.get_alerts(session_id)
    symptoms = db.get_symptoms(session_id)
    vitals = db.get_vitals(session_id)
    meds = db.get_meds(session_id)
    risk_scores = db.get_risk_scores(session_id)

    # Current alert status
    if alerts:
        latest = alerts[-1]
        severity = latest["severity"]
        color_map = {
            "routine": "#28a745",
            "monitor": "#ffc107",
            "urgent": "#fd7e14",
            "911-now": "#dc3545",
            "system-error": "#6c757d",
        }
        color = color_map.get(severity, "#6c757d")
        st.markdown(
            f"""<div style="background:{color};color:white;padding:12px 16px;border-radius:8px;
            margin-bottom:12px;font-weight:bold;font-size:18px;">
            🚨 {severity.upper()} — {latest['summary']}</div>""",
            unsafe_allow_html=True,
        )
        if latest.get("recommended_action"):
            st.caption(f"**Recommended:** {latest['recommended_action']}")
    else:
        st.markdown(
            """<div style="background:#28a745;color:white;padding:12px 16px;border-radius:8px;
            margin-bottom:12px;font-weight:bold;font-size:18px;">
            ✅ ALL CLEAR — No alerts</div>""",
            unsafe_allow_html=True,
        )

    # Risk score sparkline
    if risk_scores:
        st.caption("**Risk Score Trend**")
        scores = [r["score"] for r in risk_scores[-10:]]
        st.line_chart(scores, height=100)

    # Recovery timeline
    st.caption("**Recovery Timeline**")

    timeline_items = []
    for s in symptoms:
        timeline_items.append((s["logged_at"], "🔴" if s["severity"] >= 7 else "🟡" if s["severity"] >= 4 else "🟢",
                               f"Symptom: {s['name']} ({s['severity']}/10)", s.get("free_text", "")))
    for v in vitals:
        timeline_items.append((v["logged_at"], "📊", f"Vital: {v['type']} = {v['value']} {v['unit']}", ""))
    for m in meds:
        timeline_items.append((m["logged_at"], "💊", f"Med: {m['med_name']} ({m['dose']})", f"Taken: {m['taken_at']}"))

    timeline_items.sort(key=lambda x: x[0])

    if timeline_items:
        for ts, icon, label, detail in timeline_items:
            line = f"{icon} **{label}**"
            if detail:
                line += f" — {detail}"
            st.markdown(f"- {line}")
    else:
        st.caption("No observations yet.")

    # Alert history
    if len(alerts) > 1:
        with st.expander("Alert History"):
            for a in reversed(alerts[:-1]):
                st.markdown(f"- **{a['severity'].upper()}**: {a['summary']} ({a['created_at']})")


with right_col:
    nurse_dashboard()
