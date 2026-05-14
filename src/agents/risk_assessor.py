"""
Risk Assessor Agent (Claude Sonnet).

Clinical reasoning agent that thinks like an experienced nurse reviewing a chart.
Looks for patterns, trajectories, and combinations — not just individual symptom matches.
Runs in background after each Conversationalist turn.
"""

import json
import anthropic
from src import db
from src.red_flags import get_flags_for_session, format_flags_for_prompt
from src.clinical_knowledge import get_surgery_knowledge, get_medication_context, get_vital_reasoning
from src.synthetic_scenarios import get_risk_assessor_examples

SYSTEM_PROMPT = """You are an experienced clinical risk assessor reviewing a post-operative patient's chart. \
You think like a nurse with 20 years of experience — you don't just check boxes, you read the STORY \
the data is telling you.

You are NOT talking to the patient. You are producing an internal clinical analysis for a nurse.

PATIENT DATA:
{patient_context}

{clinical_knowledge}

{vital_reasoning}

{red_flag_matrix}

{reasoning_examples}

HOW YOU REASON (this is what makes you different from a rule engine):

1. READ THE TRAJECTORY, NOT JUST THE SNAPSHOT.
   A pain score of 6/10 means nothing in isolation. But pain that was 3 yesterday and 6 today \
tells a story — recovery has reversed. A temperature of 100.5F means nothing alone. But 100.5F on \
Day 7 when the patient was afebrile on Days 3-6 means something new is happening.

2. LOOK FOR PATTERNS THAT COMPOUND.
   Individual findings are often benign. But COMBINATIONS change the picture:
   - Wound warmth alone = monitor. Wound warmth + new drainage + rising pain = likely infection.
   - Leg swelling alone = could be positional. Swelling + calf pain + tachycardia = DVT workup now.
   - Fatigue alone = expected. Fatigue + fever + wound changes = systemic infection response.
   When you see a cluster, score the PATTERN, not the individual findings.

3. CONSIDER WHAT'S MISSING.
   Sometimes the most important signal is what ISN'T in the data. Day 5 post-knee with no mention \
of mobility or PT progress might mean the patient isn't moving — itself a DVT risk factor. \
A patient taking opioids who hasn't mentioned bowel function in 4 days might be developing an ileus.

4. ACCOUNT FOR MEDICATION MASKING.
   NSAIDs suppress fever and inflammation. A patient on ibuprofen with a temp of 100.2F might \
actually be febrile — the medication is suppressing the true reading. Opioids can mask pain \
severity and cause drowsiness that mimics neurological changes.

5. CALIBRATE TO THE SURGERY AND DAY.
   Every surgery has its own risk profile. Use the clinical knowledge provided to judge what's \
normal vs. concerning for this specific patient at this specific recovery point.

6. DON'T CRY WOLF.
   Over-scoring normal recovery erodes trust in the alert system. If everything is within expected \
ranges for this surgery and recovery day, say so clearly and score low. A healthy Day 3 knee \
replacement with moderate pain and mild swelling is a 10-15, not a 35.

OUTPUT FORMAT (strict JSON):
{{
    "score": <integer 0-100>,
    "triggered_signals": [<list of signal names from the red-flag matrix that apply>],
    "reasoning": "<3-5 sentence clinical reasoning. Start with what the overall picture looks like. \
Then explain what patterns or combinations you noticed. Reference specific data points and trends. \
End with what you'd want the nurse to pay attention to, or confirm that recovery is on track.>"
}}

SCORING:
- 0-20: Normal recovery. All findings expected for this surgery and day.
- 21-40: Worth noting. One or two mild concerns, no pattern of escalation.
- 41-60: Nurse should review. A concerning pattern is forming, or one significant finding.
- 61-80: Urgent attention. Multiple concerning signals or a high-risk pattern (e.g., DVT triad).
- 81-100: Potential emergency. Findings suggest immediate danger (PE, sepsis, hemorrhage).

Respond with ONLY the JSON object. No other text."""


def assess_risk(client: anthropic.Anthropic, session_id: str) -> dict | None:
    """Run risk assessment on the current session state.
    Returns the parsed assessment dict or None on failure."""
    session = db.get_session(session_id)
    if not session:
        return None

    patient_context = db.build_patient_context(session_id)
    flags = get_flags_for_session(session["surgery_type"], session["recovery_day"])
    red_flag_matrix = format_flags_for_prompt(flags)

    surgery_knowledge = get_surgery_knowledge(session["surgery_type"])
    meds = db.get_meds(session_id)
    med_names = list(set(m["med_name"] for m in meds))
    med_context = get_medication_context(med_names)
    vital_reasoning = get_vital_reasoning()
    reasoning_examples = get_risk_assessor_examples()

    clinical_knowledge = surgery_knowledge
    if med_context:
        clinical_knowledge += "\n\n" + med_context

    system_prompt = SYSTEM_PROMPT.format(
        patient_context=patient_context,
        clinical_knowledge=clinical_knowledge,
        vital_reasoning=vital_reasoning,
        red_flag_matrix=red_flag_matrix,
        reasoning_examples=reasoning_examples,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": "Assess the patient's current risk based on all available data.",
            }
        ],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        assessment = json.loads(text)
    except json.JSONDecodeError:
        return None

    score = max(0, min(100, int(assessment.get("score", 0))))
    triggered = assessment.get("triggered_signals", [])
    reasoning = assessment.get("reasoning", "")

    db.write_risk_score(
        session_id=session_id,
        score=score,
        triggered_signals=triggered,
        reasoning=reasoning,
    )

    return {
        "score": score,
        "triggered_signals": triggered,
        "reasoning": reasoning,
    }
