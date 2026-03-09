"""
Google Sheets Service
Handles all read/write operations for leads and performance data.

Sheet layout
────────────
Worksheet "Leads":
  A  timestamp
  B  platform           (facebook | instagram | tiktok | telegram | other)
  C  first_name
  D  last_name
  E  email
  F  phone
  G  message
  H  score              (0-100)
  I  intent             (buy | sell | rent | unknown)
  J  budget
  K  timeline
  L  location
  M  is_qualified       (TRUE | FALSE)
  N  summary
  O  status             (new | contacted | closed | lost)
  P  agent_notes

Worksheet "Performance":
  A  week_start         (YYYY-MM-DD)
  B  platform
  C  followers
  D  new_leads
  E  qualified_leads
  F  deals_closed
  G  avg_response_time  (minutes)
  H  engagement_rate    (%)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

LEADS_HEADERS = [
    "timestamp", "platform", "first_name", "last_name", "email", "phone",
    "message", "score", "intent", "budget", "timeline", "location",
    "is_qualified", "summary", "status", "agent_notes",
]

PERFORMANCE_HEADERS = [
    "week_start", "platform", "followers", "new_leads", "qualified_leads",
    "deals_closed", "avg_response_time", "engagement_rate",
]


def _get_worksheet(name: str) -> gspread.Worksheet:
    creds = Credentials.from_service_account_file(
        config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open(config.GOOGLE_SPREADSHEET_NAME)
    try:
        ws = spreadsheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=name, rows=1000, cols=20)
        headers = LEADS_HEADERS if name == "Leads" else PERFORMANCE_HEADERS
        ws.append_row(headers)
    return ws


def save_lead(lead: dict) -> bool:
    """
    Persist a qualified (or unqualified) lead to the Leads worksheet.

    Parameters
    ----------
    lead : dict
        Must contain at least: platform, message, score, intent,
        is_qualified, summary.  Optional: first_name, last_name,
        email, phone, budget, timeline, location.

    Returns
    -------
    bool – True on success.
    """
    try:
        ws = _get_worksheet("Leads")
        row = [
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            lead.get("platform", ""),
            lead.get("first_name", ""),
            lead.get("last_name", ""),
            lead.get("email", ""),
            lead.get("phone", ""),
            lead.get("message", ""),
            lead.get("score", 0),
            lead.get("intent", "unknown"),
            lead.get("budget", ""),
            lead.get("timeline", ""),
            lead.get("location", ""),
            str(lead.get("is_qualified", False)).upper(),
            lead.get("summary", ""),
            lead.get("status", "new"),
            lead.get("agent_notes", ""),
        ]
        ws.append_row(row)
        return True
    except Exception as exc:
        logger.error("Failed to save lead: %s", exc)
        return False


def get_leads(qualified_only: bool = False) -> list[dict]:
    """
    Retrieve all leads from the sheet.

    Parameters
    ----------
    qualified_only : bool
        When True, only return rows where is_qualified == TRUE.
    """
    try:
        ws = _get_worksheet("Leads")
        records = ws.get_all_records()
        if qualified_only:
            records = [r for r in records if str(r.get("is_qualified", "")).upper() == "TRUE"]
        return records
    except Exception as exc:
        logger.error("Failed to fetch leads: %s", exc)
        return []


def save_performance(data: dict) -> bool:
    """
    Append a performance record for the current week.

    Parameters
    ----------
    data : dict
        Keys: week_start, platform, followers, new_leads,
              qualified_leads, deals_closed, avg_response_time,
              engagement_rate.
    """
    try:
        ws = _get_worksheet("Performance")
        row = [
            data.get("week_start", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            data.get("platform", ""),
            data.get("followers", 0),
            data.get("new_leads", 0),
            data.get("qualified_leads", 0),
            data.get("deals_closed", 0),
            data.get("avg_response_time", 0),
            data.get("engagement_rate", 0),
        ]
        ws.append_row(row)
        return True
    except Exception as exc:
        logger.error("Failed to save performance data: %s", exc)
        return False


def get_performance(weeks: int = 4) -> list[dict]:
    """Return the last *weeks* performance records."""
    try:
        ws = _get_worksheet("Performance")
        records = ws.get_all_records()
        return records[-weeks:] if len(records) > weeks else records
    except Exception as exc:
        logger.error("Failed to fetch performance data: %s", exc)
        return []


def update_lead_status(row_index: int, status: str, notes: str = "") -> bool:
    """Update the status and notes columns for a lead row (1-based)."""
    try:
        ws = _get_worksheet("Leads")
        status_col = LEADS_HEADERS.index("status") + 1
        notes_col = LEADS_HEADERS.index("agent_notes") + 1
        ws.update_cell(row_index + 1, status_col, status)
        if notes:
            ws.update_cell(row_index + 1, notes_col, notes)
        return True
    except Exception as exc:
        logger.error("Failed to update lead status: %s", exc)
        return False


def save_lead_notes(row_index: int, notes: str) -> bool:
    """
    Update only the agent_notes column for a lead row.

    Parameters
    ----------
    row_index : int
        1-based display index of the lead (as shown by /leads).
        Row 1 in the sheet is the header; the first lead is row_index=1
        which maps to sheet row 2.
    notes : str
        Free-text note to store against the lead.
    """
    try:
        ws = _get_worksheet("Leads")
        notes_col = LEADS_HEADERS.index("agent_notes") + 1
        ws.update_cell(row_index + 1, notes_col, notes)
        return True
    except Exception as exc:
        logger.error("Failed to save lead notes: %s", exc)
        return False
