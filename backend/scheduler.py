import asyncio
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from agents.orchestrator import orchestrator
from config import settings
from db.model import DailyMetric, User, UserProfile, get_session
from db.writer import save_daily_metrics, save_workouts
from ingestion.garmin_client import GarminClient
from ingestion.normaliser import normalise_day

logger = logging.getLogger(__name__)


class NightlyScheduler:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
        self.is_running = False

    def start(self) -> None:
        self.scheduler.add_job(
            self.run_garmin_sync_range,
            trigger="cron",
            hour=5,
            minute=0,
            id="garmin_sync",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        self.scheduler.add_job(
            self.run_garmin_sync_today,
            trigger="cron",
            hour=6,
            minute=30,
            id="garmin_sync_today",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        self.scheduler.add_job(
            self.run_daily_pipeline,
            trigger="cron",
            hour=6,
            minute=45,
            id="daily_pipeline",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        self.scheduler.start()
        self.is_running = True
        logger.info(
            "Scheduler started: Garmin pre-sync at 05:00 IST, "
            "morning sync at 06:30 IST, pipeline at 06:45 IST"
        )

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        self.is_running = False

    async def run_garmin_sync_range(self) -> None:
        """Pull last 3 days including today from Garmin for all users."""
        logger.info("Starting Garmin sync (last 3 days)")

        with get_session() as session:
            users = session.execute(select(User)).scalars().all()
            user_ids = [u.id for u in users]

        for user_id in user_ids:
            try:
                with get_session() as session:
                    profile = session.get(UserProfile, user_id)
                    if profile is None:
                        logger.warning("No profile for user %s — skipping", user_id)
                        continue
                    garmin_email = profile.garmin_email
                    garmin_password = profile.garmin_password

                if not garmin_email:
                    logger.warning("No garmin_email for user %s — skipping", user_id)
                    continue

                client = GarminClient(garmin_email, garmin_password or "")
                client.connect()

                for i in range(0, 3):
                    sync_date = date.today() - timedelta(days=i)
                    date_str = sync_date.strftime("%Y-%m-%d")
                    raw = client.fetch_day(date_str)
                    metrics = normalise_day(raw, user_id)
                    save_daily_metrics(metrics)
                    save_workouts(user_id, sync_date, metrics.workouts_json)
                    await asyncio.sleep(2)

                logger.info("Garmin sync complete for user %s", user_id)

            except Exception as e:
                logger.error("Garmin sync failed for user %s: %s", user_id, e)
                continue

    async def run_garmin_sync_today(self) -> None:
        """Morning catch-up sync — today only, captures sleep data for late risers."""
        logger.info("Morning sync: pulling today's sleep and recovery data")

        with get_session() as session:
            users = session.execute(select(User)).scalars().all()
            user_ids = [u.id for u in users]

        for user_id in user_ids:
            try:
                with get_session() as session:
                    profile = session.get(UserProfile, user_id)
                    if profile is None:
                        logger.warning("No profile for user %s — skipping", user_id)
                        continue
                    garmin_email = profile.garmin_email
                    garmin_password = profile.garmin_password

                if not garmin_email:
                    logger.warning("No garmin_email for user %s — skipping", user_id)
                    continue

                client = GarminClient(garmin_email, garmin_password or "")
                client.connect()

                today_str = date.today().strftime("%Y-%m-%d")
                raw = client.fetch_day(today_str)
                metrics = normalise_day(raw, user_id)
                save_daily_metrics(metrics)
                save_workouts(user_id, date.today(), metrics.workouts_json)

                logger.info("Morning sync complete for user %s", user_id)

            except Exception as e:
                logger.error("Morning sync failed for user %s: %s", user_id, e)
                continue

    async def run_daily_pipeline(self) -> None:
        logger.info("Starting daily analysis + planning pipeline")

        with get_session() as session:
            users = session.execute(select(User)).scalars().all()
            user_ids = [u.id for u in users]

        for user_id in user_ids:
            try:
                result = await orchestrator.run_full_pipeline(user_id)
                if result.success:
                    score = result.analysis_result.report.readiness_score
                    logger.info("Pipeline complete for %s: score=%s", user_id, score)
                else:
                    logger.error("Pipeline failed for %s: %s", user_id, result.error)
            except Exception as e:
                logger.error("Pipeline exception for %s: %s", user_id, e)

    def get_todays_sleep_available(self, user_id: str) -> bool:
        """Return True if today's sleep_score has been synced for this user."""
        with get_session() as session:
            row = session.execute(
                select(DailyMetric.sleep_score).where(
                    DailyMetric.user_id == user_id,
                    DailyMetric.date == date.today(),
                )
            ).scalar_one_or_none()
        return row is not None

    def get_status(self) -> dict:
        return {
            "is_running": self.is_running,
            "jobs": [
                {
                    "id": job.id,
                    "next_run": str(job.next_run_time) if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
                for job in self.scheduler.get_jobs()
            ],
        }

    async def sync_single_user(self, user_id: str) -> None:
        logger.info("Manual Garmin sync triggered for user %s", user_id)
        try:
            with get_session() as session:
                profile = session.get(UserProfile, user_id)
                if profile is None:
                    logger.warning("No profile for user %s — skipping", user_id)
                    return
                garmin_email = profile.garmin_email
                garmin_password = profile.garmin_password

            if not garmin_email:
                logger.warning("No garmin_email for user %s — skipping", user_id)
                return

            client = GarminClient(garmin_email, garmin_password or "")
            client.connect()

            for i in range(0, 4):
                sync_date = date.today() - timedelta(days=i)
                date_str = sync_date.strftime("%Y-%m-%d")
                raw = client.fetch_day(date_str)
                metrics = normalise_day(raw, user_id)
                save_daily_metrics(metrics)
                save_workouts(user_id, sync_date, metrics.workouts_json)
                await asyncio.sleep(2)

            logger.info("Garmin sync complete for user %s", user_id)
        except Exception as e:
            logger.error("Garmin sync failed for user %s: %s", user_id, e)

    async def pipeline_single_user(self, user_id: str) -> None:
        logger.info("Manual pipeline triggered for user %s", user_id)
        try:
            result = await orchestrator.run_full_pipeline(user_id)
            if result.success:
                score = result.analysis_result.report.readiness_score
                logger.info("Pipeline complete for %s: score=%s", user_id, score)
            else:
                logger.error("Pipeline failed for %s: %s", user_id, result.error)
        except Exception as e:
            logger.error("Pipeline exception for %s: %s", user_id, e)


nightly_scheduler = NightlyScheduler()

