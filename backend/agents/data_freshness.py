"""Assess whether today's wearable data is fresh enough for a reliable readiness report."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from db.model import DailyMetric, get_session

logger = logging.getLogger(__name__)


@dataclass
class DataFreshnessReport:
    user_id: str
    assessment_date: str
    today_sleep_available: bool
    today_hrv_available: bool
    today_body_battery_available: bool
    yesterday_sleep_available: bool
    yesterday_hrv_available: bool
    last_sync_hours_ago: float | None
    recommendation: str
    confidence: str
    warning_message: str | None


def assess_data_freshness(user_id: str) -> DataFreshnessReport:
    """Assess how fresh and complete today's wearable data is."""
    today = date.today()
    yesterday = today - timedelta(days=1)

    with get_session() as session:
        rows = session.execute(
            select(DailyMetric).where(
                DailyMetric.user_id == user_id,
                DailyMetric.date.in_([today, yesterday]),
            )
        ).scalars().all()

        # Extract all needed fields inside the session to avoid DetachedInstanceError
        row_data: dict[date, dict] = {}
        for r in rows:
            row_data[r.date] = {
                "sleep_score": r.sleep_score,
                "hrv_last_night_ms": r.hrv_last_night_ms,
                "body_battery_min": r.body_battery_min,
                "synced_at": r.synced_at,
            }

    today_data = row_data.get(today)
    yesterday_data = row_data.get(yesterday)

    # ── Signal availability ───────────────────────────────────────────
    today_sleep_available = today_data is not None and today_data["sleep_score"] is not None
    today_hrv_available = today_data is not None and today_data["hrv_last_night_ms"] is not None
    today_body_battery_available = today_data is not None and today_data["body_battery_min"] is not None
    yesterday_sleep_available = yesterday_data is not None and yesterday_data["sleep_score"] is not None
    yesterday_hrv_available = yesterday_data is not None and yesterday_data["hrv_last_night_ms"] is not None

    # ── Most recent sync timestamp ────────────────────────────────────
    candidates = [
        d["synced_at"] for d in [today_data, yesterday_data]
        if d is not None and d["synced_at"] is not None
    ]
    last_sync_hours_ago: float | None = None
    if candidates:
        most_recent = max(candidates)
        now = datetime.now(tz=timezone.utc)
        if most_recent.tzinfo is None:
            most_recent = most_recent.replace(tzinfo=timezone.utc)
        last_sync_hours_ago = round((now - most_recent).total_seconds() / 3600, 2)

    # ── Determine confidence and recommendation ───────────────────────
    no_data = today_data is None and yesterday_data is None

    if no_data:
        confidence = "very_low"
        recommendation = "NO_DATA"
        warning_message = "No recent wearable data found. Run a Garmin sync first."

    elif today_sleep_available:
        confidence = "high"
        recommendation = "USE_TODAY_SLEEP"
        warning_message = None

    elif last_sync_hours_ago is not None and last_sync_hours_ago < 2:
        confidence = "medium"
        recommendation = "USE_YESTERDAY_SLEEP_RECENT_SYNC"
        warning_message = (
            "Last night's sleep not yet in Garmin — using previous night's data. "
            "Score may be slightly off."
        )

    else:
        confidence = "low"
        recommendation = "TRIGGER_RESYNC"
        warning_message = (
            "Garmin data may be stale. Consider syncing manually in Settings."
        )

    report = DataFreshnessReport(
        user_id=user_id,
        assessment_date=str(today),
        today_sleep_available=today_sleep_available,
        today_hrv_available=today_hrv_available,
        today_body_battery_available=today_body_battery_available,
        yesterday_sleep_available=yesterday_sleep_available,
        yesterday_hrv_available=yesterday_hrv_available,
        last_sync_hours_ago=last_sync_hours_ago,
        recommendation=recommendation,
        confidence=confidence,
        warning_message=warning_message,
    )

    logger.info(
        "data_freshness user=%s confidence=%s recommendation=%s sync_hours_ago=%s",
        user_id,
        confidence,
        recommendation,
        last_sync_hours_ago,
    )

    return report


def get_best_sleep_date(user_id: str) -> str:
    """Return the date string whose sleep data should be used for today's analysis."""
    freshness = assess_data_freshness(user_id)

    if freshness.today_sleep_available:
        result = str(date.today())
    else:
        result = str(date.today() - timedelta(days=1))

    logger.info(
        "sleep_date_selected date_used=%s reason=%s confidence=%s",
        result,
        freshness.recommendation,
        freshness.confidence,
    )

    return result
