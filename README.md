
# AI Fitness Coach

A full-stack AI-powered personal fitness coaching app that syncs with Garmin Connect, analyses your daily readiness (HRV, sleep, load), and generates a personalised 2-week training plan using an LLM. Designed to run on a Raspberry Pi (ARM64) as a self-hosted service.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy · SQLite · Alembic |
| AI / LLM | OpenRouter (`claude-sonnet-4.6`) or Ollama (local) |
| Data source | Garmin Connect (via `garminconnect`) |
| Frontend | SvelteKit 5 · Svelte 5 runes · Tailwind CSS v4 |
| Deployment | Docker Compose · Nginx reverse proxy · ARM64 |
| Scheduler | APScheduler (`AsyncIOScheduler`, `Asia/Kolkata` timezone) |

## Features

### Readiness & Analysis
- **Daily readiness scoring** — aggregates HRV deviation, sleep score, body battery, and ACWR into a single score and training gate (`PROCEED` / `CAUTION` / `MANDATORY_REST`)
- **Garmin Connect sync** — pulls HRV, sleep, body battery, steps, calories, resting HR, and activity data
- **Daily check-in** — RPE, mood, and free-text notes fed back to the AI before each plan patch
- **Readiness history** — 14-day history of readiness scores and gates

### AI Training Plans
- **2-week plan generation** — LLM produces a structured plan with per-session nutrition guidance (pre/during/post)
- **Daily patch** — each morning the plan's current session is automatically updated based on today's readiness and last check-in
- **Sport override** — manually switch today's or tomorrow's session to Swim / Run / Bike / Yoga / Strength / Other before the patch
- **Auto sport selection** — `"auto"` sport override picks the sport with lowest recent volume to rebalance training
- **Intensity override** — push through a rest recommendation at reduced volume, or request an easy/hard session
- **Concise AI output** — patches keep descriptions to 1–2 sentences; no verbose disclaimers
- **Skipped-session awareness** — if multiple sessions were skipped recently the AI reduces weekly load automatically
- **Separate analysis and planning models** — configure different LLMs for readiness scoring vs. plan patching

### Workout Logging & Stats
- **Garmin auto-sync** — completed workouts (swim, run, bike) pulled from Garmin Connect
- **Manual workout logging** — log yoga, strength, pilates, HIIT, boxing, climbing, or any custom sport with duration, distance, perceived effort, and notes
- **Distance progression chart** — weekly km by sport (swim / bike / run) on the Stats page
- **KPI metrics** — 14-day time-series for HRV, sleep score, body battery, steps, calories, ACWR, and weekly volume

### Skip Session
- **Mark a session as skipped** — "Couldn't do it" button on any session card; choose a preset reason (Pool closed, Travel, Illness, Injury, Work, Tired) or type a custom one
- **Consistency score** — skipped sessions are excused (removed from the denominator) so they don't unfairly penalise your consistency percentage
- **AI context** — skip history is included in the LLM prompt so the coach adjusts future load accordingly

### Athlete Profiling
- **Swim profiling** — equipment (pull buoy, paddles, fins) and stroke proficiency per stroke
- **LTHR** — lactate threshold heart rate used to set training zones
- **Current weekly volume** — per-sport baseline (swim / bike / run km/week) fed to the planner
- **Date of birth** — enables age-adjusted training recommendations
- **Auto fitness level adjustment** — daily pipeline evaluates 4-week completion rate and session volume; upgrades (≥80% rate + ≥16 sessions) or downgrades (<40% rate across two consecutive 14-day windows) automatically with zero LLM cost; manual override locks the level; history log visible in Settings
- **Goal progress reset** — reset the goal start date to today so progress % recalculates from a new baseline without changing the goal event or date

### Cost & Ops
- **Per-run LLM cost tracking** — each pipeline run logs token counts and estimated USD cost (`AgentRun` table)
- **Cost history endpoint** — query cumulative LLM spend per user
- **Plan clearing** — soft-delete the active plan so a fresh one can be generated
- **Full data reset** — wipe all user data (feedback, metrics, plans, jobs) from the DB

### Reliability & UX
- **Email-based login** — single-user app; log in by email (no password)
- **Scheduler with pause/resume** — APScheduler runs the daily pipeline automatically; can be paused and resumed from the UI
- **Schema hardening** — `StrengthExercise` and `SwimSet` schemas tolerate partial/unexpected LLM output with safe defaults and field remapping
- **Docker deployment** — single `docker compose up` spins up backend, frontend, and Nginx; SQLite DB and Garmin session persist in a bind-mounted volume
- **Mobile-optimised UI** — responsive layout targets 375px+; horizontal-scroll 7-day calendar, compact mobile header with Run Pipeline button, stacked segmented controls, 56px bottom tab bar

---

## Project Structure

```
ai-coach/
├── docker-compose.yml          ← production deployment (ARM64)
├── nginx.conf                  ← reverse proxy config
├── backend/
│   ├── Dockerfile
│   ├── .env                    ← secrets (never commit)
│   ├── main.py                 ← FastAPI app + all endpoints
│   ├── scheduler.py            ← APScheduler daily pipeline
│   ├── config.py               ← Pydantic-settings; reads from backend/.env
│   ├── alembic/                ← DB migrations
│   ├── db/
│   │   ├── model.py            ← SQLAlchemy ORM models
│   │   ├── writer.py           ← DB write helpers
│   │   ├── reader.py           ← DB read helpers
│   │   ├── feedback_writer.py  ← check-in + skip persistence
│   │   └── cost_logger.py      ← per-run LLM cost persistence
│   ├── ingestion/
│   │   ├── garmin_client.py    ← Garmin Connect API wrapper
│   │   ├── normaliser.py       ← raw data → DailyMetrics
│   │   └── sync.py             ← Garmin sync runner
│   └── agents/
│       ├── model_router.py         ← ModelClient over OpenRouter + Ollama
│       ├── plan_schemas.py         ← TrainingPlan / TrainingSession Pydantic schemas
│       ├── schemas.py              ← shared agent I/O schemas
│       ├── plan_prompt_builder.py  ← prompt construction for planning agents
│       ├── prompt_builder.py       ← prompt construction for analysis agent
│       ├── planning_agent.py       ← plan generation + patch agent
│       ├── analysis_agent.py       ← readiness scoring agent
│       ├── orchestrator.py             ← full pipeline runner
│       ├── fitness_level_evaluator.py  ← algorithmic fitness level auto-adjustment (no LLM)
│       ├── context.py              ← ConversationContext for cross-agent state
│       ├── caveman.py              ← CavemanCompressor: verbose → terse prompt tokens
│       └── data_freshness.py       ← guards pipeline if today's Garmin data missing
└── frontend/
    └── src/
        ├── lib/
        │   ├── api.ts          ← typed API client
        │   ├── types.ts        ← TypeScript interfaces
        │   ├── stores.ts       ← Svelte stores for shared state
        │   └── components/     ← SessionCard, PatchTodayModal, OverrideModal, charts
        └── routes/
            ├── +page.svelte        ← dashboard (plan, today, skip)
            ├── login/              ← email login
            ├── checkin/            ← daily check-in form
            ├── stats/              ← KPI charts + manual workout log
            └── settings/           ← profile, model config, sync controls
```

---

## Getting Started

### Option A — Docker (recommended for Raspberry Pi / production)

```bash
# 1. Copy and fill in secrets
cp backend/.env.example backend/.env
# Edit backend/.env with your Garmin credentials and OpenRouter API key

# 2. Build and start
docker compose up -d

# 3. Run initial Garmin sync (first time only)
docker compose exec backend python -m ingestion.sync --days 30

# 4. Run the first pipeline
curl -X POST http://localhost/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<your-user-id>"}'
```

App is served at `http://localhost` (port 80 via Nginx).

### Option B — Local development

#### Backend

**Prerequisites:** Python 3.11+

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `backend/.env`:

```env
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=yourpassword
DATABASE_URL=sqlite:///./db/fitness.db

OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# Optional — local model
# OLLAMA_BASE_URL=http://localhost:11434

LOG_LEVEL=INFO
```

Run migrations and start:

```bash
alembic upgrade head
PYTHONPATH=. uvicorn main:app --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

#### Frontend

**Prerequisites:** Node.js 20+

```bash
cd frontend
npm install
npm run dev
```

App runs at [http://localhost:5173](http://localhost:5173). Vite proxies `/api/*` to port 8000.

---

## First Run

1. Start both servers
2. Run an initial Garmin sync: `python -m ingestion.sync --days 30`
3. Open the app — log in with your email on the login page
4. If no plan exists you'll see a **Run Pipeline** button on the dashboard
5. Click it to score readiness and generate your first 2-week training plan
6. Submit a daily check-in from the **Check-in** page each morning
7. The scheduler auto-patches today's session every day based on your readiness

---

## Key API Endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Look up user by email; returns `user_id` (no password) |

### Pipeline & Scheduling
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/pipeline/run` | Full pipeline: Garmin sync → readiness → plan patch |
| `GET` | `/api/scheduler/status` | Check if scheduler is running or paused |
| `POST` | `/api/scheduler/pause` | Pause the daily scheduler |
| `POST` | `/api/scheduler/resume` | Resume the daily scheduler |
| `POST` | `/api/scheduler/trigger/sync` | Manually trigger a Garmin sync |
| `POST` | `/api/scheduler/trigger/pipeline` | Manually trigger the full pipeline |
| `GET` | `/api/jobs/{user_id}` | List recent pipeline job records |
| `GET` | `/api/sync/status/{user_id}` | Check Garmin sync status for today |

### Plans & Sessions
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/plans/current/{user_id}` | Current 2-week training plan |
| `DELETE` | `/api/plans/current/{user_id}` | Clear the active plan (soft-delete) |
| `GET` | `/api/plans/history/{user_id}` | List past plans |
| `GET` | `/api/plans/{user_id}/session/{session_date}` | Single session for a date |
| `POST` | `/api/plans/patch-today` | Patch today's session (intensity + sport override) |
| `GET` | `/api/plans/override-prompt/{user_id}` | Preview override prompt before patching |
| `POST` | `/api/sessions/skip` | Mark a session as skipped with optional reason |
| `DELETE` | `/api/sessions/skip` | Un-skip a session |

### Analysis & Readiness
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analysis/run` | Run readiness analysis only (no plan patch) |
| `GET` | `/api/analysis/report/{user_id}` | Latest readiness report |
| `GET` | `/api/analysis/history/{user_id}` | 14-day readiness history |

### Check-in & Workouts
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/checkin` | Submit daily check-in (RPE, mood, notes) |
| `GET` | `/api/checkin/today/{user_id}` | Today's check-in |
| `GET` | `/api/checkin/{user_id}/{check_date}` | Check-in for a specific date |
| `POST` | `/api/workouts/manual` | Log a manual workout (yoga, strength, etc.) |

### Metrics & Goals
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/metrics/kpi/{user_id}` | KPI time-series (HRV, sleep, ACWR, distance) |
| `GET` | `/api/metrics/goal/{user_id}` | Goal progress + consistency score |

### Profile & Model Config
| Method | Path | Description |
|---|---|---|
| `GET` | `/api/profile/{user_id}` | Get user profile |
| `PUT` | `/api/profile/{user_id}` | Update user profile (setting `fitness_level` auto-locks it) |
| `GET` | `/api/profile/{user_id}/model-config` | Get analysis + planning model config |
| `PUT` | `/api/profile/{user_id}/model-config` | Set analysis + planning model config |
| `GET` | `/api/profile/{user_id}/fitness-history` | Fitness level change history (auto + manual) |
| `POST` | `/api/users/{user_id}/reset-progress` | Reset goal start date to today |
| `GET` | `/api/costs/{user_id}` | LLM cost history |

### Data Management
| Method | Path | Description |
|---|---|---|
| `DELETE` | `/api/data/{user_id}` | Reset all user data (metrics, plans, feedback, jobs) |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GARMIN_EMAIL` | ✅ | Garmin Connect login email |
| `GARMIN_PASSWORD` | ✅ | Garmin Connect password |
| `DATABASE_URL` | ✅ | SQLAlchemy DB URL (`sqlite:///./db/fitness.db`) |
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API key |
| `OPENROUTER_BASE_URL` | ✅ | `https://openrouter.ai/api/v1` |
| `OLLAMA_BASE_URL` | — | Local Ollama endpoint (default: `http://localhost:11434`) |
| `LOG_LEVEL` | — | `INFO` (default) or `DEBUG` |

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration after model changes
alembic revision --autogenerate -m "describe_change"
```

> In Docker: `docker compose exec backend alembic upgrade head`

---

## Troubleshooting

**Garmin 401 / session expired** — delete `backend/db-data/.garmin_session.pkl` (Docker) or `backend/.garmin_session.pkl` (local) and retry. The app will re-authenticate automatically.

**Plan not updating** — check that the scheduler is not paused (visible in the dashboard header). Use the Resume button or call `POST /api/scheduler/resume`.

**LLM schema errors** — the `StrengthExercise` and `SwimSet` schemas tolerate partial output with safe defaults. Check the `/api/pipeline/run` response for validation warnings.

**Consistency score seems low** — use the "Couldn't do it" button on session cards to mark legitimate skips (illness, travel, etc.). Skipped sessions are excluded from the consistency denominator.

**Want to regenerate the plan from scratch** — call `DELETE /api/plans/current/{user_id}` to clear the active plan, then `POST /api/pipeline/run` to generate a new one.

**Fitness level not changing automatically** — check that the "Auto-adjust" toggle is ON in Settings → Athlete Profile. If it was turned off (or you manually selected a level), `fitness_level_locked` is `true` and the evaluator skips you. Toggle it back on to re-enable.

**Fitness level changed unexpectedly** — view the full change log in Settings → Athlete Profile → Level History. Each entry shows old level, new level, direction, and the completion-rate reason.
