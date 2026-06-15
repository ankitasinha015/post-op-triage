"""
FastAPI backend for AI Triage Nurse.
Wraps existing db.py and agent code into REST + WebSocket endpoints.
"""

import os
import sys
import json
import threading
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Add project root to path so we can import src.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db
from src.guardrails import check_emergency_bypass

# Norton TLS fix
CERT_PATH = Path.home() / "certs" / "cacert.pem"
if CERT_PATH.exists():
    os.environ["SSL_CERT_FILE"] = str(CERT_PATH)
    os.environ["REQUESTS_CA_BUNDLE"] = str(CERT_PATH)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield

app = FastAPI(
    title="AI Triage Nurse API",
    description="Post-operative recovery triage agent API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ──

class CreateSessionRequest(BaseModel):
    surgery_type: str
    recovery_day: int
    patient_name: str = "Patient"

class SendMessageRequest(BaseModel):
    message: str

class SessionResponse(BaseModel):
    id: str
    patient_name: str
    surgery_type: str
    recovery_day: int
    started_at: str

class WorklistItem(BaseModel):
    id: str
    patient_name: str
    surgery_type: str
    recovery_day: int
    started_at: str
    risk_score: int
    risk_reasoning: str | None = None
    triggered_signals: list[str] = []
    symptom_count: int = 0
    urgent_alert_count: int = 0
    latest_alert: str | None = None


# ── Scenario endpoints ──

@app.get("/api/scenarios")
def list_scenarios():
    scenarios_dir = Path(__file__).parent.parent / "src" / "scenarios"
    scenarios = []
    if scenarios_dir.exists():
        for f in sorted(scenarios_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                scenarios.append(data)
            except (json.JSONDecodeError, KeyError):
                continue
    return scenarios


# ── Session endpoints ──

@app.post("/api/sessions", response_model=SessionResponse)
def create_session(req: CreateSessionRequest):
    session_id = db.create_session(req.surgery_type, req.recovery_day, req.patient_name)
    session = db.get_session(session_id)
    return session

@app.get("/api/sessions")
def list_sessions():
    return db.get_all_sessions_with_risk()

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.get("/api/sessions/{session_id}/state")
def get_session_state(session_id: str):
    state = db.get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return state


# ── Message endpoints ──

@app.get("/api/sessions/{session_id}/messages")
def get_messages(session_id: str, limit: int = 50):
    return db.get_messages(session_id, limit=limit)

@app.post("/api/sessions/{session_id}/messages")
def send_message(session_id: str, req: SendMessageRequest):
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    emergency = check_emergency_bypass(req.message)
    if emergency:
        db.save_message(session_id, "user", req.message)
        db.write_alert(
            session_id, "911-now", emergency["alert"],
            signals=["emergency_bypass"],
            recommended_action=emergency["action"],
        )
        reply = emergency["reply"]
        db.save_message(session_id, "assistant", reply)
        return {
            "reply": reply,
            "emergency": True,
            "alert": emergency["alert"],
        }

    import anthropic
    from src.agents.conversationalist import run_turn
    client = anthropic.Anthropic()

    try:
        reply = run_turn(client, session_id, req.message)
    except Exception as e:
        db.write_alert(
            session_id, "system-error",
            f"Conversationalist failed: {type(e).__name__}",
            signals=["agent_failure"],
        )
        raise HTTPException(status_code=502, detail="Agent failed to respond")

    # Run risk assessment in background
    _run_risk_pipeline_async(client, session_id)

    # Check if this is a conclusion turn
    is_conclusion = False
    conclusion_data = None
    try:
        parsed = json.loads(reply)
        if parsed.get("conclusion"):
            is_conclusion = True
            conclusion_data = parsed
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "reply": reply,
        "emergency": False,
        "is_conclusion": is_conclusion,
        "conclusion": conclusion_data,
    }


def _run_risk_pipeline_async(client, session_id: str):
    def _run():
        try:
            from src.agents.risk_assessor import assess_risk
            from src.agents.escalator import escalate
            from src.guardrails import run_guardrails_on_risk_assessment

            risk_result = assess_risk(client, session_id)
            if risk_result:
                guardrail_result = run_guardrails_on_risk_assessment(
                    session_id, risk_result
                )
                if guardrail_result and guardrail_result.get("should_escalate"):
                    escalate(client, session_id, risk_result)
        except Exception:
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


# ── Clinical data endpoints ──

@app.get("/api/sessions/{session_id}/symptoms")
def get_symptoms(session_id: str):
    return db.get_symptoms(session_id)

@app.get("/api/sessions/{session_id}/vitals")
def get_vitals(session_id: str):
    return db.get_vitals(session_id)

@app.get("/api/sessions/{session_id}/meds")
def get_meds(session_id: str):
    return db.get_meds(session_id)

@app.get("/api/sessions/{session_id}/alerts")
def get_alerts(session_id: str):
    alerts = db.get_alerts(session_id)
    return [a for a in alerts if a["severity"] != "system-error"]

@app.get("/api/sessions/{session_id}/risk-scores")
def get_risk_scores(session_id: str):
    return db.get_risk_scores(session_id)

@app.get("/api/sessions/{session_id}/conclusion")
def get_conclusion(session_id: str):
    return db.get_session_conclusion(session_id)


# ── Worklist endpoint ──

@app.get("/api/worklist")
def get_worklist():
    return db.get_all_sessions_with_risk()


# ── Database reset (dev only) ──

@app.post("/api/reset-db")
def reset_db():
    db_path = Path(__file__).parent.parent / "triage.db"
    for suffix in ["", "-wal", "-shm"]:
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    db.init_db()
    return {"status": "ok"}


# ── WebSocket for real-time updates ──

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(session_id, []).append(ws)

    def disconnect(self, session_id: str, ws: WebSocket):
        if session_id in self.active:
            self.active[session_id] = [
                w for w in self.active[session_id] if w != ws
            ]

    async def broadcast(self, session_id: str, data: dict):
        for ws in self.active.get(session_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass

manager = ConnectionManager()

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(ws: WebSocket, session_id: str):
    await manager.connect(session_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id, ws)


# ── Serve React frontend (production) ──

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
