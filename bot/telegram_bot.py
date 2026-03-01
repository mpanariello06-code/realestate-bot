"""
Telegram Bot – Real Estate Agent Assistant

Conversation flows
──────────────────
1. /start          → show main menu
2. /post           → start listing-post flow (agent sends photo/video + description)
3. /leads          → list qualified leads with contact details
4. /performance    → show recent performance metrics
5. /report         → trigger the weekly report on demand
6. /help           → usage guide

The bot also handles incoming media messages and guides agents through the
post-listing workflow via inline keyboards.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
from bot.keyboards import (
    confirm_post_keyboard,
    lead_action_keyboard,
    main_menu_keyboard,
    posting_platform_keyboard,
)
from services import lead_qualifier, sheets, social_poster
from services.weekly_report import send_weekly_report

logger = logging.getLogger(__name__)

# Conversation states
(
    AWAITING_MEDIA,
    AWAITING_DESCRIPTION,
    AWAITING_PLATFORM,
    AWAITING_CAPTION_EDIT,
    AWAITING_CONFIRM,
) = range(5)

# Context keys
CTX_MEDIA_PATH = "media_path"
CTX_MEDIA_TYPE = "media_type"   # "photo" | "video"
CTX_DESCRIPTION = "description"
CTX_CAPTION = "caption"
CTX_PLATFORM = "platform"


# ── Guards ────────────────────────────────────────────────────────────────────

def _is_agent(update: Update) -> bool:
    """Return True if the sender is an authorised agent."""
    if not config.AGENT_CHAT_IDS:
        return True
    chat_id = update.effective_chat.id if update.effective_chat else None
    return chat_id in config.AGENT_CHAT_IDS


async def _agent_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Send a rejection message and return False if not an agent."""
    if not _is_agent(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ You are not authorised to use this bot."
            )
        return False
    return True


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _agent_only(update, context):
        return
    await update.effective_message.reply_text(
        "👋 *Welcome to the Real Estate Agent Bot!*\n\n"
        "I help you:\n"
        "• 📸 Post listings to Facebook, Instagram & TikTok\n"
        "• 🎯 Qualify and track leads\n"
        "• 📊 Monitor your performance\n"
        "• 📈 Get weekly reports\n\n"
        "Choose an option below or type /help for a command list.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _agent_only(update, context):
        return
    await update.effective_message.reply_text(
        "*Available Commands*\n\n"
        "/start – Main menu\n"
        "/post – Post a new property listing\n"
        "/leads – View qualified leads\n"
        "/performance – View performance stats\n"
        "/report – Send the weekly report now\n"
        "/help – This help message",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /leads ────────────────────────────────────────────────────────────────────

async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _agent_only(update, context):
        return
    leads = sheets.get_leads(qualified_only=True)
    if not leads:
        await update.effective_message.reply_text(
            "No qualified leads yet. Keep posting – they're coming! 🚀"
        )
        return

    for i, lead in enumerate(leads[-10:], 1):  # show last 10
        name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "Unknown"
        email = lead.get("email") or "N/A"
        phone = lead.get("phone") or "N/A"
        intent = lead.get("intent", "unknown").title()
        score = lead.get("score", 0)
        summary = lead.get("summary", "")
        status = lead.get("status", "new").title()

        text = (
            f"*Lead #{i}*\n"
            f"👤 {name}\n"
            f"📧 {email}\n"
            f"📞 {phone}\n"
            f"🏠 Intent: {intent}\n"
            f"⭐ Score: {score}/100\n"
            f"📝 {summary}\n"
            f"📌 Status: {status}"
        )
        await update.effective_message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=lead_action_keyboard(i - 1),
        )


# ── /performance ──────────────────────────────────────────────────────────────

async def cmd_performance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _agent_only(update, context):
        return
    records = sheets.get_performance(weeks=4)
    if not records:
        await update.effective_message.reply_text(
            "No performance data yet. It will appear after your first week. 📊"
        )
        return

    lines = ["*📊 Recent Performance (last 4 weeks)*\n"]
    for rec in records:
        lines.append(
            f"📅 {rec.get('week_start', 'N/A')} | {rec.get('platform', '').title()}\n"
            f"  👥 Followers: {rec.get('followers', 0):,}\n"
            f"  🎯 Leads: {rec.get('new_leads', 0)} total / {rec.get('qualified_leads', 0)} qualified\n"
            f"  🏆 Deals closed: {rec.get('deals_closed', 0)}\n"
            f"  ⚡ Avg response: {rec.get('avg_response_time', 0)} min\n"
            f"  💡 Engagement: {rec.get('engagement_rate', 0)}%\n"
        )
    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /report ───────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _agent_only(update, context):
        return
    await update.effective_message.reply_text("📈 Generating your weekly report…")
    await send_weekly_report(context.bot)


# ── Post listing flow ─────────────────────────────────────────────────────────

async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _agent_only(update, context):
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "📸 *New Listing Post*\n\n"
        "Please send me a *photo or video* of the property, "
        "or send a text description if you have no media.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return AWAITING_MEDIA


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive photo/video and save locally, then ask for description."""
    msg: Message = update.effective_message
    if msg.photo:
        file = await msg.photo[-1].get_file()
        media_type = "photo"
        suffix = ".jpg"
    elif msg.video:
        file = await msg.video.get_file()
        media_type = "video"
        suffix = ".mp4"
    else:
        await msg.reply_text("Please send a photo or video, or type a description.")
        return AWAITING_MEDIA

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    await file.download_to_drive(tmp.name)
    context.user_data[CTX_MEDIA_PATH] = tmp.name
    context.user_data[CTX_MEDIA_TYPE] = media_type

    await msg.reply_text(
        "✅ Media received!\n\n"
        "Now send me a *short description* of the property "
        "(e.g. '3-bed house in Miami, $450k, pool, renovated kitchen').",
        parse_mode=ParseMode.MARKDOWN,
    )
    return AWAITING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the description, generate a caption, ask for platform."""
    description = update.effective_message.text or ""
    context.user_data[CTX_DESCRIPTION] = description

    await update.effective_message.reply_text("✍️ Generating an AI caption for you…")
    caption = lead_qualifier.generate_listing_caption(description)
    context.user_data[CTX_CAPTION] = caption

    await update.effective_message.reply_text(
        f"*📝 Generated Caption:*\n\n{caption}\n\n"
        "Choose an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirm_post_keyboard(),
    )
    return AWAITING_CONFIRM


async def handle_caption_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the manually edited caption."""
    context.user_data[CTX_CAPTION] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "✅ Caption updated! Now select the platform:",
        reply_markup=posting_platform_keyboard(),
    )
    return AWAITING_PLATFORM


async def handle_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        _cleanup_media(context)
        await query.edit_message_text("❌ Post cancelled.")
        return ConversationHandler.END

    if query.data == "edit_caption":
        await query.edit_message_text("✏️ Please type your new caption:")
        return AWAITING_CAPTION_EDIT

    if query.data == "confirm_post":
        await query.edit_message_text(
            "📱 Select which platform(s) to post to:",
            reply_markup=posting_platform_keyboard(),
        )
        return AWAITING_PLATFORM

    return AWAITING_CONFIRM


async def handle_platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        _cleanup_media(context)
        await query.edit_message_text("❌ Post cancelled.")
        return ConversationHandler.END

    platform = query.data.replace("platform_", "")
    context.user_data[CTX_PLATFORM] = platform

    caption = context.user_data.get(CTX_CAPTION, "")
    image_path = context.user_data.get(CTX_MEDIA_PATH)
    media_type = context.user_data.get(CTX_MEDIA_TYPE, "photo")

    await query.edit_message_text(f"🚀 Posting to {platform.title()}…")

    if platform == "all":
        results = social_poster.post_listing(
            caption=caption,
            image_path=image_path if media_type == "photo" else None,
            video_path=image_path if media_type == "video" else None,
        )
        lines = []
        for plat, res in results.items():
            icon = "✅" if res.get("success") else "❌"
            lines.append(f"{icon} {plat.title()}: {res.get('post_id') or res.get('error', '')}")
        result_text = "\n".join(lines)
    elif platform == "facebook":
        res = social_poster.post_to_facebook(
            caption, image_path if media_type == "photo" else None
        )
        result_text = (
            f"✅ Facebook: {res.get('post_id', '')}"
            if res.get("success")
            else f"❌ Facebook: {res.get('error', '')}"
        )
    elif platform == "instagram":
        res = social_poster.post_to_instagram(caption, image_path or "")
        result_text = (
            f"✅ Instagram: {res.get('post_id', '')}"
            if res.get("success")
            else f"❌ Instagram: {res.get('error', '')}"
        )
    elif platform == "tiktok" and image_path:
        res = social_poster.post_to_tiktok(caption, image_path)
        result_text = (
            f"✅ TikTok: {res.get('publish_id', '')}"
            if res.get("success")
            else f"❌ TikTok: {res.get('error', '')}"
        )
    else:
        result_text = "❌ Unknown platform or missing media."

    _cleanup_media(context)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"*Post Results:*\n{result_text}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


def _cleanup_media(context: ContextTypes.DEFAULT_TYPE) -> None:
    path = context.user_data.pop(CTX_MEDIA_PATH, None)
    if path and os.path.exists(path):
        os.unlink(path)
    context.user_data.pop(CTX_MEDIA_TYPE, None)
    context.user_data.pop(CTX_DESCRIPTION, None)
    context.user_data.pop(CTX_CAPTION, None)
    context.user_data.pop(CTX_PLATFORM, None)


# ── Lead action callbacks ─────────────────────────────────────────────────────

async def handle_lead_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    if len(parts) < 3:
        return
    action = parts[1]            # contacted | closed | lost
    index = int(parts[2])        # 0-based display index
    status_map = {"contacted": "contacted", "closed": "closed", "lost": "lost"}
    status = status_map.get(action, "new")
    sheets.update_lead_status(index + 1, status)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ Lead #{index + 1} marked as *{status.title()}*.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Main menu callback ────────────────────────────────────────────────────────

async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    cmd_map = {
        "performance": cmd_performance,
        "qualified_leads": cmd_leads,
        "all_leads": cmd_leads,
        "weekly_report": cmd_report,
    }
    handler = cmd_map.get(query.data)
    if handler:
        await handler(update, context)


# ── Build Application ─────────────────────────────────────────────────────────

def build_application() -> Application:
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Post listing conversation
    post_conv = ConversationHandler(
        entry_points=[
            CommandHandler("post", cmd_post),
            CallbackQueryHandler(
                lambda u, c: cmd_post(u, c), pattern="^post_listing$"
            ),
        ],
        states={
            AWAITING_MEDIA: [
                MessageHandler(filters.PHOTO | filters.VIDEO, handle_media),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description),
            ],
            AWAITING_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description),
            ],
            AWAITING_CONFIRM: [
                CallbackQueryHandler(
                    handle_confirm_callback,
                    pattern="^(confirm_post|edit_caption|cancel)$",
                ),
            ],
            AWAITING_CAPTION_EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_caption_edit),
            ],
            AWAITING_PLATFORM: [
                CallbackQueryHandler(
                    handle_platform_callback,
                    pattern="^platform_",
                ),
                CallbackQueryHandler(
                    handle_platform_callback,
                    pattern="^cancel$",
                ),
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
    )
    app.add_handler(post_conv)

    # Simple commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("performance", cmd_performance))
    app.add_handler(CommandHandler("report", cmd_report))

    # Callback query handlers
    app.add_handler(
        CallbackQueryHandler(handle_lead_action, pattern="^lead_")
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_menu_callback,
            pattern="^(performance|qualified_leads|all_leads|weekly_report)$",
        )
    )

    return app
