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
