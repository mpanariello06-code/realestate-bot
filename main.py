"""
main.py – Entry point for the Real Estate Bot.

Starts three concurrent processes:
  1. Telegram bot (python-telegram-bot polling)
  2. Flask web portal (development server)
  3. APScheduler job for weekly reports
"""
from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from bot.telegram_bot import build_application
from portal.app import create_app
from services.weekly_report import send_weekly_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Weekly report scheduler ───────────────────────────────────────────────────

def _schedule_weekly_report(bot) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    hour, minute = config.WEEKLY_REPORT_TIME.split(":")
    trigger = CronTrigger(
        day_of_week=config.WEEKLY_REPORT_DAY,
        hour=int(hour),
        minute=int(minute),
        timezone="UTC",
    )

    def _run():
        asyncio.run(send_weekly_report(bot))

    scheduler.add_job(_run, trigger=trigger, id="weekly_report")
    scheduler.start()
    logger.info(
        "Weekly report scheduled for every %s at %s UTC",
        config.WEEKLY_REPORT_DAY.upper(),
        config.WEEKLY_REPORT_TIME,
    )
    return scheduler


# ── Flask thread ──────────────────────────────────────────────────────────────

def _start_flask():
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=config.FLASK_PORT,
        debug=(config.FLASK_ENV == "development"),
        use_reloader=False,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    logger.info("🏠 Starting Real Estate Bot…")

    # Build Telegram application
    application = build_application()

    # Start Flask in a background thread
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()
    logger.info("Web portal running on http://0.0.0.0:%s", config.FLASK_PORT)

    # Schedule weekly report
    scheduler = _schedule_weekly_report(application.bot)

    try:
        logger.info("Telegram bot polling started. Press Ctrl+C to stop.")
        application.run_polling(drop_pending_updates=True)
    finally:
        scheduler.shutdown(wait=False)
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
