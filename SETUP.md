# AI Fitness Coach — Setup Guide
> **Self-hosted · Garmin-first · Multi-agent · SvelteKit · Docker / Raspberry Pi**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Project Structure](#2-project-structure)
3. [Backend Setup](#3-backend-setup)
4. [Environment Variables](#4-environment-variables)
5. [Database Setup](#5-database-setup)
6. [Initial Garmin Sync](#6-initial-garmin-sync)
7. [First Pipeline Run](#7-first-pipeline-run)
8. [Frontend Setup](#8-frontend-setup)
9. [Docker Deployment (Raspberry Pi)](#9-docker-deployment-raspberry-pi)
10. [Local Model Setup (Free / Zero Cost)](#10-local-model-setup-free--zero-cost)
11. [Daily Operations](#11-daily-operations)
12. [Resetting Data](#12-resetting-data)
13. [Troubleshooting](#13-troubleshooting)
14. [Architecture Overview](#14-architecture-overview)
15. [API Reference](#15-api-reference)
16. [Cost Estimates](#16-cost-estimates)

---

## 1. Prerequisites

### Required (local dev)
| Dependency | Version | Check |
|---|---|---|
| Python | 3.12+ | `python --version` |
| Node.js | 20+ | `node --version` |
| npm | 9+ | `npm --version` |
| Git | any | `git --version` |

### Required (Docker / production)
| Dependency | Version | Check |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2+ | `docker compose version` |

### Accounts
| Service | Required | Purpose |
|---|---|---|
| Garmin Connect | ✅ Yes | Source of all wearable data |
| OpenRouter | ✅ Yes (free tier OK) | Cloud LLM API gateway |
| Ollama | Optional | Local model inference (zero cost) |

### Garmin Data Requirement
Your Garmin account needs **at least 14 days of activity data** for the AI analysis
to produce meaningful readiness scores and trend analysis. 30 days is ideal.

Supported Garmin devices (any device that syncs to Garmin Connect):
- Forerunner series (45, 55, 255, 955, 965)
- Fenix series (6, 7, 8)
- Vivoactive series
- Venu series
- Epix series

---

## 2. Project Structure

```
ai-coach/
├── SETUP.md                          ← this file
├── README.md
├── docker-compose.yml                ← production deployment (ARM64)
├── nginx.conf                        ← reverse proxy config
├── backend/
│   ├── Dockerfile
│   ├── .env                          ← secrets (never commit)
│   ├── db-data/                      ← bind-mount target for SQLite + Garmin session
│   ├── requirements.txt
│   ├── main.py                       ← FastAPI app + all endpoints
│   ├── config.py                     ← settings singleton
│   ├── scheduler.py                  ← APScheduler daily jobs (Asia/Kolkata)
│   ├── alembic/                      ← DB migrations
│   │   ├── env.py
│   │   └── versions/
│   ├── db/
│   │   ├── model.py                  ← SQLAlchemy ORM models
│   │   ├── writer.py                 ← DB write helpers
│   │   ├── reader.py                 ← DB read helpers for agents
│   │   ├── cost_logger.py            ← token usage logging
│   │   └── feedback_writer.py        ← check-in + skip session persistence
│   ├── ingestion/
│   │   ├── garmin_client.py          ← Garmin Connect API wrapper
│   │   ├── normaliser.py             ← raw API → DailyMetrics model
│   │   └── sync.py                   ← CLI sync script
│   └── agents/
│       ├── schemas.py                ← ReadinessReport Pydantic schema
│       ├── plan_schemas.py           ← TrainingPlan / TrainingSession schemas
│       ├── model_router.py           ← OpenRouter / Ollama abstraction
│       ├── prompt_builder.py         ← Analysis Agent prompt builder
│       ├── plan_prompt_builder.py    ← Planning + Patch Agent prompt builders
│       ├── analysis_agent.py         ← Analysis Agent
│       ├── planning_agent.py         ← Planning + Patch Agent
│       └── orchestrator.py           ← full pipeline runner
└── frontend/
    ├── Dockerfile
    ├── .env.local                    ← dev user ID (never commit)
    ├── vite.config.ts                ← dev proxy to :8000
    ├── src/
    │   ├── app.css                   ← design tokens + utility classes
    │   ├── lib/
    │   │   ├── types.ts              ← TypeScript interfaces
    │   │   ├── api.ts                ← typed API client
    │   │   ├── stores.ts             ← Svelte stores
    │   │   └── components/
    │   │       ├── PatchTodayModal.svelte  ← sport + intensity override modal
    │   │       └── charts/
    │   │           ├── LineChart.svelte
    │   │           ├── BarChart.svelte
    │   │           └── GaugeWidget.svelte
    │   └── routes/
    │       ├── +layout.svelte        ← sidebar + nav + toasts
    │       ├── +layout.ts            ← ssr: false
    │       ├── +page.svelte          ← dashboard (plan, today, skip session)
    │       ├── checkin/+page.svelte  ← daily check-in
    │       ├── stats/+page.svelte    ← KPI charts + manual workout log
    │       └── settings/+page.svelte ← profile + model config + sync
    └── static/
```

---

## 3. Backend Setup

### 3.1 Clone / Unzip the Project

```bash
# If cloning from git
git clone <your-repo-url> fitness-coach
cd fitness-coach

# OR if starting from scratch
mkdir fitness-coach && cd fitness-coach
```

### 3.2 Create Python Virtual Environment

```bash
cd backend
python -m venv .venv

# Activate (Mac/Linux)
source .venv/bin/activate

# Activate (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Activate (Windows CMD)
.venv\Scripts\activate.bat
```

You should see `(.venv)` in your terminal prompt.

### 3.3 Install Dependencies

```bash
pip install -r requirements.txt
```

If `requirements.txt` is missing, install manually:

```bash
pip install fastapi uvicorn sqlalchemy "alembic" garminconnect \
            pydantic python-dotenv structlog httpx apscheduler \
            anthropic openai cryptography rich
pip freeze > requirements.txt
```

### 3.4 Verify Installation

```bash
python -c "import fastapi, sqlalchemy, garminconnect, httpx; print('All imports OK')"
```

---

## 4. Environment Variables

Create `backend/.env`:

```bash
# ── Garmin Connect ─────────────────────────────────────────────
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=yourgarminpassword

# ── Database ───────────────────────────────────────────────────
# Local dev:
DATABASE_URL=sqlite:///./db/fitness.db
# Docker (set automatically by docker-compose.yml):
# DATABASE_URL=sqlite:////data/fitness.db

# ── OpenRouter (Cloud LLMs) ────────────────────────────────────
# Get your key at: https://openrouter.ai/keys
# Add $5 credit to start — enough for weeks of testing
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# ── Ollama (Local Models — optional) ──────────────────────────
OLLAMA_BASE_URL=http://localhost:11434

# ── App Config ─────────────────────────────────────────────────
APP_SITE_URL=http://localhost:5173
LOG_LEVEL=INFO
MAX_RETRIES=2
DEFAULT_MAX_TOKENS=2048

# ── Docker / Timezone ──────────────────────────────────────────
# TZ is set via docker-compose.yml environment block.
# To change: edit docker-compose.yml → TZ: "Your/Timezone"
# Example: "America/New_York", "Europe/London", "Asia/Kolkata"
```

### Security Notes

- **Never commit `.env`** — add it to `.gitignore` immediately:
  ```bash
  echo ".env" >> ../.gitignore
  echo ".garmin_session.pkl" >> ../.gitignore
  echo "db/*.db" >> ../.gitignore
  echo "backend/db-data/" >> ../.gitignore
  echo "frontend/.env.local" >> ../.gitignore
  ```
- Your Garmin password is stored in plain text in `.env`. This is acceptable
  for a local personal-use tool. Do not host this on a public server.
- The Garmin session token is cached as `.garmin_session.pkl` (local dev) or
  `/data/.garmin_session.pkl` (Docker). Delete it if you change your Garmin
  password — the client will re-authenticate automatically.

### Verifying Config Loads

```bash
python -c "from config import settings; print('DB:', settings.DATABASE_URL); print('Email:', settings.GARMIN_EMAIL)"
```

---

## 5. Database Setup

### 5.1 Create the DB Folder

```bash
mkdir -p db
```

### 5.2 Run Migrations

```bash
# From backend/ directory with .venv active
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> <hash>, initial_schema
INFO  [alembic.runtime.migration] Running upgrade <hash> -> <hash>, add_agent_runs
INFO  [alembic.runtime.migration] Running upgrade <hash> -> <hash>, add_agent_context
INFO  [alembic.runtime.migration] Running upgrade <hash> -> <hash>, add_readiness_reports
INFO  [alembic.runtime.migration] Running upgrade <hash> -> <hash>, add_training_plans_feedback
INFO  [alembic.runtime.migration] Running upgrade <hash> -> <hash>, add_cleared_at_to_plans
INFO  [alembic.runtime.migration] Running upgrade <hash> -> <hash>, add_workouts_garmin_fields
INFO  [alembic.runtime.migration] Running upgrade <hash> -> d4e5f6a7b8c9, add_session_skipped_to_feedback
```

> **Docker:** `docker compose exec backend alembic upgrade head`

### 5.3 Verify Tables

```bash
python -c "
import sqlite3
conn = sqlite3.connect('db/fitness.db')
tables = [t[0] for t in conn.execute(
  \"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\"
).fetchall()]
print('Tables created:')
for t in tables:
    print(f'  ✓ {t}')
"
```

Expected output:
```
Tables created:
  ✓ agent_context
  ✓ agent_runs
  ✓ alembic_version
  ✓ daily_metrics
  ✓ jobs
  ✓ readiness_reports
  ✓ training_plans
  ✓ user_feedback      ← includes session_skipped + skip_reason columns
  ✓ users
  ✓ user_profiles
  ✓ workouts           ← includes garmin_activity_id, distance_m, duration_min, sport
```

---

## 6. Initial Garmin Sync

This pulls the last 30 days of data from Garmin Connect.
**Run this before the pipeline — the agents need historical data.**

```bash
# Replace with your actual Garmin email
python -m ingestion.sync --email your@email.com --days 30
```

### What to Expect

```
Loading cached session... (or "Logging in to Garmin Connect...")
Login successful
Syncing 2025-10-14... ✓ sleep=76 hrv=42.1 bb_max=89 steps=8432
Syncing 2025-10-13... ✓ sleep=82 hrv=45.3 bb_max=91 steps=11203
Syncing 2025-10-12... ✗ hrv=None (HRV not available for this date)
...
Sync complete: 28/30 days synced
```

Some days may be missing — this is normal. Garmin doesn't always have HRV
or sleep data (device not worn, charged, or synced).

### Verify the Sync

```bash
python -c "
import sqlite3
conn = sqlite3.connect('db/fitness.db')
print('Rows in daily_metrics:', conn.execute('SELECT COUNT(*) FROM daily_metrics').fetchone()[0])
print('Rows in workouts:', conn.execute('SELECT COUNT(*) FROM workouts').fetchone()[0])
print()
print('Last 5 days:')
rows = conn.execute('''
  SELECT date, total_steps, avg_resting_hr, sleep_score, hrv_last_night_ms
  FROM daily_metrics
  ORDER BY date DESC LIMIT 5
''').fetchall()
for r in rows:
    print(f'  {r[0]} | steps={r[1]} | rhr={r[2]} | sleep={r[3]} | hrv={r[4]}')
"
```

You need at least **14 rows** in `daily_metrics` for the analysis agent to
produce meaningful results.

### Sync a Specific Date

```bash
python -m ingestion.sync --email your@email.com --date 2025-10-10
```

### Re-sync Last 7 Days (refresh)

```bash
python -m ingestion.sync --email your@email.com --days 7
```

---

## 7. First Pipeline Run

### 7.1 Get Your User ID

```bash
python -c "
import sqlite3
conn = sqlite3.connect('db/fitness.db')
row = conn.execute('SELECT id, email FROM users LIMIT 1').fetchone()
if row:
    print('user_id:', row[0])
    print('email:', row[1])
else:
    print('No user found — run sync first')
"
```

### 7.2 Run Full Pipeline (Analysis + Planning)

```bash
PYTHONPATH=. python -c "
import asyncio, sqlite3
from agents.orchestrator import orchestrator

conn = sqlite3.connect('db/fitness.db')
user_id = conn.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
print(f'Running pipeline for: {user_id}')

result = asyncio.run(orchestrator.run_full_pipeline(user_id))

print()
print('=== Pipeline Result ===')
print('Success:', result.success)
if result.success:
    r = result.analysis_result.report
    print(f'Readiness score:  {r.readiness_score}/100')
    print(f'Readiness label:  {r.readiness_label}')
    print(f'Training gate:    {r.training_gate}')
    print(f'Flags:            {r.flags}')
    print()
    p = result.planning_result.plan
    print(f'Plan period:      {p.valid_from} → {p.valid_to}')
    print(f'Sessions:         {len(p.sessions)}')
    print(f'Plan rationale:   {p.plan_rationale[:80]}...')
else:
    print('Error:', result.error)
"
```

**This takes 30–90 seconds** — two sequential LLM calls.

### 7.3 Verify Output in DB

```bash
python -c "
import sqlite3, json
conn = sqlite3.connect('db/fitness.db')

print('=== Readiness Report ===')
row = conn.execute('''
  SELECT report_date, readiness_score, readiness_label, training_gate
  FROM readiness_reports ORDER BY report_date DESC LIMIT 1
''').fetchone()
print(f'  {row}')

print()
print('=== Training Plan ===')
row = conn.execute('''
  SELECT valid_from, valid_to, is_current, tokens_in, tokens_out
  FROM training_plans ORDER BY generated_at DESC LIMIT 1
''').fetchone()
print(f'  {row}')

print()
print('=== Today Session Preview ===')
from datetime import date
plan_row = conn.execute(
  'SELECT plan_json FROM training_plans WHERE is_current=1 LIMIT 1'
).fetchone()
if plan_row:
    plan = json.loads(plan_row[0])
    today = str(date.today())
    session = next((s for s in plan['sessions'] if s['date'] == today), None)
    if session:
        print(f'  {session[\"sport\"]} | {session[\"duration_min\"]}min | {session[\"intensity_zone\"]} | {session[\"title\"]}')
"
```

---

## 8. Frontend Setup

### 8.1 Install Dependencies

```bash
cd frontend
npm install
```

### 8.2 Create Environment File

```bash
# Get your user_id from the DB
USER_ID=$(python -c "
import sqlite3
conn = sqlite3.connect('../backend/db/fitness.db')
print(conn.execute('SELECT id FROM users LIMIT 1').fetchone()[0])
")

# Create .env.local
echo "VITE_DEV_USER_ID=$USER_ID" > .env.local
echo "Created .env.local with user_id: $USER_ID"
```

### 8.3 Start Development Server

```bash
npm run dev
```

Open **http://localhost:5173** in your browser.

The Vite dev server proxies all `/api/*` requests to `http://localhost:8000`,
so both servers must be running simultaneously.

### 8.4 Start Both Servers Together

Open two terminals:

**Terminal 1 — Backend:**
```bash
cd backend
source .venv/bin/activate
PYTHONPATH=. uvicorn main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Or use a process manager (optional):

```bash
# Install concurrently
npm install -g concurrently

# From project root
concurrently \
  "cd backend && source .venv/bin/activate && PYTHONPATH=. uvicorn main:app --reload --port 8000" \
  "cd frontend && npm run dev"
```

### 8.5 Verify Frontend is Working

Open the browser and check these pages load without errors:

| Page | URL | What to see |
|---|---|---|
| Dashboard | http://localhost:5173/ | Today's session hero card |
| KPI Stats | http://localhost:5173/stats | HRV, sleep, load charts |
| Check-in | http://localhost:5173/checkin | RPE slider + mood selector |
| Settings | http://localhost:5173/settings | Profile + model config |

---

## 9. Docker Deployment (Raspberry Pi)

The app ships with a `docker-compose.yml` targeting ARM64 (Raspberry Pi 4/5).
All three services (backend, frontend, nginx) are built from local Dockerfiles.

### Quick start

```bash
# Build images
docker compose build

# Start all services
docker compose up -d

# Check all containers are healthy
docker compose ps

# Run migrations (first time only)
docker compose exec backend alembic upgrade head

# Initial Garmin sync (first time only)
docker compose exec backend python -m ingestion.sync --days 30
```

The app is available at `http://<pi-ip>` (port 80 via Nginx).
Backend API is accessible internally at `http://backend:8000` (not exposed to host).

### Volume layout

| Path (container) | Host bind-mount | Contents |
|---|---|---|
| `/data/fitness.db` | `./backend/db-data/fitness.db` | SQLite database |
| `/data/.garmin_session.pkl` | `./backend/db-data/.garmin_session.pkl` | Garmin session token |

Both files persist across `docker compose down` and image rebuilds.

### Updating

```bash
# Rebuild and restart backend only
docker compose build backend && docker compose up -d backend

# Rebuild everything
docker compose build && docker compose up -d

# Apply new migrations after a rebuild
docker compose exec backend alembic upgrade head
```

### Timezone

Change the scheduler timezone by editing `docker-compose.yml`:

```yaml
environment:
  TZ: "Europe/London"  # or America/New_York, Asia/Tokyo, etc.
```

Then `docker compose up -d backend` to apply.

---

## 10. Local Model Setup (Free / Zero Cost)

If you want to run entirely free with no API costs, use Ollama.

### 10.1 Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows
# Download from https://ollama.com/download
```

### 10.2 Start Ollama

```bash
# Start in background
ollama serve &

# Or start in its own terminal (easier to see errors)
ollama serve
```

Verify it's running:
```bash
curl http://localhost:11434/api/tags
# Should return {"models": [...]}
```

### 10.3 Pull Models

Choose based on your available RAM:

| Model | RAM needed | Speed | Quality | Best for |
|---|---|---|---|---|
| `llama3.2:3b` | 4GB | Very fast | Lower | Testing / dev |
| `mistral-nemo` | 8GB | Fast | Good | Budget option |
| `qwen2.5:32b` | 20GB | Medium | Very good | Best balance |
| `llama3.3:70b` | 40GB | Slow | Excellent | Best quality |

```bash
# Minimum (4GB RAM) — for testing
ollama pull llama3.2:3b

# Recommended (20GB RAM) — good quality
ollama pull qwen2.5:32b

# Best quality (40GB RAM)
ollama pull llama3.3:70b
```

### 10.4 Configure in Settings

1. Open http://localhost:5173/settings
2. Go to **AI Models** section
3. Change **Analysis Agent** to `ollama/llama3.2:3b` (or your chosen model)
4. Change **Planning Agent** to `ollama/llama3.2:3b`
5. Click **Save Model Config**
6. Run the pipeline — context will transfer to the new model automatically

### 10.5 Local Model Performance Notes

- **3b models**: Fast (2–4 min per pipeline run) but may produce malformed JSON.
  The self-healing validator will fix most issues.
- **32b/70b models**: Slow (10–20 min per pipeline run) but high quality.
- **Recommendation**: Use OpenRouter Claude for Analysis Agent (better reasoning),
  Ollama for Planning Agent (structured output is easier for local models).

---

## 11. Daily Operations

### How Automation Works

The scheduler (`APScheduler AsyncIOScheduler`) runs jobs automatically when the backend is running.
The default timezone is **Asia/Kolkata** (IST, UTC+5:30). Change it via `TZ` in `docker-compose.yml`.

| Job | Local time (IST) | What it does |
|---|---|---|
| Garmin Sync | 08:30 | Pulls last 3 days of Garmin data |
| AI Pipeline | 09:00 | Runs Analysis + today's patch agent, updates plan |

The pipeline patches **today's session** based on your readiness and last check-in.
A full new 2-week plan is only regenerated when the current plan expires.

### Pausing / Resuming the Scheduler

From the dashboard header, or via API:

```bash
# Pause (e.g. on holiday)
curl -X POST http://localhost:8000/api/scheduler/pause

# Resume
curl -X POST http://localhost:8000/api/scheduler/resume

# Check status
curl http://localhost:8000/api/scheduler/status | python -m json.tool
```

### Manual Operations

**Force a Garmin sync right now:**
```bash
curl -X POST http://localhost:8000/api/scheduler/trigger/sync \
  -H "Content-Type: application/json" \
  -d '{"user_id": "YOUR-USER-ID"}'
```

Or from the Settings page → Data Sync → **Sync Garmin Now**.

**Force a pipeline run right now:**
```bash
curl -X POST http://localhost:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"user_id": "YOUR-USER-ID"}'
```

Or from the Settings page → **Run AI Pipeline**.

**Check scheduler status:**
```bash
curl http://localhost:8000/api/scheduler/status | python -m json.tool
```

### Daily Check-in

Go to http://localhost:5173/checkin every morning (or after your session) and:

1. Rate yesterday's effort (RPE 1–10)
2. Select your mood (1–5 emoji)
3. Optionally add free-text notes
4. Submit

Your check-in feeds into the next day's readiness analysis.

### Push/Rest Override

When your readiness gate is `REST_RECOMMENDED` or `MANDATORY_REST`, the
dashboard shows an alert asking what you want to do:

- **Rest as Recommended** — plan updates to active recovery only
- **Push Through** — plan reduces volume by 25%, caps intensity at Z3

The override is logged and taken into account in future analysis.

---

## 12. Resetting Data

### Option A — Just Re-sync Garmin Data (safest)

Keeps your plans and reports, just refreshes the raw wearable data:

```bash
cd backend
python -c "
import sqlite3
conn = sqlite3.connect('db/fitness.db')
conn.execute('DELETE FROM workouts')
conn.execute('DELETE FROM daily_metrics')
conn.commit()
deleted = conn.execute('SELECT COUNT(*) FROM daily_metrics').fetchone()[0]
print('daily_metrics rows:', deleted)  # should be 0
"
python -m ingestion.sync --email your@email.com --days 30
```

### Option B — Clear Training Plan Only (keeps wearable data)

Via the API:
```bash
curl -X DELETE "http://localhost:8000/api/plans/current/YOUR-USER-ID"
```

Via the UI: Settings → Danger Zone → **Clear Plan**

A new plan is generated on the next pipeline run.

### Option C — Reset All Data (nuclear option)

**This deletes everything except your user account and profile.**

Via the API:
```bash
curl -X DELETE "http://localhost:8000/api/data/YOUR-USER-ID"
```

Via the UI: Settings → Danger Zone → type "RESET" → **Permanently Delete All Data**

After a reset, follow these steps:
1. Settings → Data Sync → **Sync Garmin Now** (wait 60 seconds)
2. Settings → Data Sync → **Run AI Pipeline** (wait 2 minutes)
3. Dashboard will show your new plan

### Option D — Full Database Wipe (start completely fresh)

```bash
cd backend
rm db/fitness.db
rm -f .garmin_session.pkl
alembic upgrade head
python -m ingestion.sync --email your@email.com --days 30
```

Then re-run the pipeline as in Step 7.

---

## 13. Troubleshooting

### Garmin Issues

| Problem | Symptom | Fix |
|---|---|---|
| Auth fails on first run | `GarminConnectAuthenticationError` | Check email/password in `.env`. Try logging into garminconnect.com to verify. |
| Session expired / 401 loop | Repeated 401 errors on sync | Delete `.garmin_session.pkl` (local) or `backend/db-data/.garmin_session.pkl` (Docker) and retry. The client re-authenticates automatically. |
| Rate limited | `429 Too Many Requests` | Wait 60 seconds and retry. The client adds 1-second delays between requests. |
| Missing data | Fields are `null` | Your device may not support that metric (e.g., some Forerunners don't have HRV). This is fine. |
| Sync shows 0 workouts | `workouts: 0` | Check Garmin Connect app — activities must be synced to the app first. |

### OpenRouter Issues

| Problem | Symptom | Fix |
|---|---|---|
| 401 Unauthorized | API call fails immediately | Check `OPENROUTER_API_KEY` in `.env`. No trailing spaces. |
| 402 Payment Required | API call fails | Add credits at openrouter.ai/credits |
| Model not found | 404 on API call | Visit openrouter.ai/models, search for the model, copy the exact model ID string |
| Rate limited | 429 error | The free tier has request limits. Add credits or switch to a local model. |

### Ollama Issues

| Problem | Symptom | Fix |
|---|---|---|
| Connection refused | `httpx.ConnectError` on Ollama calls | Run `ollama serve` in a separate terminal |
| Model not found | `model not found` | Run `ollama pull llama3.2:3b` first |
| Slow responses | Pipeline takes > 15 minutes | Normal for 70b models on CPU. Use 3b for testing or OpenRouter for speed. |
| JSON parse fails | Validator throws errors | Local models struggle with strict JSON. Use OpenRouter for the Analysis Agent. |
| Out of memory | Process killed | Model too large for your RAM. Use a smaller model (3b instead of 70b). |

### Database Issues

| Problem | Symptom | Fix |
|---|---|---|
| `no such table` | SQLAlchemy error | Run `alembic upgrade head` from `backend/` |
| `ModuleNotFoundError` | Import fails | Run with `PYTHONPATH=. python ...` from `backend/` dir |
| Alembic can't find models | `Target database is not up to date` | Make sure `alembic/env.py` imports `Base` from `db.models` |
| Unique constraint violation | Duplicate key error on sync | Normal — the sync is idempotent. This shouldn't happen with `session.merge()`. |

### Frontend Issues

| Problem | Symptom | Fix |
|---|---|---|
| Charts don't render | Blank chart areas | Make sure `Chart.register(...registerables)` runs in `onMount` |
| API calls return CORS error | Browser console shows CORS | Check `vite.config.ts` has proxy config; verify backend has CORS middleware |
| `VITE_DEV_USER_ID` undefined | Stores start as null | Check `.env.local` is in `frontend/` folder; restart `npm run dev` |
| Plan grid shows wrong dates | Sessions out of order | Sort sessions: `[...plan.sessions].sort((a,b) => a.date.localeCompare(b.date))` |
| Stores not updating after API call | Stale data in UI | Use `store.set(newValue)` not mutation. Check you're awaiting the API call. |

### Pipeline Issues

| Problem | Symptom | Fix |
|---|---|---|
| Agent returns invalid JSON | Validation error after retries | Check server logs for the raw LLM output. Add `"Output ONLY JSON"` to system prompt. |
| Pipeline times out | No response after 3 minutes | Increase `DEFAULT_MAX_TOKENS` or switch to a faster model (Gemini Flash). |
| Readiness score always 50 | Suspiciously average scores | Likely insufficient data. Check `daily_metrics` has 14+ rows with non-null HRV/sleep. |
| Plan has fewer than 14 sessions | Validation error | The orchestrator auto-fills missing days with REST sessions. |
| Plan patches feel too verbose | Long AI descriptions after updates | The patch prompt includes "BE CONCISE". If verbosity returns, re-run the pipeline (context injection is intentionally disabled for patches). |
| Plan not updating today | Scheduler patches tomorrow instead | Ensure `patch_target="today"` is passed. The scheduler always passes this explicitly. |
| StrengthExercise / SwimSet crash | Pydantic validation error on plan parse | Schemas include `extra="ignore"` and safe defaults. If a crash occurs, check for a completely malformed LLM response and re-run. |

### Port Already in Use

```bash
# Find and kill process on port 8000
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use a different port
PYTHONPATH=. uvicorn main:app --port 8001
# Update VITE_DEV_USER_ID proxy target in vite.config.ts to :8001
```

---

## 14. Architecture Overview

### Data Flow

```
Garmin Connect API
       │
       ▼ (garminconnect, daily ~08:30 IST)
Ingestion Service
  └── Normaliser → DailyMetrics + Workouts
       │
       ▼
  SQLite Database  (/data/fitness.db in Docker)
  ├── daily_metrics
  ├── workouts          ← Garmin + manual workouts
  └── user_feedback     ← check-ins + session_skipped + skip_reason
       │
       ▼ (daily ~09:00 IST)
Agent Orchestrator
       │
       ├──► Analysis Agent (Claude / Ollama)
       │      Input:  14d metrics + recent feedback + profile
       │      Output: ReadinessReport JSON
       │              (score, gate, HRV, sleep, ACWR signals)
       │
       └──► Planning Agent (Claude / Ollama)
              Input:  ReadinessReport + profile + recent feedback
              │       + skipped sessions history
              Output: TrainingPlan JSON (14 sessions, nutrition)
              │         OR today's session patch only
              │
              ▼ Manual triggers
       Patch Today / Patch Tomorrow
       (sport override + intensity override + skip context)
                        │
                        ▼
                  SQLite Database
                  ├── readiness_reports
                  └── training_plans
                        │
                        ▼
                  SvelteKit Frontend (via Nginx)
                  ├── Dashboard   — today's session, 2-week plan,
                  │                 skip session, sport/intensity override
                  ├── Stats       — KPI charts, distance progression,
                  │                 manual workout log
                  ├── Check-in    — RPE + mood + notes
                  └── Settings    — profile, model config, sync
```

### Key Design Decisions

**Why 2 agents instead of 10?**
One well-prompted agent with structured output handles what 6 sub-agents would
do. 2 agents = simpler, faster, cheaper.

**Why SQLite instead of PostgreSQL?**
One user, daily metrics. SQLite handles this indefinitely. Swap by changing
one SQLAlchemy connection string when going multi-user. Alembic migrations use
`render_as_batch=True` for SQLite-safe schema changes.

**Why not use the Garmin Connect MCP server?**
`garmin-connect-mcp` is great for Claude Desktop interactive queries. For a
scheduled pipeline, you need direct API control over rate limiting, session
caching, and error handling. `python-garminconnect` is used directly.

**How does the skip session feature work?**
When a user marks a session as skipped, `session_skipped=True` and an optional
`skip_reason` are stored in `user_feedback`. The consistency score excludes
skipped sessions from the denominator (excused misses). All 3 prompt builders
include recent feedback (with skip status) so the AI adjusts future load:
1 skip → no change; 2–3 skips → −15% volume; 4+ skips → rebuilding week.

**Why is context injection disabled for patches?**
Injecting prior `AgentContext` into patch calls caused the LLM to escalate
verbosity on each repeated pipeline run. Patches are now stateless — they
only receive today's readiness, the current plan JSON, and recent feedback.

**How does per-user model config work?**
Each `UserProfile` stores `model_planning` and `model_analysis` fields.
The Settings page lets you switch models independently for each agent.
Changes take effect on the next pipeline run.

---

## 15. API Reference

### Health

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service health check |

### Health

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service health check |

### Plans

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/plans/current/{user_id}` | Get current 14-day plan |
| GET | `/api/plans/{user_id}/session/{date}` | Get single session |
| GET | `/api/plans/history/{user_id}` | Plan history list |
| GET | `/api/plans/override-prompt/{user_id}` | Should push/rest UI show? |
| DELETE | `/api/plans/current/{user_id}` | Deactivate current plan |

### Sessions (patch + skip)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/sessions/patch-today` | Patch today's session (intensity + sport override) |
| POST | `/api/sessions/patch-tomorrow` | Patch tomorrow's session |
| POST | `/api/sessions/skip` | Mark a session as skipped with optional reason |
| DELETE | `/api/sessions/skip` | Un-skip a session |

### Workouts

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/workouts/manual` | Log a manual workout (yoga, strength, etc.) |

### Analysis

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/analysis/run` | Run Analysis Agent only |
| GET | `/api/analysis/report/{user_id}` | Get readiness report |
| GET | `/api/analysis/history/{user_id}` | Readiness score history |

### Pipeline

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/pipeline/run` | Full pipeline: Garmin sync → readiness → plan patch |

### Check-in

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/checkin` | Submit daily check-in |
| GET | `/api/checkin/today/{user_id}` | Get today's check-in |

### Profile

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/profile/{user_id}` | Get user profile |
| PUT | `/api/profile/{user_id}` | Update profile |
| GET | `/api/profile/{user_id}/model-config` | Get model settings |
| PUT | `/api/profile/{user_id}/model-config` | Update model settings |

### Metrics

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/metrics/kpi/{user_id}` | KPI time-series (HRV, sleep, ACWR, weekly distance) |
| GET | `/api/metrics/goals/{user_id}` | Goal progress + consistency score |

### Scheduler

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/scheduler/status` | Job schedule + next run times + pause state |
| POST | `/api/scheduler/pause` | Pause the daily scheduler |
| POST | `/api/scheduler/resume` | Resume the daily scheduler |
| POST | `/api/scheduler/trigger/sync` | Manually trigger Garmin sync |
| POST | `/api/scheduler/trigger/pipeline` | Manually trigger pipeline |

### Data Management

| Method | Endpoint | Description |
|---|---|---|
| DELETE | `/api/data/{user_id}` | Reset all data (keep profile) |
| GET | `/api/sync/status/{user_id}` | Last sync time + row counts |
| GET | `/api/jobs/{user_id}` | Recent job history |
| GET | `/api/costs/{user_id}` | Token usage summary |

---

## 16. Cost Estimates

### Cloud Models (OpenRouter)

| Configuration | Cost per day | Cost per month |
|---|---|---|
| Claude 3.5 Sonnet (both agents) | ~$0.006 | ~$0.18 |
| Claude 3.5 Sonnet (analysis) + Gemini Flash (planning) | ~$0.004 | ~$0.12 |
| Gemini Flash (both agents) | ~$0.0003 | ~$0.01 |
| Llama 3.1 70B via OpenRouter (both) | ~$0.002 | ~$0.06 |

*Estimates assume 1 pipeline run/day with Caveman compression (40% token reduction).*
*Without Caveman, multiply costs by ~1.7.*

### Local Models (Ollama — Free)

| Model | Cost | RAM Required | Pipeline time |
|---|---|---|---|
| llama3.2:3b | $0.00 | 4GB | ~5 min |
| qwen2.5:32b | $0.00 | 20GB | ~12 min |
| llama3.3:70b | $0.00 | 40GB | ~20 min |

### Recommended Setup

**Best quality** (paid): Claude 3.5 Sonnet for both agents — ~$0.18/month.

**Best value** (paid): Claude 3.5 Sonnet for analysis + Gemini Flash for planning — ~$0.12/month.

**Zero cost** (local): Both agents on `qwen2.5:32b` — $0.00, requires 20GB RAM.

**Development/testing**: OpenRouter free tier + `llama3.2:3b` locally — effectively free.

---

## Quick Reference Card

```bash
# ── Docker (production) ───────────────────────────────────────
docker compose up -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m ingestion.sync --days 30
curl http://localhost/health

# ── Local dev ─────────────────────────────────────────────────
cd backend && source .venv/bin/activate
PYTHONPATH=. uvicorn main:app --reload --port 8000 &
cd frontend && npm run dev &

# ── Get your user ID ──────────────────────────────────────────
python -c "import sqlite3; print(sqlite3.connect('backend/db/fitness.db').execute('SELECT id FROM users LIMIT 1').fetchone()[0])"

# ── Manual Garmin sync ────────────────────────────────────────
python -m ingestion.sync --email your@email.com --days 7

# ── Manual pipeline ───────────────────────────────────────────
curl -X POST http://localhost:8000/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER-ID"}'

# ── Patch today with sport override ───────────────────────────
curl -X POST http://localhost:8000/api/sessions/patch-today \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER-ID", "sport_override": "swim"}'

# ── Mark session as skipped ───────────────────────────────────
curl -X POST http://localhost:8000/api/sessions/skip \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER-ID", "session_date": "2026-05-28", "skip_reason": "Travel"}'

# ── Log manual workout ────────────────────────────────────────
curl -X POST http://localhost:8000/api/workouts/manual \
  -H "Content-Type: application/json" \
  -d '{"user_id": "USER-ID", "date": "2026-05-28", "sport": "yoga", "duration_min": 45}'

# ── Pause / resume scheduler ──────────────────────────────────
curl -X POST http://localhost:8000/api/scheduler/pause
curl -X POST http://localhost:8000/api/scheduler/resume

# ── Check everything is working ───────────────────────────────
curl http://localhost:8000/health
curl http://localhost:8000/api/scheduler/status | python -m json.tool

# ── Clear Garmin data and re-sync ─────────────────────────────
python -c "
import sqlite3; conn = sqlite3.connect('backend/db/fitness.db')
conn.execute('DELETE FROM workouts'); conn.execute('DELETE FROM daily_metrics'); conn.commit()
"
python -m ingestion.sync --email your@email.com --days 30

# ── Full reset (nuclear) ──────────────────────────────────────
rm backend/db/fitness.db backend/.garmin_session.pkl
cd backend && alembic upgrade head
python -m ingestion.sync --email your@email.com --days 30
```

---

*AI Fitness Coach — Last updated May 2026*
*Built with: FastAPI · SQLAlchemy · garminconnect · Anthropic Claude · OpenRouter · SvelteKit · Chart.js · Docker · Nginx*
