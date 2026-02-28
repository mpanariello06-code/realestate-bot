import logging

logger = logging.getLogger(__name__)


def notify_agent_qualified_lead(agent, lead, db=None) -> None:
    """Send a notification to an agent about a newly qualified lead (WhatsApp and/or Telegram)."""
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

    # Notify via WhatsApp if number is configured
    from app.services.whatsapp_service import send_whatsapp_message
    result = send_whatsapp_message(to=agent.whatsapp_number, body=message)
    if result:
        logger.info(
            "WhatsApp qualified-lead notification sent to agent %s for lead %s",
            agent.id,
            lead.id,
        )
    else:
        logger.warning(
            "Failed to send WhatsApp notification to agent %s for lead %s",
            agent.id,
            lead.id,
        )

    # Notify via Telegram if chat ID is configured
    if getattr(agent, "telegram_chat_id", None):
        from app.services.telegram_service import send_telegram_message
        tg_ok = send_telegram_message(chat_id=agent.telegram_chat_id, text=message)
        if tg_ok:
            logger.info(
                "Telegram qualified-lead notification sent to agent %s for lead %s",
                agent.id,
                lead.id,
            )
        else:
            logger.warning(
                "Failed to send Telegram notification to agent %s for lead %s",
                agent.id,
                lead.id,
            )


def notify_agent_new_lead(agent, lead) -> None:
    """Send a notification to an agent about a new (unqualified) lead."""
    message = (
        "📩 *NEW LEAD*\n\n"
        f"Name: {lead.first_name} {lead.last_name}\n"
        f"Phone: {lead.phone or 'N/A'}\n"
        f"Source: {lead.source}\n\n"
        "Lead is being analysed. You'll receive another alert if they qualify. 🔍"
    )

    from app.services.whatsapp_service import send_whatsapp_message
    send_whatsapp_message(to=agent.whatsapp_number, body=message)

    if getattr(agent, "telegram_chat_id", None):
        from app.services.telegram_service import send_telegram_message
        send_telegram_message(chat_id=agent.telegram_chat_id, text=message)
