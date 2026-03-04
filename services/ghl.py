"""
Go High Level (GHL) API Client
Handles contact look-ups, conversation creation, and outbound DM sending
via the GHL v2 REST API.

GHL API base: https://services.leadconnectorhq.com
Docs:         https://highlevel.stoplight.io/docs/integrations/

Required .env variables
───────────────────────
GHL_API_KEY       – Private Integration Key or Agency API key from
                    GHL Settings → Integrations → Private Integrations.
GHL_LOCATION_ID   – The sub-account / Location ID the bot operates under.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

GHL_BASE_URL = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"


def _headers() -> dict[str, str]:
    """Build standard GHL request headers."""
    return {
        "Authorization": f"Bearer {config.GHL_API_KEY}",
        "Content-Type": "application/json",
        "Version": GHL_API_VERSION,
    }


def is_configured() -> bool:
    """Return True if the minimum GHL credentials are present in config."""
    return bool(config.GHL_API_KEY and config.GHL_LOCATION_ID)


# ── Contacts ──────────────────────────────────────────────────────────────────

def get_contact(contact_id: str) -> Optional[dict]:
    """
    Fetch a GHL contact by ID.

    Returns the contact dict on success, or None on failure.
    """
    if not is_configured():
        logger.warning("GHL credentials not configured – skipping get_contact.")
        return None
    try:
        resp = requests.get(
            f"{GHL_BASE_URL}/contacts/{contact_id}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("contact", resp.json())
    except requests.RequestException as exc:
        logger.error("GHL get_contact(%s) failed: %s", contact_id, exc)
        return None


def get_or_create_contact(
    *,
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    source: str = "real-estate-bot",
) -> Optional[dict]:
    """
    Look up an existing GHL contact by phone/email, or create one if not found.

    Returns the contact dict (always has at least 'id') or None on error.
    """
    if not is_configured():
        logger.warning("GHL credentials not configured – skipping get_or_create_contact.")
        return None

    # Try to find an existing contact by phone or email
    search_query = phone or email
    if search_query:
        try:
            resp = requests.get(
                f"{GHL_BASE_URL}/contacts/",
                headers=_headers(),
                params={"locationId": config.GHL_LOCATION_ID, "query": search_query},
                timeout=15,
            )
            resp.raise_for_status()
            contacts = resp.json().get("contacts", [])
            if contacts:
                logger.info("GHL found existing contact for %s", search_query)
                return contacts[0]
        except requests.RequestException as exc:
            logger.error("GHL contact search failed: %s", exc)

    # Create a new contact
    try:
        payload: dict = {
            "locationId": config.GHL_LOCATION_ID,
            "source": source,
        }
        if first_name:
            payload["firstName"] = first_name
        if last_name:
            payload["lastName"] = last_name
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone

        resp = requests.post(
            f"{GHL_BASE_URL}/contacts/",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        contact = resp.json().get("contact", resp.json())
        logger.info("GHL created contact id=%s", contact.get("id"))
        return contact
    except requests.RequestException as exc:
        logger.error("GHL create_contact failed: %s", exc)
        return None


# ── Conversations / Messages ──────────────────────────────────────────────────

def send_dm(contact_id: str, message: str, message_type: str = "SMS") -> dict:
    """
    Send an outbound DM to a GHL contact.

    Parameters
    ----------
    contact_id   : GHL contact ID to send to.
    message      : Plain-text message body.
    message_type : 'SMS', 'Email', 'Live_Chat', 'WhatsApp', 'FB', 'IG', etc.
                   Default is 'SMS'.  GHL will route via whatever channel the
                   conversation is linked to if you pass the conversationId.

    Returns a dict with 'success' bool and 'messageId' or 'error'.
    """
    if not is_configured():
        return {"success": False, "error": "GHL credentials not configured"}

    try:
        payload = {
            "type": message_type,
            "contactId": contact_id,
            "locationId": config.GHL_LOCATION_ID,
            "message": message,
        }
        resp = requests.post(
            f"{GHL_BASE_URL}/conversations/messages",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        message_id = data.get("messageId") or data.get("id", "")
        logger.info("GHL DM sent to contact %s, messageId=%s", contact_id, message_id)
        return {"success": True, "messageId": message_id}
    except requests.RequestException as exc:
        logger.error("GHL send_dm to %s failed: %s", contact_id, exc)
        return {"success": False, "error": str(exc)}


def send_dm_to_conversation(conversation_id: str, message: str, message_type: str = "SMS") -> dict:
    """
    Send an outbound DM into an existing GHL conversation thread.

    This preserves the channel context (the reply will come from the same
    social channel or SMS the lead used to contact you).

    Returns a dict with 'success' bool and 'messageId' or 'error'.
    """
    if not is_configured():
        return {"success": False, "error": "GHL credentials not configured"}

    try:
        payload = {
            "type": message_type,
            "message": message,
            "conversationId": conversation_id,
        }
        resp = requests.post(
            f"{GHL_BASE_URL}/conversations/messages",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        message_id = data.get("messageId") or data.get("id", "")
        logger.info("GHL DM into conv %s sent, messageId=%s", conversation_id, message_id)
        return {"success": True, "messageId": message_id}
    except requests.RequestException as exc:
        logger.error("GHL send_dm_to_conversation(%s) failed: %s", conversation_id, exc)
        return {"success": False, "error": str(exc)}
