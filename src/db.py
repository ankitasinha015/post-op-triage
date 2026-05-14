import sqlite3
import threading
import json
import uuid
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "triage.db"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    conn = _get_conn()
    schema = _SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()


def create_session(surgery_type: str, recovery_day: int, patient_name: str = "Patient") -> str:
    session_id = str(uuid.uuid4())
    conn = _get_conn()
    conn.execute(
        "INSERT INTO session (id, surgery_type, recovery_day, patient_name) VALUES (?, ?, ?, ?)",
        (session_id, surgery_type, recovery_day, patient_name),
    )
    conn.commit()
    return session_id


def get_session(session_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def log_symptom(session_id: str, name: str, severity: int, free_text: str = "") -> int:
    severity = max(0, min(10, severity))
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO symptoms (session_id, name, severity, free_text) VALUES (?, ?, ?, ?)",
        (session_id, name, severity, free_text),
    )
    conn.commit()
    return cur.lastrowid


def log_vital(session_id: str, vital_type: str, value: float, unit: str) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO vitals (session_id, type, value, unit) VALUES (?, ?, ?, ?)",
        (session_id, vital_type, value, unit),
    )
    conn.commit()
    return cur.lastrowid


def log_med_taken(session_id: str, med_name: str, dose: str, taken_at: str) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO meds (session_id, med_name, dose, taken_at) VALUES (?, ?, ?, ?)",
        (session_id, med_name, dose, taken_at),
    )
    conn.commit()
    return cur.lastrowid


def save_message(session_id: str, role: str, content: str) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    conn.commit()
    return cur.lastrowid


def get_messages(session_id: str, limit: int = 20) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def get_symptoms(session_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT name, severity, free_text, logged_at FROM symptoms WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_vitals(session_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT type, value, unit, logged_at FROM vitals WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_meds(session_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT med_name, dose, taken_at, logged_at FROM meds WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def write_alert(session_id: str, severity: str, summary: str,
                signals: list[str] | None = None,
                recommended_action: str = "",
                citations: list[str] | None = None) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO alerts (session_id, severity, summary, signals, recommended_action, citations) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, severity, summary,
         json.dumps(signals) if signals else None,
         recommended_action,
         json.dumps(citations) if citations else None),
    )
    conn.commit()
    return cur.lastrowid


def get_alerts(session_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT severity, summary, signals, recommended_action, citations, created_at FROM alerts WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        if d["signals"]:
            d["signals"] = json.loads(d["signals"])
        if d["citations"]:
            d["citations"] = json.loads(d["citations"])
        results.append(d)
    return results


def write_risk_score(session_id: str, score: int, triggered_signals: list[str],
                     reasoning: str = "") -> int:
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO risk_scores (session_id, score, triggered_signals, reasoning) VALUES (?, ?, ?, ?)",
        (session_id, score, json.dumps(triggered_signals), reasoning),
    )
    conn.commit()
    return cur.lastrowid


def get_risk_scores(session_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT score, triggered_signals, reasoning, assessed_at FROM risk_scores WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        if d["triggered_signals"]:
            d["triggered_signals"] = json.loads(d["triggered_signals"])
        results.append(d)
    return results


def get_session_state(session_id: str) -> dict:
    session = get_session(session_id)
    if not session:
        return {}
    return {
        "session": session,
        "symptoms": get_symptoms(session_id),
        "vitals": get_vitals(session_id),
        "meds": get_meds(session_id),
        "alerts": get_alerts(session_id),
        "risk_scores": get_risk_scores(session_id),
    }


def save_patient_history(session_id: str, patient_name: str, surgery_type: str,
                         recovery_day: int, key_findings: list[str],
                         risk_level: str, unresolved_concerns: list[str],
                         resolved_concerns: list[str], session_summary: str) -> int:
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO patient_history
           (patient_name, session_id, surgery_type, recovery_day, key_findings,
            risk_level, unresolved_concerns, resolved_concerns, session_summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (patient_name, session_id, surgery_type, recovery_day,
         json.dumps(key_findings), risk_level,
         json.dumps(unresolved_concerns), json.dumps(resolved_concerns),
         session_summary),
    )
    conn.commit()
    return cur.lastrowid


def get_patient_history(patient_name: str, exclude_session_id: str = "") -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        """SELECT session_id, surgery_type, recovery_day, key_findings, risk_level,
                  unresolved_concerns, resolved_concerns, session_summary, recorded_at
           FROM patient_history WHERE patient_name = ? AND session_id != ?
           ORDER BY recorded_at DESC LIMIT 10""",
        (patient_name, exclude_session_id),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["key_findings"] = json.loads(d["key_findings"])
        d["unresolved_concerns"] = json.loads(d["unresolved_concerns"])
        d["resolved_concerns"] = json.loads(d["resolved_concerns"])
        results.append(d)
    return results


def write_investigation_gap(session_id: str, question: str,
                            priority: str = "medium", source: str = "risk_assessor") -> int:
    """Write a gap the Risk Assessor wants the Conversationalist to probe."""
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO investigation_gaps (session_id, question, priority, source) VALUES (?, ?, ?, ?)",
        (session_id, question, priority, source),
    )
    conn.commit()
    return cur.lastrowid


def get_investigation_gaps(session_id: str, only_unaddressed: bool = True) -> list[dict]:
    """Get investigation gaps for this session."""
    conn = _get_conn()
    query = "SELECT id, question, priority, source, addressed, created_at FROM investigation_gaps WHERE session_id = ?"
    if only_unaddressed:
        query += " AND addressed = 0"
    query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END, id"
    rows = conn.execute(query, (session_id,)).fetchall()
    return [dict(r) for r in rows]


def mark_gap_addressed(gap_id: int) -> None:
    """Mark an investigation gap as addressed."""
    conn = _get_conn()
    conn.execute("UPDATE investigation_gaps SET addressed = 1 WHERE id = ?", (gap_id,))
    conn.commit()


def build_patient_context(session_id: str) -> str:
    """Build a structured clinical context string for agent prompts.
    Includes: current session data, symptom trends, vital trends,
    medication timeline, prior alerts, and cross-session history."""
    session = get_session(session_id)
    if not session:
        return ""

    lines = []
    lines.append("=== CURRENT SESSION ===")
    lines.append(f"Patient: {session['patient_name']}")
    lines.append(f"Surgery: {session['surgery_type']}, Recovery Day {session['recovery_day']}")
    lines.append(f"Session started: {session['started_at']}")

    # Symptom timeline with trend detection
    symptoms = get_symptoms(session_id)
    if symptoms:
        lines.append("\n--- SYMPTOMS (chronological) ---")
        symptom_by_name: dict[str, list] = {}
        for s in symptoms:
            lines.append(f"  [{s['logged_at']}] {s['name']}: {s['severity']}/10"
                         + (f" -- \"{s['free_text']}\"" if s.get('free_text') else ""))
            symptom_by_name.setdefault(s["name"], []).append(s["severity"])

        trends = []
        for name, scores in symptom_by_name.items():
            if len(scores) >= 2:
                delta = scores[-1] - scores[0]
                if delta > 0:
                    trends.append(f"  [UP] {name}: WORSENING ({scores[0]} -> {scores[-1]})")
                elif delta < 0:
                    trends.append(f"  [DOWN] {name}: IMPROVING ({scores[0]} -> {scores[-1]})")
                else:
                    trends.append(f"  [STABLE] {name}: STABLE at {scores[-1]}")
        if trends:
            lines.append("\n--- SYMPTOM TRENDS ---")
            lines.extend(trends)
    else:
        lines.append("\n--- SYMPTOMS: None reported yet ---")

    # Vital signs
    vitals = get_vitals(session_id)
    if vitals:
        lines.append("\n--- VITALS ---")
        for v in vitals:
            lines.append(f"  [{v['logged_at']}] {v['type']}: {v['value']} {v['unit']}")
    else:
        lines.append("\n--- VITALS: None recorded yet ---")

    # Medications
    meds = get_meds(session_id)
    if meds:
        lines.append("\n--- MEDICATIONS ---")
        for m in meds:
            lines.append(f"  [{m['logged_at']}] {m['med_name']} {m['dose']} (taken: {m['taken_at']})")
    else:
        lines.append("\n--- MEDICATIONS: None recorded yet ---")

    # Prior alerts this session
    alerts = get_alerts(session_id)
    if alerts:
        lines.append("\n--- PRIOR ALERTS (this session) ---")
        for a in alerts:
            lines.append(f"  [{a['created_at']}] {a['severity'].upper()}: {a['summary']}")

    # Risk score history
    risk_scores = get_risk_scores(session_id)
    if risk_scores:
        lines.append("\n--- RISK SCORE HISTORY ---")
        for r in risk_scores:
            signals = ", ".join(r["triggered_signals"]) if r.get("triggered_signals") else "none"
            lines.append(f"  [{r['assessed_at']}] Score: {r['score']}/100 | Signals: {signals}")

    # Cross-session history
    history = get_patient_history(session["patient_name"], exclude_session_id=session_id)
    if history:
        lines.append("\n=== PRIOR SESSIONS (most recent first) ===")
        for h in history:
            lines.append(f"\n  Session: {h['surgery_type']}, Day {h['recovery_day']} ({h['recorded_at']})")
            lines.append(f"  Risk level: {h['risk_level']}")
            lines.append(f"  Summary: {h['session_summary']}")
            if h["key_findings"]:
                lines.append(f"  Key findings: {', '.join(h['key_findings'])}")
            if h["unresolved_concerns"]:
                lines.append(f"  [!] Unresolved: {', '.join(h['unresolved_concerns'])}")
            if h["resolved_concerns"]:
                lines.append(f"  [OK] Resolved: {', '.join(h['resolved_concerns'])}")

    return "\n".join(lines)
