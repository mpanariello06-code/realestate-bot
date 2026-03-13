"""
Follow-Up Service

Computes which leads need to be contacted today, which are overdue, and
generates a personalised nudge-message template the agent can send verbatim
(or adapt) for each lead.

Definitions
───────────
Due Today  — qualified (score ≥ threshold) leads whose status is still "new"
             (i.e. never contacted).
Overdue    — same as Due Today, but the original enquiry arrived more than
             ``overdue_hours`` hours ago (default 48 h).
Nudge      — a pre-written, personalised follow-up message the agent can copy
             and send to a lead who hasn't replied yet.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta


_TIMESTAMP_FMT = "%Y-%m-%d %H:%M:%S"


def get_due_today(leads: list[dict], threshold: int = 60) -> list[tuple[int, dict]]:
    """Return ``(1-based index, lead)`` pairs for qualified leads never contacted.

    Parameters
    ----------
    leads:
        Full list of lead dicts (order determines the 1-based index).
    threshold:
        Minimum qualification score to be considered for follow-up.
    """
    result = []
    for i, lead in enumerate(leads, 1):
        score = int(lead.get("score") or 0)
        status = lead.get("status", "new").lower()
        if status == "new" and score >= threshold:
            result.append((i, lead))
    return result


def get_overdue(
    leads: list[dict],
    threshold: int = 60,
    overdue_hours: int = 48,
) -> list[tuple[int, dict]]:
    """Return qualified leads that were *never contacted* and are > overdue_hours old.

    Parameters
    ----------
    leads:
        Full list of lead dicts.
    threshold:
        Minimum qualification score.
    overdue_hours:
        How many hours must have passed since the enquiry arrived for it to be
        considered overdue.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=overdue_hours)
    result = []
    for i, lead in enumerate(leads, 1):
        score = int(lead.get("score") or 0)
        if lead.get("status", "new").lower() != "new" or score < threshold:
            continue
        ts_str = lead.get("timestamp", "")
        if not ts_str:
            # No timestamp → treat as overdue (unknown age)
            result.append((i, lead))
            continue
        try:
            lead_dt = datetime.strptime(ts_str, _TIMESTAMP_FMT).replace(
                tzinfo=timezone.utc
            )
            if lead_dt <= cutoff:
                result.append((i, lead))
        except (ValueError, TypeError):
            result.append((i, lead))
    return result


def build_nudge_message(lead: dict) -> str:
    """Return a personalised follow-up message template for *lead*.

    The template is ready to copy-paste (or lightly edit) and send to the
    prospect via any channel.
    """
    first = lead.get("first_name") or ""
    name = first.strip() or "there"
    intent = (lead.get("intent") or "unknown").lower()
    budget = (lead.get("budget") or "").strip()
    location = (lead.get("location") or "").strip()

    if intent == "buy":
        msg = f"Hi {name}! Following up on your property-purchase enquiry"
        if location:
            msg += f" in {location}"
        if budget:
            msg += f" (budget: {budget})"
        msg += (
            ". I have a few great listings I'd love to share with you. "
            "When would be a good time for a quick call?"
        )
    elif intent == "sell":
        msg = f"Hi {name}! I wanted to follow up about listing your property"
        if location:
            msg += f" in {location}"
        msg += (
            ". The market is looking strong right now — "
            "would you like to schedule a complimentary valuation?"
        )
    elif intent == "rent":
        msg = f"Hi {name}! Following up on your rental search"
        if location:
            msg += f" in {location}"
        if budget:
            msg += f" (up to {budget})"
        msg += (
            ". I have some options that match your criteria. "
            "Shall we arrange a viewing this week?"
        )
    else:
        msg = (
            f"Hi {name}! Just checking in on your recent real-estate enquiry. "
            "I'm here to help — feel free to ask any questions or let me know "
            "how I can assist."
        )

    return msg


def summarise(leads: list[dict], threshold: int = 60, overdue_hours: int = 48) -> dict:
    """Return a summary dict with ``due_today`` and ``overdue`` lead lists."""
    return {
        "due_today": get_due_today(leads, threshold),
        "overdue":   get_overdue(leads, threshold, overdue_hours),
    }
