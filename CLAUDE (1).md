# Hackathon Finder

Finds in-person hackathons that offer travel reimbursement, so students can attend at little or no cost.

Read `docs/PRODUCT.md` and `docs/ARCHITECTURE.md` before any non-trivial change.

## Stack

- Backend: Python 3.12, FastAPI, SQLModel, PostgreSQL
- Scraping: httpx, BeautifulSoup, Playwright (Chromium)
- LLM: Anthropic API (Claude Haiku), used only to classify scraped text
- Email: Resend
- Frontend: React 18 + Vite, served by FastAPI from `frontend/dist`
- Hosting: Railway (nixpacks). Two processes: `web` and `scheduler`

## Commands

```
docker compose up -d                      # local Postgres
uvicorn backend.main:app --reload         # API on :8000
python -m backend.scheduler               # run the daily scrape once
cd frontend && npm run dev                # frontend on :5173, proxies /api
cd frontend && npm run build              # production build
```

Planned, not set up yet (add them, then remove this note):

```
ruff check backend
mypy backend
pytest
```

Environment variables (in `.env` locally, in Railway in production, never in the repo):
`DATABASE_URL`, `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `FROM_EMAIL`, `BASE_URL`, `MLH_SEASON`.

## How we work

1. **One source of truth.** This file plus the two docs. If code and docs disagree, fix the docs in the same change.
2. **Plan before coding.** For anything non-trivial, read the relevant code and give a short plan before changing files.
3. **Bugs: reproduce, investigate, fix, verify.** Do not change code until you can say what is wrong and show it failing.
4. **Verification is mandatory.** Every change ends with the checks listed below and a report of what was run and what was not.
5. **Approval scales with risk.** Small reversible changes go ahead. Stop and ask first for anything in the approval list.

## Project rules

- **The LLM only classifies.** It reads scraped text and returns a verdict and a short detail. It never invents hackathons, dates, locations, or links. Those come from the source listing.
- **Compliance comes before scraping.** No page of a hackathon site is fetched for content until robots.txt and the terms check have passed for that site.
- **Every verdict keeps its evidence.** `travel_details` must describe what the site says. A YES with no supporting text is a bug.
- **A misclassification gets a test case.** When a hackathon is found to be wrong, add it to the eval set with the expected answer before changing the prompt or keywords.
- **Never email the same hackathon twice** to the same subscriber, and never email unconfirmed addresses.
- **Subscriber emails are personal data.** Do not log them, export them, or send them to any service other than Resend.
- **Be polite to sites.** Identify the bot honestly, keep request counts per site bounded, and do not retry aggressively.

## Verification by area

| Area | What to run |
|---|---|
| Detector (prompt, keywords, parsing) | Eval set, with the score before and after |
| Compliance | Unit tests with saved robots.txt samples: allow, disallow, AI content signals, HTML returned, unreachable |
| Scraper | Run against 3 known sites (static, JS-rendered, accordion FAQ) and show the extracted text length |
| Scheduler | Dry run against a small list with no email sent; show the DB rows written |
| Email | Render the HTML to a file and open it; send only to a test address |
| API | Hit each changed endpoint and show the response |
| Frontend | `npm run build`, then open the page and check the changed behaviour |

## Needs approval first

- Database schema changes or anything that deletes rows
- Sending email to real subscribers, or changing who receives a digest
- Changes to compliance logic or the bot's user agent
- Changes to the detector prompt or model
- Adding a new scraping source
- New dependencies
- Auth, CORS, secrets, and Railway config
- Pushing or deploying

## Known issues

See `docs/ARCHITECTURE.md`, section "Known problems". Do not fix them in passing; each one is its own change.
