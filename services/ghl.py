"""
Go High Level (GHL) API Client
Handles contact look-ups, conversation creation, outbound DM sending,
and Social Planner posting via the GHL v2 REST API.

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
import os
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)

GHL_BASE_URL = "https://services.leadconnectorhq.com"
GHL_API_VERSION = "2021-07-28"

# ── Token management ──────────────────────────────────────────────────────────

# Holds a refreshed access token when auto-refresh has succeeded.
# Falls back to config.GHL_API_KEY when empty.
_access_token: str = ""

_AUTH_HELP = (
    "GHL API key is invalid or expired (401 Unauthorized). "
    "Please regenerate your Private Integration key in "
    "GHL → Settings → Integrations → Private Integrations "
    "and update GHL_API_KEY in your .env file. "
    "To enable automatic token refresh, also set "
    "GHL_CLIENT_ID, GHL_CLIENT_SECRET and GHL_REFRESH_TOKEN in .env."
)


def _current_token() -> str:
    """Return the active access token (refreshed or configured)."""
    return _access_token or config.GHL_API_KEY


def _is_auth_error(exc: requests.RequestException) -> bool:
    """Return True if *exc* is a 401 Unauthorized HTTP error."""
    response = getattr(exc, "response", None)
    return response is not None and response.status_code == 401


def _can_refresh() -> bool:
    """Return True if OAuth2 refresh credentials are configured."""
    return bool(
        config.GHL_CLIENT_ID
        and config.GHL_CLIENT_SECRET
        and config.GHL_REFRESH_TOKEN
    )


def _refresh_access_token() -> bool:
    """
    Refresh the GHL access token using the stored OAuth2 refresh token.

    Updates the module-level ``_access_token`` on success.
    Returns True if a new token was obtained, False otherwise.
    """
    global _access_token
    if not _can_refresh():
        return False
    try:
        resp = requests.post(
            f"{GHL_BASE_URL}/oauth/token",
            data={
                "client_id": config.GHL_CLIENT_ID,
                "client_secret": config.GHL_CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": config.GHL_REFRESH_TOKEN,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        new_token = data.get("access_token", "")
        if new_token:
            _access_token = new_token
            # Store the new refresh token if one was returned
            new_refresh = data.get("refresh_token", "")
            if new_refresh:
                config.GHL_REFRESH_TOKEN = new_refresh
            logger.info("GHL access token refreshed successfully.")
            return True
        return False
    except Exception as exc:
        logger.error("GHL token refresh failed: %s", exc)
        return False


def _do_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Make a GHL API request, automatically retrying once on 401 after a token
    refresh when OAuth2 refresh credentials are configured.

    Parameters
    ----------
    method : str
        HTTP method string to use (e.g. 'get', 'post').
    url : str
        Full request URL.
    **kwargs :
        Additional keyword arguments forwarded to ``requests.<method>()``.

    Injects the standard GHL auth headers unless the caller supplies its own
    ``headers`` kwarg (e.g. for multipart file uploads).

    Raises ``requests.RequestException`` (including ``HTTPError``) on failure.
    """
    if "headers" not in kwargs:
        kwargs["headers"] = _headers()
    fn = getattr(requests, method)
    resp = fn(url, **kwargs)
    if resp.status_code == 401 and _can_refresh():
        logger.info("GHL 401 – attempting token refresh and retry…")
        if _refresh_access_token():
            kwargs["headers"] = _headers()
            resp = fn(url, **kwargs)
    resp.raise_for_status()
    return resp


def _headers() -> dict[str, str]:
    """Build standard GHL request headers."""
    return {
        "Authorization": f"Bearer {_current_token()}",
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
        resp = _do_request(
            "get",
            f"{GHL_BASE_URL}/contacts/{contact_id}",
            timeout=15,
        )
        return resp.json().get("contact", resp.json())
    except requests.RequestException as exc:
        msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
        logger.error("GHL get_contact(%s) failed: %s", contact_id, msg)
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
            resp = _do_request(
                "get",
                f"{GHL_BASE_URL}/contacts/",
                params={"locationId": config.GHL_LOCATION_ID, "query": search_query},
                timeout=15,
            )
            contacts = resp.json().get("contacts", [])
            if contacts:
                logger.info("GHL found existing contact for %s", search_query)
                return contacts[0]
        except requests.RequestException as exc:
            msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
            logger.error("GHL contact search failed: %s", msg)

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

        resp = _do_request(
            "post",
            f"{GHL_BASE_URL}/contacts/",
            json=payload,
            timeout=15,
        )
        contact = resp.json().get("contact", resp.json())
        logger.info("GHL created contact id=%s", contact.get("id"))
        return contact
    except requests.RequestException as exc:
        msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
        logger.error("GHL create_contact failed: %s", msg)
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
        resp = _do_request(
            "post",
            f"{GHL_BASE_URL}/conversations/messages",
            json=payload,
            timeout=15,
        )
        data = resp.json()
        message_id = data.get("messageId") or data.get("id", "")
        logger.info("GHL DM sent to contact %s, messageId=%s", contact_id, message_id)
        return {"success": True, "messageId": message_id}
    except requests.RequestException as exc:
        msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
        logger.error("GHL send_dm to %s failed: %s", contact_id, msg)
        return {"success": False, "error": msg}


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
        resp = _do_request(
            "post",
            f"{GHL_BASE_URL}/conversations/messages",
            json=payload,
            timeout=15,
        )
        data = resp.json()
        message_id = data.get("messageId") or data.get("id", "")
        logger.info("GHL DM into conv %s sent, messageId=%s", conversation_id, message_id)
        return {"success": True, "messageId": message_id}
    except requests.RequestException as exc:
        msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
        logger.error("GHL send_dm_to_conversation(%s) failed: %s", conversation_id, msg)
        return {"success": False, "error": msg}


# ── Social Planner ────────────────────────────────────────────────────────────

def upload_media(file_path: str) -> Optional[str]:
    """
    Upload a local image or video file to GHL media storage.

    Returns the public CDN URL on success, or None on failure.
    """
    if not is_configured():
        logger.warning("GHL credentials not configured – skipping upload_media.")
        return None
    try:
        headers = {
            "Authorization": f"Bearer {_current_token()}",
            "Version": GHL_API_VERSION,
        }
        with open(file_path, "rb") as f:
            resp = requests.post(
                f"{GHL_BASE_URL}/medias/upload-file",
                headers=headers,
                files={"file": (os.path.basename(file_path), f)},
                timeout=60,
            )
        resp.raise_for_status()
        data = resp.json()
        url = data.get("url") or data.get("fileUrl", "")
        logger.info("GHL media uploaded: %s", url)
        return url or None
    except requests.RequestException as exc:
        msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
        logger.error("GHL media upload failed: %s", msg)
        return None


def get_social_accounts() -> list:
    """
    Return all social media accounts connected to this GHL location.

    Each entry has at least 'accountId' and 'type' keys (e.g. 'facebook',
    'instagram').  Returns an empty list when GHL is not configured or the
    request fails.
    """
    if not is_configured():
        return []
    try:
        resp = _do_request(
            "get",
            f"{GHL_BASE_URL}/social-media-posting/{config.GHL_LOCATION_ID}/accounts",
            timeout=15,
        )
        data = resp.json()
        accounts = data.get("accounts", data if isinstance(data, list) else [])
        return accounts
    except requests.RequestException as exc:
        msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
        logger.error("GHL get_social_accounts failed: %s", msg)
        return []


def post_to_social_planner(
    caption: str,
    image_path: Optional[str] = None,
) -> dict:
    """
    Publish a post via GHL Social Planner to all connected Facebook and
    Instagram accounts for this location.

    If *image_path* is provided, the image is uploaded to GHL's CDN first
    and attached to the post.  Text-only posts work without an image.

    If ``GHL_SOCIAL_ACCOUNT_IDS`` is set in the environment, only those
    accounts are targeted; otherwise all connected accounts are used.

    Returns a dict with 'success' bool and 'post_id' or 'error'.
    """
    if not is_configured():
        return {"success": False, "error": "GHL credentials not configured"}

    try:
        payload: dict = {
            "summary": caption,
            "status": "PUBLISHED",
        }

        # Upload media if a local file is supplied
        if image_path and os.path.exists(image_path):
            media_url = upload_media(image_path)
            if media_url:
                payload["media"] = [{"url": media_url, "type": "photo"}]

        # Resolve target accounts
        configured_ids = [
            aid.strip()
            for aid in config.GHL_SOCIAL_ACCOUNT_IDS.split(",")
            if aid.strip()
        ]
        if configured_ids:
            # User pre-configured specific account IDs.
            # Supports an optional type prefix: "fb:<id>" or "ig:<id>".
            # Without a prefix the ID is treated as a Facebook account.
            def _parse_account(raw: str) -> dict:
                if raw.startswith("fb:"):
                    return {"accountId": raw[3:], "type": "facebook"}
                if raw.startswith("ig:"):
                    return {"accountId": raw[3:], "type": "instagram"}
                return {"accountId": raw, "type": "facebook"}

            payload["accounts"] = [_parse_account(aid) for aid in configured_ids]
        else:
            # Auto-discover all connected accounts
            accounts = get_social_accounts()
            if accounts:
                payload["accounts"] = [
                    {
                        "accountId": a.get("accountId") or a.get("id", ""),
                        "type": a.get("type") or a.get("platform", "facebook"),
                    }
                    for a in accounts
                ]

        resp = _do_request(
            "post",
            f"{GHL_BASE_URL}/social-media-posting/{config.GHL_LOCATION_ID}/posts",
            json=payload,
            timeout=30,
        )
        data = resp.json()
        post_id = data.get("id") or data.get("postId", "")
        logger.info("GHL Social Planner post created: %s", post_id)
        return {"success": True, "post_id": post_id}
    except requests.RequestException as exc:
        msg = _AUTH_HELP if _is_auth_error(exc) else str(exc)
        logger.error("GHL Social Planner post failed: %s", msg)
        return {"success": False, "error": msg}
