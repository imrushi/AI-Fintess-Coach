"""Analysis Agent — produces a daily ReadinessReport from wearable data."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from agents.caveman import compress
from agents.context import AgentContextRepository, ConversationContext
from agents.model_router import get_model_client
from agents.prompt_builder import build_analysis_prompt
from agents.schemas import ReadinessReport
from config import settings
from db.cost_logger import log_agent_run
from db.model import ReadinessReportRow, get_session
from db.reader import get_user_profile, get_weeks_to_goal

from sqlalchemy import select

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    report: ReadinessReport
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    compression_ratio: float
    attempt_count: int


class AnalysisAgent:
    def __init__(self, user_id: str, model_str: str) -> None:
        self.user_id = user_id
        self.model_str = model_str
        self.client = get_model_client(model_str)
        self.ctx_repo = AgentContextRepository()
        self.max_retries = settings.MAX_RETRIES

    async def run(self, target_date: str | None = None) -> AnalysisResult:
        if target_date is None:
            target_date = str(date.today())

        # Step 1 — Load context injection
        ctx = self.ctx_repo.load_latest(self.user_id, "analysis")
        context_injection = ctx.to_system_injection() if ctx else None

        # Step 2 — Build prompt
        pkg = build_analysis_prompt(self.user_id, target_date, context_injection)
        logger.info(
            "Analysis prompt ready: ~%d tokens, compression=%.1f%%",
            pkg.token_estimate,
            pkg.compression_ratio * 100,
        )

        # Step 3 — Call model with retry loop
        messages = [{"role": "user", "content": pkg.compressed_user_prompt}]
        report: ReadinessReport | None = None
        response = None
        attempt = 0

        for attempt in range(1, self.max_retries + 2):
            response = await self.client.complete(
                messages=messages,
                system=pkg.system_prompt,
                json_mode=True,
            )
            try:
                report = ReadinessReport.from_llm_response(response.content)
                logger.info(
                    "Analysis complete: score=%d gate=%s",
                    report.readiness_score,
                    report.training_gate.value,
                )
                break
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning("Attempt %d failed: %s", attempt, e)
                if attempt == self.max_retries + 1:
                    raise
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your response was not valid JSON or failed schema validation: {e}. "
                            f"Output ONLY the JSON object, nothing else."
                        ),
                    }
                )

        assert report is not None and response is not None

        # Step 4 — Persist to DB (upsert: reuse existing row ID if present)
        report_date_obj = date.fromisoformat(target_date)
        with get_session() as session:
            existing = session.execute(
                select(ReadinessReportRow).where(
                    ReadinessReportRow.user_id == self.user_id,
                    ReadinessReportRow.report_date == report_date_obj,
                )
            ).scalar_one_or_none()
            row_id = existing.id if existing else str(uuid4())
            session.merge(
                ReadinessReportRow(
                    id=row_id,
                    user_id=self.user_id,
                    report_date=report_date_obj,
                    readiness_score=report.readiness_score,
                    readiness_label=report.readiness_label.value,
                    training_gate=report.training_gate.value,
                    report_json=report.model_dump_json(),
                    model_used=self.model_str,
                    tokens_in=response.prompt_tokens,
                    tokens_out=response.completion_tokens,
                )
            )

        # Step 5 — Update ConversationContext
        new_ctx = ConversationContext(
            agent_type="analysis",
            user_id=self.user_id,
            date_range=f"last 14d ending {target_date}",
            compressed_summary=compress(
                f"date:{target_date} score:{report.readiness_score} "
                f"gate:{report.training_gate.value} flags:{','.join(report.flags)} "
                f"narrative:{report.narrative[:100]}"
            )[0],
            pinned_facts=self._get_pinned_facts(),
            recent_readiness_scores=self._get_recent_scores(),
            last_training_gate=report.training_gate.value,
            model_used=self.model_str,
            total_tokens_used=response.total_tokens,
        )
        self.ctx_repo.save(new_ctx)

        # Step 6 — Log cost
        log_agent_run(self.user_id, "analysis", response)

        # Step 7 — Return
        return AnalysisResult(
            report=report,
            model_used=self.model_str,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            compression_ratio=pkg.compression_ratio,
            attempt_count=attempt,
        )

    def _get_pinned_facts(self) -> dict:
        profile = get_user_profile(self.user_id) or {}
        return {
            "goal_event": profile.get("goal_event"),
            "goal_date": str(profile.get("goal_date")) if profile.get("goal_date") else None,
            "medical_conditions": profile.get("medical_conditions"),
            "weeks_to_goal": get_weeks_to_goal(self.user_id),
        }

    def _get_recent_scores(self) -> list[int]:
        with get_session() as session:
            rows = (
                session.execute(
                    select(ReadinessReportRow.readiness_score)
                    .where(ReadinessReportRow.user_id == self.user_id)
                    .order_by(ReadinessReportRow.report_date.desc())
                    .limit(7)
                )
                .scalars()
                .all()
            )
        return list(reversed(rows))
