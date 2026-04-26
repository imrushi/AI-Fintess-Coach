"""Planning Agent — produces a 7-day TrainingPlan from readiness data."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import uuid4

from agents.caveman import compress
from agents.context import AgentContextRepository, ConversationContext
from agents.model_router import get_model_client
from agents.plan_prompt_builder import build_planning_prompt
from agents.plan_schemas import TrainingPlan
from agents.schemas import ReadinessReport
from config import settings
from db.cost_logger import log_agent_run
from db.model import TrainingPlanRow, get_session

from sqlalchemy import delete, update

logger = logging.getLogger(__name__)


@dataclass
class PlanningResult:
    plan: TrainingPlan
    plan_db_id: str
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    compression_ratio: float
    attempt_count: int


class PlanningAgent:
    def __init__(self, user_id: str, model_str: str) -> None:
        self.user_id = user_id
        self.model_str = model_str
        self.client = get_model_client(model_str)
        self.ctx_repo = AgentContextRepository()
        self.max_retries = settings.MAX_RETRIES

    async def run(
        self,
        readiness_report: ReadinessReport,
        override_choice: str | None = None,
    ) -> PlanningResult:
        # Step 1 — Load context injection
        ctx = self.ctx_repo.load_latest(self.user_id, "planning")
        context_injection = ctx.to_system_injection() if ctx else None

        # Step 2 — Build prompt
        pkg = build_planning_prompt(self.user_id, readiness_report, override_choice)
        logger.info(
            "Planning prompt ready: ~%d tokens, compression=%.1f%%",
            pkg.token_estimate,
            pkg.compression_ratio * 100,
        )

        # Step 3 — Call model with retry loop
        system = pkg.system_prompt
        if context_injection:
            system = context_injection + "\n\n" + system

        messages = [{"role": "user", "content": pkg.compressed_user_prompt}]
        plan: TrainingPlan | None = None
        response = None
        attempt = 0

        for attempt in range(1, self.max_retries + 1):
            response = await self.client.complete(
                messages=messages,
                system=system,
                json_mode=True,
            )
            try:
                plan = TrainingPlan.from_llm_response(response.content)

                # Inject user_id in case model forgot it
                plan.user_id = self.user_id
                plan.plan_id = str(uuid4())
                plan.generated_at = datetime.utcnow().isoformat()

                logger.info(
                    "Plan generated: %d sessions, gate=%s",
                    len(plan.sessions),
                    readiness_report.training_gate.value,
                )
                break
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning("Planning attempt %d failed: %s", attempt, e)
                if attempt >= self.max_retries:
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

        assert plan is not None and response is not None

        # Step 4 — Persist to DB (upsert: delete old row for same date, then insert)
        with get_session() as session:
            session.execute(
                update(TrainingPlanRow)
                .where(
                    TrainingPlanRow.user_id == self.user_id,
                    TrainingPlanRow.is_current == True,  # noqa: E712
                )
                .values(is_current=False)
            )
            session.execute(
                delete(TrainingPlanRow).where(
                    TrainingPlanRow.user_id == self.user_id,
                    TrainingPlanRow.valid_from == date.fromisoformat(plan.valid_from),
                )
            )
            session.add(
                TrainingPlanRow(
                    id=plan.plan_id,
                    user_id=self.user_id,
                    valid_from=date.fromisoformat(plan.valid_from),
                    valid_to=date.fromisoformat(plan.valid_to),
                    plan_json=plan.model_dump_json(),
                    readiness_score=readiness_report.readiness_score,
                    training_gate=readiness_report.training_gate.value,
                    override_applied=override_choice,
                    model_used=self.model_str,
                    tokens_in=response.prompt_tokens,
                    tokens_out=response.completion_tokens,
                    is_current=True,
                )
            )

        # Step 5 — Update ConversationContext
        summary_text, _ = compress(
            f"plan:{plan.valid_from}to{plan.valid_to} "
            f"gate:{readiness_report.training_gate.value} "
            f"sessions:{len(plan.sessions)} "
            f"rationale:{plan.plan_rationale[:80]}"
        )
        new_ctx = ConversationContext(
            agent_type="planning",
            user_id=self.user_id,
            date_range=f"{plan.valid_from} to {plan.valid_to}",
            compressed_summary=summary_text,
            pinned_facts=self._get_pinned_facts(readiness_report),
            recent_readiness_scores=[readiness_report.readiness_score],
            last_training_gate=readiness_report.training_gate.value,
            model_used=self.model_str,
            total_tokens_used=response.total_tokens,
        )
        self.ctx_repo.save(new_ctx)

        # Step 6 — Log cost
        log_agent_run(self.user_id, "planning", response)

        # Step 7 — Return
        return PlanningResult(
            plan=plan,
            plan_db_id=plan.plan_id,
            model_used=self.model_str,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            compression_ratio=pkg.compression_ratio,
            attempt_count=attempt,
        )

    @staticmethod
    def _get_pinned_facts(readiness_report: ReadinessReport) -> dict:
        return {
            "readiness_score": readiness_report.readiness_score,
            "training_gate": readiness_report.training_gate.value,
            "flags": readiness_report.flags,
        }
