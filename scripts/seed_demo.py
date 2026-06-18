"""
Seed the database with realistic demo data for interview presentations.

Run: python scripts/seed_demo.py
Resets the DB and creates 3 patient sessions at different risk levels
so the nurse dashboard looks populated from the start.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db


def seed():
    # Wipe and reinitialize
    db_path = Path(__file__).parent.parent / "triage.db"
    for suffix in ["", "-wal", "-shm"]:
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    db.init_db()

    # ── Patient 1: Alex — Knee replacement Day 3, URGENT ──
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
        "fever — reported 99.8F could be higher without NSAID suppression. "
        "Compound pattern: unilateral swelling + warmth + worsening pain = DVT risk cluster.")

    db.write_alert(s1, "urgent",
        "DVT risk pattern: unilateral calf swelling + warmth + worsening pain post-knee replacement",
        signals=["leg_swelling", "calf_pain", "worsening_pain"],
        recommended_action="1. Focused assessment of left lower extremity — check for Homans sign\n"
                          "2. Measure calf circumference bilaterally and compare\n"
                          "3. Obtain stat duplex ultrasound of left leg\n"
                          "4. Notify attending surgeon with SBAR\n"
                          "5. Verify DVT prophylaxis compliance")

    db.write_investigation_gap(s1, "Ask about any shortness of breath or chest discomfort — PE screening given DVT risk", "high")

    # ── Patient 2: Jordan — Appendectomy Day 1, ROUTINE ──
    s2 = db.create_session("appendectomy", 1, "Jordan Rivera")

    db.save_message(s2, "assistant", "Hi Jordan, welcome to your day 1 post-op check-in after your appendectomy. How are you doing?")
    db.save_message(s2, "user", "I'm doing okay I think. A little sore around the incision and kinda nauseous. Is that normal?")
    db.save_message(s2, "assistant", "That's very common for day 1 after an appendectomy. The soreness around your incision and nausea are typical effects of the anesthesia and surgery. How would you rate the pain — and have you been able to keep any fluids down?")
    db.save_message(s2, "user", "Pain is maybe a 3. I had some water and crackers earlier and kept them down. I also took the Tylenol they gave me.")

    db.log_symptom(s2, "incision_soreness", 3, "Mild soreness around surgical site, expected for day 1")
    db.log_symptom(s2, "nausea", 2, "Mild post-anesthesia nausea, tolerating fluids")

    db.log_vital(s2, "temperature", 98.9, "F")
    db.log_vital(s2, "heart_rate", 78, "bpm")
    db.log_vital(s2, "spo2", 98, "%")

    db.log_med_taken(s2, "acetaminophen", "500mg", "2 hours ago")

    db.write_risk_score(s2, 12, [],
        "Day 1 post-appendectomy with expected recovery pattern. Mild incision soreness (3/10) "
        "and post-anesthesia nausea are within normal ranges. Tolerating oral intake. "
        "Vitals stable — temp 98.9, HR 78, SpO2 98%. No red flags. Continue routine monitoring.")

    db.write_alert(s2, "routine",
        "Normal day 1 recovery: mild soreness and nausea within expected ranges",
        signals=[],
        recommended_action="Continue routine monitoring. Encourage ambulation and oral fluid intake. "
                          "Reassess at next shift.")

    # ── Patient 3: Sam — Hip replacement Day 5, MONITOR ──
    s3 = db.create_session("hip_replacement", 5, "Sam Chen")

    db.save_message(s3, "assistant", "Hi Sam, good to check in with you on day 5 after your hip replacement. How has your recovery been going?")
    db.save_message(s3, "user", "Overall okay but I noticed some redness around my incision today. It wasn't there yesterday. The pain has been about the same though.")
    db.save_message(s3, "assistant", "New redness around the incision on day 5 is worth paying attention to. Can you tell me — is the area warm to the touch? And have you noticed any drainage or fluid from the incision site?")
    db.save_message(s3, "user", "Yeah it does feel a little warm. No drainage that I can see though. I've been keeping it clean like they told me. My temperature was 100.1 this morning.")

    db.log_symptom(s3, "wound_redness", 4, "New redness around incision, not present yesterday")
    db.log_symptom(s3, "wound_warmth", 3, "Incision area warm to touch")
    db.log_symptom(s3, "hip_pain", 4, "Stable, unchanged from prior days")

    db.log_vital(s3, "temperature", 100.1, "F")
    db.log_vital(s3, "heart_rate", 84, "bpm")

    db.log_med_taken(s3, "ibuprofen", "400mg", "6 hours ago")
    db.log_med_taken(s3, "acetaminophen", "500mg", "3 hours ago")

    db.write_risk_score(s3, 42, ["wound_redness", "wound_warmth", "persistent_fever"],
        "New wound redness and warmth on day 5 post-hip replacement is a potential early infection sign. "
        "Temperature 100.1F — note patient took ibuprofen 6 hours ago (duration ~6h), so NSAID fever "
        "suppression may have worn off. True temperature could be higher. No drainage yet is reassuring, "
        "but the trend (new finding, not present yesterday) warrants increased monitoring. "
        "Pain stable is a positive sign — worsening pain + wound changes would be more concerning.")

    db.write_alert(s3, "monitor",
        "Early infection watch: new wound redness + warmth on day 5, low-grade fever 100.1F",
        signals=["wound_redness", "wound_warmth", "persistent_fever"],
        recommended_action="1. Document wound appearance — photo if possible\n"
                          "2. Increase monitoring frequency to every 4 hours\n"
                          "3. Track temperature trend over next 12 hours\n"
                          "4. Watch for drainage, increasing redness, or fever >101.5F\n"
                          "5. Educate patient on infection warning signs to report immediately")

    print(f"Demo data seeded successfully!")
    print(f"  - Alex Thompson  (knee_replacement, day 3) — URGENT  [score: 62]")
    print(f"  - Jordan Rivera  (appendectomy, day 1)     — ROUTINE [score: 12]")
    print(f"  - Sam Chen       (hip_replacement, day 5)  — MONITOR [score: 42]")
    print(f"\nStart the server: python -m uvicorn api.main:app --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    seed()
