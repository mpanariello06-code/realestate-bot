"""
Entry point: runs FastAPI (uvicorn) and the Telegram bot concurrently
using a single asyncio event loop.
"""

import asyncio
import logging
import os
import signal
import sys

import uvicorn
from dotenv import load_dotenv

load_dotenv()

# Configure logging before importing application modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _check_env() -> None:
    """Warn about missing critical environment variables."""
    required = ["TELEGRAM_BOT_TOKEN", "SECRET_KEY"]
    for var in required:
        if not os.getenv(var):
            logger.warning("Environment variable %s is not set", var)


async def main() -> None:
    _check_env()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    api_host = os.getenv("API_HOST", "0.0.0.0")
    api_port = int(os.getenv("API_PORT", "8000"))

    # -----------------------------------------------------------------------
    # Build the Telegram bot application
    # -----------------------------------------------------------------------
    from bot import build_application
    from main import app as fastapi_app
    from main import set_telegram_app
    from scheduler import create_scheduler, set_telegram_app as scheduler_set_app

    telegram_app = build_application(bot_token)

    # Share the Telegram app instance with FastAPI and the scheduler
    set_telegram_app(telegram_app)
    scheduler_set_app(telegram_app)

    # -----------------------------------------------------------------------
    # Start the scheduler
    # -----------------------------------------------------------------------
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("APScheduler started")

    # -----------------------------------------------------------------------
    # Configure uvicorn
    # -----------------------------------------------------------------------
    uvicorn_config = uvicorn.Config(
        app=fastapi_app,
        host=api_host,
        port=api_port,
        log_level="info",
        loop="none",  # We manage the event loop ourselves
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)

    # -----------------------------------------------------------------------
    # Graceful shutdown handler
    # -----------------------------------------------------------------------
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    def _handle_signal(*_) -> None:
        logger.info("Shutdown signal received")
        # Use call_soon_threadsafe so this is safe to call from a Windows
        # signal context where the function runs outside the event loop.
        loop.call_soon_threadsafe(stop_event.set)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows does not support add_signal_handler; fall back to
            # signal.signal which calls _handle_signal from a thread context.
            signal.signal(sig, _handle_signal)

    # -----------------------------------------------------------------------
    # Run both services concurrently
    # -----------------------------------------------------------------------
    logger.info("Starting FastAPI on %s:%d", api_host, api_port)
    logger.info("Starting Telegram bot (polling mode)")

    async with telegram_app:
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling(drop_pending_updates=True)

        try:
            await asyncio.gather(
                uvicorn_server.serve(),
                stop_event.wait(),
            )
        finally:
            logger.info("Stopping services…")
            scheduler.shutdown(wait=False)
            await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()
            logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
