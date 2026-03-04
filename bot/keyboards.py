"""
Telegram Inline Keyboard helpers.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Full function menu shown on /start and after every completed action.
    Every button triggers an instant toast auto-reply via query.answer(text=…).
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📸 Post Listing", callback_data="post_listing"),
            InlineKeyboardButton("🔍 Qualify Lead", callback_data="qualify_lead"),
        ],
        [
            InlineKeyboardButton("🎯 Qualified Leads", callback_data="qualified_leads"),
            InlineKeyboardButton("📋 All Leads", callback_data="all_leads"),
        ],
        [
            InlineKeyboardButton("📊 Performance", callback_data="performance"),
            InlineKeyboardButton("📈 Weekly Report", callback_data="weekly_report"),
        ],
        [
            InlineKeyboardButton("📡 Zapier", callback_data="zapier_status"),
            InlineKeyboardButton("📝 Notes Help", callback_data="notes_info"),
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="help"),
            InlineKeyboardButton("⏹ Stop Bot", callback_data="stop_bot"),
        ],
    ])


def start_bot_keyboard() -> InlineKeyboardMarkup:
    """Shown when the bot is paused – only the Start Bot button is active."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Start Bot", callback_data="start_bot"),
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
            InlineKeyboardButton("📘 Facebook", callback_data="platform_facebook"),
            InlineKeyboardButton("📷 Instagram", callback_data="platform_instagram"),
        ],
        [
            InlineKeyboardButton("🌐 All Platforms", callback_data="platform_all"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ])


def lead_action_keyboard(lead_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Mark Contacted",
                callback_data=f"lead_contacted_{lead_index}",
            ),
            InlineKeyboardButton(
                "🏆 Mark Closed",
                callback_data=f"lead_closed_{lead_index}",
            ),
        ],
        [
            InlineKeyboardButton(
                "❌ Mark Lost",
                callback_data=f"lead_lost_{lead_index}",
            ),
        ],
    ])


def confirm_post_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm Post", callback_data="confirm_post"),
            InlineKeyboardButton("✏️ Edit Caption", callback_data="edit_caption"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ])


def qualify_action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💾 Save to Leads", callback_data="qualify_save"),
            InlineKeyboardButton("🗑 Discard", callback_data="qualify_discard"),
        ],
    ])
