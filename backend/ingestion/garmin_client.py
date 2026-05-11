import logging
import os
import pickle
from datetime import date
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError

logger = logging.getLogger(__name__)

_SESSION_DIR = os.environ.get("GARMIN_SESSION_DIR", "")
if _SESSION_DIR:
    _SESSION_PATH = Path(_SESSION_DIR) / ".garmin_session.pkl"
else:
    _SESSION_PATH = Path(__file__).resolve().parent / ".garmin_session.pkl"


class GarminClient:
    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self.client: Garmin | None = None

    def connect(self) -> None:
        if _SESSION_PATH.exists():
            print("Loading cached session...")
            try:
                with open(_SESSION_PATH, "rb") as f:
                    self.client = pickle.load(f)
                # Validate the session is still alive
                self.client.get_full_name()
                print("Cached session valid.")
                return
            except (GarminConnectAuthenticationError, Exception):
                print("Cached session expired, re-authenticating...")

        print("Logging in to Garmin Connect...")
        self.client = Garmin(self.email, self.password)
        self.client.login()
        with open(_SESSION_PATH, "wb") as f:
            pickle.dump(self.client, f)
        print("Login successful.")

    # ── Individual data fetchers ─────────────────────────────────────────

    def get_sleep(self, date_str: str):
        return self.client.get_sleep_data(date_str)

    def get_hrv(self, date_str: str):
        return self.client.get_hrv_data(date_str)

    def get_body_battery(self, date_str: str):
        return self.client.get_body_battery(date_str)

    def get_stress(self, date_str: str):
        return self.client.get_stress_data(date_str)

    def get_activities(self, start: int, limit: int):
        return self.client.get_activities(start, limit)

    def get_stats(self, date_str: str):
        return self.client.get_stats(date_str)

    def get_weight(self, start_date: str, end_date: str):
        return self.client.get_weigh_ins(start_date, end_date)

    def get_training_status(self, date_str: str):
        return self.client.get_training_status(date_str)

    def get_max_metrics(self, date_str: str):
        return self.client.get_max_metrics(date_str)

    # ── Combined daily fetch ─────────────────────────────────────────────

    def fetch_today_recovery(self) -> dict:
        """Fetch today's data and log which recovery signals are available."""
        today_str = date.today().strftime("%Y-%m-%d")
        result = self.fetch_day(today_str)

        recovery_signals = ["sleep", "hrv", "body_battery", "stress"]
        available = [s for s in recovery_signals if result.get(s) is not None]
        missing = [s for s in recovery_signals if s not in available]

        logger.info(
            "today_recovery_fetch date=%s available_signals=%s missing_signals=%s",
            today_str,
            available,
            missing,
        )
        return result

    def fetch_day(self, date_str: str) -> dict:
        result: dict = {"date": date_str}

        fetchers = {
            "sleep": lambda: self.get_sleep(date_str),
            "hrv": lambda: self.get_hrv(date_str),
            "body_battery": lambda: self.get_body_battery(date_str),
            "stress": lambda: self.get_stress(date_str),
            "stats": lambda: self.get_stats(date_str),
            "training_status": lambda: self.get_training_status(date_str),
            "max_metrics": lambda: self.get_max_metrics(date_str),
            "activities": lambda: [
                a
                for a in self.get_activities(0, 5)
                if a.get("startTimeLocal", "").startswith(date_str)
            ],
            "weight": lambda: self.get_weight(date_str, date_str),
        }

        for key, fetcher in fetchers.items():
            try:
                result[key] = fetcher()
                print(f"  ✓ {key}")
            except Exception as exc:
                result[key] = None
                print(f"  ✗ {key}: {exc}")

        return result
