
# AI Fitness Coach

A full-stack AI-powered personal fitness coaching app that syncs with Garmin Connect, analyses your daily readiness (HRV, sleep, load), and generates a personalised 2-week training plan using an LLM.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · SQLAlchemy · SQLite |
| AI / LLM | OpenRouter or Ollama (configurable) |
| Data source | Garmin Connect (via `garminconnect`) |
| Frontend | SvelteKit 5 · Svelte 5 runes · Tailwind CSS v4 |

## Features

- **Daily readiness scoring** — aggregates HRV deviation, sleep score, body battery, and ACWR into a single readiness score and training gate (`PROCEED` → `MANDATORY_REST`)
- **AI training plan generation** — LLM produces a structured 2-week plan with per-session nutrition guidance
- **Daily check-in** — RPE, mood, and free-text notes fed back into the model
- **Override system** — rest-recommended alerts with push-through option (volume/intensity adjusted)
- **KPI metrics endpoint** — 14-day time-series for HRV, sleep, body battery, steps, calories, ACWR

---

## Getting Started

### 1. Backend

**Prerequisites:** Python 3.11+

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file inside the `backend/` directory:

```env
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=yourpassword
DATABASE_URL=sqlite:///./db/fitness.db

# LLM — pick one:
LLM_MODEL=openrouter/anthropic/claude-sonnet-4.6
# LLM_MODEL=ollama/llama3

# Optional
LOG_LEVEL=INFO
```

Start the API server:

```bash
cd backend && PYTHONPATH=. uvicorn main:app --reload --port 8000
```

API docs available at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### 2. Frontend

**Prerequisites:** Node.js 18+

```bash
cd frontend
npm install
npm run dev
```

App runs at [http://localhost:5173](http://localhost:5173). The Vite dev server proxies `/api/*` requests to the backend on port 8000.

---

## First Run

1. Start both servers (backend on `:8000`, frontend on `:5173`)
2. Open the app — if no plan exists you'll see a **Run Pipeline** button on the dashboard
3. Click it to sync Garmin data, score readiness, and generate your first training plan
4. Submit a daily check-in from the **Check-in** page each morning before training