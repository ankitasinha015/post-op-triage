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
from src.guardrails import check_emergency_bypass, check_semantic_emergency, check_manipulation

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
    # Auto-seed demo data if database is empty
    if not db.get_all_sessions_with_risk():
        try:
            seed_demo()
        except Exception:
            pass
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

    # Layer 1a: Regex emergency bypass (0ms, free)
    emergency = check_emergency_bypass(req.message)
    if emergency:
        db.save_message(session_id, "user", req.message)
        db.write_alert(
            session_id, "911-now", emergency["summary"],
            signals=emergency["signals"],
            recommended_action=emergency["recommended_action"],
        )
        reply = (
            "I'm detecting emergency keywords in your message. "
            "If you are experiencing a life-threatening emergency, please call 911 immediately. "
            "A clinical team member has been alerted."
        )
        db.save_message(session_id, "assistant", reply)
        return {
            "reply": reply,
            "emergency": True,
            "alert": emergency["summary"],
        }

    import anthropic
    from src.agents.conversationalist import run_turn
    client = anthropic.Anthropic()

    # Layer 1b: Semantic emergency classifier (~500ms, catches what regex misses)
    semantic_emergency = check_semantic_emergency(client, req.message)
    if semantic_emergency:
        db.save_message(session_id, "user", req.message)
        db.write_alert(
            session_id, "911-now", semantic_emergency["summary"],
            signals=semantic_emergency["signals"],
            recommended_action=semantic_emergency["recommended_action"],
        )
        reply = (
            "I'm concerned about what you're describing. "
            "If you are experiencing a life-threatening emergency, please call 911 immediately. "
            "A clinical team member has been alerted and will review your situation."
        )
        db.save_message(session_id, "assistant", reply)
        return {
            "reply": reply,
            "emergency": True,
            "alert": semantic_emergency["summary"],
        }

    # Layer 6: Manipulation / off-topic detector
    manipulation = check_manipulation(req.message, client)
    if manipulation:
        db.save_message(session_id, "user", req.message)
        db.save_message(session_id, "assistant", manipulation["safe_reply"])
        return {
            "reply": manipulation["safe_reply"],
            "emergency": False,
            "guardrail": manipulation["type"],
        }

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

    # Layer 7: Data completeness check on conclusion
    completeness = None
    if is_conclusion:
        from src.guardrails import check_data_completeness
        completeness = check_data_completeness(session_id)
        if completeness["severity"] == "insufficient":
            db.write_alert(
                session_id, "monitor",
                f"Session concluded with insufficient clinical data (score: {completeness['completeness_score']}/100)",
                signals=["data_completeness_gap"],
                recommended_action="; ".join(completeness["gaps"]),
            )

    return {
        "reply": reply,
        "emergency": False,
        "is_conclusion": is_conclusion,
        "conclusion": conclusion_data,
        "completeness": completeness,
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
                if guardrail_result:
                    if guardrail_result.get("guardrail_adjustments"):
                        db.write_risk_score(
                            session_id=session_id,
                            score=guardrail_result["score"],
                            triggered_signals=guardrail_result["triggered_signals"],
                            reasoning=guardrail_result["reasoning"],
                        )
                    escalate(client, session_id, guardrail_result)
        except Exception as e:
            import traceback
            print(f"[RISK PIPELINE ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
            db.write_alert(
                session_id, "system-error",
                f"Risk pipeline failed: {type(e).__name__}: {e}",
                signals=["pipeline_failure"],
            )

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
    if os.environ.get("ENVIRONMENT", "development") == "production":
        raise HTTPException(status_code=403, detail="Database reset disabled in production")
    db_path = Path(__file__).parent.parent / "triage.db"
    for suffix in ["", "-wal", "-shm"]:
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    db.init_db()
    return {"status": "ok"}


# ── Seed demo data ──

@app.post("/api/seed-demo")
def seed_demo():
    existing = db.get_all_sessions_with_risk()
    if existing:
        return {"status": "skipped", "reason": "Data already exists", "patients": len(existing)}

    # Patient 1: Alex — Knee Day 3, URGENT (DVT risk)
    s1 = db.create_session("knee_replacement", 3, "Alex Thompson")
    db.save_message(s1, "assistant", "Hi Alex, I'm your recovery check-in nurse. How are you feeling today on day 3 after your knee replacement?")
    db.save_message(s1, "user", "My knee is really swollen and it hurts a lot more than yesterday. The pain meds aren't helping as much.")
    db.save_message(s1, "assistant", "I'm sorry to hear the pain is increasing. Can you describe the swelling — is it mostly around the knee, or does it extend down your leg? And what's your pain level on a scale of 0 to 10?")
    db.save_message(s1, "user", "It's like a 7 out of 10. The swelling is around my knee but my calf also feels tight and warm. I took my oxycodone an hour ago but it barely touched it.")
    db.save_message(s1, "assistant", "Thank you for those details, Alex. The combination of calf tightness and warmth with worsening pain is something I want to make sure the care team knows about. Is the warmth and tightness in one leg or both?")
    db.save_message(s1, "user", "Just the left leg, the one they operated on. The right one feels fine.")
    db.log_symptom(s1, "knee_pain", 7, "Worsening from yesterday, oxycodone not controlling well")
    db.log_symptom(s1, "swelling", 6, "Around knee and extending to calf")
    db.log_symptom(s1, "calf_tightness", 5, "Left calf feels tight and warm, unilateral")
    db.log_symptom(s1, "calf_warmth", 5, "Left calf warm to touch")
    db.log_vital(s1, "heart_rate", 92, "bpm")
    db.log_vital(s1, "temperature", 99.8, "F")
    db.log_med_taken(s1, "oxycodone", "5mg", "1 hour ago")
    db.log_med_taken(s1, "ibuprofen", "400mg", "4 hours ago")
    db.write_risk_score(s1, 62, ["leg_swelling", "calf_pain", "worsening_pain", "medication_ineffectiveness"],
        "Unilateral calf swelling and warmth after knee replacement raises DVT concern. "
        "Pain trajectory worsening despite opioid coverage. Ibuprofen may be masking true "
        "fever — reported 99.8F could be higher without NSAID suppression.")
    db.write_alert(s1, "urgent",
        "DVT risk pattern: unilateral calf swelling + warmth + worsening pain post-knee replacement",
        signals=["leg_swelling", "calf_pain", "worsening_pain"],
        recommended_action="1. Focused assessment of left lower extremity\n2. Measure calf circumference bilaterally\n3. Obtain stat duplex ultrasound of left leg\n4. Notify attending surgeon with SBAR\n5. Verify DVT prophylaxis compliance")

    # Patient 2: Jordan — Appendectomy Day 1, ROUTINE
    s2 = db.create_session("appendectomy", 1, "Jordan Rivera")
    db.save_message(s2, "assistant", "Hi Jordan, welcome to your day 1 post-op check-in after your appendectomy. How are you doing?")
    db.save_message(s2, "user", "I'm doing okay I think. A little sore around the incision and kinda nauseous. Is that normal?")
    db.save_message(s2, "assistant", "That's very common for day 1 after an appendectomy. How would you rate the pain — and have you been able to keep any fluids down?")
    db.save_message(s2, "user", "Pain is maybe a 3. I had some water and crackers earlier and kept them down. I also took the Tylenol they gave me.")
    db.log_symptom(s2, "incision_soreness", 3, "Mild soreness around surgical site, expected for day 1")
    db.log_symptom(s2, "nausea", 2, "Mild post-anesthesia nausea, tolerating fluids")
    db.log_vital(s2, "temperature", 98.9, "F")
    db.log_vital(s2, "heart_rate", 78, "bpm")
    db.log_vital(s2, "spo2", 98, "%")
    db.log_med_taken(s2, "acetaminophen", "500mg", "2 hours ago")
    db.write_risk_score(s2, 12, [],
        "Day 1 post-appendectomy with expected recovery pattern. Mild incision soreness (3/10) "
        "and post-anesthesia nausea are within normal ranges. Vitals stable. No red flags.")
    db.write_alert(s2, "routine",
        "Normal day 1 recovery: mild soreness and nausea within expected ranges",
        signals=[],
        recommended_action="Continue routine monitoring. Encourage ambulation and oral fluid intake.")

    # Patient 3: Sam — Hip Day 5, MONITOR (early infection)
    s3 = db.create_session("hip_replacement", 5, "Sam Chen")
    db.save_message(s3, "assistant", "Hi Sam, good to check in with you on day 5 after your hip replacement. How has your recovery been going?")
    db.save_message(s3, "user", "Overall okay but I noticed some redness around my incision today. It wasn't there yesterday. The pain has been about the same though.")
    db.save_message(s3, "assistant", "New redness around the incision on day 5 is worth paying attention to. Can you tell me — is the area warm to the touch? And have you noticed any drainage?")
    db.save_message(s3, "user", "Yeah it does feel a little warm. No drainage that I can see though. My temperature was 100.1 this morning.")
    db.log_symptom(s3, "wound_redness", 4, "New redness around incision, not present yesterday")
    db.log_symptom(s3, "wound_warmth", 3, "Incision area warm to touch")
    db.log_symptom(s3, "hip_pain", 4, "Stable, unchanged from prior days")
    db.log_vital(s3, "temperature", 100.1, "F")
    db.log_vital(s3, "heart_rate", 84, "bpm")
    db.log_med_taken(s3, "ibuprofen", "400mg", "6 hours ago")
    db.log_med_taken(s3, "acetaminophen", "500mg", "3 hours ago")
    db.write_risk_score(s3, 42, ["wound_redness", "wound_warmth", "persistent_fever"],
        "New wound redness and warmth on day 5 post-hip replacement is a potential early infection sign. "
        "Temperature 100.1F — ibuprofen taken 6 hours ago (duration ~6h), NSAID fever suppression "
        "may have worn off. No drainage yet is reassuring but trend warrants monitoring.")
    db.write_alert(s3, "monitor",
        "Early infection watch: new wound redness + warmth on day 5, low-grade fever 100.1F",
        signals=["wound_redness", "wound_warmth", "persistent_fever"],
        recommended_action="1. Document wound appearance\n2. Increase monitoring to every 4 hours\n3. Track temperature trend over next 12 hours\n4. Watch for drainage or fever >101.5F")

    return {"status": "seeded", "patients": 3}


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
