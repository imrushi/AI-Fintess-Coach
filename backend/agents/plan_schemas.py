"""Pydantic v2 schemas for training plan generation."""

from __future__ import annotations

import json
import re
from datetime import date as date_cls, timedelta
from enum import Enum

from pydantic import BaseModel, ValidationError, field_validator, model_validator


# ── Enums ────────────────────────────────────────────────────────────────

class SportType(str, Enum):
    SWIM = "swim"
    BIKE = "bike"
    RUN = "run"
    BRICK = "brick"
    STRENGTH = "strength"
    YOGA = "yoga"
    ACTIVE_RECOVERY = "active_recovery"
    REST = "rest"


class IntensityZone(str, Enum):
    Z1 = "Z1"
    Z2 = "Z2"
    Z3 = "Z3"
    Z4 = "Z4"
    Z5 = "Z5"


class SessionStatus(str, Enum):
    PLANNED = "planned"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    MODIFIED = "modified"


# ── Session models ───────────────────────────────────────────────────────

class NutritionGuidance(BaseModel):
    pre_session: str | None = None
    during_session: str | None = None
    post_session: str | None = None
    daily_notes: str | None = None


class StrengthExercise(BaseModel):
    exercise: str
    sets: int
    reps_or_duration: str
    notes: str | None = None


class SwimSet(BaseModel):
    stroke: str = "freestyle"
    distance_m: int = 100
    reps: int = 1
    rest_sec: int | None = None
    intensity: str | None = None
    notes: str | None = None
    # Accept extra LLM fields without failing
    model_config = {"extra": "ignore"}

    @field_validator("stroke", mode="before")
    @classmethod
    def coerce_stroke(cls, v: object) -> str:
        if v is None or v == "":
            return "freestyle"
        return str(v)

    @field_validator("reps", "distance_m", mode="before")
    @classmethod
    def coerce_int(cls, v: object) -> int:
        if v is None:
            return 1
        try:
            return int(v)
        except (TypeError, ValueError):
            return 1


# Map common LLM sport names to our enum values
_SPORT_ALIASES: dict[str, str] = {
    "cycling": "bike",
    "biking": "bike",
    "swimming": "swim",
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "running": "run",
    "walking": "active_recovery",
    "walk": "active_recovery",
    "walk_or_yoga": "yoga",
    "recovery": "active_recovery",
}


class TrainingSession(BaseModel):
    date: str
    day_of_week: str
    sport: SportType = SportType.REST
    status: SessionStatus = SessionStatus.PLANNED
    duration_min: int | None = None
    distance_m: float | None = None
    intensity_zone: IntensityZone | None = None
    title: str = "Rest Day"
    description: str = "Recovery — no structured training."
    key_focus: str = "Rest and recovery"
    exercises: list[StrengthExercise] = []
    swim_sets: list[SwimSet] = []
    nutrition: NutritionGuidance = NutritionGuidance()
    override_applied: str | None = None
    readiness_adjusted: bool = False

    @field_validator("exercises", "swim_sets", mode="before")
    @classmethod
    def coerce_none_list(cls, v: object) -> object:
        if v is None:
            return []
        return v

    @field_validator("override_applied", mode="before")
    @classmethod
    def coerce_override(cls, v: object) -> object:
        if isinstance(v, bool) or v is False or v is True:
            return None
        return v

    @field_validator("sport", mode="before")
    @classmethod
    def normalise_sport(cls, v: str) -> str:
        if isinstance(v, str):
            v = _SPORT_ALIASES.get(v.lower(), v.lower())
        return v

    @field_validator("nutrition", mode="before")
    @classmethod
    def coerce_nutrition(cls, v: object) -> object:
        if isinstance(v, str):
            return {"daily_notes": v}
        return v


class WeeklyTargets(BaseModel):
    week_number: int = 1
    week_start: str = ""
    total_volume_min: int = 0
    long_session_sport: SportType | None = None
    key_workout: str | None = None
    weekly_theme: str | None = None
    intensity_distribution: dict = {}

    @field_validator("long_session_sport", mode="before")
    @classmethod
    def normalise_weekly_sport(cls, v: object) -> object:
        if isinstance(v, str):
            return _SPORT_ALIASES.get(v.lower(), v.lower())
        return v


# ── Main plan model ─────────────────────────────────────────────────────

class TrainingPlan(BaseModel):
    plan_id: str
    user_id: str
    generated_at: str
    valid_from: str
    valid_to: str
    goal_event: str | None = None
    goal_date: str | None = None
    weeks_to_goal: int | None = None
    sessions: list[TrainingSession]
    weekly_targets: list[WeeklyTargets] = []
    readiness_report_id: str | None = None
    readiness_score_at_generation: int | None = None
    training_gate_at_generation: str | None = None
    override_applied: str | None = None
    plan_rationale: str = ""
    nutrition_weekly_notes: str | None = None

    @field_validator("weekly_targets", mode="before")
    @classmethod
    def coerce_weekly_targets(cls, v: object) -> object:
        if isinstance(v, dict):
            return [v]
        return v

    @model_validator(mode="after")
    def auto_fill_sessions(self) -> TrainingPlan:
        """Ensure exactly 7 sessions within the valid window.
        
        - If < 7: pad missing days with REST sessions.
        - If > 7: keep only sessions within valid_from..valid_to window.
        """
        start = date_cls.fromisoformat(self.valid_from)
        end = date_cls.fromisoformat(self.valid_to)
        valid_dates = {(start + timedelta(days=i)).isoformat() for i in range(7)}

        if len(self.sessions) == 7 and all(s.date in valid_dates for s in self.sessions):
            return self

        # Trim any sessions outside the window
        in_window = [s for s in self.sessions if s.date in valid_dates]
        existing_dates = {s.date for s in in_window}

        # Pad missing days
        for i in range(7):
            d = (start + timedelta(days=i)).isoformat()
            if d not in existing_dates:
                day_name = (start + timedelta(days=i)).strftime("%A")
                in_window.append(
                    TrainingSession(
                        date=d,
                        day_of_week=day_name,
                        sport=SportType.REST,
                        title="Rest Day",
                        description="Recovery — no structured training.",
                        key_focus="Rest and recovery",
                    )
                )
        in_window.sort(key=lambda s: s.date)
        if len(in_window) != 7:
            raise ValueError(
                f"sessions must contain exactly 7 entries, got {len(in_window)}"
            )
        self.sessions = in_window
        return self

    @model_validator(mode="after")
    def valid_to_matches(self) -> TrainingPlan:
        expected = date_cls.fromisoformat(self.valid_from) + timedelta(days=6)
        if date_cls.fromisoformat(self.valid_to) != expected:
            raise ValueError(
                f"valid_to must be valid_from + 6 days "
                f"(expected {expected}, got {self.valid_to})"
            )
        return self

    @classmethod
    def from_llm_response(cls, json_str: str) -> TrainingPlan:
        """Parse an LLM response (possibly wrapped in markdown fences) into a TrainingPlan."""
        cleaned = re.sub(r"```(?:json)?\s*", "", json_str).strip().rstrip("`")
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from LLM: {exc}") from exc
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            failed = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            )
            raise ValueError(f"LLM plan failed validation — {failed}") from exc


# ── Override / check-in request models ───────────────────────────────────

class OverrideRequest(BaseModel):
    user_id: str
    override_date: str
    choice: str  # 'rest_as_recommended' or 'push_through'
    reason: str | None = None


class CheckInRequest(BaseModel):
    user_id: str
    check_in_date: str
    perceived_effort: int | None = None
    mood: int | None = None
    free_text: str | None = None
    override_choice: str | None = None
    override_reason: str | None = None
