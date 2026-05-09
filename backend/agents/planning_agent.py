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
from agents.plan_prompt_builder import build_daily_patch_prompt, build_planning_prompt
from agents.plan_schemas import TrainingPlan, TrainingSession
from agents.schemas import ReadinessReport, TrainingGate, TrainingGate
from config import settings
from db.cost_logger import log_agent_run
from db.model import TrainingPlanRow, get_session

from sqlalchemy import delete, select, update

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
    no_change: bool = False  # True when patch was skipped (session unchanged)


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

    async def run_patch(
        self,
        readiness_report: ReadinessReport,
        current_plan_json: str,
        override_choice: str | None = None,
    ) -> PlanningResult:
        """Update only tomorrow's session in the existing plan. Much cheaper than a full run."""
        current_plan_dict = json.loads(current_plan_json)

        # Pre-check: if gate == PROCEED with no override and tomorrow already has a session,
        # the plan is fine as-is — skip LLM entirely (zero token cost).
        tomorrow_str_pre = str(date.today() + timedelta(days=1))
        existing_tomorrow = next(
            (s for s in current_plan_dict.get("sessions", []) if s.get("date") == tomorrow_str_pre),
            None,
        )
        if (
            readiness_report.training_gate == TrainingGate.PROCEED
            and override_choice is None
            and existing_tomorrow is not None
        ):
            logger.info(
                "Patch skipped for %s — gate=PROCEED, no override, tomorrow session exists (%s). Zero tokens used.",
                self.user_id, tomorrow_str_pre,
            )
            existing_plan = TrainingPlan.model_validate(current_plan_dict)
            return PlanningResult(
                plan=existing_plan,
                plan_db_id=current_plan_dict.get("plan_id", ""),
                model_used=self.model_str,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=0,
                compression_ratio=0.0,
                attempt_count=0,
                no_change=True,
            )

        # Step 1 — Build patch prompt
        pkg = build_daily_patch_prompt(
            self.user_id, readiness_report, current_plan_dict, override_choice
        )
        logger.info(
            "Patch prompt ready: ~%d tokens (vs full plan ~400+)", pkg.token_estimate
        )

        # Step 2 — Call model
        ctx = self.ctx_repo.load_latest(self.user_id, "planning")
        system = pkg.system_prompt
        if ctx:
            system = ctx.to_system_injection() + "\n\n" + system

        messages = [{"role": "user", "content": pkg.compressed_user_prompt}]
        response = None
        session_dict: dict | None = None

        for attempt in range(1, self.max_retries + 1):
            response = await self.client.complete(
                messages=messages,
                system=system,
                json_mode=True,
            )
            try:
                # Parse as a single TrainingSession (or no_change signal)
                raw = json.loads(response.content)
                if raw.get("no_change") is True:
                    logger.info(
                        "LLM signalled no_change for %s tomorrow=%s — skipping DB write.",
                        self.user_id, pkg.tomorrow,
                    )
                    log_agent_run(self.user_id, "planning_patch", response)
                    existing_plan = TrainingPlan.model_validate(current_plan_dict)
                    return PlanningResult(
                        plan=existing_plan,
                        plan_db_id=current_plan_dict.get("plan_id", ""),
                        model_used=self.model_str,
                        prompt_tokens=response.prompt_tokens,
                        completion_tokens=response.completion_tokens,
                        latency_ms=response.latency_ms,
                        compression_ratio=pkg.compression_ratio,
                        attempt_count=attempt,
                        no_change=True,
                    )
                session_obj = TrainingSession.model_validate(raw)
                session_dict = session_obj.model_dump()
                break
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning("Patch attempt %d failed: %s", attempt, e)
                if attempt >= self.max_retries:
                    raise
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Invalid JSON or schema error: {e}. "
                        f"Output ONLY the single TrainingSession JSON object, or {{\"no_change\": true}} if unchanged."
                    ),
                })

        assert response is not None and session_dict is not None

        # Step 3 — Splice updated session into existing plan
        sessions = current_plan_dict.get("sessions", [])
        tomorrow_str = pkg.tomorrow
        updated = False
        for i, s in enumerate(sessions):
            if s.get("date") == tomorrow_str:
                sessions[i] = session_dict
                updated = True
                break
        if not updated:
            sessions.append(session_dict)
            sessions.sort(key=lambda s: s.get("date", ""))

        current_plan_dict["sessions"] = sessions

        # Re-validate the full plan so it round-trips cleanly
        updated_plan = TrainingPlan.model_validate(current_plan_dict)
        updated_plan.user_id = self.user_id
        from uuid import uuid4
        new_plan_id = str(uuid4())
        updated_plan.plan_id = new_plan_id
        from datetime import datetime
        updated_plan.generated_at = datetime.utcnow().isoformat()

        # Step 4 — Persist (retire old, delete old, insert updated)
        with get_session() as db:
            db.execute(
                update(TrainingPlanRow)
                .where(
                    TrainingPlanRow.user_id == self.user_id,
                    TrainingPlanRow.is_current == True,  # noqa: E712
                )
                .values(is_current=False)
            )
            db.execute(
                delete(TrainingPlanRow).where(
                    TrainingPlanRow.user_id == self.user_id,
                    TrainingPlanRow.valid_from == date.fromisoformat(updated_plan.valid_from),
                )
            )
            db.add(
                TrainingPlanRow(
                    id=new_plan_id,
                    user_id=self.user_id,
                    valid_from=date.fromisoformat(updated_plan.valid_from),
                    valid_to=date.fromisoformat(updated_plan.valid_to),
                    plan_json=updated_plan.model_dump_json(),
                    readiness_score=readiness_report.readiness_score,
                    training_gate=readiness_report.training_gate.value,
                    override_applied=override_choice,
                    model_used=self.model_str,
                    tokens_in=response.prompt_tokens,
                    tokens_out=response.completion_tokens,
                    is_current=True,
                )
            )

        # Step 5 — Log cost
        log_agent_run(self.user_id, "planning_patch", response)

        logger.info(
            "Patch complete for %s: updated session %s, tokens_in=%d tokens_out=%d",
            self.user_id, tomorrow_str, response.prompt_tokens, response.completion_tokens,
        )

        return PlanningResult(
            plan=updated_plan,
            plan_db_id=new_plan_id,
            model_used=self.model_str,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            compression_ratio=pkg.compression_ratio,
            attempt_count=1,
        )
