"""
Telegram Bot — provides commands to control the job search pipeline.

Commands:
  /search          Trigger a full job search run now
  /status          Show last run stats and total jobs in Excel
  /jobs [n]        List the latest n jobs (default 10)
  /report          Send jobs.xlsx as a file
  /schedule on|off Enable or disable the daily scheduled run
  /help            List all commands
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from telegram import Update, Document
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

from src.config import TELEGRAM_BOT_TOKEN, EXCEL_PATH
from src.excel_manager import get_stats

logger = logging.getLogger(__name__)

# Shared state (set by main.py)
_pipeline_runner = None   # async callable: async def run_pipeline() -> dict
_schedule_enabled = True
_last_run_info: dict = {}


def set_pipeline_runner(fn):
    """Register the pipeline runner so the bot can trigger it."""
    global _pipeline_runner
    _pipeline_runner = fn


def set_last_run_info(info: dict):
    global _last_run_info
    _last_run_info = info


def is_schedule_enabled() -> bool:
    return _schedule_enabled


# ── Helpers ─────────────────────────────────────────────────────────────────

def _escape(text: str) -> str:
    """Escape special chars for MarkdownV2."""
    specials = r"\_*[]()~`>#+-=|{}.!"
    for ch in specials:
        text = text.replace(ch, f"\\{ch}")
    return text


# ── Command handlers ─────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "*OpenClaw Job Search Bot*\n\n"
        "/search — Trigger a full job search run\n"
        "/status — Show stats and last run info\n"
        "/jobs \\[n\\] — List latest n jobs \\(default 10\\)\n"
        "/report — Receive jobs\\.xlsx as a file\n"
        "/schedule on\\|off — Enable/disable daily schedule\n"
        "/help — Show this message"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if _pipeline_runner is None:
        await update.message.reply_text("Pipeline not initialised. Start main.py properly.")
        return

    await update.message.reply_text("Starting job search... this may take a few minutes.")
    try:
        result = await asyncio.get_event_loop().run_in_executor(None, _pipeline_runner)
        added = result.get("added", 0)
        total = result.get("total_found", 0)
        high = result.get("high_matches", 0)
        duration = result.get("duration_seconds", 0)

        text = (
            f"Search complete in {duration:.0f}s\n\n"
            f"Jobs found   : {total}\n"
            f"New in Excel : {added}\n"
            f"High matches (≥80%) : {high}\n\n"
            f"Use /jobs to browse or /report to download the sheet."
        )
        await update.message.reply_text(text)
    except Exception as exc:
        logger.exception("Pipeline error")
        await update.message.reply_text(f"Error during search: {exc}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_stats()
    last_run = _last_run_info.get("timestamp", "Never")
    schedule_state = "ON" if _schedule_enabled else "OFF"

    lines = [
        f"Schedule   : {schedule_state}",
        f"Last run   : {last_run}",
        f"Total jobs : {stats['total']}",
        f"New        : {stats.get('new', 0)}",
        f"Applied    : {stats.get('applied', 0)}",
        f"Excel path : {stats['path']}",
    ]
    await update.message.reply_text("\n".join(lines))


async def cmd_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import openpyxl
    from src.config import EXCEL_COLUMNS

    n = 10
    if context.args:
        try:
            n = int(context.args[0])
        except ValueError:
            pass
    n = min(n, 30)  # cap at 30

    if not EXCEL_PATH.exists():
        await update.message.reply_text("No jobs.xlsx found yet. Run /search first.")
        return

    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
    ws = wb.active
    title_idx = EXCEL_COLUMNS.index("Job Title")
    company_idx = EXCEL_COLUMNS.index("Company")
    score_idx = EXCEL_COLUMNS.index("Match Score")
    url_idx = EXCEL_COLUMNS.index("URL")
    status_idx = EXCEL_COLUMNS.index("Status")

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    # Latest jobs = last n rows
    latest = rows[-n:] if len(rows) >= n else rows
    latest = list(reversed(latest))  # most recent first

    if not latest:
        await update.message.reply_text("No jobs found yet. Run /search first.")
        return

    lines = [f"Latest {len(latest)} jobs:\n"]
    for row in latest:
        title = row[title_idx] or ""
        company = row[company_idx] or ""
        score = row[score_idx] or 0
        url = row[url_idx] or ""
        status = row[status_idx] or "New"
        lines.append(f"{score}% | {title} @ {company} [{status}]\n{url}\n")

    await update.message.reply_text("\n".join(lines)[:4000])


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not EXCEL_PATH.exists():
        await update.message.reply_text("No jobs.xlsx found yet. Run /search first.")
        return

    await update.message.reply_document(
        document=open(EXCEL_PATH, "rb"),
        filename="jobs.xlsx",
        caption=f"jobs.xlsx — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global _schedule_enabled
    if not context.args:
        state = "ON" if _schedule_enabled else "OFF"
        await update.message.reply_text(f"Daily schedule is currently {state}.\nUse /schedule on or /schedule off")
        return

    arg = context.args[0].lower()
    if arg == "on":
        _schedule_enabled = True
        await update.message.reply_text("Daily schedule ENABLED. Runs every day at 9 AM.")
    elif arg == "off":
        _schedule_enabled = False
        await update.message.reply_text("Daily schedule DISABLED.")
    else:
        await update.message.reply_text("Usage: /schedule on  or  /schedule off")


# ── Bot builder ──────────────────────────────────────────────────────────────

def build_application() -> Application:
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("jobs", cmd_jobs))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    return app


async def send_notification(app: Application, chat_id: int, text: str):
    """Send a proactive notification message to a specific chat."""
    try:
        await app.bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:
        logger.error(f"Failed to send Telegram notification: {exc}")
