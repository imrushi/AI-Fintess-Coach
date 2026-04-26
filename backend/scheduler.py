import asyncio
import logging
from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from agents.orchestrator import orchestrator
from config import settings
from db.model import User, UserProfile, get_session
from db.writer import save_daily_metrics, save_workouts
from ingestion.garmin_client import GarminClient
from ingestion.normaliser import normalise_day

logger = logging.getLogger(__name__)


class NightlyScheduler:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.is_running = False

    def start(self) -> None:
        self.scheduler.add_job(
            self.run_garmin_sync,
            trigger="cron",
            hour=3,
            minute=0,
            id="garmin_sync",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        self.scheduler.add_job(
            self.run_daily_pipeline,
            trigger="cron",
            hour=6,
            minute=0,
            id="daily_pipeline",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        self.scheduler.start()
        self.is_running = True
        logger.info("Scheduler started: Garmin sync at 03:00 UTC, pipeline at 06:00 UTC")

    def stop(self) -> None:
        self.scheduler.shutdown(wait=False)
        self.is_running = False

    async def run_garmin_sync(self) -> None:
        logger.info("Starting nightly Garmin sync")

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

                for i in range(1, 4):
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

            for i in range(1, 30):
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
