import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select

from agents.orchestrator import orchestrator
from agents.plan_schemas import CheckInRequest
from agents.schemas import ReadinessReport
from config import settings
from db.cost_logger import get_cost_summary
from db.feedback_writer import get_todays_override, save_check_in
from db.model import (
    AgentContext,
    AgentRun,
    Base,
    DailyMetric,
    Job,
    ReadinessReportRow,
    TrainingPlanRow,
    UserFeedback,
    UserProfile,
    Workout,
    get_engine,
    get_session,
)
from scheduler import nightly_scheduler

logger = logging.getLogger(__name__)

# ── Lifespan ─────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    Base.metadata.create_all(get_engine())
    nightly_scheduler.start()
    logger.info("Application started")
    yield
    nightly_scheduler.stop()
    logger.info("Application stopped")


# ── App ──────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Fitness Coach API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────────────────

_VALID_DIETS = {"omnivore", "vegetarian", "vegan", "vegan-junk"}


def _profile_to_dict(p: UserProfile) -> dict:
    return {
        "user_id": p.user_id,
        "display_name": p.display_name,
        "goal_event": p.goal_event,
        "goal_date": str(p.goal_date) if p.goal_date else None,
        "fitness_level": p.fitness_level,
        "medical_conditions": p.medical_conditions,
        "dietary_preference": p.dietary_preference,
        "dietary_allergies": p.dietary_allergies,
        "max_weekly_hours": p.max_weekly_hours,
        "garmin_email": p.garmin_email,
        "swim_equipment": p.swim_equipment,
        "swim_strokes": p.swim_strokes,
        "date_of_birth": str(p.date_of_birth) if p.date_of_birth else None,
        "lthr": p.lthr,
        "model_analysis": p.model_analysis,
        "model_planning": p.model_planning,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Request / Response Models ────────────────────────────────────────────


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    goal_event: str | None = None
    goal_date: date | None = None
    fitness_level: str | None = None
    medical_conditions: list[str] | str | None = None
    dietary_preference: str | None = None
    dietary_allergies: str | None = None
    max_weekly_hours: float | None = None
    garmin_email: str | None = None
    garmin_password: str | None = None
    swim_equipment: str | None = None  # e.g. "pull_buoy,paddles"
    swim_strokes: str | None = None    # e.g. "freestyle:expert,breaststroke:expert,backstroke:beginner,butterfly:learning"
    date_of_birth: date | None = None
    lthr: int | None = None            # Lactate Threshold HR in bpm

    @field_validator("goal_date")
    @classmethod
    def goal_date_in_future(cls, v: date | None) -> date | None:
        if v is not None and v <= date.today():
            raise ValueError("goal_date must be in the future")
        return v

    @field_validator("dietary_preference")
    @classmethod
    def valid_diet(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalised = v.lower()
        if normalised not in _VALID_DIETS:
            raise ValueError(f"dietary_preference must be one of {_VALID_DIETS}")
        return normalised


class RunAnalysisRequest(BaseModel):
    user_id: str
    target_date: str | None = None


class RunAnalysisResponse(BaseModel):
    success: bool
    report_date: str
    readiness_score: int | None = None
    readiness_label: str | None = None
    training_gate: str | None = None
    narrative: str | None = None
    flags: list[str] = []
    tokens_used: int | None = None
    latency_ms: int | None = None
    error: str | None = None


class ModelConfigRequest(BaseModel):
    model_analysis: str
    model_planning: str

    @field_validator("model_analysis", "model_planning")
    @classmethod
    def valid_prefix(cls, v: str) -> str:
        if not (v.startswith("openrouter/") or v.startswith("ollama/")):
            raise ValueError("Model must start with 'openrouter/' or 'ollama/'")
        return v


class RunPipelineRequest(BaseModel):
    user_id: str
    override_choice: str | None = None


class RunPipelineResponse(BaseModel):
    success: bool
    readiness_score: int | None = None
    training_gate: str | None = None
    plan_valid_from: str | None = None
    plan_valid_to: str | None = None
    session_count: int | None = None
    total_tokens_used: int | None = None
    error: str | None = None


# ── Routes ───────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/scheduler/status")
def scheduler_status():
    return nightly_scheduler.get_status()


class SchedulerTriggerRequest(BaseModel):
    user_id: str


@app.post("/api/scheduler/trigger/sync")
async def trigger_sync(body: SchedulerTriggerRequest):
    asyncio.create_task(nightly_scheduler.sync_single_user(body.user_id))
    return {"triggered": True, "message": "Sync started in background"}


@app.post("/api/scheduler/trigger/pipeline")
async def trigger_pipeline(body: SchedulerTriggerRequest):
    asyncio.create_task(nightly_scheduler.pipeline_single_user(body.user_id))
    return {"triggered": True}


@app.get("/api/profile/{user_id}")
def get_profile(user_id: str):
    with get_session() as session:
        profile = session.get(UserProfile, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return _profile_to_dict(profile)


@app.put("/api/profile/{user_id}")
def update_profile(user_id: str, body: UpdateProfileRequest):
    with get_session() as session:
        profile = session.get(UserProfile, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        updates = body.model_dump(exclude_unset=True)
        for field, value in updates.items():
            # Coerce list → comma-separated string for DB text columns
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            setattr(profile, field, value)
        profile.updated_at = datetime.now(timezone.utc)
        session.flush()
        return _profile_to_dict(profile)


@app.get("/api/profile/{user_id}/model-config")
def get_model_config(user_id: str):
    with get_session() as session:
        profile = session.get(UserProfile, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {
            "model_analysis": profile.model_analysis,
            "model_planning": profile.model_planning,
        }


@app.put("/api/profile/{user_id}/model-config")
def update_model_config(user_id: str, body: ModelConfigRequest):
    with get_session() as session:
        profile = session.get(UserProfile, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        changed = (
            profile.model_analysis != body.model_analysis
            or profile.model_planning != body.model_planning
        )
        profile.model_analysis = body.model_analysis
        profile.model_planning = body.model_planning
        profile.updated_at = datetime.now(timezone.utc)
        return {"updated": True, "context_transfer_required": changed}


@app.get("/api/costs/{user_id}")
def get_costs(user_id: str):
    return get_cost_summary(user_id, days=7)


# ── Analysis Endpoints ───────────────────────────────────────────────────


@app.post("/api/analysis/run")
async def run_analysis(body: RunAnalysisRequest):
    result = await orchestrator.run_analysis(body.user_id, body.target_date)
    if not result.success or result.analysis_result is None:
        return RunAnalysisResponse(
            success=False,
            report_date=result.run_date,
            error=result.error or "Unknown error",
        )
    ar = result.analysis_result
    return RunAnalysisResponse(
        success=True,
        report_date=result.run_date,
        readiness_score=ar.report.readiness_score,
        readiness_label=ar.report.readiness_label.value,
        training_gate=ar.report.training_gate.value,
        narrative=ar.report.narrative,
        flags=ar.report.flags,
        tokens_used=ar.prompt_tokens + ar.completion_tokens,
        latency_ms=ar.latency_ms,
    )


@app.get("/api/analysis/report/{user_id}")
async def get_analysis_report(
    user_id: str,
    report_date: str = Query(default=None),
):
    rd = report_date or str(date.today())
    with get_session() as session:
        row = session.execute(
            select(ReadinessReportRow).where(
                ReadinessReportRow.user_id == user_id,
                ReadinessReportRow.report_date == date.fromisoformat(rd),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No report found for this date")
        return {
            **json.loads(row.report_json),
            "model_used": row.model_used,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
        }


@app.get("/api/analysis/history/{user_id}")
async def get_analysis_history(
    user_id: str,
    days: int = Query(default=14, ge=1, le=365),
):
    cutoff = date.today() - timedelta(days=days)
    with get_session() as session:
        rows = (
            session.execute(
                select(ReadinessReportRow)
                .where(
                    ReadinessReportRow.user_id == user_id,
                    ReadinessReportRow.report_date >= cutoff,
                )
                .order_by(ReadinessReportRow.report_date.desc())
            )
            .scalars()
            .all()
        )
        return [
            {
                "report_date": str(r.report_date),
                "readiness_score": r.readiness_score,
                "readiness_label": r.readiness_label,
                "training_gate": r.training_gate,
                "flags": json.loads(r.report_json).get("flags", []),
            }
            for r in rows
        ]


# ── Pipeline Endpoint ─────────────────────────────────────────────────────


@app.post("/api/pipeline/run")
async def run_pipeline(body: RunPipelineRequest):
    result = await orchestrator.run_full_pipeline(body.user_id, body.override_choice)
    if not result.success or result.analysis_result is None:
        return RunPipelineResponse(
            success=False,
            error=result.error or "Unknown error",
        )
    ar = result.analysis_result
    pr = result.planning_result
    total_tokens = ar.prompt_tokens + ar.completion_tokens
    resp = RunPipelineResponse(
        success=True,
        readiness_score=ar.report.readiness_score,
        training_gate=ar.report.training_gate.value,
    )
    if pr is not None:
        total_tokens += pr.prompt_tokens + pr.completion_tokens
        resp.plan_valid_from = pr.plan.valid_from
        resp.plan_valid_to = pr.plan.valid_to
        resp.session_count = len(pr.plan.sessions)
    resp.total_tokens_used = total_tokens
    return resp


# ── Plan Endpoints ────────────────────────────────────────────────────────


@app.get("/api/plans/current/{user_id}")
def get_current_plan(user_id: str):
    with get_session() as session:
        row = session.execute(
            select(TrainingPlanRow).where(
                TrainingPlanRow.user_id == user_id,
                TrainingPlanRow.is_current == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No current plan found")
        plan = json.loads(row.plan_json)
        return {
            **plan,
            "_meta": {
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
                "model_used": row.model_used,
                "tokens_in": row.tokens_in,
                "tokens_out": row.tokens_out,
            },
        }


@app.get("/api/plans/{user_id}/session/{session_date}")
def get_plan_session(user_id: str, session_date: str):
    with get_session() as session:
        row = session.execute(
            select(TrainingPlanRow).where(
                TrainingPlanRow.user_id == user_id,
                TrainingPlanRow.is_current == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="No current plan found")
        plan = json.loads(row.plan_json)
        for sess in plan.get("sessions", []):
            if sess.get("date") == session_date:
                return sess
        raise HTTPException(status_code=404, detail=f"No session found for {session_date}")


@app.get("/api/plans/history/{user_id}")
def get_plan_history(
    user_id: str,
    limit: int = Query(default=5, ge=1, le=50),
):
    with get_session() as session:
        rows = (
            session.execute(
                select(TrainingPlanRow)
                .where(TrainingPlanRow.user_id == user_id)
                .order_by(TrainingPlanRow.valid_from.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [
            {
                "plan_id": r.id,
                "valid_from": str(r.valid_from),
                "valid_to": str(r.valid_to),
                "training_gate": r.training_gate,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            }
            for r in rows
        ]


# ── Check-in Endpoints ────────────────────────────────────────────────────


@app.post("/api/checkin")
async def submit_checkin(body: CheckInRequest):
    fb_id = save_check_in(
        user_id=body.user_id,
        check_in_date=body.check_in_date,
        perceived_effort=body.perceived_effort,
        mood=body.mood,
        free_text=body.free_text,
        override_choice=body.override_choice,
        override_reason=body.override_reason,
    )

    plan_updated = False
    if body.override_choice is not None:
        with get_session() as session:
            report_row = session.execute(
                select(ReadinessReportRow)
                .where(ReadinessReportRow.user_id == body.user_id)
                .order_by(ReadinessReportRow.report_date.desc())
                .limit(1)
            ).scalar_one_or_none()
            report_json = report_row.report_json if report_row is not None else None

        if report_json is not None:
            report = ReadinessReport.model_validate_json(report_json)
            if report.training_gate.value in ("REST_RECOMMENDED", "MANDATORY_REST"):
                await orchestrator.run_planning(
                    body.user_id,
                    report,
                    override_choice=body.override_choice,
                )
                plan_updated = True

    msg = "Plan updated based on your decision." if plan_updated else "Check-in saved."
    return {
        "saved": True,
        "feedback_id": fb_id,
        "override_applied": body.override_choice,
        "plan_updated": plan_updated,
        "message": msg,
    }


@app.get("/api/checkin/today/{user_id}")
def get_today_checkin(user_id: str):
    with get_session() as session:
        row = session.execute(
            select(UserFeedback).where(
                UserFeedback.user_id == user_id,
                UserFeedback.feedback_date == date.today(),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "id": row.id,
            "feedback_date": str(row.feedback_date),
            "perceived_effort": row.perceived_effort,
            "mood": row.mood,
            "free_text": row.free_text,
            "override_choice": row.override_choice,
            "override_reason": row.override_reason,
        }


# ── Override Prompt Endpoint ──────────────────────────────────────────────


@app.get("/api/plans/override-prompt/{user_id}")
def get_override_prompt(user_id: str):
    with get_session() as session:
        report_row = session.execute(
            select(ReadinessReportRow)
            .where(ReadinessReportRow.user_id == user_id)
            .order_by(ReadinessReportRow.report_date.desc())
            .limit(1)
        ).scalar_one_or_none()

        if report_row is None:
            return {
                "show_prompt": False,
                "training_gate": None,
                "readiness_score": None,
                "narrative": None,
                "already_decided": False,
                "decision": None,
            }

        report = json.loads(report_row.report_json)
        gate = report_row.training_gate
        readiness_score = report_row.readiness_score

    show = gate in ("REST_RECOMMENDED", "MANDATORY_REST")
    decision = get_todays_override(user_id)
    already_decided = decision is not None

    return {
        "show_prompt": show,
        "training_gate": gate,
        "readiness_score": readiness_score,
        "narrative": report.get("narrative"),
        "already_decided": already_decided,
        "decision": decision,
    }


# ── Metrics Endpoint ──────────────────────────────────────────────────────


def _avg(values: list) -> float | None:
    filtered = [v for v in values if v is not None]
    return sum(filtered) / len(filtered) if filtered else None


def compute_trend(values: list[float | None]) -> str:
    filtered = [v for v in values if v is not None]
    if len(filtered) < 4:
        return "insufficient_data"
    mid = len(filtered) // 2
    first_avg = sum(filtered[:mid]) / mid
    second_half = filtered[mid:]
    second_avg = sum(second_half) / len(second_half)
    if second_avg > first_avg * 1.03:
        return "improving"
    if second_avg < first_avg * 0.97:
        return "declining"
    return "stable"


@app.get("/api/metrics/kpi/{user_id}")
def get_kpi_metrics(
    user_id: str,
    days: int = Query(default=14, ge=1, le=365),
):
    cutoff = date.today() - timedelta(days=days - 1)
    cutoff_4w = date.today() - timedelta(weeks=4)

    with get_session() as session:
        metric_rows = (
            session.execute(
                select(DailyMetric)
                .where(
                    DailyMetric.user_id == user_id,
                    DailyMetric.date >= cutoff,
                )
                .order_by(DailyMetric.date.asc())
            )
            .scalars()
            .all()
        )
        report_rows = (
            session.execute(
                select(ReadinessReportRow)
                .where(
                    ReadinessReportRow.user_id == user_id,
                    ReadinessReportRow.report_date >= cutoff,
                )
                .order_by(ReadinessReportRow.report_date.asc())
            )
            .scalars()
            .all()
        )
        workout_rows = (
            session.execute(
                select(Workout)
                .where(
                    Workout.user_id == user_id,
                    Workout.date >= cutoff_4w,
                )
                .order_by(Workout.date.asc())
            )
            .scalars()
            .all()
        )

        # Eagerly copy all values out before session closes
        metrics_by_date: dict[str, dict] = {
            str(r.date): {
                "hrv_last_night_ms": r.hrv_last_night_ms,
                "sleep_score": r.sleep_score,
                "body_battery_max": r.body_battery_max,
                "acwr": r.acwr,
                "avg_resting_hr": r.avg_resting_hr,
                "total_steps": r.total_steps,
                "active_calories": r.active_calories,
            }
            for r in metric_rows
        }
        readiness_by_date: dict[str, int] = {
            str(r.report_date): r.readiness_score for r in report_rows
        }
        workouts_raw = [
            {
                "date": str(w.date),
                "sport": w.sport,
                "duration_min": w.duration_min,
                "distance_m": w.distance_m,
                "avg_hr": w.avg_hr,
            }
            for w in workout_rows
        ]

    # ── Build parallel arrays ─────────────────────────────────────────
    dates_out: list[str] = []
    readiness_scores: list[int | None] = []
    hrv_ms: list[float | None] = []
    sleep_scores: list[float | None] = []
    body_battery_max: list[int | None] = []
    acwr: list[float | None] = []
    resting_hr: list[int | None] = []
    total_steps: list[int | None] = []
    active_calories: list[int | None] = []

    for offset in range(days):
        d = cutoff + timedelta(days=offset)
        ds = str(d)
        m = metrics_by_date.get(ds)
        dates_out.append(ds)
        readiness_scores.append(readiness_by_date.get(ds))
        hrv_ms.append(m["hrv_last_night_ms"] if m else None)
        sleep_scores.append(m["sleep_score"] if m else None)
        body_battery_max.append(m["body_battery_max"] if m else None)
        acwr.append(m["acwr"] if m else None)
        resting_hr.append(m["avg_resting_hr"] if m else None)
        total_steps.append(m["total_steps"] if m else None)
        active_calories.append(m["active_calories"] if m else None)

    # ── Summary ───────────────────────────────────────────────────────
    readiness_non_null = [v for v in readiness_scores if v is not None]
    days_with_data = len(readiness_non_null)

    # Last-7 slices (tail of the parallel arrays)
    r7 = readiness_scores[-7:]
    h7 = hrv_ms[-7:]
    s7 = sleep_scores[-7:]
    a7 = acwr[-7:]

    cutoff_7d = date.today() - timedelta(days=6)
    cutoff_14d = date.today() - timedelta(days=13)
    total_min_7d = sum(
        (w["duration_min"] or 0)
        for w in workouts_raw
        if w["date"] >= str(cutoff_7d)
    )
    total_min_14d = sum(
        (w["duration_min"] or 0)
        for w in workouts_raw
        if w["date"] >= str(cutoff_14d)
    )

    summary = {
        "avg_readiness_7d": _avg(r7),
        "avg_hrv_7d": _avg(h7),
        "avg_sleep_score_7d": _avg(s7),
        "avg_acwr_7d": _avg(a7),
        "total_training_min_7d": total_min_7d,
        "total_training_min_14d": total_min_14d,
        "trend_readiness": compute_trend(readiness_scores),
        "trend_hrv": compute_trend(hrv_ms),
        "trend_sleep": compute_trend(sleep_scores),
        "best_readiness_14d": max(readiness_non_null) if readiness_non_null else None,
        "worst_readiness_14d": min(readiness_non_null) if readiness_non_null else None,
        "days_with_data": days_with_data,
        "data_completeness_pct": round(days_with_data / days * 100) if days else 0,
    }

    # ── workouts_14d ──────────────────────────────────────────────────
    workouts_14d = [
        w for w in workouts_raw if w["date"] >= str(cutoff_14d)
    ]

    # ── weekly_volume (last 4 weeks) ──────────────────────────────────
    weekly: dict[str, dict] = {}
    for w in workouts_raw:
        if not w["date"]:
            continue
        d = date.fromisoformat(w["date"])
        # ISO week Monday
        week_start = str(d - timedelta(days=d.weekday()))
        if week_start not in weekly:
            weekly[week_start] = {"week_start": week_start, "total_min": 0, "by_sport": {}}
        dur = w["duration_min"] or 0
        weekly[week_start]["total_min"] += dur
        sport = w["sport"] or "unknown"
        weekly[week_start]["by_sport"][sport] = (
            weekly[week_start]["by_sport"].get(sport, 0) + dur
        )

    weekly_volume = sorted(weekly.values(), key=lambda x: x["week_start"])

    return {
        "summary": summary,
        "dates": dates_out,
        "readiness_scores": readiness_scores,
        "hrv_ms": hrv_ms,
        "sleep_scores": sleep_scores,
        "body_battery_max": body_battery_max,
        "acwr": acwr,
        "resting_hr": resting_hr,
        "total_steps": total_steps,
        "active_calories": active_calories,
        "workouts_14d": workouts_14d,
        "weekly_volume": weekly_volume,
    }


# ── Goal Endpoint ─────────────────────────────────────────────────────────

_PHASE_VOLUME: dict[str, int] = {
    "base": 300,
    "build": 420,
    "peak": 540,
    "taper": 240,
    "race_week": 120,
    "complete": 60,
}


def _compute_phase(weeks: int | None) -> tuple[str, str]:
    if weeks is None:
        return "base", "Building aerobic foundation"
    if weeks < 0:
        return "complete", "Race completed"
    if weeks <= 1:
        return "race_week", "Race week — minimal load"
    if weeks <= 3:
        return "taper", "Final preparation"
    if weeks <= 6:
        return "taper", "Reducing load, sharpening fitness"
    if weeks <= 10:
        return "peak", "Highest intensity and volume"
    if weeks <= 16:
        return "build", "Race-specific training block"
    if weeks <= 20:
        return "build", "Increasing volume and specific fitness"
    return "base", "Building aerobic foundation"


@app.get("/api/metrics/goal/{user_id}")
def get_goal_metrics(user_id: str):
    today = date.today()
    cutoff_2w = today - timedelta(days=13)

    with get_session() as session:
        profile = session.get(UserProfile, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        goal_event = profile.goal_event
        goal_date_val = profile.goal_date
        max_weekly_hours = profile.max_weekly_hours

        plan_row = session.execute(
            select(TrainingPlanRow).where(
                TrainingPlanRow.user_id == user_id,
                TrainingPlanRow.is_current == True,  # noqa: E712
            )
        ).scalar_one_or_none()

        plan_data = json.loads(plan_row.plan_json) if plan_row else None
        plan_valid_from = str(plan_row.valid_from) if (plan_row and plan_row.valid_from) else None

        workout_dates = {
            str(w.date)
            for w in session.execute(
                select(Workout).where(
                    Workout.user_id == user_id,
                    Workout.date >= cutoff_2w,
                )
            ).scalars().all()
        }

        readiness_rows = session.execute(
            select(ReadinessReportRow)
            .where(
                ReadinessReportRow.user_id == user_id,
                ReadinessReportRow.report_date >= cutoff_2w,
            )
            .order_by(ReadinessReportRow.report_date.asc())
        ).scalars().all()
        readiness_scores_14d = [r.readiness_score for r in readiness_rows]
        latest_readiness = readiness_scores_14d[-1] if readiness_scores_14d else None

    # ── Weeks / days to goal ──────────────────────────────────────────
    if goal_date_val:
        days_to_goal = (goal_date_val - today).days
        weeks_to_goal = days_to_goal // 7
    else:
        days_to_goal = None
        weeks_to_goal = None

    # ── Phase ─────────────────────────────────────────────────────────
    phase, phase_description = _compute_phase(weeks_to_goal)

    # ── Completion % ──────────────────────────────────────────────────
    if plan_valid_from and goal_date_val:
        plan_start = date.fromisoformat(plan_valid_from)
        total_days = (goal_date_val - plan_start).days
        elapsed = (today - plan_start).days
        completion_pct = (
            min(100.0, max(0.0, round(elapsed / total_days * 100, 1)))
            if total_days > 0
            else 100.0
        )
    else:
        completion_pct = 0.0

    # ── Weekly volume target ──────────────────────────────────────────
    base_target = _PHASE_VOLUME.get(phase, 300)
    if max_weekly_hours:
        weekly_volume_target_min = min(base_target, int(max_weekly_hours * 60))
    else:
        weekly_volume_target_min = base_target

    # ── Recent consistency ────────────────────────────────────────────
    if plan_data:
        planned = [
            s for s in plan_data.get("sessions", [])
            if str(cutoff_2w) <= s.get("date", "") <= str(today)
            and s.get("sport") != "rest"
        ]
        planned_count = len(planned)
        completed_count = len({s["date"] for s in planned} & workout_dates)
        recent_consistency = (
            round(completed_count / planned_count * 100, 1) if planned_count else 100.0
        )
    else:
        recent_consistency = 0.0

    # ── Readiness trend ───────────────────────────────────────────────
    readiness_trend = compute_trend(readiness_scores_14d)

    # ── On track ──────────────────────────────────────────────────────
    on_track = (latest_readiness or 0) > 60 and recent_consistency > 70

    # ── Coaching note ─────────────────────────────────────────────────
    if on_track:
        coaching_note = f"Great consistency — you're on track for {goal_event or 'your goal'}."
    elif recent_consistency < 70:
        coaching_note = "Focus on consistency this week."
    elif readiness_trend == "declining":
        coaching_note = "Prioritise recovery."
    else:
        coaching_note = "Keep building your base steadily."

    return {
        "goal_event": goal_event,
        "goal_date": str(goal_date_val) if goal_date_val else None,
        "weeks_to_goal": weeks_to_goal,
        "days_to_goal": days_to_goal,
        "phase": phase,
        "phase_description": phase_description,
        "completion_pct": completion_pct,
        "weekly_volume_target_min": weekly_volume_target_min,
        "recent_consistency": recent_consistency,
        "readiness_trend": readiness_trend,
        "on_track": on_track,
        "coaching_note": coaching_note,
    }


# ── Danger-zone / utility Endpoints ──────────────────────────────────────


@app.delete("/api/plans/current/{user_id}")
def clear_current_plan(user_id: str):
    with get_session() as session:
        rows = session.execute(
            select(TrainingPlanRow).where(
                TrainingPlanRow.user_id == user_id,
                TrainingPlanRow.is_current == True,  # noqa: E712
            )
        ).scalars().all()
        if not rows:
            raise HTTPException(status_code=404, detail="No active plan found")
        now = datetime.now(timezone.utc)
        for row in rows:
            row.is_current = False
            row.cleared_at = now
        plans_affected = len(rows)
        session.flush()
    logger.warning("Plan cleared for user=%s plans_affected=%d", user_id, plans_affected)
    return {
        "cleared": True,
        "plans_affected": plans_affected,
        "message": "Training plan cleared. Run the pipeline to generate a new one.",
    }


@app.delete("/api/data/{user_id}")
def reset_all_data(user_id: str):
    import os

    counts: dict[str, int] = {}
    try:
        with get_session() as session:
            def _del(model, col) -> int:
                result = session.execute(
                    delete(model).where(col == user_id)
                )
                return result.rowcount

            counts["user_feedback"]      = _del(UserFeedback,       UserFeedback.user_id)
            counts["agent_context"]      = _del(AgentContext,        AgentContext.user_id)
            counts["agent_runs"]         = _del(AgentRun,            AgentRun.user_id)
            counts["jobs"]               = _del(Job,                 Job.user_id)
            counts["readiness_reports"]  = _del(ReadinessReportRow,  ReadinessReportRow.user_id)
            counts["training_plans"]     = _del(TrainingPlanRow,     TrainingPlanRow.user_id)
            counts["workouts"]           = _del(Workout,             Workout.user_id)
            counts["daily_metrics"]      = _del(DailyMetric,         DailyMetric.user_id)
            session.flush()
    except Exception as exc:
        logger.error("reset_all_data failed for user=%s: %s", user_id, exc)
        raise HTTPException(status_code=500, detail=f"Reset failed: {exc}")

    try:
        os.remove(".garmin_session.pkl")
    except FileNotFoundError:
        pass

    logger.warning(
        "All data reset for user=%s counts=%s",
        user_id,
        counts,
    )
    return {
        "reset": True,
        "deleted": counts,
        "message": "All data cleared. Garmin session removed. Re-sync to start fresh.",
        "next_steps": [
            "Run POST /api/scheduler/trigger/sync to re-sync Garmin data",
            "Run POST /api/pipeline/run to generate a new plan",
        ],
    }


@app.get("/api/sync/status/{user_id}")
def get_sync_status(user_id: str):
    with get_session() as session:
        from sqlalchemy import func
        total_days: int = session.execute(
            select(func.count()).where(DailyMetric.user_id == user_id)
        ).scalar_one()

        latest_row = session.execute(
            select(DailyMetric)
            .where(DailyMetric.user_id == user_id)
            .order_by(DailyMetric.synced_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        last_synced_at = (
            latest_row.synced_at.isoformat() if latest_row and latest_row.synced_at else None
        )

        # completeness: days with HRV data in last 14 days as proxy
        cutoff = date.today() - timedelta(days=13)
        days_with_hrv: int = session.execute(
            select(func.count()).where(
                DailyMetric.user_id == user_id,
                DailyMetric.date >= cutoff,
                DailyMetric.hrv_last_night_ms.is_not(None),
            )
        ).scalar_one()

    return {
        "last_synced_at": last_synced_at,
        "total_days": total_days,
        "data_completeness_pct": round(days_with_hrv / 14 * 100) if total_days else 0,
    }


# ── Job Endpoints ─────────────────────────────────────────────────────────


@app.get("/api/jobs/{user_id}")
def get_jobs(user_id: str):
    with get_session() as session:
        rows = session.execute(
            select(Job)
            .where(Job.user_id == user_id)
            .order_by(Job.created_at.desc())
            .limit(10)
        ).scalars().all()
        return [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status,
                "payload": j.payload,
                "error": j.error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in rows
        ]
