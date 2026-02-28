import logging

logger = logging.getLogger(__name__)


def notify_agent_qualified_lead(agent, lead, db=None) -> None:
    """Send a WhatsApp notification to an agent about a newly qualified lead."""
    from app.services.whatsapp_service import send_whatsapp_message

    message = (
        "🎯 *QUALIFIED LEAD ALERT*\n\n"
        f"Name: {lead.first_name} {lead.last_name}\n"
        f"Phone: {lead.phone or 'N/A'}\n"
        f"Email: {lead.email or 'N/A'}\n"
        f"Source: {lead.source}\n"
        f"Score: {lead.qualification_score:.0f}/100\n"
        f"Analysis: {lead.ai_analysis or 'N/A'}\n\n"
        "Please contact this lead as soon as possible! 🏠"
    )
    result = send_whatsapp_message(to=agent.whatsapp_number, body=message)
    if result:
        logger.info(
            "Qualified lead notification sent to agent %s for lead %s",
            agent.id,
            lead.id,
        )
    else:
        logger.warning(
            "Failed to send qualified lead notification to agent %s for lead %s",
            agent.id,
            lead.id,
        )


def notify_agent_new_lead(agent, lead) -> None:
    """Send a WhatsApp notification to an agent about a new (unqualified) lead."""
    from app.services.whatsapp_service import send_whatsapp_message

    message = (
        "📩 *NEW LEAD*\n\n"
        f"Name: {lead.first_name} {lead.last_name}\n"
        f"Phone: {lead.phone or 'N/A'}\n"
        f"Source: {lead.source}\n\n"
        "Lead is being analysed. You'll receive another alert if they qualify. 🔍"
    )
    send_whatsapp_message(to=agent.whatsapp_number, body=message)
