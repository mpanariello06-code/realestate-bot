"""
Lead Qualification Service
Uses OpenAI to analyse lead messages, score them, and generate
qualifying follow-up questions for serious prospects.
"""
from __future__ import annotations

import json
import logging

from openai import OpenAI

import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = """You are a real estate lead qualification assistant.
Your job is to analyse a message from a potential client and return a JSON
object with the following fields:
- score (integer 0-100): how qualified/serious the lead is
- intent ("buy" | "sell" | "rent" | "unknown"): what the lead wants
- budget (string | null): mentioned budget or price range
- timeline (string | null): how soon they want to act
- location (string | null): area or city of interest
- is_qualified (boolean): true if score >= threshold
- summary (string): one-sentence summary of the lead
- follow_up_questions (list[string]): 2-4 questions to ask to qualify further

Return ONLY valid JSON, no markdown fences or extra text."""


def qualify_lead(message: str) -> dict:
    """
    Analyse a raw lead message and return a qualification dict.

    Parameters
    ----------
    message : str
        The raw text sent by the prospective client.

    Returns
    -------
    dict with keys: score, intent, budget, timeline, location,
                    is_qualified, summary, follow_up_questions
    """
    threshold = config.LEAD_QUALIFICATION_THRESHOLD
    prompt = (
        f"Lead qualification threshold is {threshold}/100.\n\n"
        f"Lead message:\n{message}"
    )
    try:
        response = _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        result.setdefault("is_qualified", result.get("score", 0) >= threshold)
        return result
    except Exception as exc:
        logger.error("Lead qualification failed: %s", exc)
        return {
            "score": 0,
            "intent": "unknown",
            "budget": None,
            "timeline": None,
            "location": None,
            "is_qualified": False,
            "summary": "Could not analyse message",
            "follow_up_questions": [],
        }


AUTO_REPLY_SYSTEM_PROMPT = """You are a friendly, professional real estate assistant chatbot.
Your role is to help potential buyers, sellers, and renters with their property questions.
Keep responses concise (2-4 sentences), warm, and helpful.
If they ask about a specific property or want to schedule a viewing, let them know an agent
will follow up with them shortly.
Do not invent specific property details or prices.
Encourage them to share their contact details if they would like a callback."""


def generate_auto_reply(user_message: str) -> str:
    """
    Generate a helpful AI reply for an incoming user message.

    Parameters
    ----------
    user_message : str
        The raw text sent by the user.

    Returns
    -------
    str
        A short, friendly response from the real estate assistant.
        Falls back to a canned message when the OpenAI call fails.
    """
    try:
        response = _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": AUTO_REPLY_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Auto-reply generation failed: %s", exc)
        return (
            "Thanks for your message! 👋 One of our agents will get back to you shortly. "
            "Feel free to ask any questions about our properties in the meantime."
        )


LISTING_DESCRIPTION_PROMPT = """You are a real estate marketing copywriter.
Given a property description from an agent, write an engaging social-media
post caption (max 220 characters for Instagram, include relevant emojis).
Return ONLY the caption text."""


def generate_listing_caption(agent_description: str) -> str:
    """
    Turn an agent's raw property description into an engaging social-media
    caption.
    """
    try:
        response = _get_client().chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": LISTING_DESCRIPTION_PROMPT},
                {"role": "user", "content": agent_description},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Caption generation failed: %s", exc)
        return agent_description
