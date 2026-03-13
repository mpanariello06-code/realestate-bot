"""
Appointments Service

Handles scheduled calls, property showings, and consultations.

Two sources are combined:
  1. ``DEMO_APPOINTMENTS`` — hard-coded realistic demo entries used as the
     fallback when Google Sheets is not configured.
  2. ``agent_notes`` field of each lead — any note that contains scheduling
     keywords (e.g. "booked", "viewing", "call", "showing") is surfaced as an
     appointment so the agent has a single place to review upcoming commitments.

The module also provides helpers for adding a new appointment note to a lead
(stored via the sheets service) and for formatting appointment cards for
Telegram display.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

# Keywords used to detect appointment-like notes in agent_notes.
_APPT_KEYWORDS = re.compile(
    r"\b(booked|viewing|call|showing|consultation|meeting|appointment|scheduled|visit)\b",
    re.IGNORECASE,
)

# Types mapped from keyword detection → display label
_TYPE_LABELS: dict[str, str] = {
    "viewing":      "Property Viewing",
    "showing":      "Property Showing",
    "call":         "Call",
    "consultation": "Consultation",
    "meeting":      "Meeting",
    "appointment":  "Appointment",
    "visit":        "Visit",
    "booked":       "Booking",
    "scheduled":    "Scheduled",
}


def _detect_type(note: str) -> str:
    """Best-effort appointment type label from a free-text note."""
    note_lower = note.lower()
    for keyword, label in _TYPE_LABELS.items():
        if keyword in note_lower:
            return label
    return "Appointment"


def parse_appointments_from_leads(leads: list[dict]) -> list[dict]:
    """Extract appointments from ``agent_notes`` fields across all leads.

    Returns a list of appointment dicts:
        lead_num   : 1-based index in the leads list
        lead_name  : display name
        type       : appointment type label (e.g. "Property Viewing")
        note       : the original agent note text
        source     : always "notes"
    """
    appointments: list[dict] = []
    for i, lead in enumerate(leads, 1):
        notes = (lead.get("agent_notes") or "").strip()
        if not notes:
            continue
        if _APPT_KEYWORDS.search(notes):
            first = lead.get("first_name") or ""
            last = lead.get("last_name") or ""
            name = f"{first} {last}".strip() or f"Lead #{i}"
            appointments.append(
                {
                    "lead_num":  i,
                    "lead_name": name,
                    "type":      _detect_type(notes),
                    "note":      notes,
                    "source":    "notes",
                }
            )
    return appointments


def merge_appointments(
    demo_appointments: list[dict],
    note_appointments: list[dict],
) -> list[dict]:
    """Combine demo + note-derived appointments, de-duplicating by lead_num.

    Demo entries take precedence (they have richer metadata).
    """
    seen_lead_nums: set[int] = set()
    merged: list[dict] = []
    for appt in demo_appointments:
        merged.append(appt)
        seen_lead_nums.add(appt.get("lead_num", -1))
    for appt in note_appointments:
        if appt.get("lead_num") not in seen_lead_nums:
            merged.append(appt)
    # Sort: entries with a datetime_str first (chronologically), then the rest
    def _sort_key(a: dict) -> tuple:
        dt_str = a.get("datetime_str") or ""
        if dt_str:
            try:
                return (0, datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
            except ValueError:
                pass
        return (1, datetime.min)

    merged.sort(key=_sort_key)
    return merged


def format_appointment_card(appt: dict, idx: int) -> str:
    """Render one appointment as a Telegram Markdown block.

    Parameters
    ----------
    appt:
        Appointment dict (see ``parse_appointments_from_leads`` return shape).
    idx:
        1-based display index.
    """
    lead_num  = appt.get("lead_num", "?")
    lead_name = appt.get("lead_name", "Unknown")
    appt_type = appt.get("type", "Appointment")
    dt_str    = appt.get("datetime_str") or ""
    note      = appt.get("note", "")

    lines = [f"*{idx}. {appt_type} — {lead_name}*  (Lead #{lead_num})"]
    if dt_str:
        lines.append(f"When:  {dt_str}")
    if note:
        lines.append(f"Note:  {note}")
    return "\n".join(lines)


def get_all_appointments(
    demo_appointments: list[dict],
    leads: list[dict],
) -> list[dict]:
    """Return merged list of all appointments (demo + parsed from notes)."""
    note_appts = parse_appointments_from_leads(leads)
    return merge_appointments(demo_appointments, note_appts)
