"""
Synthetic clinical reasoning examples for few-shot prompts.
These teach agents HOW to think — forming hypotheses, weighing evidence,
noticing patterns a rule engine would miss.
"""

CONVERSATIONALIST_REASONING_EXAMPLES = [
    {
        "scenario": "Hip replacement Day 5, patient mentions leg swelling",
        "patient_says": "My right leg seems more swollen than my left today.",
        "bad_response": (
            "I've logged that as swelling, severity 5/10. Have you checked your temperature today?"
        ),
        "good_response": (
            "Thanks for telling me, Sam. Swelling in one leg after hip surgery is something "
            "I want to understand better. Can you tell me — is the swelling in your calf area "
            "or more around the thigh and hip? And does the swollen area feel warm or tender to touch?"
        ),
        "reasoning": (
            "Unilateral leg swelling post-hip replacement is a DVT red flag. Instead of just logging "
            "it and moving on, the agent forms a HYPOTHESIS (possible DVT) and INVESTIGATES by asking "
            "about calf vs thigh location, warmth, and tenderness — all DVT discriminators. "
            "It doesn't alarm the patient but gathers the specific data needed to assess the risk."
        ),
    },
    {
        "scenario": "Knee replacement Day 3, pain was improving but now worse",
        "patient_says": "The pain was getting better yesterday but it's worse again today. I'd say 7 out of 10.",
        "bad_response": (
            "I'm sorry to hear that, Alex. I've logged your pain at 7/10. Are you taking your medication?"
        ),
        "good_response": (
            "That's important to know, Alex. Pain that was improving and then gets worse is something "
            "I want to understand. A few things would help me: Did anything change — like more activity "
            "than usual, or did you miss a dose of your pain medication? And is the pain in the same "
            "place as before, or has it moved or spread?"
        ),
        "reasoning": (
            "Reversal of a pain trend is clinically significant — more so than a static pain number. "
            "The agent recognizes this pattern and investigates CAUSE: was it mechanical (overdid PT), "
            "pharmacological (missed meds), or pathological (infection, hardware issue)? "
            "The location question distinguishes expected surgical site pain from concerning spread."
        ),
    },
    {
        "scenario": "Appendectomy Day 1, patient reports nausea",
        "patient_says": "I feel pretty nauseous and I threw up once this morning.",
        "bad_response": (
            "I'm sorry you're feeling nauseous. I've logged nausea at severity 5/10. Have you been able to eat?"
        ),
        "good_response": (
            "Nausea and vomiting on Day 1 after an appendectomy is actually quite common, Jordan — "
            "it's often from the anesthesia wearing off. Are you able to keep small sips of water or "
            "clear fluids down? And when you vomited, was it just liquid or did you notice anything "
            "unusual like a dark or greenish color?"
        ),
        "reasoning": (
            "The agent calibrates its concern to the TIMELINE. Day 1 nausea post-appendectomy is expected "
            "(anesthesia effect). Instead of alarming the patient, it normalizes while still gathering "
            "discriminating data — fluid tolerance (dehydration risk) and vomit characteristics "
            "(bilious vomiting would suggest bowel obstruction, which is not expected). "
            "The same nausea on Day 5 would get a very different response."
        ),
    },
    {
        "scenario": "Hip replacement Day 5, patient mentions wound changes",
        "patient_says": "There's some stuff coming out of my incision. It's kind of yellowish.",
        "bad_response": (
            "I've logged wound drainage. Can you rate the amount on a scale of 1-10?"
        ),
        "good_response": (
            "I want to make sure I understand this clearly, Sam. By Day 5, your incision should "
            "generally be dry. Can you describe: Is the drainage thin and watery, or thick? "
            "Does it have any smell? And has the skin around the incision become more red or "
            "warm compared to a day or two ago?"
        ),
        "reasoning": (
            "The agent applies TIMELINE KNOWLEDGE — drainage by Day 5 is abnormal (should be dry). "
            "This shifts the prior from 'probably fine' to 'possibly concerning.' It then probes for "
            "infection discriminators: consistency (serous vs purulent), odor (anaerobic infection), "
            "and surrounding tissue changes (cellulitis). A 1-10 scale is meaningless for drainage — "
            "the CHARACTER of the drainage matters more than the amount."
        ),
    },
]

RISK_ASSESSOR_REASONING_EXAMPLES = [
    {
        "scenario": "Subtle infection pattern",
        "patient_data": {
            "surgery": "Total Knee Replacement, Day 7",
            "symptoms": [
                {"name": "pain", "severity": 5, "note": "was 3 yesterday"},
                {"name": "wound_warmth", "severity": 4, "note": "incision feels warm"},
                {"name": "fatigue", "severity": 6, "note": "more tired than yesterday"},
            ],
            "vitals": [{"type": "temperature", "value": 100.2, "unit": "F"}],
            "meds": [{"name": "ibuprofen", "dose": "400mg", "time": "4 hours ago"}],
        },
        "bad_assessment": {
            "score": 25,
            "reasoning": "Low-grade fever, mild pain, some warmth. Nothing individually alarming.",
        },
        "good_assessment": {
            "score": 55,
            "triggered_signals": ["fever_persistent", "wound_warmth", "pain_worsening"],
            "reasoning": (
                "While no single finding is alarming, the PATTERN is concerning: pain was improving (3/10) "
                "but reversed to 5/10, wound warmth appeared, AND there's a low-grade fever — all on Day 7. "
                "This is the classic presentation of early surgical site infection: pain reversal + local "
                "wound changes + systemic inflammatory response. The fever is only 100.2F but it appeared "
                "AFTER the expected post-op inflammatory period (Day 1-2). Additionally, the patient is on "
                "ibuprofen which suppresses fever — the true temperature may be higher. Fatigue compounds "
                "the picture as a non-specific infection marker. Score: 55 (moderate-high) — nurse should "
                "examine the wound today."
            ),
        },
    },
    {
        "scenario": "DVT warning signs building over time",
        "patient_data": {
            "surgery": "Total Hip Replacement, Day 5",
            "symptoms": [
                {"name": "calf_pain", "severity": 4, "note": "right calf feels tight"},
                {"name": "swelling", "severity": 5, "note": "right leg bigger than left"},
            ],
            "vitals": [{"type": "heart_rate", "value": 105, "unit": "bpm"}],
            "prior_session": "Day 3: mild swelling noted, advised to elevate. No calf pain at that time.",
        },
        "bad_assessment": {
            "score": 40,
            "reasoning": "Some swelling and calf tightness. Heart rate slightly elevated, likely from pain.",
        },
        "good_assessment": {
            "score": 75,
            "triggered_signals": ["dvt_leg_swelling", "dvt_calf_pain", "tachycardia"],
            "reasoning": (
                "This is a HIGH-RISK DVT presentation. Three independent findings converge: (1) Unilateral "
                "leg swelling that was mild on Day 3 and has WORSENED to Day 5 — progression matters more "
                "than absolute severity. (2) NEW calf pain that wasn't present on Day 3 — this is a new "
                "symptom in the classic DVT location. (3) Resting tachycardia at 105bpm — while HR can be "
                "elevated from pain, the patient's pain is only 4/10 which doesn't explain 105bpm. "
                "Unexplained tachycardia + DVT signs raises concern for PE (pulmonary embolism). "
                "Hip replacement patients are in the highest DVT risk category. The TRAJECTORY — from mild "
                "swelling to swelling + calf pain + tachycardia over 48 hours — is the most important signal. "
                "Score: 75 — urgent nurse review, likely needs Doppler ultrasound."
            ),
        },
    },
    {
        "scenario": "Normal recovery misread as concerning",
        "patient_data": {
            "surgery": "Laparoscopic Appendectomy, Day 1",
            "symptoms": [
                {"name": "pain", "severity": 5, "note": "incision hurts"},
                {"name": "nausea", "severity": 4, "note": "feel queasy"},
                {"name": "shoulder_pain", "severity": 3, "note": "weird pain in left shoulder"},
            ],
            "vitals": [{"type": "temperature", "value": 99.8, "unit": "F"}],
        },
        "bad_assessment": {
            "score": 50,
            "reasoning": "Multiple symptoms present including unusual shoulder pain. Low-grade fever.",
        },
        "good_assessment": {
            "score": 15,
            "triggered_signals": [],
            "reasoning": (
                "This is NORMAL Day 1 post-appendectomy recovery. Every symptom has an expected explanation: "
                "(1) Incision pain 5/10 is within expected range for Day 1 (expected 4-6/10). "
                "(2) Nausea is classic post-anesthesia effect, typically resolves by Day 2. "
                "(3) Shoulder pain — this SOUNDS unusual but is actually a well-known phenomenon: referred "
                "pain from residual CO2 gas used during laparoscopic surgery irritating the diaphragm. "
                "It's benign and resolves within 24-48 hours. (4) Temperature 99.8F on Day 1 is the body's "
                "normal inflammatory response to surgery. "
                "The danger of over-scoring normal recovery is crying wolf — it erodes trust in the alert "
                "system. Score: 15 — routine recovery, no action needed."
            ),
        },
    },
]


def get_conversationalist_examples() -> str:
    """Format reasoning examples for the Conversationalist prompt."""
    lines = ["CLINICAL REASONING EXAMPLES — study how these demonstrate hypothesis-driven thinking:\n"]
    for i, ex in enumerate(CONVERSATIONALIST_REASONING_EXAMPLES, 1):
        lines.append(f"Example {i}: {ex['scenario']}")
        lines.append(f"  Patient says: \"{ex['patient_says']}\"")
        lines.append(f"  WRONG approach: \"{ex['bad_response']}\"")
        lines.append(f"  RIGHT approach: \"{ex['good_response']}\"")
        lines.append(f"  WHY: {ex['reasoning']}")
        lines.append("")
    return "\n".join(lines)


def get_risk_assessor_examples() -> str:
    """Format reasoning examples for the Risk Assessor prompt."""
    lines = ["CLINICAL REASONING EXAMPLES — study how these demonstrate pattern recognition:\n"]
    for i, ex in enumerate(RISK_ASSESSOR_REASONING_EXAMPLES, 1):
        lines.append(f"Example {i}: {ex['scenario']}")
        lines.append(f"  Patient data: {ex['patient_data']}")
        lines.append(f"  WRONG assessment (score {ex['bad_assessment']['score']}): {ex['bad_assessment']['reasoning']}")
        lines.append(f"  RIGHT assessment (score {ex['good_assessment']['score']}): {ex['good_assessment']['reasoning']}")
        lines.append("")
    return "\n".join(lines)
