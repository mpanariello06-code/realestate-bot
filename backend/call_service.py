"""
Call-triggering service for the AI receptionist.

Supports GoHighLevel (GHL) workflows as primary and Twilio as fallback.
Also sends Telegram notifications to agents when a lead is qualified.
"""

import logging
import os
from typing import TYPE_CHECKING, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 15.0

if TYPE_CHECKING:
    from telegram.ext import Application

    from database import Agent, Lead


# ---------------------------------------------------------------------------
# GHL
# ---------------------------------------------------------------------------


async def trigger_ghl_call(lead: "Lead", agent: "Agent") -> bool:
    """
    Trigger a GoHighLevel workflow to initiate an AI-receptionist outbound call.

    The workflow is expected to accept a contact lookup (by phone/email) and
    immediately dial the lead from the agent's GHL number.

    Args:
        lead: ORM Lead object with contact details.
        agent: ORM Agent object; uses agent.ghl_contact_id for the sub-account.

    Returns:
        True on success, False on any failure.
    """
    api_key = os.getenv("GHL_API_KEY", "")
    workflow_id = os.getenv("GHL_WORKFLOW_ID", "")

    if not api_key or not workflow_id:
        logger.warning("GHL credentials not configured – skipping GHL call trigger")
        return False

    payload = {
        "workflowId": workflow_id,
        "contactPhone": lead.phone or "",
        "contactEmail": lead.email or "",
        "contactName": f"{lead.name or ''} {lead.last_name or ''}".strip(),
        "agentId": agent.ghl_contact_id or "",
        "leadId": lead.id,
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                "https://rest.gohighlevel.com/v1/workflows/trigger",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info("GHL call triggered for lead %s (agent %s)", lead.id, agent.id)
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "GHL API error for lead %s: %s – %s",
                lead.id,
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error triggering GHL call: %s", exc)

    return False


# ---------------------------------------------------------------------------
# Twilio
# ---------------------------------------------------------------------------


async def trigger_twilio_call(lead: "Lead", agent: "Agent") -> bool:
    """
    Initiate an outbound call via Twilio as a fallback to GHL.

    The call uses Twilio's REST API to dial the lead's phone number from the
    configured Twilio number.  The TwiML URL should be a pre-built IVR / AI
    receptionist flow hosted separately.

    Args:
        lead: ORM Lead object.
        agent: ORM Agent object (unused for now; reserved for per-agent numbers).

    Returns:
        True on success, False on failure.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_PHONE_NUMBER", "")
    twiml_url = os.getenv("TWILIO_TWIML_URL", "https://demo.twilio.com/welcome/voice/")

    if not account_sid or not auth_token or not from_number:
        logger.warning("Twilio credentials not configured – skipping call trigger")
        return False

    if not lead.phone:
        logger.warning("Lead %s has no phone number – cannot trigger Twilio call", lead.id)
        return False

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json",
                auth=(account_sid, auth_token),
                data={
                    "To": lead.phone,
                    "From": from_number,
                    "Url": twiml_url,
                },
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            call_sid = resp.json().get("sid")
            logger.info("Twilio call %s placed for lead %s", call_sid, lead.id)
            return True
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Twilio API error for lead %s: %s – %s",
                lead.id,
                exc.response.status_code,
                exc.response.text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error triggering Twilio call: %s", exc)

    return False


# ---------------------------------------------------------------------------
# Telegram notification
# ---------------------------------------------------------------------------


async def notify_agent_qualified_lead(
    lead: "Lead",
    agent: "Agent",
    application: Optional["Application"] = None,
) -> bool:
    """
    Send a Telegram message to the agent notifying them of a qualified lead.

    Args:
        lead: Qualified ORM Lead object.
        agent: ORM Agent who owns the lead.
        application: Running python-telegram-bot Application instance.

    Returns:
        True if message was sent, False otherwise.
    """
    if application is None:
        logger.warning("Telegram application not available – skipping agent notification")
        return False

    full_name = " ".join(filter(None, [lead.name, lead.last_name])) or "Unknown"
    score = lead.qualification_score or 0
    platform = lead.platform or "unknown"

    message = (
        f"🌟 *New Qualified Lead!*\n\n"
        f"👤 *Name:* {full_name}\n"
        f"📧 *Email:* {lead.email or 'N/A'}\n"
        f"📞 *Phone:* {lead.phone or 'N/A'}\n"
        f"🏠 *Platform:* {platform.capitalize()}\n"
        f"📊 *Score:* {score}/100\n\n"
        f"💬 *Message:*\n_{lead.message or 'N/A'}_\n\n"
        f"📝 *AI Notes:*\n{lead.qualification_notes or 'N/A'}"
    )

    try:
        await application.bot.send_message(
            chat_id=agent.telegram_id,
            text=message,
            parse_mode="Markdown",
        )
        logger.info("Sent qualified lead notification to agent %s for lead %s", agent.id, lead.id)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to send Telegram notification to agent %s: %s", agent.telegram_id, exc
        )
        return False
