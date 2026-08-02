"""Read helpers that load DB data for agent consumption."""

from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta

from sqlalchemy import func, select

from db.model import (
    DailyMetric,
    ReadinessReportRow,
    TrainingPlanRow,
    UserFeedback,
    UserProfile,
    Workout,
    get_session,
)

log = logging.getLogger(__name__)

# Columns to exclude from DailyMetric dicts (too large / internal)
_METRIC_EXCLUDE = {"raw_garmin_json", "_sa_instance_state"}


def get_recent_metrics(user_id: str, days: int = 14) -> list[dict]:
    """Return the last *days* daily-metric rows for *user_id*, oldest-first.

    Includes today's row — today's entry contains last night's sleep data
    which is the primary readiness signal for the current day.
    """
    cutoff = date.today() - timedelta(days=days)
    with get_session() as s:
        rows = (
            s.execute(
                select(DailyMetric)
                .where(DailyMetric.user_id == user_id, DailyMetric.date >= cutoff)
                .order_by(DailyMetric.date.desc())
                .limit(days)
            )
            .scalars()
            .all()
        )
        results: list[dict] = []
        for r in reversed(rows):  # oldest-first
            d = {k: v for k, v in r.__dict__.items() if k not in _METRIC_EXCLUDE}
            # Parse workouts_json string → list
            wj = d.get("workouts_json")
            if isinstance(wj, str):
                try:
                    d["workouts_json"] = json.loads(wj)
                except json.JSONDecodeError:
                    d["workouts_json"] = []
            results.append(d)
    return results


def get_hrv_baseline(user_id: str, days: int = 28) -> float | None:
    """Average HRV over the last *days* days including today.  Returns None if < 3 data points."""
    cutoff = date.today() - timedelta(days=days)
    with get_session() as s:
        rows = (
            s.execute(
                select(DailyMetric.hrv_last_night_ms)
                .where(
                    DailyMetric.user_id == user_id,
                    DailyMetric.date >= cutoff,
                    DailyMetric.hrv_last_night_ms.is_not(None),
                )
            )
            .scalars()
            .all()
        )
    if len(rows) < 3:
        return None
    return sum(rows) / len(rows)


def get_todays_recovery(user_id: str) -> dict:
    """Return today's recovery signals from daily_metrics.

    Returns a dict with key recovery fields and availability flags.
    If no row exists for today all metric values are None and data_available=False.
    """
    today = date.today()
    with get_session() as s:
        row = s.execute(
            select(DailyMetric).where(
                DailyMetric.user_id == user_id,
                DailyMetric.date == today,
            )
        ).scalar_one_or_none()

        if row is None:
            return {
                "date": str(today),
                "sleep_score": None,
                "sleep_duration_min": None,
                "deep_sleep_min": None,
                "rem_sleep_min": None,
                "hrv_last_night_ms": None,
                "body_battery_min": None,
                "body_battery_max": None,
                "stress_avg": None,
                "data_available": False,
                "sleep_available": False,
                "hrv_available": False,
            }

        # Read all fields inside the session to avoid DetachedInstanceError
        sleep_score = row.sleep_score
        sleep_duration_min = row.sleep_duration_min
        deep_sleep_min = row.deep_sleep_min
        rem_sleep_min = row.rem_sleep_min
        hrv_last_night_ms = row.hrv_last_night_ms
        body_battery_min = row.body_battery_min
        body_battery_max = row.body_battery_max
        stress_avg = row.stress_avg
        row_date = row.date

    sleep_available = sleep_score is not None
    hrv_available = hrv_last_night_ms is not None
    data_available = any([
        sleep_available,
        hrv_available,
        body_battery_min is not None,
        body_battery_max is not None,
        stress_avg is not None,
    ])

    return {
        "date": str(row_date),
        "sleep_score": sleep_score,
        "sleep_duration_min": sleep_duration_min,
        "deep_sleep_min": deep_sleep_min,
        "rem_sleep_min": rem_sleep_min,
        "hrv_last_night_ms": hrv_last_night_ms,
        "body_battery_min": body_battery_min,
        "body_battery_max": body_battery_max,
        "stress_avg": stress_avg,
        "data_available": data_available,
        "sleep_available": sleep_available,
        "hrv_available": hrv_available,
    }


def get_recent_workouts(user_id: str, days: int = 7) -> list[dict]:
    """Return recent workouts (no raw_json), newest-first."""
    cutoff = date.today() - timedelta(days=days)
    with get_session() as s:
        rows = (
            s.execute(
                select(Workout)
                .where(Workout.user_id == user_id, Workout.date >= cutoff)
                .order_by(Workout.date.desc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "date": str(r.date),
                "sport": r.sport,
                "duration_min": r.duration_min,
                "distance_m": r.distance_m,
                "avg_hr": r.avg_hr,
                "perceived_effort": r.perceived_effort,
            }
            for r in rows
        ]


def get_recent_feedback(user_id: str, days: int = 7) -> list[dict]:
    """Return recent user feedback rows."""
    cutoff = date.today() - timedelta(days=days)
    with get_session() as s:
        rows = (
            s.execute(
                select(UserFeedback)
                .where(UserFeedback.user_id == user_id, UserFeedback.feedback_date >= cutoff)
                .order_by(UserFeedback.feedback_date.desc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "feedback_date": str(r.feedback_date),
                "free_text": r.free_text,
                "perceived_effort": r.perceived_effort,
                "mood": r.mood,
                "override_choice": r.override_choice,
                "session_skipped": r.session_skipped,
                "skip_reason": r.skip_reason,
            }
            for r in rows
        ]


def get_user_profile(user_id: str) -> dict | None:
    """Load the user profile as a plain dict, parsing JSON list fields."""
    with get_session() as s:
        profile = s.get(UserProfile, user_id)
        if profile is None:
            return None
        d = {k: v for k, v in profile.__dict__.items() if k != "_sa_instance_state"}
        for field in ("medical_conditions", "dietary_allergies"):
            raw = d.get(field)
            if isinstance(raw, str):
                try:
                    d[field] = json.loads(raw)
                except json.JSONDecodeError:
                    d[field] = [raw] if raw else []
        return d


def compute_acwr(user_id: str) -> tuple[float | None, float | None, float | None]:
    """Return (acute_load, chronic_load, acwr) using active_calories as proxy."""
    today = date.today()
    cutoff_28 = today - timedelta(days=28)
    with get_session() as s:
        rows = (
            s.execute(
                select(DailyMetric.date, DailyMetric.active_calories)
                .where(
                    DailyMetric.user_id == user_id,
                    DailyMetric.date >= cutoff_28,
                    DailyMetric.active_calories.is_not(None),
                )
                .order_by(DailyMetric.date.desc())
            )
            .all()
        )
    if not rows:
        return (None, None, None)

    cutoff_7 = today - timedelta(days=7)
    acute_vals = [cal for d, cal in rows if d >= cutoff_7]
    chronic_vals = [cal for _, cal in rows]

    acute = sum(acute_vals) / len(acute_vals) if acute_vals else None
    chronic = sum(chronic_vals) / len(chronic_vals) if chronic_vals else None

    if acute is None or chronic is None or chronic == 0:
        return (acute, chronic, None)

    acwr = round(acute / chronic, 2)
    return (acute, chronic, acwr)


def get_weeks_to_goal(user_id: str) -> int | None:
    """Weeks remaining until the user's goal_date, or None if unset."""
    with get_session() as s:
        profile = s.get(UserProfile, user_id)
        if profile is None or profile.goal_date is None:
            return None
        delta = profile.goal_date - date.today()
        if delta.days <= 0:
            return 0
        return math.ceil(delta.days / 7)


def compute_hr_zones(user_id: str) -> dict | None:
    """Compute HR zones using the best available method.

    Priority:
    1. LTHR (user-set) → Friel's endurance zones
    2. Max HR from recorded workouts → percentage-based zones
    3. Age-based max HR (220 − age) → percentage-based zones

    Returns a dict with keys 'method' and 'zones' (Z1–Z5 BPM strings), or None.
    """
    with get_session() as s:
        profile = s.get(UserProfile, user_id)
        if profile is None:
            return None

        lthr = profile.lthr
        dob = profile.date_of_birth

        max_hr_recorded: int | None = s.execute(
            select(func.max(Workout.max_hr)).where(
                Workout.user_id == user_id,
                Workout.max_hr.is_not(None),
            )
        ).scalar()

    # ── Method 1: LTHR (Friel zones) ─────────────────────────────────
    if lthr:
        return {
            "method": f"LTHR={lthr} bpm (user-set, Friel zones)",
            "zones": {
                "Z1": f"< {round(lthr * 0.85)} bpm (recovery)",
                "Z2": f"{round(lthr * 0.85)}–{round(lthr * 0.89)} bpm (aerobic)",
                "Z3": f"{round(lthr * 0.90)}–{round(lthr * 0.94)} bpm (tempo)",
                "Z4": f"{round(lthr * 0.95)}–{round(lthr * 0.99)} bpm (threshold)",
                "Z5": f"≥ {lthr} bpm (VO2max)",
            },
        }

    # ── Method 2: Recorded max HR ─────────────────────────────────────
    max_hr = max_hr_recorded
    method_label: str | None = None
    if max_hr is not None:
        method_label = f"Recorded max HR={max_hr} bpm (from workouts)"

    # ── Method 3: Age formula ─────────────────────────────────────────
    if max_hr is None and dob is not None:
        age = (date.today() - dob).days // 365
        max_hr = 220 - age
        method_label = f"Age-based max HR={max_hr} bpm (220−{age})"

    if max_hr is None:
        return None

    return {
        "method": method_label,
        "zones": {
            "Z1": f"{round(max_hr * 0.50)}–{round(max_hr * 0.60)} bpm (recovery)",
            "Z2": f"{round(max_hr * 0.60)}–{round(max_hr * 0.70)} bpm (aerobic)",
            "Z3": f"{round(max_hr * 0.70)}–{round(max_hr * 0.80)} bpm (tempo)",
            "Z4": f"{round(max_hr * 0.80)}–{round(max_hr * 0.90)} bpm (threshold)",
            "Z5": f"{round(max_hr * 0.90)}–{max_hr} bpm (VO2max)",
        },
    }


_ZONE_LABELS = ["Recovery", "Aerobic", "Tempo", "Threshold", "VO2max"]
_ZONE_KEYS = ["Z1", "Z2", "Z3", "Z4", "Z5"]


def _friel_zones(lthr: int) -> dict:
    return {
        "Z1": {"label": "Recovery",   "low": 0,                        "high": round(lthr * 0.85) - 1},
        "Z2": {"label": "Aerobic",    "low": round(lthr * 0.85),       "high": round(lthr * 0.89)},
        "Z3": {"label": "Tempo",      "low": round(lthr * 0.90),       "high": round(lthr * 0.94)},
        "Z4": {"label": "Threshold",  "low": round(lthr * 0.95),       "high": round(lthr * 0.99)},
        "Z5": {"label": "VO2max",     "low": lthr,                     "high": 999},
    }


def _max_hr_pct_zones(max_hr: int) -> dict:
    return {
        "Z1": {"label": "Recovery",   "low": round(max_hr * 0.50), "high": round(max_hr * 0.60) - 1},
        "Z2": {"label": "Aerobic",    "low": round(max_hr * 0.60), "high": round(max_hr * 0.70) - 1},
        "Z3": {"label": "Tempo",      "low": round(max_hr * 0.70), "high": round(max_hr * 0.80) - 1},
        "Z4": {"label": "Threshold",  "low": round(max_hr * 0.80), "high": round(max_hr * 0.90) - 1},
        "Z5": {"label": "VO2max",     "low": round(max_hr * 0.90), "high": max_hr},
    }


def get_hr_zone_definitions(user_id: str) -> dict:
    """Return HR zone definitions for both LTHR (Friel) and max-HR% methods.

    Each method carries 'available', 'method' (label string), and 'zones' (or None).
    """
    with get_session() as s:
        profile = s.get(UserProfile, user_id)
        if profile is None:
            return {
                "lthr": {"available": False, "method": "No user profile found", "zones": None},
                "max_hr_pct": {"available": False, "method": "No user profile found", "zones": None},
            }

        lthr = profile.lthr
        dob = profile.date_of_birth

        max_hr_recorded: int | None = s.execute(
            select(func.max(Workout.max_hr)).where(
                Workout.user_id == user_id,
                Workout.max_hr.is_not(None),
            )
        ).scalar()

    # LTHR method
    if lthr:
        lthr_def = {
            "available": True,
            "method": f"LTHR={lthr} bpm (Friel zones)",
            "zones": _friel_zones(lthr),
        }
    else:
        lthr_def = {
            "available": False,
            "method": "LTHR not set — configure in Settings",
            "zones": None,
        }

    # Max-HR% method
    max_hr = max_hr_recorded
    if max_hr is not None:
        max_hr_label = f"Recorded max HR={max_hr} bpm (from workouts)"
    elif dob is not None:
        age = (date.today() - dob).days // 365
        max_hr = 220 - age
        max_hr_label = f"Age-based max HR={max_hr} bpm (220−{age})"
    else:
        max_hr_label = None

    if max_hr is not None:
        max_hr_def = {
            "available": True,
            "method": max_hr_label,
            "zones": _max_hr_pct_zones(max_hr),
        }
    else:
        max_hr_def = {
            "available": False,
            "method": "No max HR data — record workouts with HR or set date of birth",
            "zones": None,
        }

    return {"lthr": lthr_def, "max_hr_pct": max_hr_def}


def get_hr_zone_summary(user_id: str, days: int = 14) -> dict:
    """Return aggregate zone time and per-workout breakdown for the given period."""
    cutoff = date.today() - timedelta(days=days)
    empty_agg = {z: 0 for z in _ZONE_KEYS}

    with get_session() as s:
        rows = (
            s.execute(
                select(Workout)
                .where(Workout.user_id == user_id, Workout.date >= cutoff)
                .order_by(Workout.date.asc())
            )
            .scalars()
            .all()
        )
        workout_data = [
            {
                "id": r.id,
                "date": str(r.date),
                "sport": r.sport,
                "duration_min": r.duration_min,
                "garmin_activity_id": r.garmin_activity_id,
                "hr_zone_secs_json": r.hr_zone_secs_json,
                "hr_zone_thresholds_json": r.hr_zone_thresholds_json,
            }
            for r in rows
        ]

    aggregate_secs = {z: 0.0 for z in _ZONE_KEYS}
    workouts_with_zones = 0
    workout_list = []

    for w in workout_data:
        raw_secs = w["hr_zone_secs_json"]
        raw_thresh = w["hr_zone_thresholds_json"]

        if not raw_secs:
            continue

        try:
            secs_by_garmin_zone: dict = json.loads(raw_secs)
        except (json.JSONDecodeError, TypeError):
            continue

        # Map Garmin numeric keys ("1"–"5") → "Z1"–"Z5"
        zone_secs = {f"Z{k}": float(v) for k, v in secs_by_garmin_zone.items() if k.isdigit()}
        # Fill missing zones with 0
        for z in _ZONE_KEYS:
            zone_secs.setdefault(z, 0.0)

        # Parse thresholds
        zone_thresholds = None
        if raw_thresh:
            try:
                thresh_raw: dict = json.loads(raw_thresh)
                zone_thresholds = {f"Z{k}": v for k, v in thresh_raw.items() if k.isdigit()}
            except (json.JSONDecodeError, TypeError):
                pass

        for z in _ZONE_KEYS:
            aggregate_secs[z] += zone_secs.get(z, 0.0)

        workouts_with_zones += 1
        workout_list.append({
            "date": w["date"],
            "sport": w["sport"],
            "duration_min": w["duration_min"],
            "garmin_activity_id": w["garmin_activity_id"],
            "zone_secs": {z: round(zone_secs.get(z, 0.0)) for z in _ZONE_KEYS},
            "zone_thresholds": zone_thresholds,
        })

    return {
        "total_workouts": len(workout_data),
        "workouts_with_zones": workouts_with_zones,
        "aggregate_secs": {z: round(v) for z, v in aggregate_secs.items()},
        "workouts": workout_list,
    }


def get_latest_readiness_report(user_id: str) -> dict | None:
    """Return the most recent readiness report as a dict, or None."""
    with get_session() as s:
        row = s.execute(
            select(ReadinessReportRow)
            .where(ReadinessReportRow.user_id == user_id)
            .order_by(ReadinessReportRow.report_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        report = json.loads(row.report_json)
        report["_meta"] = {
            "db_id": row.id,
            "model_used": row.model_used,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
        }
        return report


def get_current_plan(user_id: str) -> dict | None:
    """Return the current active training plan as a dict, or None."""
    with get_session() as s:
        row = s.execute(
            select(TrainingPlanRow)
            .where(
                TrainingPlanRow.user_id == user_id,
                TrainingPlanRow.is_current == True,  # noqa: E712
            )
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            return None
        plan = json.loads(row.plan_json)
        plan["_meta"] = {
            "db_id": row.id,
            "generated_at": row.generated_at.isoformat() if row.generated_at else None,
            "model_used": row.model_used,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
            "training_gate": row.training_gate,
            "override_applied": row.override_applied,
        }
        return plan
