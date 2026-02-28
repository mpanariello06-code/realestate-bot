import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.lead import Lead, LeadStatus
from app.models.listing import Listing, ListingStatus
from app.models.performance import PerformanceMetric

logger = logging.getLogger(__name__)


def generate_weekly_report(agent_id: int, db: Session) -> dict:
    """Generate a weekly performance report for an agent."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday
    week_end = week_start + timedelta(days=6)
    prev_week_start = week_start - timedelta(weeks=1)
    prev_week_end = week_start - timedelta(days=1)

    current = (
        db.query(PerformanceMetric)
        .filter(
            PerformanceMetric.agent_id == agent_id,
            PerformanceMetric.week_start == week_start,
        )
        .first()
    )

    previous = (
        db.query(PerformanceMetric)
        .filter(
            PerformanceMetric.agent_id == agent_id,
            PerformanceMetric.week_start == prev_week_start,
        )
        .first()
    )

    # Live counts from DB as fallback
    total_leads = db.query(Lead).filter(Lead.agent_id == agent_id).count()
    qualified_leads = (
        db.query(Lead)
        .filter(Lead.agent_id == agent_id, Lead.status == LeadStatus.QUALIFIED)
        .count()
    )
    active_listings = (
        db.query(Listing)
        .filter(Listing.agent_id == agent_id, Listing.status == ListingStatus.ACTIVE)
        .count()
    )

    def _trend(current_val: float, previous_val: float) -> str:
        if previous_val == 0:
            return "N/A"
        change = ((current_val - previous_val) / previous_val) * 100
        arrow = "▲" if change >= 0 else "▼"
        return f"{arrow} {abs(change):.1f}%"

    report = {
        "period": f"{week_start} to {week_end}",
        "week_start": str(week_start),
        "week_end": str(week_end),
        "total_leads": current.total_leads if current else total_leads,
        "qualified_leads": current.qualified_leads if current else qualified_leads,
        "deals_closed": current.deals_closed if current else 0,
        "total_posts": current.total_posts if current else 0,
        "total_engagements": current.total_engagements if current else 0,
        "facebook_followers": current.facebook_followers if current else 0,
        "instagram_followers": current.instagram_followers if current else 0,
        "tiktok_followers": current.tiktok_followers if current else 0,
        "avg_response_time_minutes": current.avg_response_time_minutes if current else 0.0,
        "active_listings": active_listings,
        "trends": {},
    }

    if previous:
        report["trends"] = {
            "leads": _trend(report["total_leads"], previous.total_leads),
            "qualified": _trend(report["qualified_leads"], previous.qualified_leads),
            "deals": _trend(report["deals_closed"], previous.deals_closed),
            "engagements": _trend(report["total_engagements"], previous.total_engagements),
        }

    return report


def format_report_message(report: dict, agent_name: str) -> str:
    """Format a weekly report dict as a WhatsApp-friendly text message."""
    trends = report.get("trends", {})

    lines = [
        f"📊 *Weekly Performance Report for {agent_name}*",
        f"📅 {report['period']}",
        "",
        f"👥 Total Leads: {report['total_leads']} {trends.get('leads', '')}",
        f"✅ Qualified Leads: {report['qualified_leads']} {trends.get('qualified', '')}",
        f"🏡 Deals Closed: {report['deals_closed']} {trends.get('deals', '')}",
        f"📝 Active Listings: {report['active_listings']}",
        f"📱 Total Posts: {report['total_posts']}",
        f"❤️ Total Engagements: {report['total_engagements']} {trends.get('engagements', '')}",
        "",
        f"👍 Facebook Followers: {report['facebook_followers']}",
        f"📸 Instagram Followers: {report['instagram_followers']}",
        f"🎵 TikTok Followers: {report['tiktok_followers']}",
        "",
        f"⏱ Avg Response Time: {report['avg_response_time_minutes']:.1f} min",
    ]
    return "\n".join(lines)


def send_weekly_report_whatsapp(agent_id: int, db: Session) -> None:
    """Generate and send a weekly performance report to an agent via WhatsApp."""
    from app.models.agent import Agent
    from app.services.whatsapp_service import send_whatsapp_message

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        logger.warning("Agent %s not found for weekly report.", agent_id)
        return

    report = generate_weekly_report(agent_id, db)
    message = format_report_message(report, agent.name)
    send_whatsapp_message(to=agent.whatsapp_number, body=message)
    logger.info("Weekly report sent to agent %s (%s)", agent.name, agent.whatsapp_number)
