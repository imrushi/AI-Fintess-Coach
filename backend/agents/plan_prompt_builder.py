"""Build the Planning-Agent prompt from readiness report + DB data."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from agents.caveman import compress
from agents.schemas import ReadinessReport
from db.model import TrainingPlanRow, get_session
from db.reader import compute_hr_zones, get_recent_feedback, get_recent_workouts, get_user_profile, get_weeks_to_goal

from sqlalchemy import select

log = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """\
You are a world-class endurance coach specialising in triathlon (Ironman, 70.3), \
marathon, and multi-sport training. You write 7-day rolling training plans.

COACHING PHILOSOPHY:
- Polarised training model: 80% low intensity (Z1-Z2), 20% quality work (Z3-Z5)
- Never plan consecutive hard days (Z4/Z5) back to back
- Long sessions on weekends only (athlete has work week constraints)
- Recovery weeks every 3-4 weeks (reduce volume 30-40%)
- Respect the readiness gate — it overrides all other considerations

GATE RULES (non-negotiable):
- PROCEED: deliver the planned training week as designed
- PROCEED_WITH_CAUTION: reduce intensity one zone, cap session duration at 75% of planned
- REST_RECOMMENDED: replace all Z3+ sessions with Z1-Z2; max 60min per session
- MANDATORY_REST: active recovery only (yoga, walk, easy swim < 30min); no running or cycling

PUSH_THROUGH OVERRIDE (athlete chose to ignore rest recommendation):
- Reduce volume by 25% from what you would normally plan
- Cap intensity at Z3 maximum — no threshold or VO2max work
- Add explicit warning in session description

WEEKLY SCHEDULE CONSTRAINTS (non-negotiable):
- Tuesday: athlete travels to office — ONLY upper-body strength/calisthenics allowed (no running, cycling, or swimming). No gym equipment assumed; bodyweight only.
- Wednesday: athlete travels back 200 km — mandatory REST day. No training of any kind. Active recovery (light walk or breathwork) is acceptable but do not schedule a workout.

STRENGTH SESSIONS:
- Include calisthenics/strength work on low-intensity days where appropriate
- Format strength exercises as a list under the "exercises" key: [{"exercise": str, "sets": int, "reps_or_duration": str, "notes": str}]
- Beginner level: prioritise bodyweight compound movements (push-ups, dead bugs, pike push-ups, wall holds)
- Tuesday strength must be upper-body only: push-ups, pike push-ups, diamond push-ups, tricep dips, wall handstand holds, shoulder taps, plank variations, dead bugs
- Do not programme strength on the same day as Z4/Z5 sessions
- For non-strength sessions, omit the exercises key or set it to []

SWIMMING SKILLS:
- Use athlete's available equipment in drill prescriptions (e.g. pull buoy for isolation sets, paddles for catch development)
- Match stroke choice to proficiency: expert strokes for main sets, weaker strokes only in drill/technique segments
- For learning strokes (e.g. butterfly): include dedicated drill progressions (body-dolphin kick, one-arm fly) not full-stroke laps
- Backstroke weakness: include backstroke drills (catch-up back, single-arm back) as warm-up or cool-down periodically

SWIM SET STRUCTURE:
- For swim sessions, include a detailed set breakdown under the "swim_sets" key
- Format: [{"stroke": str, "distance_m": int, "reps": int, "rest_sec": int|null, "intensity": str|null, "notes": str|null}]
- Structure as warm-up sets → main set(s) → cool-down; label each group in notes
- Allowed stroke values: freestyle, backstroke, breaststroke, butterfly, drill, kick, choice
- rest_sec is rest between reps within the set (e.g. 30 = 30s rest between each rep)
- Include technique cues in notes (e.g. "bilateral breathing every 3", "high elbow catch")
- For non-swim sessions, omit swim_sets or set to []

YOGA SESSIONS:
- Always include a dedicated breathing exercise block (5–10 min) — prescribe it explicitly in the exercises list
- Breathing options: box breathing (4-4-4-4), diaphragmatic breathing, alternate-nostril breathing (Nadi Shodhana), 4-7-8 breathing for recovery, Wim Hof if appropriate
- Include specific named yoga poses/flows in the exercises list, not just generic descriptions
- Recommended poses by goal: hip flexor release → Low Lunge, Pigeon Pose, Lizard Pose; hamstrings → Standing Forward Fold, Seated Forward Fold, Pyramid Pose; back/core → Cat-Cow, Child's Pose, Supine Twist; shoulders/chest → Thread-the-Needle, Eagle Arms, Doorway Stretch; balance/strength → Warrior I, Warrior II, Warrior III, Chair Pose, Tree Pose; recovery flow → Legs-up-the-Wall, Reclined Butterfly, Savasana
- Structure yoga sessions as: breathing warm-up → active poses → passive stretches → breathwork cool-down / Savasana
- Set reps_or_duration to hold times (e.g. "45 sec each side") or breath counts (e.g. "5 breaths")

MEDICAL/DIETARY:
- Always respect medical conditions when prescribing sessions
- Asthma: avoid high Z5 intervals; prefer Z2-Z3 sustained efforts
- Joint injuries: reduce impact (more swimming/cycling, less running)
- Include nutrition guidance respecting dietary preference and allergies

OUTPUT: Valid compact single-line JSON only — no markdown, no prose, no pretty-printing, no newlines inside the JSON.
Schema: TrainingPlan with exactly 7 sessions (one per calendar day)."""


def _v(val: object) -> str:
    return "~" if val is None else str(val)


def _vol(v: object) -> str:
    """Format volume — None or 0 means the discipline is unavailable."""
    if v is None or v == 0:
        return "N/A (not available)"
    return f"{v} km"


@dataclass
class PlanPromptPackage:
    system_prompt: str
    user_prompt: str
    compressed_user_prompt: str
    compression_ratio: float
    token_estimate: int


def load_previous_plan_summary(user_id: str) -> str | None:
    """Load the most recent plan and return a compact summary of its last 7 sessions."""
    with get_session() as s:
        row = (
            s.execute(
                select(TrainingPlanRow)
                .where(TrainingPlanRow.user_id == user_id)
                .order_by(TrainingPlanRow.valid_from.desc())
                .limit(1)
            )
            .scalar_one_or_none()
        )
        if row is None:
            return None
        try:
            plan = json.loads(row.plan_json)
        except json.JSONDecodeError:
            return None

    sessions = plan.get("sessions", [])
    # Take the last 7 sessions for continuity context
    tail = sessions[-7:] if len(sessions) > 7 else sessions
    lines = []
    for sess in tail:
        lines.append(
            f"{sess.get('date','?')} | {sess.get('sport','?')} | "
            f"{_v(sess.get('duration_min'))}min | {_v(sess.get('intensity_zone'))} | "
            f"{sess.get('title','')}"
        )
    return "\n".join(lines)


def build_planning_prompt(
    user_id: str,
    readiness_report: ReadinessReport,
    override_choice: str | None = None,
) -> PlanPromptPackage:
    """Assemble the full Planning-Agent prompt."""

    profile = get_user_profile(user_id) or {}
    recent_workouts = get_recent_workouts(user_id, days=14)
    weeks_to_goal = get_weeks_to_goal(user_id)
    hr_zones = compute_hr_zones(user_id)
    today = date.today()
    plan_start = today
    plan_end = today + timedelta(days=6)

    goal_event = profile.get("goal_event", "not set")
    goal_date = profile.get("goal_date", "not set")
    fitness_level = profile.get("fitness_level", "unknown")
    max_hours = profile.get("max_weekly_hours") or "not set, assume 8-10h"
    medical = profile.get("medical_conditions", "none")
    diet_pref = profile.get("dietary_preference", "not set")
    diet_allergy = profile.get("dietary_allergies", "none")
    swim_equipment = profile.get("swim_equipment") or "none"
    swim_strokes = profile.get("swim_strokes") or "not specified"
    current_swim_km = profile.get("current_swim_km_week")
    current_bike_km = profile.get("current_bike_km_week")
    current_run_km = profile.get("current_run_km_week")
    swim_max_min = profile.get("swim_max_session_min")

    _swim_per_session_m = int(current_swim_km * 1000 / 2) if current_swim_km else None

    sections: list[str] = []

    # Section 1 — Goal & context
    sections.append(
        f"## Athlete\n"
        f"Goal: {goal_event} | Target date: {goal_date} | Weeks remaining: {weeks_to_goal}\n"
        f"Fitness level: {fitness_level}\n"
        f"Max weekly training hours: {max_hours}\n"
        f"Medical conditions: {medical}\n"
        f"Dietary preference: {diet_pref}\n"
        f"Allergies: {diet_allergy}\n"
        f"Preferred long day: Saturday\n"
        f"Travel constraints: Tuesday = office day (upper-body only); Wednesday = long return trip (rest day)\n"
        f"Swim equipment available: {swim_equipment}\n"
        f"Swim stroke proficiency: {swim_strokes}\n"
        f"Current weekly volume — Swim: {_vol(current_swim_km)} | Bike: {_vol(current_bike_km)} | Run: {_vol(current_run_km)}\n"
        + (
            f"Swim per-session baseline: {_swim_per_session_m}m "
            f"(= {_vol(current_swim_km)}/week ÷ 2 sessions). "
            f"NEVER prescribe below {_swim_per_session_m}m for a standard swim session. "
            f"Hard intensity target: ≥{int(_swim_per_session_m * 1.1)}m.\n"
            if _swim_per_session_m else ""
        ) +
        (f"Swim pool time cap: {swim_max_min} min — do NOT exceed this total session duration.\n" if swim_max_min else "") +
        f"IMPORTANT: For any discipline marked N/A, do NOT prescribe sessions of that type."
    )

    # Section 2 — Readiness context
    r = readiness_report
    acwr = _v(r.key_signals.load.acwr)
    hrv_dev = _v(r.key_signals.hrv.deviation_pct)
    sections.append(
        f"## Today's Readiness\n"
        f"Score: {r.readiness_score}/100\n"
        f"Label: {r.readiness_label.value}\n"
        f"Gate: {r.training_gate.value}\n"
        f"Flags: {', '.join(r.flags) or 'none'}\n"
        f"Narrative: {r.narrative}\n"
        f"ACWR: {acwr}\n"
        f"HRV deviation: {hrv_dev}%"
    )

    # Section 2b — HR Zones
    if hr_zones:
        zone_lines = "\n".join(
            f"{z}: {bpm}" for z, bpm in hr_zones["zones"].items()
        )
        sections.append(
            f"## HR Zones\n"
            f"Method: {hr_zones['method']}\n"
            f"{zone_lines}\n"
            f"Use these exact BPM ranges when prescribing intensity zones in sessions."
        )
    else:
        sections.append(
            "## HR Zones\n"
            "Not available (no LTHR, no recorded max HR, no date of birth set).\n"
            "Use RPE and zone labels only."
        )

    # Section 3 — Override
    if override_choice == "push_through":
        sections.append(
            "## Override: Athlete chose PUSH THROUGH despite REST_RECOMMENDED gate.\n"
            "Apply push_through rules: -25% volume, cap Z3, add warnings."
        )
    elif override_choice == "rest_as_recommended":
        sections.append(
            "## Override: Athlete confirmed REST. Apply MANDATORY_REST rules for today."
        )

    # Section 4 — Recent training history
    header = "date | sport | duration_min | intensity | avg_hr | rpe"
    rows: list[str] = []
    for w in recent_workouts:
        rows.append(
            " | ".join([
                str(w.get("date", "?")),
                str(w.get("sport", "?")),
                _v(w.get("duration_min")),
                "~",
                _v(w.get("avg_hr")),
                _v(w.get("perceived_effort")),
            ])
        )
    sections.append(
        f"## Recent Training (14d)\n{header}\n" + ("\n".join(rows) if rows else "No workouts logged.")
    )

    # Section 5 — Previous plan continuity
    prev = load_previous_plan_summary(user_id)
    sections.append(
        f"## Previous Plan Summary\n{prev or 'No previous plan — start fresh.'}"
    )

    # Section 5b — Recent athlete feedback
    recent_feedback = get_recent_feedback(user_id, days=7)
    if recent_feedback:
        sections.append(
            f"## Athlete Feedback (7d)\n"
            + json.dumps(recent_feedback, separators=(",", ":"), default=str)
        )

    # Section 6 — Plan request
    sections.append(
        f"## Plan Required\n"
        f"Generate 7-day rolling plan: {plan_start} to {plan_end}\n\n"
        f"JSON schema to follow exactly:\n"
        "{\n"
        f'  "plan_id": "<uuid>",\n'
        f'  "user_id": "{user_id}",\n'
        f'  "generated_at": "<ISO datetime>",\n'
        f'  "valid_from": "{plan_start}",\n'
        f'  "valid_to": "{plan_end}",\n'
        f'  "goal_event": "{goal_event}",\n'
        f'  "goal_date": "{goal_date}",\n'
        f'  "weeks_to_goal": {weeks_to_goal},\n'
        '  "sessions": [<7 TrainingSession objects>],\n'
        '  "weekly_targets": [<1 WeeklyTargets object>],\n'
        '  "plan_rationale": "<2-3 sentences>",\n'
        '  "nutrition_weekly_notes": "<weekly nutrition strategy>"\n'
        "}\n\n"
        "Each session must have: date, day_of_week, sport, duration_min, "
        "intensity_zone, title, description, key_focus, nutrition.\n"
        "For strength sessions also include: exercises (list of {exercise, sets, reps_or_duration, notes}).\n"
        "For swim sessions also include: swim_sets (list of {stroke, distance_m, reps, rest_sec, intensity, notes}).\n"
        "ALLOWED sport values (use EXACTLY): swim, bike, run, brick, strength, yoga, active_recovery, rest.\n"
        "nutrition must be an object with keys: pre_session, during_session, post_session.\n"
        "weekly_targets must include: week_number, week_start, total_volume_min, intensity_distribution.\n"
        "Keep descriptions concise (1-2 sentences max).\n"
        "Output compact single-line JSON — no pretty-printing, no newlines inside the JSON."
    )

    user_prompt = "\n\n".join(sections)

    # Compress
    compressed, ratio = compress(user_prompt)

    token_estimate = (len(PLAN_SYSTEM_PROMPT) + len(compressed)) // 4

    return PlanPromptPackage(
        system_prompt=PLAN_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        compressed_user_prompt=compressed,
        compression_ratio=round(ratio, 3),
        token_estimate=token_estimate,
    )


PATCH_SYSTEM_PROMPT = """\
You are a world-class endurance coach. A weekly training plan already exists. \
Your task is to update ONLY a single session for tomorrow based on today's readiness data.

Apply the same gate rules as a full plan:
- PROCEED: deliver the session as originally planned
- PROCEED_WITH_CAUTION: reduce intensity one zone, cap duration at 75%
- REST_RECOMMENDED: replace Z3+ with Z1-Z2, max 60min
- MANDATORY_REST: active recovery only (yoga, walk, easy swim <30min)

Weekly schedule constraints:
- Tuesday: upper-body strength/calisthenics only (no run/bike/swim — athlete travels to office)
- Wednesday: mandatory rest day (athlete travels back 200 km)

Yoga sessions must include named poses, a breathing exercise block (box breathing, Nadi Shodhana, 4-7-8, etc.), \
and be structured as: breathing warm-up → active poses → passive stretches → breathwork cool-down.

Output ONLY a single valid compact JSON object matching the TrainingSession schema — \
no markdown, no prose, no array wrapper.
Schema: {date, day_of_week, sport, duration_min, intensity_zone, title, description, \
key_focus, exercises, swim_sets, nutrition, override_applied, readiness_adjusted}"""


@dataclass
class PatchPromptPackage:
    system_prompt: str
    user_prompt: str
    compressed_user_prompt: str
    compression_ratio: float
    token_estimate: int
    tomorrow: str  # YYYY-MM-DD


def build_daily_patch_prompt(
    user_id: str,
    readiness_report: ReadinessReport,
    current_plan_json: dict,
    override_choice: str | None = None,
) -> PatchPromptPackage:
    """Build a minimal prompt to update only tomorrow's session."""
    from db.reader import get_user_profile

    profile = get_user_profile(user_id) or {}
    hr_zones = compute_hr_zones(user_id)

    today = date.today()
    tomorrow = today + timedelta(days=1)
    tomorrow_str = str(tomorrow)

    import calendar
    tomorrow_dow = calendar.day_name[tomorrow.weekday()]

    # Find tomorrow's existing session from the plan (if any)
    existing_session = next(
        (s for s in current_plan_json.get("sessions", []) if s.get("date") == tomorrow_str),
        None,
    )

    goal_event = profile.get("goal_event", "not set")
    medical = profile.get("medical_conditions", "none")
    swim_equipment = profile.get("swim_equipment") or "none"
    swim_strokes = profile.get("swim_strokes") or "not specified"
    current_swim_km = profile.get("current_swim_km_week")
    current_bike_km = profile.get("current_bike_km_week")
    current_run_km = profile.get("current_run_km_week")
    swim_max_min = profile.get("swim_max_session_min")

    _swim_per_session_m = int(current_swim_km * 1000 / 2) if current_swim_km else None

    sections: list[str] = []

    # Athlete context (minimal)
    sections.append(
        f"## Athlete\n"
        f"Goal: {goal_event}\n"
        f"Medical: {medical}\n"
        f"Swim equipment: {swim_equipment}\n"
        f"Swim strokes: {swim_strokes}\n"
        f"Current weekly volume — Swim: {_vol(current_swim_km)} | Bike: {_vol(current_bike_km)} | Run: {_vol(current_run_km)}\n"
        + (
            f"Swim per-session baseline: {_swim_per_session_m}m "
            f"(= {_vol(current_swim_km)}/week ÷ 2 sessions). "
            f"NEVER prescribe below {_swim_per_session_m}m for a standard swim session. "
            f"Hard intensity target: ≥{int(_swim_per_session_m * 1.1)}m.\n"
            if _swim_per_session_m else ""
        ) +
        (f"Swim pool time cap: {swim_max_min} min — do NOT exceed this total session duration.\n" if swim_max_min else "") +
        f"IMPORTANT: For any discipline marked N/A, do NOT prescribe sessions of that type."
    )

    # Readiness
    r = readiness_report
    sections.append(
        f"## Today's Readiness\n"
        f"Score: {r.readiness_score}/100 | Gate: {r.training_gate.value}\n"
        f"Flags: {', '.join(r.flags) or 'none'}\n"
        f"Narrative: {r.narrative}"
    )

    # HR Zones
    if hr_zones:
        zone_lines = "\n".join(f"{z}: {bpm}" for z, bpm in hr_zones["zones"].items())
        sections.append(f"## HR Zones ({hr_zones['method']})\n{zone_lines}")

    # Override
    if override_choice == "push_through":
        sections.append("## Override: PUSH THROUGH — -25% volume, cap Z3, add warning.")
    elif override_choice == "rest_as_recommended":
        sections.append("## Override: REST confirmed. Apply MANDATORY_REST rules.")

    # Existing session for tomorrow
    if existing_session:
        sections.append(
            f"## Planned session for tomorrow (to adapt if needed)\n"
            + json.dumps(existing_session, separators=(",", ":"))
        )
    else:
        sections.append(
            f"## No session was planned for tomorrow — create an appropriate one."
        )

    # Recent athlete feedback
    recent_feedback = get_recent_feedback(user_id, days=7)
    if recent_feedback:
        sections.append(
            f"## Athlete Feedback (7d)\n"
            + json.dumps(recent_feedback, separators=(",", ":"), default=str)
        )

    # Task
    sections.append(
        f"## Task\n"
        f"Update ONLY tomorrow's session: {tomorrow_str} ({tomorrow_dow}).\n"
        f"If the existing session already satisfies the gate rules and no flags require adjustment, "
        f"respond with exactly: {{\"no_change\": true}}\n"
        f"Otherwise output a single TrainingSession JSON object. "
        f"Set readiness_adjusted=true if you changed the session due to gate/flags.\n"
        f"nutrition must have keys: pre_session, during_session, post_session."
    )

    user_prompt = "\n\n".join(sections)
    compressed, ratio = compress(user_prompt)
    token_estimate = (len(PATCH_SYSTEM_PROMPT) + len(compressed)) // 4

    return PatchPromptPackage(
        system_prompt=PATCH_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        compressed_user_prompt=compressed,
        compression_ratio=round(ratio, 3),
        token_estimate=token_estimate,
        tomorrow=tomorrow_str,
    )


def build_today_patch_prompt(
    user_id: str,
    readiness_report: ReadinessReport,
    current_plan_json: dict,
    intensity_preference: str | None = None,
) -> PatchPromptPackage:
    """Build a prompt to re-generate only TODAY's session.

    intensity_preference: 'easy' | 'moderate' | 'hard' | 'as_planned' | 'rest' | None
    """
    import calendar
    from db.reader import compute_hr_zones, get_user_profile

    profile = get_user_profile(user_id) or {}
    hr_zones = compute_hr_zones(user_id)

    today = date.today()
    today_str = str(today)
    today_dow = calendar.day_name[today.weekday()]

    existing_session = next(
        (s for s in current_plan_json.get("sessions", []) if s.get("date") == today_str),
        None,
    )

    goal_event = profile.get("goal_event", "not set")
    medical = profile.get("medical_conditions", "none")
    current_swim_km = profile.get("current_swim_km_week")
    current_bike_km = profile.get("current_bike_km_week")
    current_run_km = profile.get("current_run_km_week")
    swim_max_min = profile.get("swim_max_session_min")

    _swim_per_session_m = int(current_swim_km * 1000 / 2) if current_swim_km else None

    sections: list[str] = []

    sections.append(
        f"## Athlete\n"
        f"Goal: {goal_event}\n"
        f"Medical: {medical}\n"
        f"Current weekly volume — Swim: {_vol(current_swim_km)} | Bike: {_vol(current_bike_km)} | Run: {_vol(current_run_km)}\n"
        + (
            f"Swim per-session baseline: {_swim_per_session_m}m "
            f"(= {_vol(current_swim_km)}/week ÷ 2 sessions). "
            f"NEVER prescribe below {_swim_per_session_m}m for a standard swim session. "
            f"Hard intensity target: ≥{int(_swim_per_session_m * 1.1)}m.\n"
            if _swim_per_session_m else ""
        ) +
        (f"Swim pool time cap: {swim_max_min} min — do NOT exceed this total session duration.\n" if swim_max_min else "") +
        f"IMPORTANT: For any discipline marked N/A, do NOT prescribe sessions of that type."
    )

    r = readiness_report
    sections.append(
        f"## Today's Readiness ({today_str}, {today_dow})\n"
        f"Score: {r.readiness_score}/100 | Gate: {r.training_gate.value}\n"
        f"Flags: {', '.join(r.flags) or 'none'}\n"
        f"Narrative: {r.narrative}"
    )

    if hr_zones:
        zone_lines = "\n".join(f"{z}: {bpm}" for z, bpm in hr_zones["zones"].items())
        sections.append(f"## HR Zones ({hr_zones['method']})\n{zone_lines}")

    if intensity_preference:
        intensity_map = {
            "easy": "Scale intensity DOWN — keep in Z1/Z2, reduce duration by 20-30%.",
            "moderate": "Keep planned intensity — adjust for readiness gate if needed.",
            "hard": "Scale intensity UP — push to Z3/Z4 where appropriate. Only if gate allows.",
            "as_planned": "Keep session exactly as originally planned. Do not adjust.",
            "rest": "Replace with active recovery or rest day regardless of gate.",
        }
        instr = intensity_map.get(intensity_preference, f"User preference: {intensity_preference}")
        sections.append(f"## User Intensity Preference\n{instr}")

    if existing_session:
        sections.append(
            f"## Current Today's Session (to be updated)\n"
            + json.dumps(existing_session, separators=(",", ":"))
        )
    else:
        sections.append("## Current Today's Session\nNo session currently planned for today.")

    # Recent athlete feedback
    recent_feedback = get_recent_feedback(user_id, days=7)
    if recent_feedback:
        sections.append(
            f"## Athlete Feedback (7d)\n"
            + json.dumps(recent_feedback, separators=(",", ":"), default=str)
        )

    sections.append(
        f"## Task\n"
        f"Generate an updated session for TODAY ({today_str}, {today_dow}).\n"
        f"Apply the readiness gate and user intensity preference.\n"
        f"Output ONLY the single session JSON object."
    )

    user_prompt = "\n\n".join(sections)
    compressed, ratio = compress(user_prompt)
    token_estimate = (len(PATCH_SYSTEM_PROMPT) + len(compressed)) // 4

    return PatchPromptPackage(
        system_prompt=PATCH_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        compressed_user_prompt=compressed,
        compression_ratio=round(ratio, 3),
        token_estimate=token_estimate,
        tomorrow=today_str,  # reusing field — indicates the target date
    )


if __name__ == "__main__":
    from agents.schemas import (
        HRVSignal,
        KeySignals,
        LoadSignal,
        ReadinessLabel,
        SleepSignal,
        TrainingGate,
    )
    from db.model import User

    with get_session() as s:
        user = s.query(User).first()

    if not user:
        print("No users in DB — run sync first.")
        raise SystemExit(1)

    # Build a sample readiness report for testing
    sample_report = ReadinessReport(
        report_date=str(date.today()),
        readiness_score=65,
        readiness_label=ReadinessLabel.MODERATE,
        training_gate=TrainingGate.PROCEED_WITH_CAUTION,
        key_signals=KeySignals(
            hrv=HRVSignal(current_ms=60.0, baseline_ms=67.0, deviation_pct=-10.4),
            sleep=SleepSignal(score=58, duration_min=360, quality_label="fair"),
            load=LoadSignal(acwr=1.1, acwr_risk="optimal"),
        ),
        flags=["HRV_DROP_MILD"],
        narrative="Mild HRV dip. Sleep below average. OK for reduced intensity.",
    )

    pkg = build_planning_prompt(user.id, sample_report)
    print("=" * 60)
    print("SYSTEM PROMPT (first 300 chars)")
    print("=" * 60)
    print(pkg.system_prompt[:300], "...")
    print(f"\n[system length: {len(pkg.system_prompt)} chars]")
    print("\n" + "=" * 60)
    print("USER PROMPT (compressed)")
    print("=" * 60)
    print(pkg.compressed_user_prompt)
    print(f"\n[original: {len(pkg.user_prompt)} chars]")
    print(f"[compressed: {len(pkg.compressed_user_prompt)} chars]")
    print(f"[compression ratio: {pkg.compression_ratio:.1%}]")
    print(f"[estimated tokens: {pkg.token_estimate}]")
