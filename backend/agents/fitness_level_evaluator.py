"""Algorithmically evaluate whether a user's fitness level should change.

Runs during the daily pipeline when fitness_level_locked is False.
No LLM calls — pure math on existing plan session data.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from db.model import FitnessLevelHistory, TrainingPlanRow, UserProfile, get_session

logger = logging.getLogger(__name__)

LEVELS = ["beginner", "intermediate", "advanced"]

# Upgrade: ≥80% completion AND ≥16 completed sessions over 28 days
UPGRADE_MIN_RATE = 0.80
UPGRADE_MIN_SESSIONS = 16

# Downgrade: <40% completion OR <4 completed in each of two consecutive 14-day windows
DOWNGRADE_MAX_RATE = 0.40
DOWNGRADE_MAX_SESSIONS = 4

# Minimum total sessions before we trust the signal
MIN_SESSIONS_FOR_EVAL = 14


def _sessions_in_window(plan_rows: list[dict], start: date, end: date) -> list[dict]:
    sessions = []
    for plan_json_str in plan_rows:
        try:
            plan = json.loads(plan_json_str)
            for s in plan.get("sessions", []):
                try:
                    s_date = date.fromisoformat(s["date"])
                    if start <= s_date <= end:
                        sessions.append(s)
                except (KeyError, ValueError):
                    continue
        except (json.JSONDecodeError, AttributeError):
            continue
    return sessions


def _window_fails_thresholds(sessions: list[dict]) -> bool:
    non_skipped = [s for s in sessions if s.get("status") != "skipped"]
    if not non_skipped:
        return True
    completed = [s for s in non_skipped if s.get("status") in ("completed", "modified")]
    rate = len(completed) / len(non_skipped)
    return rate < DOWNGRADE_MAX_RATE or len(completed) < DOWNGRADE_MAX_SESSIONS


def check_and_update_fitness_level(user_id: str) -> tuple[str | None, str | None]:
    """Evaluate and apply a fitness level change if warranted.

    Returns (new_level, reason) if changed, else (None, None).
    Does not update the DB — caller decides whether to persist.
    """
    with get_session() as s:
        profile = s.get(UserProfile, user_id)
        if profile is None or profile.fitness_level_locked:
            return None, None
        current_level = profile.fitness_level

    if current_level not in LEVELS:
        return None, None

    current_idx = LEVELS.index(current_level)
    today = date.today()
    cutoff_28 = today - timedelta(days=28)

    with get_session() as s:
        rows = s.execute(
            select(TrainingPlanRow.plan_json).where(
                TrainingPlanRow.user_id == user_id,
                TrainingPlanRow.valid_to >= str(cutoff_28),
            )
        ).scalars().all()

    all_sessions = _sessions_in_window(list(rows), cutoff_28, today)

    if len(all_sessions) < MIN_SESSIONS_FOR_EVAL:
        logger.debug("Fitness eval skipped for %s: only %d sessions in window", user_id, len(all_sessions))
        return None, None

    non_skipped_28 = [s for s in all_sessions if s.get("status") != "skipped"]
    completed_28 = [s for s in non_skipped_28 if s.get("status") in ("completed", "modified")]
    total_28 = len(non_skipped_28)
    count_28 = len(completed_28)
    rate_28 = count_28 / total_28 if total_28 > 0 else 0.0

    # Upgrade check
    if current_idx < len(LEVELS) - 1 and rate_28 >= UPGRADE_MIN_RATE and count_28 >= UPGRADE_MIN_SESSIONS:
        new_level = LEVELS[current_idx + 1]
        reason = f"Upgraded from {current_level}: {count_28} sessions completed in 28 days ({round(rate_28 * 100)}% completion rate)"
        _persist_change(user_id, current_level, new_level, reason)
        return new_level, reason

    # Downgrade check — both 14-day windows must fail
    if current_idx > 0:
        cutoff_14 = today - timedelta(days=14)
        recent_14 = _sessions_in_window(list(rows), cutoff_14 + timedelta(days=1), today)
        prior_14 = _sessions_in_window(list(rows), cutoff_28, cutoff_14)

        if _window_fails_thresholds(recent_14) and _window_fails_thresholds(prior_14):
            new_level = LEVELS[current_idx - 1]
            reason = f"Downgraded from {current_level}: low completion rate over 4 weeks ({round(rate_28 * 100)}%)"
            _persist_change(user_id, current_level, new_level, reason)
            return new_level, reason

    return None, None


def _persist_change(user_id: str, old_level: str | None, new_level: str, reason: str) -> None:
    with get_session() as s:
        profile = s.get(UserProfile, user_id)
        if profile is None:
            return
        profile.fitness_level = new_level
        profile.updated_at = datetime.now(timezone.utc)
        s.add(FitnessLevelHistory(
            user_id=user_id,
            old_level=old_level,
            new_level=new_level,
            reason=reason,
            source="auto",
            created_at=datetime.now(timezone.utc),
        ))
    logger.info("Fitness level auto-adjusted for %s: %s → %s", user_id, old_level, new_level)
