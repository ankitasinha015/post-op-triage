"""
Red-flag matrix for post-operative risk assessment.
Typed dataclasses validated at import time. Each rule defines a clinical signal
that the Risk Assessor checks against patient data.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RedFlag:
    signal_name: str
    description: str
    base_weight: int  # 0-100, contribution to risk score
    category: str  # infection, cardiovascular, respiratory, neurological, wound, pain, medication
    urgency: str  # routine, monitor, urgent, 911-now
    applicable_surgeries: list[str] = field(default_factory=lambda: ["all"])
    day_range: tuple[int, int] = (0, 30)  # recovery days where this flag applies
    condition: str = ""  # human-readable condition for the LLM to evaluate


RED_FLAGS: list[RedFlag] = [
    # --- INFECTION ---
    RedFlag(
        signal_name="fever_persistent",
        description="Temperature >= 101.5°F (38.6°C) persisting or appearing after day 2",
        base_weight=35,
        category="infection",
        urgency="urgent",
        day_range=(2, 30),
        condition="Temperature >= 101.5°F after post-op day 2. Day 1 low-grade fever is expected.",
    ),
    RedFlag(
        signal_name="fever_high",
        description="Temperature >= 103°F (39.4°C) at any point",
        base_weight=50,
        category="infection",
        urgency="911-now",
        condition="Temperature >= 103°F at any recovery stage. Indicates severe systemic response.",
    ),
    RedFlag(
        signal_name="wound_redness_spreading",
        description="Incision redness expanding beyond 1 inch from wound edge",
        base_weight=30,
        category="wound",
        urgency="urgent",
        condition="Patient reports redness around incision that is spreading or growing larger.",
    ),
    RedFlag(
        signal_name="wound_discharge_purulent",
        description="Cloudy, yellow, green, or foul-smelling drainage from incision",
        base_weight=40,
        category="wound",
        urgency="urgent",
        condition="Any cloudy, colored, or foul-smelling discharge from the surgical site.",
    ),
    RedFlag(
        signal_name="wound_warmth",
        description="Incision site feels hot to touch, especially with swelling",
        base_weight=25,
        category="wound",
        urgency="monitor",
        condition="Surgical site is warm/hot to touch, particularly if accompanied by swelling or redness.",
    ),

    # --- CARDIOVASCULAR / DVT ---
    RedFlag(
        signal_name="dvt_leg_swelling",
        description="Unilateral leg swelling, especially after hip or knee surgery",
        base_weight=45,
        category="cardiovascular",
        urgency="urgent",
        applicable_surgeries=["Total Hip Replacement", "Total Knee Replacement"],
        condition="One leg is noticeably more swollen than the other. High DVT risk post-joint surgery.",
    ),
    RedFlag(
        signal_name="dvt_calf_pain",
        description="Calf pain or tenderness, especially with dorsiflexion",
        base_weight=35,
        category="cardiovascular",
        urgency="urgent",
        applicable_surgeries=["Total Hip Replacement", "Total Knee Replacement"],
        condition="Pain in the calf muscle, worse when flexing foot upward. Classic DVT sign.",
    ),
    RedFlag(
        signal_name="tachycardia",
        description="Resting heart rate > 100 bpm",
        base_weight=30,
        category="cardiovascular",
        urgency="monitor",
        condition="Heart rate above 100 bpm at rest. May indicate pain, infection, dehydration, or PE.",
    ),
    RedFlag(
        signal_name="chest_pain",
        description="Any new chest pain post-surgery",
        base_weight=60,
        category="cardiovascular",
        urgency="911-now",
        condition="Patient reports chest pain, tightness, or pressure. Could indicate PE or cardiac event.",
    ),

    # --- RESPIRATORY ---
    RedFlag(
        signal_name="shortness_of_breath",
        description="New or worsening difficulty breathing",
        base_weight=55,
        category="respiratory",
        urgency="911-now",
        condition="Patient reports difficulty breathing, can't catch breath, or breathing is getting worse.",
    ),
    RedFlag(
        signal_name="low_spo2",
        description="Oxygen saturation below 92%",
        base_weight=50,
        category="respiratory",
        urgency="911-now",
        condition="SpO2 reading below 92%. Indicates significant respiratory compromise.",
    ),
    RedFlag(
        signal_name="persistent_cough",
        description="New persistent cough developing after surgery",
        base_weight=20,
        category="respiratory",
        urgency="monitor",
        condition="Patient develops a new cough that wasn't present before surgery.",
    ),

    # --- NEUROLOGICAL ---
    RedFlag(
        signal_name="confusion",
        description="New confusion, disorientation, or altered mental status",
        base_weight=40,
        category="neurological",
        urgency="urgent",
        condition="Patient seems confused, disoriented, or their mental clarity has changed from baseline.",
    ),
    RedFlag(
        signal_name="numbness_new",
        description="New numbness or tingling not present before surgery",
        base_weight=25,
        category="neurological",
        urgency="monitor",
        applicable_surgeries=["Total Hip Replacement", "Total Knee Replacement"],
        condition="New numbness, tingling, or loss of sensation that wasn't present pre-op.",
    ),

    # --- PAIN ---
    RedFlag(
        signal_name="pain_worsening",
        description="Pain increasing after initial improvement, or sudden severe pain",
        base_weight=30,
        category="pain",
        urgency="monitor",
        condition="Pain was getting better but is now getting worse, or sudden spike in pain severity.",
    ),
    RedFlag(
        signal_name="pain_uncontrolled",
        description="Pain remains >= 8/10 despite medication",
        base_weight=40,
        category="pain",
        urgency="urgent",
        condition="Patient rates pain 8 or higher out of 10 even after taking prescribed pain medication.",
    ),
    RedFlag(
        signal_name="pain_medication_ineffective",
        description="Pain medication not providing relief within expected timeframe",
        base_weight=25,
        category="pain",
        urgency="monitor",
        condition="Patient took pain medication but reports no improvement after reasonable time (1-2 hours).",
    ),

    # --- GI / GENERAL ---
    RedFlag(
        signal_name="vomiting_persistent",
        description="Persistent vomiting preventing oral intake",
        base_weight=30,
        category="infection",
        urgency="urgent",
        condition="Patient cannot keep food or fluids down due to repeated vomiting.",
    ),
    RedFlag(
        signal_name="no_bowel_function",
        description="No bowel movement or gas passage for 3+ days post-op",
        base_weight=25,
        category="infection",
        urgency="monitor",
        applicable_surgeries=["Laparoscopic Appendectomy"],
        day_range=(3, 30),
        condition="Patient has not passed gas or had a bowel movement for 3+ days after abdominal surgery.",
    ),
    RedFlag(
        signal_name="bleeding_uncontrolled",
        description="Active bleeding soaking through bandages",
        base_weight=60,
        category="wound",
        urgency="911-now",
        condition="Bleeding from surgical site that soaks through dressings and doesn't stop with pressure.",
    ),

    # --- MOBILITY ---
    RedFlag(
        signal_name="inability_to_bear_weight",
        description="Complete inability to put weight on surgical limb when expected",
        base_weight=30,
        category="pain",
        urgency="monitor",
        applicable_surgeries=["Total Hip Replacement", "Total Knee Replacement"],
        day_range=(3, 30),
        condition="Patient cannot bear any weight on the operated leg by day 3+, when partial weight-bearing is expected.",
    ),
]


def get_flags_for_session(surgery_type: str, recovery_day: int) -> list[RedFlag]:
    """Return red flags applicable to this surgery type and recovery day."""
    applicable = []
    for flag in RED_FLAGS:
        if flag.day_range[0] <= recovery_day <= flag.day_range[1]:
            if "all" in flag.applicable_surgeries or surgery_type in flag.applicable_surgeries:
                applicable.append(flag)
    return applicable


def format_flags_for_prompt(flags: list[RedFlag]) -> str:
    """Format red flags into a structured string for the Risk Assessor prompt."""
    lines = ["RED FLAG MATRIX — evaluate each against current patient data:\n"]
    by_category: dict[str, list[RedFlag]] = {}
    for f in flags:
        by_category.setdefault(f.category.upper(), []).append(f)

    for category, cat_flags in sorted(by_category.items()):
        lines.append(f"\n[{category}]")
        for f in cat_flags:
            lines.append(f"  • {f.signal_name} (weight: {f.base_weight}, urgency: {f.urgency})")
            lines.append(f"    Condition: {f.condition}")

    return "\n".join(lines)


# Validate at import time
assert len(RED_FLAGS) > 0, "Red flag matrix is empty"
for _f in RED_FLAGS:
    assert 0 <= _f.base_weight <= 100, f"Invalid weight for {_f.signal_name}: {_f.base_weight}"
    assert _f.urgency in ("routine", "monitor", "urgent", "911-now"), f"Invalid urgency for {_f.signal_name}"
    assert _f.day_range[0] <= _f.day_range[1], f"Invalid day range for {_f.signal_name}"
