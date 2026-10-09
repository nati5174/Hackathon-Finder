# Hackathon Finder

Automatically finds hackathons on MLH that offer travel reimbursement, and emails subscribers when new ones are posted.

## What it does

- Scrapes the MLH season events page every 24 hours
- For each hackathon, visits their website and uses Claude to detect whether they offer travel reimbursement (stipends, grants, covered flights, shuttles, etc.)
- Shows results on a filterable web UI (by region, in-person vs hybrid)
- Emails confirmed subscribers when new travel-reimbursed hackathons are found

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + SQLModel |
| Database | PostgreSQL |
| Scraping | Playwright (headless Chromium) + httpx |
| Detection | Claude Haiku via Anthropic API |
| Email | Resend |
| Scheduler | APScheduler |
| Frontend | React + Vite |
| Deploy | Railway |

## Local setup

**Prerequisites:** Python 3.12, Node 20, PostgreSQL running locally

1. Clone and install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   cd frontend && npm install
   ```

2. Create a `.env` file in the project root:
   ```
   ANTHROPIC_API_KEY=your_key
   DATABASE_URL=postgresql://postgres:@localhost:5432/hackathon_dev
   RESEND_API_KEY=your_key
   FROM_EMAIL=onboarding@resend.dev
   BASE_URL=http://localhost:8000
   ```

3. Start the backend:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

4. Start the frontend:
   ```bash
   cd frontend && npm run dev
   ```

App runs at http://localhost:5173, API at http://localhost:8000.

## API endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/hackathons` | Hackathons with travel reimbursement |
| GET | `/api/hackathons/all` | All hackathons |
| GET | `/api/stats` | Counts and last updated time |
| POST | `/api/subscribe` | Subscribe with email + preferences |
| GET | `/api/confirm/:token` | Confirm email subscription |
| GET | `/api/preferences/:token` | View/update alert preferences |
| GET | `/api/unsubscribe/:token` | Unsubscribe |
| POST | `/api/admin/recheck/:id` | Force re-scrape a single hackathon |

## Eval

A ground truth eval set lives in `eval/ground_truth.json`. Run it anytime you change the scraper or detector prompt:

```bash
# Precision/recall against ground truth (currently 8/8, 100%)
python eval/run_eval.py ground_truth

# Re-run detector on N random DB entries, flag any label flips
python eval/run_eval.py consistency 20

# Quick spot-check
python eval/run_eval.py spot 5
```

To add a new ground truth case, append to `eval/ground_truth.json`:
```json
{
  "name": "Hackathon Name",
  "url": "https://example.com",
  "travel_reimbursement": true,
  "notes": "Offers $200 travel stipend"
}
```

## Deploy (Railway)

The project includes `railway.toml` and `Procfile` for Railway deployment.

Set the following environment variables in Railway:
- `ANTHROPIC_API_KEY`
- `DATABASE_URL` (Railway Postgres plugin provides this)
- `RESEND_API_KEY`
- `FROM_EMAIL`
- `BASE_URL` (your Railway app URL)
- `MLH_SEASON` (e.g. `2026`)

Two processes run: `web` (FastAPI) and `scheduler` (background scraper).
