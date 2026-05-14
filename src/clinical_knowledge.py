"""
Clinical knowledge base for post-operative recovery.
NOT a rule engine. This is reference knowledge that agents use to REASON,
the same way a nurse consults their training — not a flowchart to follow.
"""

RECOVERY_TIMELINES = {
    "Total Knee Replacement": {
        "expected_pain_curve": {
            "day_1": "Severe (7-9/10), managed with strong pain meds. This is normal.",
            "day_2_3": "Moderate-severe (5-8/10). Should start decreasing. PT begins.",
            "day_4_7": "Moderate (4-6/10). Noticeable improvement expected. Walking with walker.",
            "day_7_14": "Mild-moderate (3-5/10). Significant mobility gains. Stairs possible.",
            "day_14_plus": "Mild (2-4/10). Pain during PT is normal. Rest pain should be low.",
        },
        "milestones": [
            "Day 1: Sit up, dangle legs. May stand with assistance.",
            "Day 2-3: Walk short distances with walker. Bend knee to ~90 degrees.",
            "Day 5-7: Walk longer distances. Reduce strong pain meds.",
            "Week 2: Stairs with rail. Shower independently.",
            "Week 4-6: Drive (if off narcotics). Walk without assistive device.",
        ],
        "red_flags_context": (
            "Knee replacements have HIGH DVT risk (days 3-14 especially). "
            "Unilateral leg swelling is never 'just swelling' — always rule out DVT. "
            "Infection risk peaks days 5-10. Wound should be dry by day 5. "
            "Any new drainage after day 3 is concerning. "
            "Stiffness is expected but INCREASING stiffness after day 7 suggests arthrofibrosis."
        ),
    },
    "Total Hip Replacement": {
        "expected_pain_curve": {
            "day_1": "Moderate-severe (6-8/10). Groin/thigh pain common.",
            "day_2_3": "Moderate (4-7/10). Walking with walker expected.",
            "day_4_7": "Mild-moderate (3-5/10). Hip precautions still critical.",
            "day_7_14": "Mild (2-4/10). Increasing independence.",
            "day_14_plus": "Minimal (1-3/10). Some aching with activity normal for months.",
        },
        "milestones": [
            "Day 1: Stand with walker. Short walks.",
            "Day 2-3: Walk hallway distances. Practice hip precautions.",
            "Day 5-7: Longer walks. May begin stair training.",
            "Week 2: Light daily activities. Reduce assistive device use.",
            "Week 6: Most normal activities resume. Driving (if off narcotics).",
        ],
        "red_flags_context": (
            "Hip replacements carry DISLOCATION risk — sudden severe pain with leg shortening/rotation "
            "is an emergency. DVT risk is very high (higher than knee). "
            "Posterior approach: avoid flexing hip >90 degrees, crossing legs, internal rotation. "
            "Infection can present subtly — persistent low-grade fever + groin pain that was improving "
            "then worsens is classic. Leg length discrepancy sensation is common and usually resolves."
        ),
    },
    "Laparoscopic Appendectomy": {
        "expected_pain_curve": {
            "day_1": "Moderate (4-6/10). Incision pain + shoulder pain from gas.",
            "day_2_3": "Mild-moderate (3-5/10). Shoulder pain resolving. Walking helps gas pain.",
            "day_4_7": "Mild (2-3/10). Most patients return to light activity.",
            "day_7_plus": "Minimal (0-2/10). Full recovery by 2-4 weeks.",
        },
        "milestones": [
            "Day 1: Walk within hours of surgery. Clear liquids, advance diet as tolerated.",
            "Day 2-3: Regular diet if tolerating. Manage pain with OTC meds.",
            "Day 5-7: Return to desk work. Light activity.",
            "Week 2-4: Resume exercise. Full recovery.",
        ],
        "red_flags_context": (
            "Appendectomy is generally low-risk but watch for: "
            "ABSCESS formation (fever + RLQ pain returning after initial improvement — classic day 5-7). "
            "Ileus (no bowel sounds, distension, vomiting — especially if patient isn't walking). "
            "Port site infection (redness/drainage at any of the 3 incision sites). "
            "If appendix was perforated, infection risk is significantly higher — "
            "treat any fever after day 2 seriously."
        ),
    },
}

MEDICATION_KNOWLEDGE = {
    "ibuprofen": {
        "class": "NSAID",
        "onset": "30-60 minutes",
        "peak_effect": "1-2 hours",
        "duration": "4-6 hours",
        "max_daily": "2400mg (800mg x3) for acute pain",
        "clinical_notes": (
            "If pain isn't responding to ibuprofen at adequate doses, the pain source may be "
            "inflammatory (infection) or mechanical (hardware issue) rather than typical post-op pain. "
            "Watch for GI side effects — nausea/stomach pain may be the med, not a complication."
        ),
    },
    "acetaminophen": {
        "class": "Analgesic/Antipyretic",
        "onset": "30-45 minutes",
        "peak_effect": "1-2 hours",
        "duration": "4-6 hours",
        "max_daily": "3000mg (1000mg x3, reduced from 4000mg for safety)",
        "clinical_notes": (
            "Effective for mild-moderate pain and fever. Does NOT reduce inflammation — "
            "if swelling is the issue, acetaminophen alone is insufficient. "
            "Liver toxicity risk if combined with alcohol. Often used in combination with NSAIDs."
        ),
    },
    "oxycodone": {
        "class": "Opioid analgesic",
        "onset": "15-30 minutes",
        "peak_effect": "30-60 minutes",
        "duration": "3-6 hours",
        "max_daily": "Per prescription — typically 5-10mg every 4-6 hours as needed",
        "clinical_notes": (
            "If patient needs opioids beyond day 5-7 for joint replacement (or day 3 for "
            "appendectomy), reassess pain source. Constipation is almost universal — "
            "ask about bowel function. Drowsiness/confusion may be opioid effect, not neurological."
        ),
    },
    "aspirin": {
        "class": "NSAID/Antiplatelet",
        "onset": "30-60 minutes",
        "peak_effect": "1-2 hours",
        "duration": "4-6 hours (pain), 7-10 days (antiplatelet)",
        "max_daily": "4000mg (pain), 81-325mg (DVT prophylaxis)",
        "clinical_notes": (
            "Often prescribed post-joint replacement for DVT prevention. "
            "If patient isn't taking their aspirin, DVT risk increases significantly. "
            "Compliance matters more here than for pain meds."
        ),
    },
}

VITAL_RANGES = {
    "temperature": {
        "normal": "97.0-99.5 F (36.1-37.5 C)",
        "low_grade_fever": "99.5-100.9 F — common Day 1-2 post-op, inflammatory response",
        "fever": "101.0-102.9 F — concerning after Day 2, suggests infection",
        "high_fever": "103.0+ F — urgent, systemic infection or sepsis risk",
        "clinical_reasoning": (
            "Day 1-2 fever is the body's inflammatory response to surgery — expected and benign. "
            "The critical distinction is TIMING: the same 101F that's normal on Day 1 is alarming on Day 5. "
            "Also consider TREND: a temp that was 99 yesterday and 101 today is more concerning than "
            "a stable 100 that's been there since surgery. Fever + wound changes = infection until proven otherwise."
        ),
    },
    "heart_rate": {
        "normal": "60-100 bpm at rest",
        "tachycardia": ">100 bpm — could be pain, anxiety, dehydration, infection, or PE",
        "bradycardia": "<60 bpm — may be medication effect (beta blockers) or concerning",
        "clinical_reasoning": (
            "Heart rate is a sensitive but non-specific vital sign. A HR of 110 in a patient with "
            "8/10 pain is likely pain-driven — treat the pain first. The same HR in someone with "
            "mild pain + sudden shortness of breath = think PE. Always interpret HR in context."
        ),
    },
    "blood_pressure": {
        "normal": "90/60 - 140/90 mmHg",
        "hypotension": "<90/60 — possible bleeding, dehydration, sepsis, medication effect",
        "hypertension": ">140/90 — pain-driven, anxiety, or underlying condition",
        "clinical_reasoning": (
            "Post-op BP fluctuations are common. Pain drives it up, meds can push it down. "
            "The worry is SUSTAINED hypotension (could mean internal bleeding) or sudden hypertension "
            "with headache (could mean autonomic response to severe pain or complication)."
        ),
    },
    "spo2": {
        "normal": "95-100%",
        "mild_hypoxemia": "92-94% — concerning, needs monitoring",
        "significant_hypoxemia": "<92% — urgent, may indicate PE, pneumonia, or respiratory failure",
        "clinical_reasoning": (
            "Post-op patients are at risk for atelectasis (collapsed lung segments from shallow breathing). "
            "SpO2 of 93% with deep breathing improving to 97% = atelectasis, encourage incentive spirometry. "
            "SpO2 of 93% that doesn't improve with deep breathing + tachycardia = think PE urgently."
        ),
    },
}


def get_surgery_knowledge(surgery_type: str) -> str:
    """Get clinical knowledge relevant to this surgery type."""
    info = RECOVERY_TIMELINES.get(surgery_type)
    if not info:
        return f"No specific recovery timeline available for {surgery_type}. Apply general post-operative principles."

    lines = [f"CLINICAL KNOWLEDGE — {surgery_type}:\n"]

    lines.append("Expected pain trajectory:")
    for period, description in info["expected_pain_curve"].items():
        lines.append(f"  {period.replace('_', ' ').title()}: {description}")

    lines.append("\nRecovery milestones:")
    for m in info["milestones"]:
        lines.append(f"  {m}")

    lines.append(f"\nSurgery-specific concerns: {info['red_flags_context']}")

    return "\n".join(lines)


def get_medication_context(med_names: list[str]) -> str:
    """Get clinical context for medications the patient is taking."""
    if not med_names:
        return ""

    lines = ["MEDICATION CONTEXT:"]
    for name in med_names:
        key = name.lower().strip()
        info = MEDICATION_KNOWLEDGE.get(key)
        if info:
            lines.append(f"\n  {name} ({info['class']}):")
            lines.append(f"    Onset: {info['onset']}, Peak: {info['peak_effect']}, Duration: {info['duration']}")
            lines.append(f"    Clinical note: {info['clinical_notes']}")
        else:
            lines.append(f"\n  {name}: No specific knowledge available. Apply general pharmacological principles.")

    return "\n".join(lines)


def get_vital_reasoning() -> str:
    """Get vital sign interpretation guidance."""
    lines = ["VITAL SIGN INTERPRETATION GUIDE:\n"]
    for vital, info in VITAL_RANGES.items():
        lines.append(f"  {vital.replace('_', ' ').title()}:")
        for key, value in info.items():
            if key != "clinical_reasoning":
                lines.append(f"    {key}: {value}")
        lines.append(f"    Reasoning: {info['clinical_reasoning']}")
        lines.append("")

    return "\n".join(lines)
