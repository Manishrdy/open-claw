# OpenClaw — Instructions for Claude

## Project Overview
Job search automation tool (Python). Scrapes multiple job boards, scores listings with Gemini, writes results to Excel, and notifies via Telegram.

## Code Style
- Python 3.x, keep it simple and readable
- Use type hints for function signatures
- Use logging (not bare print) in library code; print is OK in main.py CLI output
- Follow existing patterns in src/ — new searchers should subclass `base.py`

## Architecture
- Searchers live in `src/searchers/` and extend the base class
- Gemini-powered searchers (LinkedIn, FundedStartups) must run sequentially to avoid rate limits — do NOT parallelize them
- Config values come from `src/config.py` (loaded from .env) — never hardcode API keys or secrets

## Do NOT
- Modify `jobs.xlsx` directly — always go through `src/excel_manager.py`
- Touch the `venv/` folder
- Commit `.env` files or API keys
- Add new dependencies without mentioning it

## Testing
- Run with `python main.py --dry-run` to verify changes without writing to Excel or calling Gemini scoring
