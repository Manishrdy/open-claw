# OpenClaw — AI Job Search Automation

Reads your PDF resumes, searches multiple job boards for matching roles in the USA,
scores each match with Gemini AI, and appends results to `jobs.xlsx`.
Controlled via a Telegram bot with optional daily scheduling.

## Setup

```bash
# 1. Create and activate the virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt
```

Your `.env` (already present) must contain:
```
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
```

> **Gemini quota**: The free tier allows ~15 req/min and ~1500 req/day.
> For production use, enable billing at https://ai.google.dev to remove limits.

## Usage

```bash
# Test resume parsing only
python main.py --parse-only

# Run searches + scoring + write Excel (no Telegram bot)
python main.py --search-only

# Dry-run: search only, print results, don't write Excel
python main.py --search-only --dry-run

# Full mode: bot + daily scheduler (recommended)
python main.py
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/search` | Trigger a full job search run now |
| `/status` | Show last run stats and Excel totals |
| `/jobs 15` | List latest 15 jobs found |
| `/report` | Receive `jobs.xlsx` as a file attachment |
| `/schedule on\|off` | Enable or disable daily 9 AM runs |
| `/help` | Show all commands |

## Job Boards Covered

| Board | Method |
|-------|--------|
| **Greenhouse** | Direct public JSON API — 68 AI/tech companies |
| **Ashby HQ** | Direct public JSON API — 24 AI startups |
| **Indeed** | RSS feed (last 14 days) |
| **LinkedIn** | Gemini Google Search grounding |
| **Wellfound** | HTTP scraper |
| **Funded Startups** | Gemini grounding — searches TechCrunch/Crunchbase for recent funding + hiring |

## Excel Output (`jobs.xlsx`)

Columns: `Job Title · Company · Location · Source · URL · Date Posted · Match Score ·
Matched Skills · Missing Skills · Salary · Date Found · Status · Notes`

- Score is colour-coded: green ≥80%, yellow ≥65%, red <65%
- URLs are clickable hyperlinks
- `Status` defaults to **New** — change to **Applied / Rejected / Interviewing** manually
- Duplicates (same URL) are automatically skipped on subsequent runs

## Configuration

Edit [`src/config.py`](src/config.py) to adjust:
- `MIN_MATCH_SCORE` — minimum score to include (default: 60)
- `SEARCH_DAYS_BACK` — how far back to look (default: 14 days)
- `MAX_JOBS_TO_SCORE` — Gemini scoring cap per run (default: 100)
- `SCHEDULE_HOUR` — daily run time (default: 9 AM)
- `GREENHOUSE_COMPANY_SLUGS` / `ASHBY_COMPANY_SLUGS` — add more companies
