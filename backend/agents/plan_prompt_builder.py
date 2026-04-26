"""Build the Planning-Agent prompt from readiness report + DB data."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from agents.caveman import compress
from agents.schemas import ReadinessReport
from db.model import TrainingPlanRow, get_session
from db.reader import get_recent_workouts, get_user_profile, get_weeks_to_goal

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

STRENGTH SESSIONS:
- Include calisthenics/strength work on low-intensity days where appropriate
- Format strength exercises as a list under the "exercises" key: [{"exercise": str, "sets": int, "reps_or_duration": str, "notes": str}]
- Beginner level: prioritise bodyweight compound movements (push-ups, dead bugs, pike push-ups, wall holds)
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

MEDICAL/DIETARY:
- Always respect medical conditions when prescribing sessions
- Asthma: avoid high Z5 intervals; prefer Z2-Z3 sustained efforts
- Joint injuries: reduce impact (more swimming/cycling, less running)
- Include nutrition guidance respecting dietary preference and allergies

OUTPUT: Valid compact single-line JSON only — no markdown, no prose, no pretty-printing, no newlines inside the JSON.
Schema: TrainingPlan with exactly 7 sessions (one per calendar day)."""


def _v(val: object) -> str:
    return "~" if val is None else str(val)


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
        f"Swim equipment available: {swim_equipment}\n"
        f"Swim stroke proficiency: {swim_strokes}"
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
