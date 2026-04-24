import argparse
import hashlib
import time
from datetime import date, timedelta

from config import settings
from db.model import Base, get_engine
from db.writer import ensure_user, save_daily_metrics, save_workouts
from ingestion.garmin_client import GarminClient
from ingestion.normaliser import normalise_day


def make_user_id(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:36]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Garmin data to local DB")
    parser.add_argument("--email", type=str, required=True, help="Garmin email / user identifier")
    parser.add_argument("--days", type=int, default=30, help="How many days back to sync (default: 30)")
    parser.add_argument("--date", type=str, default=None, help="Sync a specific date only (YYYY-MM-DD)")
    args = parser.parse_args()

    # Ensure tables exist
    Base.metadata.create_all(get_engine())

    user_id = make_user_id(args.email)
    ensure_user(user_id, args.email)
    print(f"User: {args.email} (id={user_id[:8]}...)")

    # Build date list
    if args.date:
        dates = [args.date]
    else:
        today = date.today()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, args.days + 1)]

    # Connect to Garmin
    client = GarminClient(settings.GARMIN_EMAIL, settings.GARMIN_PASSWORD)
    client.connect()

    success_count = 0
    total = len(dates)

    for i, date_str in enumerate(dates):
        try:
            print(f"\nSyncing {date_str}...")
            raw = client.fetch_day(date_str)
            metrics = normalise_day(raw, user_id)
            save_daily_metrics(metrics)
            save_workouts(user_id, metrics.date, metrics.workouts_json)
            success_count += 1
        except Exception as exc:
            print(f"  ERROR syncing {date_str}: {exc}")

        if i < total - 1:
            time.sleep(1)

    print(f"\nSync complete: {success_count}/{total} days synced")


if __name__ == "__main__":
    main()
