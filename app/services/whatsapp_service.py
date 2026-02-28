import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _get_twilio_client():
    """Return a Twilio REST client, or None if credentials are missing."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.warning("Twilio credentials not configured. WhatsApp messaging disabled.")
        return None
    try:
        from twilio.rest import Client
        return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    except Exception as exc:
        logger.error("Failed to initialise Twilio client: %s", exc)
        return None


def send_whatsapp_message(to: str, body: str, media_url: Optional[str] = None) -> Optional[str]:
    """Send a WhatsApp message via Twilio. Returns the message SID on success."""
    client = _get_twilio_client()
    if client is None:
        logger.warning("Skipping WhatsApp send to %s – no Twilio client.", to)
        return None
    try:
        kwargs = {
            "from_": settings.TWILIO_WHATSAPP_NUMBER,
            "to": to,
            "body": body,
        }
        if media_url:
            kwargs["media_url"] = [media_url]
        message = client.messages.create(**kwargs)
        logger.info("WhatsApp message sent to %s, SID=%s", to, message.sid)
        return message.sid
    except Exception as exc:
        logger.error("Failed to send WhatsApp message to %s: %s", to, exc)
        return None


def parse_incoming_message(form_data: dict) -> dict:
    """Parse incoming Twilio WhatsApp webhook data into a normalised dict."""
    num_media = int(form_data.get("NumMedia", 0))
    media_urls = []
    for i in range(num_media):
        url = form_data.get(f"MediaUrl{i}")
        content_type = form_data.get(f"MediaContentType{i}", "")
        if url:
            media_urls.append({"url": url, "content_type": content_type})

    return {
        "from": form_data.get("From", ""),
        "to": form_data.get("To", ""),
        "body": form_data.get("Body", ""),
        "media_urls": media_urls,
        "num_media": num_media,
        "message_sid": form_data.get("MessageSid", ""),
        "profile_name": form_data.get("ProfileName", ""),
    }
