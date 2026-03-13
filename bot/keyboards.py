"""
Telegram Inline Keyboard helpers.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Full function menu shown on /start and after every completed action.
    Layout (7 rows):
      1. Primary actions — Post Listing | Qualify Lead
      2. Lead reports    — Qualified Leads | All Leads
      3. Analytics       — Performance | Weekly Report
      4. CRM actions     — Follow-Ups | Appointments
      5. Detail views    — Lead Detail | Tasks
      6. Utilities       — Integrations | Notes | Help
      7. Control         — Stop Marcello  (alone, reduces accidental taps)
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Post Listing",    callback_data="post_listing"),
            InlineKeyboardButton("Qualify Lead",    callback_data="qualify_lead"),
        ],
        [
            InlineKeyboardButton("Qualified Leads", callback_data="qualified_leads"),
            InlineKeyboardButton("All Leads",       callback_data="all_leads"),
        ],
        [
            InlineKeyboardButton("Performance",     callback_data="performance"),
            InlineKeyboardButton("Weekly Report",   callback_data="weekly_report"),
        ],
        [
            InlineKeyboardButton("Follow-Ups",      callback_data="follow_ups"),
            InlineKeyboardButton("Appointments",    callback_data="appointments"),
        ],
        [
            InlineKeyboardButton("Lead Detail",     callback_data="lead_detail"),
            InlineKeyboardButton("Tasks",           callback_data="tasks"),
        ],
        [
            InlineKeyboardButton("Integrations",    callback_data="zapier_status"),
            InlineKeyboardButton("Notes",           callback_data="notes_info"),
            InlineKeyboardButton("Help",            callback_data="help"),
        ],
        [
            InlineKeyboardButton("■  Stop Marcello",  callback_data="stop_bot"),
        ],
    ])


def start_bot_keyboard() -> InlineKeyboardMarkup:
    """Shown when the assistant is offline – only the Start Assistant button is active."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶  Start Assistant", callback_data="start_bot"),
        ],
    ])


def posting_platform_keyboard() -> InlineKeyboardMarkup:
    """
    Fallback platform keyboard – only shown when GHL is NOT configured.
    When GHL is configured, posts go directly via GHL Social Planner and
    this keyboard is never displayed.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Facebook",      callback_data="platform_facebook"),
            InlineKeyboardButton("Instagram",     callback_data="platform_instagram"),
        ],
        [
            InlineKeyboardButton("All Platforms", callback_data="platform_all"),
        ],
        [
            InlineKeyboardButton("Cancel",        callback_data="cancel"),
        ],
    ])


def lead_action_keyboard(lead_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "Mark Contacted",
                callback_data=f"lead_contacted_{lead_index}",
            ),
            InlineKeyboardButton(
                "Mark Closed",
                callback_data=f"lead_closed_{lead_index}",
            ),
        ],
        [
            InlineKeyboardButton(
                "Mark Lost",
                callback_data=f"lead_lost_{lead_index}",
            ),
        ],
    ])


def confirm_post_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Confirm",      callback_data="confirm_post"),
            InlineKeyboardButton("Edit Caption", callback_data="edit_caption"),
            InlineKeyboardButton("Cancel",       callback_data="cancel"),
        ],
    ])


def qualify_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Save",    callback_data="qualify_save"),
            InlineKeyboardButton("Discard", callback_data="qualify_discard"),
        ],
    ])


def followup_section_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard shown after the Follow-Ups summary."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Due Today",  callback_data="followup_due_today"),
            InlineKeyboardButton("Overdue",    callback_data="followup_overdue"),
        ],
        [
            InlineKeyboardButton("Back to Menu", callback_data="back_to_menu"),
        ],
    ])


def lead_detail_keyboard(lead_num: int, status: str = "new") -> InlineKeyboardMarkup:
    """Contextual keyboard shown beneath a Lead Detail card."""
    buttons = []
    status_lower = status.lower()
    if status_lower == "new":
        buttons.append(
            InlineKeyboardButton(
                "Mark Contacted",
                callback_data=f"lead_contacted_{lead_num - 1}",
            )
        )
    if status_lower in ("new", "contacted"):
        buttons.append(
            InlineKeyboardButton(
                "Mark Closed",
                callback_data=f"lead_closed_{lead_num - 1}",
            )
        )
    rows = [buttons] if buttons else []
    rows.append(
        [InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]
    )
    return InlineKeyboardMarkup(rows)

