import json
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

QUALIFICATION_PROMPT = """
You are a real estate lead qualification assistant. Analyze the following conversation
and determine if this lead is serious about buying or selling property.

Conversation:
{conversation}

Respond with a JSON object with these exact keys:
{{
  "is_serious": true or false,
  "qualification_score": integer from 0 to 100,
  "reasoning": "brief explanation",
  "lead_type": "buyer" or "seller" or "both" or "unknown",
  "urgency": "immediate" or "within_3_months" or "within_6_months" or "just_browsing" or "unknown",
  "recommended_action": "call_immediately" or "follow_up" or "nurture" or "disqualify"
}}
Respond ONLY with the JSON object, no extra text.
"""

AUTO_REPLY_PROMPT = """
You are a professional real estate assistant. Write a helpful, warm auto-reply to this lead inquiry.
Keep it concise (2-3 sentences), professional, and end with a call-to-action.

{listing_context}

Lead message:
{conversation}

Reply:
"""

_DEFAULT_QUALIFICATION = {
    "is_serious": False,
    "qualification_score": 0,
    "reasoning": "AI qualification unavailable",
    "lead_type": "unknown",
    "urgency": "unknown",
    "recommended_action": "follow_up",
}


def _get_openai_client():
    if not settings.OPENAI_API_KEY:
        logger.warning("OpenAI API key not configured. Lead qualification disabled.")
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as exc:
        logger.error("Failed to initialise OpenAI client: %s", exc)
        return None


def qualify_lead(conversation_text: str) -> dict:
    """Use OpenAI to qualify a lead based on conversation text."""
    client = _get_openai_client()
    if client is None:
        return dict(_DEFAULT_QUALIFICATION)

    prompt = QUALIFICATION_PROMPT.format(conversation=conversation_text)
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)
        # Ensure required keys exist with sane defaults
        result.setdefault("is_serious", False)
        result.setdefault("qualification_score", 0)
        result.setdefault("reasoning", "")
        result.setdefault("lead_type", "unknown")
        result.setdefault("urgency", "unknown")
        result.setdefault("recommended_action", "follow_up")
        return result
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse OpenAI JSON response: %s", exc)
        return dict(_DEFAULT_QUALIFICATION)
    except Exception as exc:
        logger.error("OpenAI qualification error: %s", exc)
        return dict(_DEFAULT_QUALIFICATION)


def get_auto_reply(conversation_text: str, listing_info: str = "") -> str:
    """Generate an AI auto-reply for a lead inquiry."""
    client = _get_openai_client()
    if client is None:
        return (
            "Thank you for your interest! One of our agents will be in touch with you shortly. "
            "Please feel free to share any additional details about what you're looking for."
        )

    listing_context = f"Listing information:\n{listing_info}" if listing_info else ""
    prompt = AUTO_REPLY_PROMPT.format(
        conversation=conversation_text,
        listing_context=listing_context,
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("OpenAI auto-reply error: %s", exc)
        return (
            "Thank you for reaching out! An agent will contact you shortly. "
            "Please share any questions or preferences you have."
        )
