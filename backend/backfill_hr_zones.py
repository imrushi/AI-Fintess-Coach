#!/usr/bin/env python3
"""
One-time backfill: fetch HR zone data from Garmin for all existing workouts
that have a garmin_activity_id but no hr_zone_secs_json.

Usage:
    cd backend
    PYTHONPATH=. python backfill_hr_zones.py [--user-id USER_ID] [--dry-run] [--delay 0.5]
"""

import argparse
import time

from sqlalchemy import select

from config import settings
from db.model import Base, User, UserProfile, Workout, get_engine, get_session
from ingestion.garmin_client import GarminClient
from ingestion.zone_utils import parse_zone_response


def backfill_user(user_id: str, garmin_email: str, garmin_password: str, dry_run: bool, delay: float, debug: bool = False) -> None:
    client = GarminClient(garmin_email, garmin_password)
    client.connect()

    with get_session() as session:
        rows = (
            session.execute(
                select(Workout)
                .where(
                    Workout.user_id == user_id,
                    Workout.garmin_activity_id.is_not(None),
                    Workout.hr_zone_secs_json.is_(None),
                )
                .order_by(Workout.date.desc())
            )
            .scalars()
            .all()
        )
        # Eagerly copy out what we need before session closes
        targets = [
            {"id": r.id, "garmin_activity_id": r.garmin_activity_id, "date": r.date}
            for r in rows
        ]

    print(f"  Found {len(targets)} workout(s) to backfill for user {user_id[:8]}...")

    success = 0
    for i, t in enumerate(targets, 1):
        garmin_id = t["garmin_activity_id"]
        try:
            raw = client.get_activity_hr_in_timezones(garmin_id)
            if debug:
                print(f"  RAW response for {garmin_id}: {raw!r}")
            parsed = parse_zone_response(raw)
            if parsed is None:
                print(f"  [{i}/{len(targets)}] {t['date']} activity={garmin_id}: no zone data returned")
                if delay:
                    time.sleep(delay)
                continue

            secs, thresholds = parsed
            if dry_run:
                print(f"  [{i}/{len(targets)}] {t['date']} activity={garmin_id}: DRY RUN — zones={list(secs.keys())}")
            else:
                import json
                with get_session() as session:
                    workout = session.get(Workout, t["id"])
                    if workout:
                        workout.hr_zone_secs_json = json.dumps(secs)
                        workout.hr_zone_thresholds_json = json.dumps(thresholds)
                print(f"  [{i}/{len(targets)}] {t['date']} activity={garmin_id}: saved zones={list(secs.keys())}")
                success += 1

        except Exception as exc:
            print(f"  [{i}/{len(targets)}] {t['date']} activity={garmin_id}: ERROR — {exc}")

        if delay and i < len(targets):
            time.sleep(delay)

    if not dry_run:
        print(f"  Backfilled {success}/{len(targets)} workout(s) for user {user_id[:8]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill HR zone data from Garmin")
    parser.add_argument("--user-id", type=str, default=None, help="Process only this user ID")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between API calls (default 0.5)")
    parser.add_argument("--debug", action="store_true", help="Print raw Garmin API responses")
    args = parser.parse_args()

    Base.metadata.create_all(get_engine())

    with get_session() as session:
        if args.user_id:
            profiles = [session.get(UserProfile, args.user_id)]
            profiles = [p for p in profiles if p is not None]
        else:
            profiles = (
                session.execute(
                    select(UserProfile).where(UserProfile.garmin_email.is_not(None))
                )
                .scalars()
                .all()
            )
        users = [
            {
                "user_id": p.user_id,
                "garmin_email": p.garmin_email,
                "garmin_password": p.garmin_password or "",
            }
            for p in profiles
            if p.garmin_email
        ]

    if not users:
        print("No users with Garmin credentials found.")
        return

    print(f"Processing {len(users)} user(s){' [DRY RUN]' if args.dry_run else ''}...")
    for u in users:
        print(f"\nUser {u['user_id'][:8]}... ({u['garmin_email']})")
        try:
            backfill_user(u["user_id"], u["garmin_email"], u["garmin_password"], args.dry_run, args.delay, args.debug)
        except Exception as exc:
            print(f"  FAILED: {exc}")

    print("\nDone.")


if __name__ == "__main__":
    main()
