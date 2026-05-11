"""Build the Analysis-Agent prompt from DB data + caveman compression."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from agents.caveman import compress
from agents.data_freshness import DataFreshnessReport, assess_data_freshness
from db.reader import (
    compute_acwr,
    get_hrv_baseline,
    get_recent_feedback,
    get_recent_metrics,
    get_recent_workouts,
    get_todays_recovery,
    get_user_profile,
    get_weeks_to_goal,
)

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an elite endurance sports physiologist and data analyst embedded in an AI coaching system.

Your job: analyse wearable data and produce a daily ReadinessReport in strict JSON format.

You assess:
- HRV trend vs personal baseline (key injury/overtraining signal)
- Sleep quality: score, duration, deep+REM ratio
- Acute:Chronic Workload Ratio (ACWR) — flag if > 1.3, danger if > 1.5
- Body battery morning value (< 30 = mandatory rest)
- Resting HR trend (elevated = fatigue signal)
- Recent workout quality vs RPE
- Athlete's subjective feedback

The TODAY'S RECOVERY section contains last night's sleep data
(the sleep that ended this morning). This is the primary signal
for today's readiness gate. The 14-day table provides trend context.
Weight today's recovery data at least 3x more than historical averages.

Training gate rules (apply strictly):
- PROCEED: readiness >= 70, no critical flags
- PROCEED_WITH_CAUTION: readiness 50-69 OR ACWR 1.3-1.5 OR single mild flag
- REST_RECOMMENDED: readiness 30-49 OR body_battery < 30 OR sleep_score < 55
- MANDATORY_REST: readiness < 30 OR body_battery < 20 OR ACWR > 1.5

Output ONLY valid JSON matching this exact schema — no prose, no markdown fences:
{
  "report_date": "YYYY-MM-DD",
  "readiness_score": <int 0-100>,
  "readiness_label": <"EXCELLENT"|"GOOD"|"MODERATE"|"POOR"|"VERY_POOR">,
  "training_gate": <"PROCEED"|"PROCEED_WITH_CAUTION"|"REST_RECOMMENDED"|"MANDATORY_REST">,
  "key_signals": {
    "hrv": {"current_ms": <float|null>, "baseline_ms": <float|null>, "deviation_pct": <float|null>, "trend_3d": <str|null>},
    "sleep": {"score": <int|null>, "duration_min": <int|null>, "deep_min": <int|null>, "rem_min": <int|null>, "quality_label": <str|null>},
    "load": {"acwr": <float|null>, "acute_load": <float|null>, "chronic_load": <float|null>, "acwr_risk": <str|null>},
    "body_battery_morning": <int|null>,
    "resting_hr": <int|null>,
    "resting_hr_trend": <str|null>,
    "stress_avg": <int|null>
  },
  "flags": [<list of string flag codes>],
  "narrative": "<2-3 sentence plain English summary>",
  "recommendations": ["<actionable point 1>", "<actionable point 2>"],
  "data_completeness_pct": <int 0-100>
}

Flag codes to use: HRV_DROP_SIGNIFICANT (>20% below baseline), HRV_DROP_MILD (10-20%), \
SLEEP_DEBT_ACUTE (score<55), SLEEP_SHORT (<300min), HIGH_ACWR (1.3-1.5), \
DANGER_ACWR (>1.5), LOW_BODY_BATTERY (<30), ELEVATED_RHR, HIGH_STRESS, \
CONSECUTIVE_HARD_DAYS (3+ days RPE>7)."""


def _v(val: object) -> str:
    """Format a value for the compact metrics table — '~' for None."""
    return "~" if val is None else str(val)


@dataclass
class AnalysisPromptPackage:
    system_prompt: str
    user_prompt: str
    compressed_user_prompt: str
    compression_ratio: float
    context_injection: str | None
    token_estimate: int


def build_analysis_prompt(
    user_id: str,
    target_date: str,
    context_injection: str | None = None,
    freshness: DataFreshnessReport | None = None,
) -> AnalysisPromptPackage:
    """Assemble the full Analysis-Agent prompt from DB data."""

    # ── Load data ────────────────────────────────────────────────────
    # Use pre-computed freshness if provided, otherwise compute it now
    if freshness is None:
        freshness = assess_data_freshness(user_id)
    today_recovery = get_todays_recovery(user_id)
    metrics = get_recent_metrics(user_id, days=14)
    hrv_baseline = get_hrv_baseline(user_id, days=28)
    workouts = get_recent_workouts(user_id, days=7)
    feedback = get_recent_feedback(user_id, days=7)
    profile = get_user_profile(user_id) or {}
    acute, chronic, acwr = compute_acwr(user_id)
    weeks = get_weeks_to_goal(user_id)

    # ── Section 1 — Athlete context ──────────────────────────────────
    goal_event = profile.get("goal_event", "not set")
    goal_date = profile.get("goal_date", "not set")
    medical = profile.get("medical_conditions", "none")
    fitness = profile.get("fitness_level", "unknown")
    sections: list[str] = [
        f"## Athlete\n"
        f"Goal: {goal_event} on {goal_date} ({weeks} weeks away)\n"
        f"Medical: {medical}\n"
        f"Fitness level: {fitness}",
    ]

    # ── Section 2 — Today's recovery (highlighted) ──────────────────
    today_date = date.today()
    yesterday_date = today_date - timedelta(days=1)
    if today_recovery["data_available"]:
        slp_min = today_recovery["sleep_duration_min"]
        slp_hrs = f"{slp_min // 60}h {slp_min % 60}m" if slp_min is not None else "~"
        hrv_now = today_recovery["hrv_last_night_ms"]
        if hrv_now is not None and hrv_baseline is not None:
            hrv_dev = f"{round((hrv_now - hrv_baseline) / hrv_baseline * 100):+.1f}%"
        else:
            hrv_dev = "~"
        baseline_str = f"{hrv_baseline:.1f} ms" if hrv_baseline is not None else "insufficient data"
        available_count = sum([
            today_recovery["sleep_score"] is not None,
            today_recovery["hrv_last_night_ms"] is not None,
            today_recovery["body_battery_min"] is not None,
            today_recovery["deep_sleep_min"] is not None,
            today_recovery["rem_sleep_min"] is not None,
            today_recovery["stress_avg"] is not None,
        ])
        sections.append(
            f"## TODAY'S RECOVERY (Last Night: {yesterday_date} → {today_date} morning)\n"
            f"\u26a0\ufe0f  This is the MOST IMPORTANT signal — use this for today's readiness gate.\n\n"
            f"Sleep score:      {_v(today_recovery['sleep_score'])} / 100\n"
            f"Sleep duration:   {_v(slp_min)} min ({slp_hrs})\n"
            f"Deep sleep:       {_v(today_recovery['deep_sleep_min'])} min\n"
            f"REM sleep:        {_v(today_recovery['rem_sleep_min'])} min\n"
            f"HRV last night:   {_v(hrv_now)} ms  (baseline: {baseline_str}, deviation: {hrv_dev})\n"
            f"Body battery AM:  {_v(today_recovery['body_battery_min'])} → {_v(today_recovery['body_battery_max'])}\n"
            f"Morning stress:   {_v(today_recovery['stress_avg'])}\n\n"
            f"Data completeness: {available_count} / 6 signals available"
        )
    else:
        sections.append(
            f"## TODAY'S RECOVERY\n"
            f"\u26a0\ufe0f  Last night's sleep data NOT YET SYNCED from Garmin.\n"
            f"Garmin may not have uploaded this morning's data yet.\n"
            f"Fall back to yesterday's sleep data for the readiness gate.\n"
            f"Reduce confidence in readiness score — note data_completeness_pct accordingly."
        )

    # ── Section 3 — 14-day metrics table ─────────────────────────────
    header = "date | steps | rhr | hrv_ms | bb_min | bb_max | slp_score | slp_min | deep_min | stress | vo2max | acute_load | chronic_load | acwr"
    rows: list[str] = []
    for i, m in enumerate(reversed(metrics)):  # newest first (today at top)
        if i == 0:
            label = "  ← TODAY (most recent)"
        elif i == 1:
            label = "  ← YESTERDAY"
        else:
            label = ""
        rows.append(
            " | ".join(
                [
                    str(m.get("date", "?")) + label,
                    _v(m.get("total_steps")),
                    _v(m.get("avg_resting_hr")),
                    _v(m.get("hrv_last_night_ms")),
                    _v(m.get("body_battery_min")),
                    _v(m.get("body_battery_max")),
                    _v(m.get("sleep_score")),
                    _v(m.get("sleep_duration_min")),
                    _v(m.get("deep_sleep_min")),
                    _v(m.get("stress_avg")),
                    _v(m.get("vo2max")),
                    _v(m.get("acute_load")),
                    _v(m.get("chronic_load")),
                    _v(m.get("acwr")),
                ]
            )
        )
    sections.append(
        f"## Daily Metrics (14d, newest first)\n{header}\n" + "\n".join(rows)
    )

    # ── Section 4 — HRV baseline ────────────────────────────────────
    baseline_str = f"{hrv_baseline:.1f}" if hrv_baseline is not None else "insufficient data"
    sections.append(f"## HRV Baseline (28d avg): {baseline_str} ms")

    # ── Section 5 — Training load ───────────────────────────────────
    # Use stored Garmin training load values from the most recent day if available
    latest = metrics[-1] if metrics else {}
    stored_acute = latest.get("acute_load")
    stored_chronic = latest.get("chronic_load")
    stored_acwr = latest.get("acwr")
    sections.append(
        f"## Training Load\n"
        f"Acute load (Garmin, latest): {_v(stored_acute)}\n"
        f"Chronic load (Garmin, latest): {_v(stored_chronic)}\n"
        f"ACWR (Garmin, latest): {_v(stored_acwr)}\n"
        f"Acute (7d avg kcal, computed): {_v(acute)}\n"
        f"Chronic (28d avg kcal, computed): {_v(chronic)}\n"
        f"ACWR (computed): {_v(acwr)}"
    )

    # ── Section 6 — Recent workouts ─────────────────────────────────
    sections.append(
        f"## Recent Workouts (7d)\n"
        + json.dumps(workouts, separators=(",", ":"), default=str)
    )

    # ── Section 7 — Subjective feedback ─────────────────────────────
    sections.append(
        f"## Athlete Feedback (7d)\n"
        + json.dumps(feedback, separators=(",", ":"), default=str)
    )

    # ── Section 8 — Task ────────────────────────────────────────────
    sections.append(
        f"## Task\nAnalyse readiness for: {target_date}\nOutput ReadinessReport JSON now."
    )

    user_prompt = "\n\n".join(sections)

    # ── Compress ─────────────────────────────────────────────────────
    compressed, ratio = compress(user_prompt)

    # ── System prompt (+ optional context injection) ─────────────────
    sys = SYSTEM_PROMPT
    if context_injection:
        sys = context_injection.rstrip() + "\n\n" + sys

    token_estimate = (len(sys) + len(compressed)) // 4

    return AnalysisPromptPackage(
        system_prompt=sys,
        user_prompt=user_prompt,
        compressed_user_prompt=compressed,
        compression_ratio=round(ratio, 3),
        context_injection=context_injection,
        token_estimate=token_estimate,
    )


if __name__ == "__main__":
    from db.model import User, get_session

    with get_session() as s:
        user = s.query(User).first()

    if not user:
        print("No users in DB — run sync first.")
        raise SystemExit(1)

    pkg = build_analysis_prompt(user.id, str(date.today()))
    print("=" * 60)
    print("SYSTEM PROMPT")
    print("=" * 60)
    print(pkg.system_prompt[:500], "...")
    print(f"\n[system length: {len(pkg.system_prompt)} chars]")
    print("\n" + "=" * 60)
    print("USER PROMPT (original)")
    print("=" * 60)
    print(pkg.user_prompt)
    print(f"\n[original: {len(pkg.user_prompt)} chars]")
    print("\n" + "=" * 60)
    print("USER PROMPT (compressed)")
    print("=" * 60)
    print(pkg.compressed_user_prompt)
    print(f"\n[compressed: {len(pkg.compressed_user_prompt)} chars]")
    print(f"[compression ratio: {pkg.compression_ratio:.1%}]")
    print(f"[estimated tokens: {pkg.token_estimate}]")
