import json
from datetime import date
from uuid import uuid4

from sqlalchemy import select

from db.model import DailyMetric, User, UserProfile, Workout, get_session
from ingestion.normaliser import DailyMetrics


def ensure_user(user_id: str, email: str) -> str:
    """Ensure a user exists; return the canonical user_id for this email."""
    with get_session() as session:
        # 1. Look up by the supplied ID first
        existing = session.get(User, user_id)
        if existing:
            return existing.id
        # 2. Look up by email (may exist with a different ID from the API)
        existing_by_email = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if existing_by_email:
            return existing_by_email.id
        # 3. Create new user
        session.merge(User(id=user_id, email=email))
        session.merge(UserProfile(user_id=user_id))
        return user_id


def save_daily_metrics(metrics: DailyMetrics) -> str:
    with get_session() as session:
        # Look up existing row by unique constraint to preserve its id
        row = session.execute(
            select(DailyMetric).where(
                DailyMetric.user_id == metrics.user_id,
                DailyMetric.date == metrics.date,
                DailyMetric.source == metrics.source,
            )
        ).scalar_one_or_none()

        row_id = row.id if row else str(uuid4())
        data = metrics.model_dump()
        data["id"] = row_id
        session.merge(DailyMetric(**data))

    print(f"Saved metrics for {metrics.date}")
    return row_id


def save_workouts(
    user_id: str,
    date_obj: date,
    activities_json: str | None,
    zone_data_map: dict[str, dict] | None = None,
) -> int:
    if not activities_json:
        return 0

    activities = json.loads(activities_json)
    if not activities:
        return 0

    count = 0
    with get_session() as session:
        for activity in activities:
            garmin_id = str(activity.get("activityId", ""))

            # Look up existing by garmin_activity_id to preserve its PK
            existing = session.execute(
                select(Workout).where(
                    Workout.garmin_activity_id == garmin_id,
                    Workout.user_id == user_id,
                )
            ).scalar_one_or_none()

            duration_s = activity.get("duration")
            duration_min = int(duration_s / 60) if duration_s else None

            avg_hr_val = activity.get("averageHR")
            max_hr_val = activity.get("maxHR")

            # Resolve zone data — preserve existing if no new data provided
            zone_entry = (zone_data_map or {}).get(garmin_id)
            hr_zone_secs = (
                json.dumps(zone_entry["secs"]) if zone_entry
                else (existing.hr_zone_secs_json if existing else None)
            )
            hr_zone_thresholds = (
                json.dumps(zone_entry["thresholds"]) if zone_entry
                else (existing.hr_zone_thresholds_json if existing else None)
            )

            workout = Workout(
                id=existing.id if existing else str(uuid4()),
                user_id=user_id,
                date=date_obj,
                sport=activity.get("activityType", {}).get("typeKey", "other"),
                duration_min=duration_min,
                distance_m=activity.get("distance"),
                avg_hr=int(avg_hr_val) if avg_hr_val is not None else None,
                max_hr=int(max_hr_val) if max_hr_val is not None else None,
                garmin_activity_id=garmin_id,
                raw_json=json.dumps(activity, default=str),
                hr_zone_secs_json=hr_zone_secs,
                hr_zone_thresholds_json=hr_zone_thresholds,
            )
            session.merge(workout)
            count += 1

    print(f"Saved {count} workout(s) for {date_obj}")
    return count
