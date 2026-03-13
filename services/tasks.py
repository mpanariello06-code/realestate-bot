"""
Tasks / Reminders Service

Generates a prioritised daily task list from the current state of all leads.

Priority levels
───────────────
  High    — qualified lead that has *never* been contacted (status = "new",
             score ≥ threshold)
  Medium  — lead that was contacted but still needs follow-up (status =
             "contacted", no recent note indicating the deal advanced)
  Low     — leads to keep an eye on (borderline score, or vague timeline)

Each task dict has the keys:
    priority   : "high" | "medium" | "low"
    lead_num   : 1-based index in the original leads list
    lead_name  : display name
    action     : short plain-text description of what the agent should do
    detail     : optional extra context (e.g. budget, timeline)
"""
from __future__ import annotations

_PRIORITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


def get_tasks(leads: list[dict], threshold: int = 60) -> list[dict]:
    """Build a sorted task list from *leads*.

    Parameters
    ----------
    leads:
        Full lead list (order determines the 1-based ``lead_num``).
    threshold:
        Qualification score threshold.  Leads at or above this score are
        included in High-priority tasks.

    Returns
    -------
    list[dict] – sorted by priority (high → medium → low), then by lead_num.
    """
    tasks: list[dict] = []

    for i, lead in enumerate(leads, 1):
        first = lead.get("first_name") or ""
        last  = lead.get("last_name") or ""
        name  = f"{first} {last}".strip() or f"Lead #{i}"
        score  = int(lead.get("score") or 0)
        status = (lead.get("status") or "new").lower()
        intent = (lead.get("intent") or "unknown").title()
        budget   = (lead.get("budget") or "").strip()
        timeline = (lead.get("timeline") or "").strip()
        notes    = (lead.get("agent_notes") or "").strip()

        detail_parts = []
        if budget:
            detail_parts.append(f"Budget: {budget}")
        if timeline:
            detail_parts.append(f"Timeline: {timeline}")
        detail = "  ·  ".join(detail_parts)

        if status == "new" and score >= threshold:
            tasks.append(
                {
                    "priority":  "high",
                    "lead_num":  i,
                    "lead_name": name,
                    "action":    f"First contact — {intent} enquiry (score {score}/100)",
                    "detail":    detail,
                }
            )
        elif status == "contacted":
            if notes:
                action = f"Follow up — {notes[:60]}{'…' if len(notes) > 60 else ''}"
            else:
                action = f"Follow up — {intent} lead (score {score}/100)"
            tasks.append(
                {
                    "priority":  "medium",
                    "lead_num":  i,
                    "lead_name": name,
                    "action":    action,
                    "detail":    detail,
                }
            )
        elif status == "new" and 0 < score < threshold:
            # Borderline — low priority nurture task
            tasks.append(
                {
                    "priority":  "low",
                    "lead_num":  i,
                    "lead_name": name,
                    "action":    f"Nurture — borderline lead (score {score}/100)",
                    "detail":    detail,
                }
            )

    tasks.sort(key=lambda t: (_PRIORITY_ORDER.get(t["priority"], 99), t["lead_num"]))
    return tasks


def format_task_line(task: dict, idx: int) -> str:
    """Render a task dict as a single Telegram Markdown line."""
    priority = task["priority"].upper()
    lead_num  = task["lead_num"]
    lead_name = task["lead_name"]
    action    = task["action"]
    detail    = task.get("detail", "")

    label = {"HIGH": "[ ! ]", "MEDIUM": "[ + ]", "LOW": "[ · ]"}.get(priority, "[ · ]")
    line = f"{label} *{lead_name}* (Lead #{lead_num})\n      {action}"
    if detail:
        line += f"\n      _{detail}_"
    return line
