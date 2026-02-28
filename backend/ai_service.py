"""
AI service for lead qualification and caption generation using OpenAI.
"""

import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv

from models import QualificationResult

load_dotenv()

logger = logging.getLogger(__name__)

_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Primary model; falls back to gpt-3.5-turbo if quota/availability issues arise.
_PRIMARY_MODEL = "gpt-4o-mini"
_FALLBACK_MODEL = "gpt-3.5-turbo"


def _get_client():
    """Lazily import and create the OpenAI client."""
    from openai import OpenAI  # noqa: PLC0415

    return OpenAI(api_key=_OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Lead qualification
# ---------------------------------------------------------------------------

_QUALIFICATION_SYSTEM_PROMPT = """
You are an expert real estate lead qualification assistant.
Analyze the lead's message and the listing information to determine how serious the lead is.

Scoring guidelines:
- 80-100: Highly qualified – mentions viewing appointment, financing pre-approval, specific timeline, price negotiation
- 50-79: Moderately qualified – asks specific questions about the property, location, or price
- 20-49: Low qualification – generic interest, "just browsing", vague questions
- 0-19: Not qualified – spam, irrelevant content, or no genuine interest

Return ONLY valid JSON with the following keys:
{
  "score": <integer 0-100>,
  "status": "<qualified|unqualified>",
  "notes": "<brief explanation of the score>",
  "suggested_response": "<a short, friendly response to send back to the lead>"
}
"qualified" means score >= 70.
"""


def qualify_lead(lead_message: str, listing_info: str) -> QualificationResult:
    """
    Use OpenAI to qualify a lead message against a listing.

    Args:
        lead_message: The raw message sent by the potential buyer/renter.
        listing_info: A text summary of the listing (title, price, location, etc.).

    Returns:
        A QualificationResult with score, status, notes, and suggested response.
    """
    if not _OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set – returning default unqualified result")
        return QualificationResult(
            score=0,
            status="unqualified",
            notes="OpenAI API key not configured.",
            suggested_response="Thank you for your interest! We'll be in touch shortly.",
        )

    user_content = (
        f"Listing information:\n{listing_info}\n\n"
        f"Lead message:\n{lead_message}"
    )

    for model in (_PRIMARY_MODEL, _FALLBACK_MODEL):
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _QUALIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            score = int(data.get("score", 0))
            status = "qualified" if score >= 70 else "unqualified"
            return QualificationResult(
                score=score,
                status=status,
                notes=str(data.get("notes", "")),
                suggested_response=str(data.get("suggested_response", "")),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Lead qualification failed with model %s: %s", model, exc)

    # Final fallback
    return QualificationResult(
        score=0,
        status="unqualified",
        notes="AI qualification unavailable at this time.",
        suggested_response="Thank you for reaching out! We'll contact you soon.",
    )


# ---------------------------------------------------------------------------
# Caption generation
# ---------------------------------------------------------------------------

_CAPTION_SYSTEM_PROMPT = """
You are a creative real estate social media copywriter.
Write an engaging, professional post caption for the listing details provided.
Include relevant emojis, a clear call-to-action, and keep it under 300 words.
Do NOT include hashtags – the caller will append them.
"""


def generate_listing_caption(description: str, price: str, location: str) -> str:
    """
    Generate an engaging social media caption for a property listing.

    Args:
        description: Free-text description of the property.
        price: Listing price (e.g. "$450,000").
        location: City/neighbourhood of the property.

    Returns:
        A ready-to-post caption string, or a simple fallback if AI is unavailable.
    """
    if not _OPENAI_API_KEY:
        return f"🏠 {description}\n📍 {location}\n💰 {price}\nContact us for more details!"

    user_content = (
        f"Property description: {description}\n"
        f"Price: {price}\n"
        f"Location: {location}"
    )

    for model in (_PRIMARY_MODEL, _FALLBACK_MODEL):
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _CAPTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
                max_tokens=400,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("Caption generation failed with model %s: %s", model, exc)

    return f"🏠 {description}\n📍 {location}\n💰 {price}\nContact us for more details!"
