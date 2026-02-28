import json
import logging

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agent import Agent
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.listing import Listing, ListingStatus
from app.services.lead_qualifier import get_auto_reply, qualify_lead
from app.services.notifications import notify_agent_qualified_lead
from app.services.social_media import post_listing_to_all_platforms
from app.services.whatsapp_service import parse_incoming_message, send_whatsapp_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["whatsapp"])

HELP_MESSAGE = """
🤖 *Real Estate Bot Commands*

*POST* <description> — Create a listing from attached media and post to all your connected social platforms.

*LIST* — View your active listings.

*LEADS* — See your recent leads summary.

*PERFORMANCE* — View your performance stats.

*HELP* — Show this help message.

Any other message is treated as a lead enquiry and will be auto-qualified by AI.
"""


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    parsed = parse_incoming_message(dict(form_data))

    from_number = parsed["from"]
    body = parsed["body"].strip()
    body_upper = body.upper()

    # Check if sender is a registered agent
    agent = db.query(Agent).filter(Agent.whatsapp_number == from_number).first()

    if agent:
        reply = _handle_agent_message(agent, body, body_upper, parsed, db)
    else:
        reply = _handle_lead_message(from_number, body, parsed, db)

    # Return TwiML response so Twilio delivers the reply
    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{_escape_xml(reply)}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")


def _handle_agent_message(agent, body: str, body_upper: str, parsed: dict, db: Session) -> str:
    if body_upper.startswith("POST"):
        return _handle_post_command(agent, body, parsed, db)
    elif body_upper == "LIST":
        return _handle_list_command(agent, db)
    elif body_upper == "LEADS":
        return _handle_leads_command(agent, db)
    elif body_upper == "PERFORMANCE":
        return _handle_performance_command(agent, db)
    elif body_upper == "HELP":
        return HELP_MESSAGE
    else:
        return (
            f"Hi {agent.name}! I didn't recognise that command.\n\n"
            "Send *HELP* to see available commands."
        )


def _handle_post_command(agent, body: str, parsed: dict, db: Session) -> str:
    # Extract description (everything after "POST")
    description = body[4:].strip() if len(body) > 4 else "New property listing"
    media_urls = [m["url"] for m in parsed.get("media_urls", [])]

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
        reply_lines.append("ℹ️ No social accounts connected yet. Visit your portal to connect them.")

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


def _handle_lead_message(from_number: str, body: str, parsed: dict, db: Session) -> str:
    """Handle an inbound message from an unknown number (treat as a lead)."""
    # For simplicity, assign to first active agent or leave unassigned
    # In production you would route by campaign/number
    default_agent = db.query(Agent).filter(Agent.is_active == True).first()  # noqa: E712
    if default_agent is None:
        return "Thank you for your message! An agent will be in touch shortly."

    # Check if this phone already has a lead
    existing_lead = (
        db.query(Lead).filter(Lead.phone == from_number, Lead.agent_id == default_agent.id).first()
    )

    if existing_lead:
        # Append to conversation
        prev_convo = existing_lead.conversation_text or ""
        existing_lead.conversation_text = prev_convo + f"\nLead: {body}"
        db.commit()
        lead = existing_lead
    else:
        lead = Lead(
            agent_id=default_agent.id,
            first_name=parsed.get("profile_name", "Unknown").split()[0],
            last_name=" ".join(parsed.get("profile_name", "Unknown").split()[1:]) or "Unknown",
            phone=from_number,
            source=LeadSource.WHATSAPP,
            conversation_text=f"Lead: {body}",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)

    # Qualify with AI
    qualification = qualify_lead(lead.conversation_text or body)
    lead.qualification_score = float(qualification.get("qualification_score", 0))
    lead.is_serious = bool(qualification.get("is_serious", False))
    lead.ai_analysis = qualification.get("reasoning", "")

    if lead.is_serious:
        lead.status = LeadStatus.QUALIFIED
        db.commit()
        notify_agent_qualified_lead(default_agent, lead, db)
    else:
        db.commit()

    auto_reply = get_auto_reply(body)
    return auto_reply


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
