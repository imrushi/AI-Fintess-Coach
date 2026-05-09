"""Orchestrator — manages the daily pipeline execution."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

from agents.analysis_agent import AnalysisAgent, AnalysisResult
from agents.planning_agent import PlanningAgent, PlanningResult
from agents.schemas import ReadinessReport
from db.model import Job, TrainingPlanRow, get_session
from db.reader import get_user_profile

from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    user_id: str
    run_date: str
    analysis_result: AnalysisResult | None = None
    planning_result: PlanningResult | None = None
    error: str | None = None
    success: bool = False


class AgentOrchestrator:
    async def run_analysis(
        self, user_id: str, target_date: str | None = None
    ) -> PipelineResult:
        run_date = target_date or str(date.today())
        result = PipelineResult(user_id=user_id, run_date=run_date)
        job_id = str(uuid4())

        # Step 1 — Create job record
        with get_session() as s:
            s.add(Job(id=job_id, user_id=user_id, job_type="analysis", status="running"))

        # Step 2 — Resolve model from profile
        profile = get_user_profile(user_id)
        if profile is None:
            err = f"No profile found for user {user_id}"
            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = err
            result.error = err
            logger.error(err)
            return result

        model_str = profile.get(
            "model_analysis", "openrouter/anthropic/claude-sonnet-4.6"
        )

        # Step 3 — Run Analysis Agent
        try:
            agent = AnalysisAgent(user_id=user_id, model_str=model_str)
            analysis = await agent.run(target_date)
            result.analysis_result = analysis
            result.success = True

            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "done"
                    job.payload = json.dumps(
                        {
                            "score": analysis.report.readiness_score,
                            "gate": analysis.report.training_gate.value,
                        }
                    )

            logger.info(
                "Pipeline complete for %s: score=%d",
                user_id,
                analysis.report.readiness_score,
            )
        except Exception as e:
            result.error = str(e)
            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(e)
            logger.exception("Pipeline failed for %s", user_id)

        return result

    async def run_planning(
        self,
        user_id: str,
        readiness_report: ReadinessReport,
        override_choice: str | None = None,
    ) -> PipelineResult:
        run_date = str(date.today())
        result = PipelineResult(user_id=user_id, run_date=run_date)
        job_id = str(uuid4())

        with get_session() as s:
            s.add(Job(id=job_id, user_id=user_id, job_type="planning", status="running"))

        profile = get_user_profile(user_id)
        if profile is None:
            err = f"No profile found for user {user_id}"
            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = err
            result.error = err
            logger.error(err)
            return result

        model_str = profile.get(
            "model_planning", "openrouter/anthropic/claude-sonnet-4.6"
        )

        try:
            agent = PlanningAgent(user_id=user_id, model_str=model_str)
            planning = await agent.run(readiness_report, override_choice)
            result.planning_result = planning
            result.success = True

            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "done"
                    job.payload = json.dumps({"plan_id": planning.plan_db_id})

            logger.info(
                "Planning complete for %s: plan_id=%s",
                user_id,
                planning.plan_db_id,
            )
        except Exception as e:
            result.error = str(e)
            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(e)
            logger.exception("Planning failed for %s", user_id)

        return result

    async def run_full_pipeline(
        self, user_id: str, override_choice: str | None = None
    ) -> PipelineResult:
        result = await self.run_analysis(user_id)
        if not result.success:
            return result

        report = result.analysis_result.report

        # Check for an existing current plan —
        # if one exists, only patch tomorrow's session (token-efficient).
        # If none exists, generate a fresh 7-day plan.
        import json as _json
        existing_plan_json: str | None = None
        with get_session() as s:
            existing_row = s.execute(
                select(TrainingPlanRow).where(
                    TrainingPlanRow.user_id == user_id,
                    TrainingPlanRow.is_current == True,  # noqa: E712
                )
            ).scalar_one_or_none()
            if existing_row is not None:
                existing_plan_json = existing_row.plan_json

        if existing_plan_json is not None:
            logger.info(
                "Existing plan found for %s — running daily patch (tomorrow only)", user_id
            )
            planning = await self.run_planning_patch(
                user_id, report, existing_plan_json, override_choice
            )
        else:
            logger.info("No existing plan for %s — generating full 7-day plan", user_id)
            planning = await self.run_planning(user_id, report, override_choice)

        result.planning_result = planning.planning_result

        logger.info("Full pipeline complete for %s", user_id)
        return result

    async def run_planning_patch(
        self,
        user_id: str,
        readiness_report: ReadinessReport,
        current_plan_json: str,
        override_choice: str | None = None,
    ) -> PipelineResult:
        run_date = str(date.today())
        result = PipelineResult(user_id=user_id, run_date=run_date)
        job_id = str(uuid4())

        with get_session() as s:
            s.add(Job(id=job_id, user_id=user_id, job_type="planning_patch", status="running"))

        profile = get_user_profile(user_id)
        if profile is None:
            err = f"No profile found for user {user_id}"
            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = err
            result.error = err
            return result

        model_str = profile.get("model_planning", "openrouter/anthropic/claude-sonnet-4.6")

        try:
            agent = PlanningAgent(user_id=user_id, model_str=model_str)
            planning = await agent.run_patch(readiness_report, current_plan_json, override_choice)
            result.planning_result = planning
            result.success = True

            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "done"
                    mode = "patch_no_change" if planning.no_change else "patch"
                    job.payload = json.dumps({"plan_id": planning.plan_db_id, "mode": mode})

            if planning.no_change:
                logger.info("Patch planning no-op for %s — session unchanged, no DB write.", user_id)
            else:
                logger.info("Patch planning complete for %s", user_id)
        except Exception as e:
            result.error = str(e)
            with get_session() as s:
                job = s.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error = str(e)
            logger.exception("Patch planning failed for %s", user_id)

        return result


orchestrator = AgentOrchestrator()
