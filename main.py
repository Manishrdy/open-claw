"""
OpenClaw — Job Search Automation
=================================
Entry point that orchestrates the full pipeline:
  1. Parse resumes → CandidateProfile
  2. Run all job board searchers in parallel
  3. Score each listing with Gemini → filter by MIN_MATCH_SCORE
  4. Append new results to jobs.xlsx
  5. Notify via Telegram

Run modes:
  python main.py                   Full pipeline + Telegram bot + scheduler
  python main.py --parse-only      Just parse resume and print profile
  python main.py --search-only     Search + score + Excel, no Telegram bot
  python main.py --dry-run         Search only, print results, don't write Excel
"""

import argparse
import asyncio
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import SCHEDULE_HOUR, SCHEDULE_MINUTE
from src.excel_manager import append_jobs, get_stats
from src.job_matcher import match_jobs
from src.resume_parser import load_candidate_profile
from src.searchers.ashby import AshbySearcher
from src.searchers.funded_startups import FundedStartupsSearcher
from src.searchers.greenhouse import GreenhouseSearcher
from src.searchers.indeed import IndeedSearcher
from src.searchers.linkedin import LinkedInSearcher
from src.searchers.wellfound import WellfoundSearcher
from src.telegram_bot import (
    build_application,
    is_schedule_enabled,
    send_notification,
    set_last_run_info,
    set_pipeline_runner,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("openclaw")

# All searchers — instantiated once at startup
SEARCHERS = [
    GreenhouseSearcher(),
    AshbySearcher(),
    IndeedSearcher(),
    LinkedInSearcher(),
    WellfoundSearcher(),
    FundedStartupsSearcher(),
]

# Cache the parsed profile so we don't re-parse on every scheduled run
_profile_cache = None


def get_profile():
    global _profile_cache
    if _profile_cache is None:
        _profile_cache = load_candidate_profile()
    return _profile_cache


def run_pipeline(dry_run: bool = False) -> dict:
    """
    Execute the full job search pipeline synchronously.
    Returns a summary dict: {added, total_found, high_matches, duration_seconds, timestamp}
    """
    start = time.time()
    profile = get_profile()

    print("\n" + "=" * 60)
    print(f" OpenClaw search run — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # Run non-Gemini searchers in parallel, Gemini-based ones sequentially
    # to avoid rate limiting on the grounding API
    parallel_searchers = [GreenhouseSearcher(), AshbySearcher(), IndeedSearcher(), WellfoundSearcher()]
    sequential_searchers = [LinkedInSearcher(), FundedStartupsSearcher()]

    all_listings = []

    print("\n[pipeline] Running parallel scrapers (Greenhouse, Ashby, Indeed, Wellfound)...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(s.search, profile): s.name for s in parallel_searchers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results = future.result()
                all_listings.extend(results)
                print(f"[pipeline] {name}: {len(results)} listings")
            except Exception as exc:
                print(f"[pipeline] {name} failed: {exc}")

    print("\n[pipeline] Running Gemini-powered searchers (LinkedIn, FundedStartups)...")
    for searcher in sequential_searchers:
        try:
            results = searcher.search(profile)
            all_listings.extend(results)
            print(f"[pipeline] {searcher.name}: {len(results)} listings")
        except Exception as exc:
            print(f"[pipeline] {searcher.name} failed: {exc}")

    total_found = len(all_listings)
    print(f"\n[pipeline] Total raw listings: {total_found}")

    if dry_run:
        print("\n[pipeline] DRY RUN — skipping Gemini scoring and Excel write")
        for job in all_listings[:20]:
            print(f"  [{job.source}] {job.title} @ {job.company} — {job.location}")
        return {"added": 0, "total_found": total_found, "high_matches": 0, "duration_seconds": time.time() - start}

    # Score with Gemini
    print("\n[pipeline] Scoring listings with Gemini...")
    matches = match_jobs(all_listings, profile)

    high_matches = sum(1 for m in matches if m.score >= 80)
    print(f"[pipeline] Matches after scoring: {len(matches)} ({high_matches} high ≥80%)")

    # Write to Excel
    added = append_jobs(matches)

    duration = time.time() - start
    result = {
        "added": added,
        "total_found": total_found,
        "scored": len(matches),
        "high_matches": high_matches,
        "duration_seconds": duration,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    set_last_run_info(result)

    print(f"\n[pipeline] Done in {duration:.1f}s — {added} new jobs added to Excel")
    return result


# ── CLI Entry Points ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="OpenClaw Job Search Automation")
    parser.add_argument("--parse-only", action="store_true", help="Parse resume and print profile, then exit")
    parser.add_argument("--search-only", action="store_true", help="Run pipeline once then exit (no bot)")
    parser.add_argument("--dry-run", action="store_true", help="Search without scoring/writing, then exit")
    args = parser.parse_args()

    if args.parse_only:
        profile = load_candidate_profile()
        print("\n--- Candidate Profile ---")
        print(f"Name          : {profile.name}")
        print(f"Target Roles  : {profile.target_roles}")
        print(f"Skills        : {profile.skills}")
        print(f"Experience    : {profile.experience_years} years")
        print(f"Keywords      : {profile.search_keywords}")
        return

    if args.search_only or args.dry_run:
        run_pipeline(dry_run=args.dry_run)
        stats = get_stats()
        print(f"\nExcel stats: {stats}")
        return

    # Full mode: pipeline + Telegram bot + scheduler
    print("\n[openclaw] Starting full mode (bot + scheduler)...")

    # Pre-load profile at startup so first scheduled run is fast
    profile = get_profile()
    print(f"[openclaw] Profile loaded: {profile.name} — {', '.join(profile.target_roles)}")

    # Register the sync pipeline runner for the Telegram bot to call
    set_pipeline_runner(lambda: run_pipeline(dry_run=False))

    # Build Telegram application
    app = build_application()

    # APScheduler — daily cron
    scheduler = BackgroundScheduler()

    def scheduled_job():
        if not is_schedule_enabled():
            logger.info("[scheduler] Schedule is disabled — skipping run")
            return
        logger.info("[scheduler] Triggered daily job search run")
        result = run_pipeline(dry_run=False)

        # Try to notify Telegram (best-effort, no chat_id stored — user must /search once first)
        msg = (
            f"Daily search complete\n"
            f"Found: {result['total_found']} listings\n"
            f"New: {result['added']} added to Excel\n"
            f"High matches (≥80%): {result['high_matches']}"
        )
        logger.info(f"[scheduler] {msg}")

    scheduler.add_job(
        scheduled_job,
        trigger=CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE),
        id="daily_search",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[openclaw] Scheduler started — daily run at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}")

    # Run Telegram bot (blocking)
    print("[openclaw] Telegram bot polling started. Send /help to your bot.")
    print("[openclaw] Press Ctrl+C to stop.\n")
    app.run_polling(drop_pending_updates=True)

    scheduler.shutdown()
    print("[openclaw] Stopped.")


if __name__ == "__main__":
    main()
