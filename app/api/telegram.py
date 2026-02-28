import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import Agent
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.listing import Listing, ListingStatus
from app.services.lead_qualifier import get_auto_reply, qualify_lead
from app.services.notifications import notify_agent_qualified_lead
from app.services.social_media import post_listing_to_all_platforms
from app.services.telegram_service import (
    get_file_url,
    parse_telegram_update,
    send_telegram_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["telegram"])

HELP_MESSAGE = """
🤖 *Real Estate Bot Commands*

*POST* <description> — Create a listing from attached media and post to all connected social platforms. Send a photo/video with the caption `POST description` or just send the text.

*LIST* — View your 5 most recent active listings.

*LEADS* — See your recent leads summary.

*PERFORMANCE* — View your weekly performance stats.

*HELP* — Show this help message.

Any other message is treated as a lead enquiry and will be auto-qualified by AI.
"""


@router.post("/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    parsed = parse_telegram_update(body)

    chat_id = parsed["chat_id"]
    text = parsed["text"].strip()
    text_upper = text.upper()

    if not chat_id:
        return JSONResponse({"ok": True})

    # Check if sender is a registered agent
    agent = db.query(Agent).filter(Agent.telegram_chat_id == chat_id).first()

    if agent:
        reply = _handle_agent_message(agent, text, text_upper, parsed, db)
    else:
        reply = _handle_lead_message(chat_id, text, parsed, db)

    send_telegram_message(chat_id, reply)
    return JSONResponse({"ok": True})


def _handle_agent_message(agent, text: str, text_upper: str, parsed: dict, db: Session) -> str:
    has_media = bool(parsed["media_file_ids"])
    if text_upper.startswith("POST") or (has_media and not any(
        text_upper == cmd for cmd in ("LIST", "LEADS", "PERFORMANCE", "HELP", "/HELP", "/START")
    )):
        return _handle_post_command(agent, text, parsed, db)
    elif text_upper == "LIST":
        return _handle_list_command(agent, db)
    elif text_upper == "LEADS":
        return _handle_leads_command(agent, db)
    elif text_upper == "PERFORMANCE":
        return _handle_performance_command(agent, db)
    elif text_upper in ("HELP", "/HELP", "/START"):
        return HELP_MESSAGE
    else:
        return (
            f"Hi {agent.name}! I didn't recognise that command.\n\n"
            "Send *HELP* to see available commands."
        )


def _handle_post_command(agent, text: str, parsed: dict, db: Session) -> str:
    # Extract description: text after "POST " or the full caption/text if media present
    if text.strip().upper().startswith("POST"):
        description = text[4:].strip() if len(text) > 4 else "New property listing"
    else:
        description = text.strip() or "New property listing"

    # Resolve Telegram file IDs to public URLs
    media_urls = []
    for file_id in parsed.get("media_file_ids", []):
        url = get_file_url(file_id)
        if url:
            media_urls.append(url)

    listing = Listing(
        agent_id=agent.id,
        address="To be updated",
        price=0.0,
        description=description,
        media_urls=json.dumps(media_urls),
        status=ListingStatus.ACTIVE,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)

    results = post_listing_to_all_platforms(listing, agent, db)

    platforms_posted = [p for p, v in results.items() if v != "error"]
    platforms_failed = [p for p, v in results.items() if v == "error"]

    reply_lines = [f"✅ Listing #{listing.id} created and posted!"]
    if platforms_posted:
        reply_lines.append(f"📱 Posted to: {', '.join(platforms_posted)}")
    if platforms_failed:
        reply_lines.append(f"⚠️ Failed on: {', '.join(platforms_failed)}")
    if not results:
        reply_lines.append(
            "ℹ️ No social accounts connected yet. Visit your portal to connect them."
        )

    return "\n".join(reply_lines)


def _handle_list_command(agent, db: Session) -> str:
    listings = (
        db.query(Listing)
        .filter(Listing.agent_id == agent.id, Listing.status == ListingStatus.ACTIVE)
        .order_by(Listing.created_at.desc())
        .limit(5)
        .all()
    )
    if not listings:
        return "You have no active listings."

    lines = [f"🏠 *Your Active Listings* ({len(listings)} shown)\n"]
    for lst in listings:
        platforms = json.loads(lst.posted_platforms or "[]")
        lines.append(
            f"#{lst.id} — {lst.address}\n"
            f"   💰 ${lst.price:,.0f} | Posted: {', '.join(platforms) or 'nowhere'}"
        )
    return "\n".join(lines)


def _handle_leads_command(agent, db: Session) -> str:
    leads = (
        db.query(Lead)
        .filter(Lead.agent_id == agent.id)
        .order_by(Lead.created_at.desc())
        .limit(5)
        .all()
    )
    total = db.query(Lead).filter(Lead.agent_id == agent.id).count()
    qualified = (
        db.query(Lead)
        .filter(Lead.agent_id == agent.id, Lead.status == LeadStatus.QUALIFIED)
        .count()
    )

    if not leads:
        return "You have no leads yet."

    lines = [f"👥 *Recent Leads* (Total: {total}, Qualified: {qualified})\n"]
    for lead in leads:
        lines.append(
            f"{lead.first_name} {lead.last_name} — {lead.status.value.upper()}\n"
            f"   📞 {lead.phone or 'N/A'} | Score: {lead.qualification_score:.0f}/100"
        )
    return "\n".join(lines)


def _handle_performance_command(agent, db: Session) -> str:
    from app.services.reporting import format_report_message, generate_weekly_report

    report = generate_weekly_report(agent.id, db)
    return format_report_message(report, agent.name)


def _handle_lead_message(chat_id: str, text: str, parsed: dict, db: Session) -> str:
    """Handle a message from an unregistered Telegram user (treat as a lead).

    Assigns the lead to the first active agent. In production, route by
    campaign, phone number, or custom logic instead.
    """
    default_agent = db.query(Agent).filter(Agent.is_active.is_(True)).first()
    if default_agent is None:
        return "Thank you for your message! An agent will be in touch shortly."

    existing_lead = (
        db.query(Lead)
        .filter(Lead.phone == chat_id, Lead.agent_id == default_agent.id)
        .first()
    )

    if existing_lead:
        prev_convo = existing_lead.conversation_text or ""
        existing_lead.conversation_text = prev_convo + f"\nLead: {text}"
        db.commit()
        lead = existing_lead
    else:
        first_name = parsed.get("first_name", "Unknown")
        last_name = parsed.get("last_name", "Unknown") or "Unknown"
        lead = Lead(
            agent_id=default_agent.id,
            first_name=first_name,
            last_name=last_name,
            phone=chat_id,
            source=LeadSource.TELEGRAM,
            conversation_text=f"Lead: {text}",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)

    qualification = qualify_lead(lead.conversation_text or text)
    lead.qualification_score = float(qualification.get("qualification_score", 0))
    lead.is_serious = bool(qualification.get("is_serious", False))
    lead.ai_analysis = qualification.get("reasoning", "")

    if lead.is_serious:
        lead.status = LeadStatus.QUALIFIED
        db.commit()
        notify_agent_qualified_lead(default_agent, lead, db)
    else:
        db.commit()

    return get_auto_reply(text)
