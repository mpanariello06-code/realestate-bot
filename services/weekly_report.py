"""
Weekly Report Generator
Compiles performance metrics and sends them to all configured agents
via Telegram.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import config
from services.sheets import get_leads, get_performance

logger = logging.getLogger(__name__)


def _build_report_text() -> str:
    """Build the weekly report as a Telegram-formatted text string."""
    today = datetime.now(timezone.utc)
    week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    week_end = today.strftime("%Y-%m-%d")

    leads = get_leads()
    perf_records = get_performance(weeks=1)

    # ── Lead metrics ──────────────────────────────────────────────────────────
    total_leads = len(leads)
    qualified_leads = [l for l in leads if str(l.get("is_qualified", "")).upper() == "TRUE"]
    n_qualified = len(qualified_leads)
    contacted = [l for l in leads if l.get("status") in ("contacted", "closed")]
    n_contacted = len(contacted)
    n_closed = len([l for l in leads if l.get("status") == "closed"])
    conversion_rate = round((n_closed / total_leads * 100), 1) if total_leads else 0

    # ── Platform metrics ──────────────────────────────────────────────────────
    platform_lines = []
    for rec in perf_records:
        platform = rec.get("platform", "N/A")
        followers = rec.get("followers", 0)
        engagement = rec.get("engagement_rate", 0)
        response_time = rec.get("avg_response_time", 0)
        platform_lines.append(
            f"  • {platform.title()}: {followers:,} followers | "
            f"{engagement}% engagement | {response_time} min avg response"
        )

    platform_section = "\n".join(platform_lines) if platform_lines else "  No platform data recorded yet."

    report = (
        f"📊 *Weekly Performance Report*\n"
        f"📅 {week_start} → {week_end}\n"
        f"{'─' * 32}\n\n"
        f"*🏠 Lead Summary*\n"
        f"  • Total leads: *{total_leads}*\n"
        f"  • Qualified: *{n_qualified}*\n"
        f"  • Contacted: *{n_contacted}*\n"
        f"  • Deals closed: *{n_closed}*\n"
        f"  • Conversion rate: *{conversion_rate}%*\n\n"
        f"*📱 Platform Performance*\n"
        f"{platform_section}\n\n"
        f"*🎯 Key Takeaway*\n"
        f"  You have *{n_qualified - n_contacted}* qualified lead(s) still "
        f"waiting to be contacted. Follow up now to close more deals! 🚀"
    )
    return report


async def send_weekly_report(bot) -> None:
    """
    Generate the weekly report and send it to all agent chat IDs.

    Parameters
    ----------
    bot : telegram.Bot
        An initialised python-telegram-bot Bot instance.
    """
    report_text = _build_report_text()
    for chat_id in config.AGENT_CHAT_IDS:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=report_text,
                parse_mode="Markdown",
            )
            logger.info("Weekly report sent to agent %s", chat_id)
        except Exception as exc:
            logger.error("Failed to send report to %s: %s", chat_id, exc)
