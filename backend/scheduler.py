"""
APScheduler-based scheduler for periodic background jobs:
  - Weekly report generation and delivery (every Monday 8am UTC)
  - Daily unresponded-lead nudge (every day at 10am UTC)
  - Daily performance snapshot
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import Agent, Lead, Listing, Performance, SessionLocal

logger = logging.getLogger(__name__)

# Module-level reference to the running Telegram Application (set at startup)
_telegram_app = None
_scheduler: Optional[AsyncIOScheduler] = None


def set_telegram_app(app) -> None:
    """Register the Telegram Application instance so the scheduler can send messages."""
    global _telegram_app
    _telegram_app = app


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------


async def generate_agent_report(agent: Agent, db) -> str:
    """
    Build a formatted weekly report string for the given agent.

    Args:
        agent: ORM Agent object.
        db: Active SQLAlchemy session.

    Returns:
        Markdown-formatted report text.
    """
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    # Fetch or create performance record for this week
    perf = (
        db.query(Performance)
        .filter(Performance.agent_id == agent.id, Performance.week_start >= week_start)
        .first()
    )

    if not perf:
        # Create a fresh snapshot from current data
        perf = _build_performance_snapshot(agent, db, week_start)
        db.add(perf)
        db.commit()
        db.refresh(perf)

    # Top listing (most leads this week)
    top_listing_title = "N/A"
    top_listing = (
        db.query(Listing)
        .join(Lead, Lead.listing_id == Listing.id)
        .filter(Listing.agent_id == agent.id, Lead.created_at >= week_start)
        .group_by(Listing.id)
        .order_by(Lead.id.desc())
        .first()
    )
    if top_listing:
        top_listing_title = top_listing.title

    report = (
        f"📊 *Weekly Performance Report*\n"
        f"_{week_start.strftime('%b %d')} – {now.strftime('%b %d, %Y')}_\n\n"
        f"👤 Agent: *{agent.name}*\n\n"
        f"📥 *Leads This Week:* {perf.leads_count}\n"
        f"⭐ *Qualified Leads:* {perf.qualified_leads}\n"
        f"🤝 *Deals Closed:* {perf.deals_closed}\n"
        f"⏱ *Avg Response Time:* {perf.avg_response_time_minutes:.1f} min\n\n"
        f"👥 *Followers*\n"
        f"  📘 Facebook: {perf.followers_facebook}\n"
        f"  📸 Instagram: {perf.followers_instagram}\n"
        f"  🎵 TikTok: {perf.followers_tiktok}\n\n"
        f"🏆 *Top Listing:* {top_listing_title}\n\n"
        f"Keep up the great work! 🚀"
    )
    return report


def _build_performance_snapshot(agent: Agent, db, week_start: datetime) -> Performance:
    """Create a Performance record from current DB data for the given week."""
    leads_this_week = (
        db.query(Lead)
        .filter(Lead.agent_id == agent.id, Lead.created_at >= week_start)
        .all()
    )

    leads_count = len(leads_this_week)
    qualified = sum(1 for l in leads_this_week if l.qualification_status == "qualified")
    deals_closed = sum(
        1
        for l in leads_this_week
        if l.qualification_status == "called"
    )

    # Average response time: time between lead creation and first update (naive approximation)
    response_times = []
    for lead in leads_this_week:
        if lead.updated_at and lead.created_at and lead.updated_at > lead.created_at:
            delta = (lead.updated_at - lead.created_at).total_seconds() / 60
            response_times.append(delta)
    avg_response = sum(response_times) / len(response_times) if response_times else 0.0

    return Performance(
        agent_id=agent.id,
        week_start=week_start,
        leads_count=leads_count,
        qualified_leads=qualified,
        deals_closed=deals_closed,
        avg_response_time_minutes=avg_response,
    )


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------


async def job_send_weekly_reports() -> None:
    """Send weekly performance reports to all active agents via Telegram."""
    if _telegram_app is None:
        logger.warning("Telegram app not set – skipping weekly report send")
        return

    db = SessionLocal()
    try:
        agents = db.query(Agent).filter(Agent.is_active.is_(True)).all()
        for agent in agents:
            try:
                report = await generate_agent_report(agent, db)
                await _telegram_app.bot.send_message(
                    chat_id=agent.telegram_id,
                    text=report,
                    parse_mode="Markdown",
                )
                # Mark report as sent
                now = datetime.now(timezone.utc)
                week_start = now - timedelta(days=now.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                perf = (
                    db.query(Performance)
                    .filter(
                        Performance.agent_id == agent.id,
                        Performance.week_start >= week_start,
                    )
                    .first()
                )
                if perf:
                    perf.report_sent = True
                    db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to send weekly report to agent %s: %s", agent.id, exc)
    finally:
        db.close()


async def job_nudge_unresponded_leads() -> None:
    """
    Notify agents about leads older than 2 hours that have not been acted upon.
    """
    if _telegram_app is None:
        return

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        stale_leads = (
            db.query(Lead)
            .filter(
                Lead.qualification_status == "new",
                Lead.created_at <= cutoff,
                Lead.is_notified.is_(True),  # already notified, now nudging
            )
            .all()
        )

        # Group by agent to avoid spamming
        by_agent: dict[int, list] = {}
        for lead in stale_leads:
            by_agent.setdefault(lead.agent_id, []).append(lead)

        for agent_id, leads in by_agent.items():
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                continue
            try:
                await _telegram_app.bot.send_message(
                    chat_id=agent.telegram_id,
                    text=(
                        f"⏰ *Reminder:* You have {len(leads)} unresponded lead(s) "
                        "waiting for over 2 hours.\n\nUse /leads to review them.",
                    ),
                    parse_mode="Markdown",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Nudge failed for agent %s: %s", agent_id, exc)
    finally:
        db.close()


async def job_daily_performance_snapshot() -> None:
    """Take a daily performance snapshot for all agents (updates current week record)."""
    db = SessionLocal()
    try:
        agents = db.query(Agent).filter(Agent.is_active.is_(True)).all()
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        for agent in agents:
            existing = (
                db.query(Performance)
                .filter(
                    Performance.agent_id == agent.id,
                    Performance.week_start >= week_start,
                )
                .first()
            )
            if existing:
                # Refresh counts
                snapshot = _build_performance_snapshot(agent, db, week_start)
                existing.leads_count = snapshot.leads_count
                existing.qualified_leads = snapshot.qualified_leads
                existing.deals_closed = snapshot.deals_closed
                existing.avg_response_time_minutes = snapshot.avg_response_time_minutes
            else:
                snapshot = _build_performance_snapshot(agent, db, week_start)
                db.add(snapshot)
        db.commit()
        logger.info("Daily performance snapshot completed for %d agents", len(agents))
    except Exception as exc:  # noqa: BLE001
        logger.error("Daily snapshot job failed: %s", exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler factory
# ---------------------------------------------------------------------------


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    global _scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Weekly report: every Monday at 08:00 UTC
    scheduler.add_job(
        job_send_weekly_reports,
        CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_reports",
        replace_existing=True,
    )

    # Daily lead nudge: every day at 10:00 UTC
    scheduler.add_job(
        job_nudge_unresponded_leads,
        CronTrigger(hour=10, minute=0),
        id="daily_nudge",
        replace_existing=True,
    )

    # Daily snapshot: every day at 23:50 UTC
    scheduler.add_job(
        job_daily_performance_snapshot,
        CronTrigger(hour=23, minute=50),
        id="daily_snapshot",
        replace_existing=True,
    )

    _scheduler = scheduler
    return scheduler
