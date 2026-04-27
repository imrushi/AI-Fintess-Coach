import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    ForeignKey,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
)

from config import settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Base ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Users ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    profile: Mapped["UserProfile"] = relationship(back_populates="user")
    daily_metrics: Mapped[list["DailyMetric"]] = relationship(back_populates="user")
    workouts: Mapped[list["Workout"]] = relationship(back_populates="user")
    feedbacks: Mapped[list["UserFeedback"]] = relationship(back_populates="user")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user")


# ── User Profiles ────────────────────────────────────────────────────────

class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    goal_event: Mapped[str | None] = mapped_column(String, nullable=True)
    goal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fitness_level: Mapped[str | None] = mapped_column(String, nullable=True)
    medical_conditions: Mapped[str | None] = mapped_column(String, nullable=True)
    dietary_preference: Mapped[str | None] = mapped_column(String, nullable=True)
    dietary_allergies: Mapped[str | None] = mapped_column(String, nullable=True)
    max_weekly_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    garmin_email: Mapped[str | None] = mapped_column(String, nullable=True)
    garmin_password: Mapped[str | None] = mapped_column(String, nullable=True)
    swim_equipment: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "pull_buoy,paddles"
    swim_strokes: Mapped[str | None] = mapped_column(String, nullable=True)    # e.g. "freestyle:expert,breaststroke:expert,backstroke:beginner,butterfly:learning"
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    lthr: Mapped[int | None] = mapped_column(Integer, nullable=True)           # Lactate Threshold HR in bpm
    model_analysis: Mapped[str] = mapped_column(
        String, default="openrouter/anthropic/claude-sonnet-4.6"
    )
    model_planning: Mapped[str] = mapped_column(
        String, default="openrouter/anthropic/claude-sonnet-4.6"
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="profile")


# ── Daily Metrics ────────────────────────────────────────────────────────

class DailyMetric(Base):
    __tablename__ = "daily_metrics"
    __table_args__ = (
        UniqueConstraint("user_id", "date", "source", name="uq_daily_metrics_user_date_source"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String, default="garmin")
    active_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_resting_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hrv_last_night_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    vo2max: Mapped[float | None] = mapped_column(Float, nullable=True)
    acute_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    chronic_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    acwr: Mapped[float | None] = mapped_column(Float, nullable=True)
    body_battery_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body_battery_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deep_sleep_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rem_sleep_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stress_avg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    workouts_json: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_garmin_json: Mapped[str | None] = mapped_column(String, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="daily_metrics")


# ── Workouts ─────────────────────────────────────────────────────────────

class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sport: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_pace_s_per_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    tss: Mapped[float | None] = mapped_column(Float, nullable=True)
    perceived_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    garmin_activity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_json: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship(back_populates="workouts")
    feedbacks: Mapped[list["UserFeedback"]] = relationship(back_populates="workout")


# ── User Feedback ────────────────────────────────────────────────────────

class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    feedback_date: Mapped[date] = mapped_column(Date, nullable=False)
    workout_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("workouts.id"), nullable=True
    )
    free_text: Mapped[str | None] = mapped_column(String, nullable=True)
    perceived_effort: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_choice: Mapped[str | None] = mapped_column(String, nullable=True)
    override_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="feedbacks")
    workout: Mapped["Workout | None"] = relationship(back_populates="feedbacks")


# ── Jobs ─────────────────────────────────────────────────────────────────

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending")
    payload: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User | None"] = relationship(back_populates="jobs")


# ── Agent Runs ───────────────────────────────────────────────────────────

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)
    model_str: Mapped[str] = mapped_column(String, nullable=False)
    backend: Mapped[str] = mapped_column(String, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    run_date: Mapped[date] = mapped_column(Date, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Readiness Reports ────────────────────────────────────────────────────

class ReadinessReportRow(Base):
    __tablename__ = "readiness_reports"
    __table_args__ = (
        UniqueConstraint("user_id", "report_date", name="uq_readiness_user_date"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    readiness_score: Mapped[int] = mapped_column(Integer, nullable=False)
    readiness_label: Mapped[str] = mapped_column(String, nullable=False)
    training_gate: Mapped[str] = mapped_column(String, nullable=False)
    report_json: Mapped[str] = mapped_column(String, nullable=False)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Training Plans ──────────────────────────────────────────────────────

class TrainingPlanRow(Base):
    __tablename__ = "training_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "valid_from", name="uq_training_plan_user_from"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False)
    plan_json: Mapped[str] = mapped_column(String, nullable=False)
    readiness_report_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("readiness_reports.id"), nullable=True
    )
    readiness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    training_gate: Mapped[str | None] = mapped_column(String, nullable=True)
    override_applied: Mapped[str | None] = mapped_column(String, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Agent Context ────────────────────────────────────────────────────────

class AgentContext(Base):
    __tablename__ = "agent_context"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)
    model_used: Mapped[str] = mapped_column(String, nullable=False)
    context_date: Mapped[date] = mapped_column(Date, default=date.today)
    context_json: Mapped[str] = mapped_column(String, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ── Engine & Session ─────────────────────────────────────────────────────

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.DATABASE_URL, echo=False)
    return _engine


@contextmanager
def get_session():
    session = Session(get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
