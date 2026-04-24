import pickle
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError

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

    # ── Combined daily fetch ─────────────────────────────────────────────

    def fetch_day(self, date_str: str) -> dict:
        result: dict = {"date": date_str}

        fetchers = {
            "sleep": lambda: self.get_sleep(date_str),
            "hrv": lambda: self.get_hrv(date_str),
            "body_battery": lambda: self.get_body_battery(date_str),
            "stress": lambda: self.get_stress(date_str),
            "stats": lambda: self.get_stats(date_str),
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
