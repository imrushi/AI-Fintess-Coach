# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Apply/create migrations
alembic upgrade head
alembic revision --autogenerate -m "describe_change"

# Run dev server (from repo root or backend/)
PYTHONPATH=. uvicorn main:app --reload --port 8000

# Run integration tests
PYTHONPATH=. python -m tests.test_model_router

# Manual Garmin sync
python -m ingestion.sync --days 30
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173
npm run check        # svelte-check + TypeScript
npm run build        # production build
```

### Docker (production)

```bash
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m ingestion.sync --days 30
```

---

## Architecture

This is a full-stack self-hosted fitness coaching app. The **backend** is a single FastAPI app (`backend/main.py`) containing all API endpoints. The **frontend** is SvelteKit 5 with Svelte 5 runes and Tailwind CSS v4, proxying `/api/*` to the backend via Vite.

### Backend layers

| Layer | Location | Role |
|---|---|---|
| API | `main.py` | All FastAPI endpoints; imports agents and db helpers |
| Agents | `agents/` | LLM-powered analysis, planning, prompt building |
| Scheduler | `scheduler.py` | APScheduler daily pipeline (`Asia/Kolkata` TZ) |
| DB | `db/` | SQLAlchemy ORM models, read/write helpers, cost logging |
| Ingestion | `ingestion/` | Garmin Connect API wrapper + sync runner |
| Config | `config.py` | Pydantic-settings; reads from `backend/.env` |

### Agent subsystem (`backend/agents/`)

- **`model_router.py`** — `ModelClient` abstraction over OpenRouter and Ollama; returns a `ModelResponse` with token counts and latency. The active model is resolved from the user's profile at runtime.
- **`analysis_agent.py`** — scores daily readiness (HRV, sleep, body battery, ACWR) → `AnalysisResult` with a `ReadinessReport`.
- **`planning_agent.py`** — generates and patches the 2-week `TrainingPlan`; patching uses the current readiness, check-in, skip history, and sport/intensity overrides.
- **`orchestrator.py`** — `AgentOrchestrator` runs the full pipeline: analysis → plan patch → DB persistence → job record.
- **`plan_schemas.py`** — Pydantic v2 schemas (`TrainingPlan`, `TrainingSession`, `StrengthExercise`, `SwimSet`, etc.). Schemas use `model_validator` to tolerate partial/remapped LLM output.
- **`plan_prompt_builder.py`** — constructs all LLM prompts; keeps descriptions to 1–2 sentences.
- **`context.py`** / **`caveman.py`** — `ConversationContext` for cross-agent state transfer; `CavemanCompressor` replaces verbose fitness phrases with abbreviations to reduce prompt tokens.
- **`data_freshness.py`** — checks whether today's Garmin data is available before running readiness scoring.
- **`cost_logger.py`** (`db/`) — estimates and persists per-run LLM cost (`AgentRun` table).

### Database (`backend/db/model.py`)

Key ORM models: `User`, `UserProfile`, `DailyMetric`, `Workout`, `UserFeedback`, `TrainingPlanRow`, `ReadinessReportRow`, `Job`, `AgentRun`, `AgentContext`. Session-scoped helpers: `get_session()` (context manager), `get_engine()`.

Migrations live in `backend/alembic/`. After adding or changing an ORM model, always generate a migration with `alembic revision --autogenerate`.

### Frontend (`frontend/src/`)

- **`lib/api.ts`** — typed API client; all fetch calls go through here. `USER_ID_KEY` / `getStoredUserId()` manage the user ID in localStorage.
- **`lib/types.ts`** — shared TypeScript interfaces mirroring backend Pydantic schemas.
- **`lib/stores.ts`** — Svelte stores for shared state.
- **`routes/+page.svelte`** — main dashboard: today's session, plan calendar, skip/patch controls.
- **`routes/checkin/`** — daily check-in (RPE, mood, notes).
- **`routes/stats/`** — KPI time-series charts (Chart.js) and manual workout logging.
- **`routes/settings/`** — user profile, model selection, scheduler controls, Garmin sync.

The frontend uses **Svelte 5 runes** (`$state`, `$derived`, `$effect`) — avoid the legacy `$:` reactive syntax.

### Key invariants

- The `UserProfile.model` field (set in Settings) is the model string passed to `model_router.get_model_client()`. Format is `openrouter/<provider>/<model>` or `ollama/<model>`.
- `TrainingSession.status` drives display logic: `planned`, `completed`, `skipped`, `modified`. Skipped sessions are excluded from the consistency-score denominator.
- The daily pipeline writes a `Job` record at start and updates its status to `completed` or `failed` at the end; the dashboard polls job status to show pipeline progress.
- `StrengthExercise` and `SwimSet` schemas use `extra="ignore"` and `model_validator` remapping to tolerate LLM field-name drift — keep this resilience when modifying those schemas.
