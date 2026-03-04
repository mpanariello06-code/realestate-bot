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
    qualify_action_keyboard,
    start_bot_keyboard,
)
from services import lead_qualifier, sheets, social_poster
from services.weekly_report import send_weekly_report
from services import ghl as ghl_service
from services import zapier as zapier_service
from services import cloudinary_upload

logger = logging.getLogger(__name__)

# Whether the bot is paused (Stop Bot was pressed).
# When True every agent-only command/callback returns a paused message.
_bot_paused: bool = False

# Conversation states
(
    AWAITING_MEDIA,
    AWAITING_DESCRIPTION,
    AWAITING_PLATFORM,
    AWAITING_CAPTION_EDIT,
    AWAITING_CONFIRM,
    AWAITING_QUALIFY_MESSAGE,
    AWAITING_QUALIFY_SAVE,
    AWAITING_PRICE,
    AWAITING_LOCATION,
    AWAITING_BEDROOMS,
    AWAITING_BATHROOMS,
    AWAITING_CONTACT_PHONE,
) = range(12)

# Context keys
CTX_MEDIA_PATH = "media_path"
CTX_MEDIA_TYPE = "media_type"   # "photo" | "video"
CTX_DESCRIPTION = "description"
CTX_CAPTION = "caption"
CTX_PLATFORM = "platform"
CTX_QUALIFY_RESULT = "qualify_result"
CTX_PRICE = "price"
CTX_LOCATION = "location"
CTX_BEDROOMS = "bedrooms"
CTX_BATHROOMS = "bathrooms"
CTX_CONTACT_PHONE = "contact_phone"


# ── Guards ────────────────────────────────────────────────────────────────────

def _is_agent(update: Update) -> bool:
    """Return True if the sender is an authorised agent."""
    if not config.AGENT_CHAT_IDS:
        return True
    chat_id = update.effective_chat.id if update.effective_chat else None
    return chat_id in config.AGENT_CHAT_IDS


async def _agent_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return False (and send a message) if not an agent or bot is paused."""
    if _bot_paused:
        if update.effective_message:
            await update.effective_message.reply_text(
                "⏹ *Bot is paused.*\n\n"
                "Tap the button below to resume.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=start_bot_keyboard(),
            )
        return False
    if not _is_agent(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "⛔ You are not authorised to use this bot.\n\n"
                "To get access, send /myid to this bot to find your Telegram "
                "chat ID, then add it to the AGENT_CHAT_IDS line in your .env "
                "file and restart the bot."
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
        "• 📸 Post listings to Facebook & Instagram via GHL Social Planner\n"
        "• 🔍 Qualify and track leads with AI\n"
        "• 📊 Monitor your performance\n"
        "• 📈 Get weekly reports\n"
        "• 🔗 Manage Go High Level auto-DM replies\n\n"
        "Tap a button below or type /help for a full command list.\n"
        "Use *⏹ Stop Bot* to pause all functions.",
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
        "/post – Post a new property listing via GHL Social Planner\n"
        "/qualify – Paste a lead message to get an instant AI score & follow-up questions\n"
        "/leads – View qualified leads\n"
        "/notes – Add a note to a lead (e.g. `/notes 3 Viewing Saturday 2pm`)\n"
        "/performance – View performance stats\n"
        "/report – Send the weekly report now\n"
        "/ghl – Go High Level integration status & setup guide\n"
        "/stopbot – Pause the bot (disable all functions)\n"
        "/startbot – Resume the bot after pausing\n"
        "/myid – Show your Telegram chat ID (useful for setup)\n"
        "/help – This help message",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /myid ─────────────────────────────────────────────────────────────────────

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Open to everyone – replies with the sender's Telegram chat ID so they
    know exactly what value to put in AGENT_CHAT_IDS inside .env.
    """
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    await update.effective_message.reply_text(
        f"🪪 *Your Telegram Chat ID is:*\n`{chat_id}`\n\n"
        "To authorise yourself as an agent:\n"
        "1️⃣ Open the `.env` file in the project folder.\n"
        "2️⃣ Set `AGENT_CHAT_IDS` to this number:\n"
        f"   `AGENT_CHAT_IDS={chat_id}`\n"
        "3️⃣ Save the file and restart the bot with `python main.py`.\n\n"
        "To add multiple agents, separate each ID with a comma:\n"
        "   `AGENT_CHAT_IDS=111111111,222222222`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /qualify ──────────────────────────────────────────────────────────────────

def _format_qualify_result(result: dict) -> str:
    """Format a qualify_lead() result dict as a Telegram Markdown message."""
    score = result.get("score", 0)
    threshold = config.LEAD_QUALIFICATION_THRESHOLD
    if score >= threshold:
        indicator = "🟢 Qualified"
    elif score >= threshold // 2:
        indicator = "🟡 Borderline"
    else:
        indicator = "🔴 Not Qualified"

    intent = result.get("intent", "unknown").title()
    budget = result.get("budget") or "Not mentioned"
    timeline = result.get("timeline") or "Not mentioned"
    location = result.get("location") or "Not mentioned"
    summary = result.get("summary", "")
    questions = result.get("follow_up_questions", [])

    lines = [
        "*🔍 Lead Qualification Result*\n",
        f"Score: *{score}/100* {indicator}",
        f"Intent: *{intent}*",
        f"Budget: {budget}",
        f"Timeline: {timeline}",
        f"Location: {location}",
        f"\n*📝 Summary:*\n{summary}",
    ]
    if questions:
        lines.append("\n*❓ Suggested Follow-up Questions:*")
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")
    lines.append("\nSave this lead to your sheet?")
    return "\n".join(lines)


async def cmd_qualify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the qualify flow – ask the agent to paste the prospect's message."""
    if not await _agent_only(update, context):
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "📋 *Qualify a Lead*\n\n"
        "Paste the enquiry message from the prospect (WhatsApp, DM, email, etc.) "
        "and I'll score it instantly.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return AWAITING_QUALIFY_MESSAGE


async def handle_qualify_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the prospect's message, run AI qualification, show results."""
    message_text = update.effective_message.text or ""
    await update.effective_message.reply_text("🤖 Analysing lead…")

    result = lead_qualifier.qualify_lead(message_text)
    result["message"] = message_text
    context.user_data[CTX_QUALIFY_RESULT] = result

    await update.effective_message.reply_text(
        _format_qualify_result(result),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=qualify_action_keyboard(),
    )
    return AWAITING_QUALIFY_SAVE


async def handle_qualify_save_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle the Save / Discard button after qualification."""
    query = update.callback_query

    if query.data == "qualify_discard":
        await query.answer("🗑 Discarded")
        context.user_data.pop(CTX_QUALIFY_RESULT, None)
        await query.edit_message_text("🗑 Lead discarded.")
        return ConversationHandler.END

    if query.data == "qualify_save":
        await query.answer("💾 Saving…")
        result = context.user_data.pop(CTX_QUALIFY_RESULT, {})
        result.setdefault("platform", "telegram")
        saved = sheets.save_lead(result)
        if saved:
            await query.edit_message_text("✅ Lead saved to your Google Sheet!")
        else:
            await query.edit_message_text(
                "❌ Could not save lead – check your Google Sheets connection."
            )
        return ConversationHandler.END

    await query.answer()
    return AWAITING_QUALIFY_SAVE


# ── /notes ────────────────────────────────────────────────────────────────────

async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /notes <lead_number> <note text>

    Add or update the agent notes for a specific lead.
    Example: /notes 3 Called back – viewing Saturday at 2pm
    """
    if not await _agent_only(update, context):
        return
    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: `/notes <lead_number> <your note>`\n"
            "Example: `/notes 3 Called back – viewing Saturday at 2pm`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    lead_num = int(args[0])
    note_text = " ".join(args[1:])
    success = sheets.save_lead_notes(lead_num, note_text)
    if success:
        await update.effective_message.reply_text(
            f"✅ Notes saved for lead #{lead_num}."
        )
    else:
        await update.effective_message.reply_text(
            f"❌ Could not save notes for lead #{lead_num}. "
            "Check the lead number and your Google Sheets connection."
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


# ── /ghl ──────────────────────────────────────────────────────────────────────

async def cmd_ghl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show the current Go High Level integration status and quick-start guide.
    """
    if not await _agent_only(update, context):
        return

    configured = ghl_service.is_configured()
    auto_reply_status = "✅ Enabled" if config.GHL_AUTO_REPLY_ENABLED else "❌ Disabled"
    api_status = "✅ Credentials set" if configured else "❌ Not configured"

    lines = [
        "*🔗 Go High Level Integration*\n",
        f"API Status: {api_status}",
        f"Auto-DM Reply: {auto_reply_status}",
    ]

    if configured:
        lines.append(f"Location ID: `{config.GHL_LOCATION_ID}`")
        lines.append(
            "\n*Auto-reply message:*\n"
            f"_{config.GHL_AUTO_REPLY_MESSAGE.format(first_name='[Name]', last_name='', full_name='[Name]')}_"
        )
        lines.append(
            "\n*Webhook URL* (register this in GHL → Settings → Webhooks):\n"
            "`<your-server>/webhook/ghl`\n"
            "Subscribe to: `InboundMessage`"
        )
    else:
        lines.append(
            "\n*Setup Steps:*\n"
            "1️⃣ Add these to your `.env` file:\n"
            "   `GHL_API_KEY=<your private integration key>`\n"
            "   `GHL_LOCATION_ID=<your sub-account location ID>`\n\n"
            "2️⃣ In GHL → Settings → Webhooks, add:\n"
            "   URL: `<your-server>/webhook/ghl`\n"
            "   Event: `InboundMessage`\n\n"
            "3️⃣ Restart the bot and run `/ghl` again to confirm.\n\n"
            "4️⃣ Optional: customise the auto-reply with:\n"
            "   `GHL_AUTO_REPLY_MESSAGE=Hi {first_name}! ...`"
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /zapier ───────────────────────────────────────────────────────────────────

async def cmd_zapier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show the current Zapier integration status and quick-start guide.
    """
    if not await _agent_only(update, context):
        return

    configured = zapier_service.is_configured()
    status = "✅ Webhook URL configured" if configured else "❌ Not configured"

    lines = [
        "*📡 Zapier Integration*\n",
        f"Status: {status}",
    ]

    if configured:
        cloudinary_ok = cloudinary_upload.is_configured()
        cloudinary_status = "✅ Cloudinary configured" if cloudinary_ok else "⚠️ Cloudinary not set (no image_url)"
        lines.append(f"Cloudinary: {cloudinary_status}")
        lines.append(
            "\n*How it works:*\n"
            "When you tap *Post Listing*, the bot:\n"
            "1️⃣ Collects listing details (price, location, bedrooms, bathrooms, phone)\n"
            "2️⃣ Uploads the photo to Cloudinary to get a public URL\n"
            "3️⃣ Sends structured JSON to Zapier:\n"
            "```\n"
            "{\n"
            '  "description":   "...",\n'
            '  "price":         "...",\n'
            '  "location":      "...",\n'
            '  "bedrooms":      "...",\n'
            '  "bathrooms":     "...",\n'
            '  "contact_phone": "...",\n'
            '  "image_url":     "https://res.cloudinary.com/..."\n'
            "}\n"
            "```\n"
            "Zapier then publishes to Facebook & Instagram automatically."
        )
    else:
        lines.append(
            "\n*Setup Steps:*\n"
            "1️⃣ In Zapier, create a new Zap:\n"
            "   Trigger: *Webhooks by Zapier → Catch Hook*\n"
            "   Copy the generated webhook URL.\n\n"
            "2️⃣ Add your posting actions, e.g.:\n"
            "   Action 1: *Facebook Pages → Create Page Post*\n"
            "   Map `description` + `price` to the post body.\n"
            "   Action 2: *Instagram for Business → Create Photo Post*\n"
            "   Map `image_url` to the Photo, `description` to the Caption.\n\n"
            "3️⃣ Set up Cloudinary (for photo uploads):\n"
            "   Register free at cloudinary.com, then add to `.env`:\n"
            "   `CLOUDINARY_CLOUD_NAME=...`\n"
            "   `CLOUDINARY_API_KEY=...`\n"
            "   `CLOUDINARY_API_SECRET=...`\n\n"
            "4️⃣ Add to your `.env` file:\n"
            "   `ZAPIER_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/...`\n\n"
            "5️⃣ Restart the bot and run `/zapier` again to confirm."
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Post listing flow ─────────────────────────────────────────────────────────

async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _agent_only(update, context):
        return ConversationHandler.END
    if zapier_service.is_configured():
        channel_note = "Your post will be published via *Zapier* (Facebook & Instagram)."
    elif ghl_service.is_configured():
        channel_note = "Your post will be published via *GHL Social Planner* (Facebook & Instagram)."
    else:
        channel_note = "You will choose the target platform after confirming the caption."
    await update.effective_message.reply_text(
        "📸 *New Listing Post*\n\n"
        "Please send me a *photo or video* of the property, "
        "or send a text description if you have no media.\n\n"
        + channel_note,
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
    """Receive the description, generate a caption, then collect listing details (Zapier) or confirm."""
    description = update.effective_message.text or ""
    context.user_data[CTX_DESCRIPTION] = description

    await update.effective_message.reply_text("✍️ Generating an AI caption for you…")
    caption = lead_qualifier.generate_listing_caption(description)
    context.user_data[CTX_CAPTION] = caption

    # When Zapier is configured, collect structured listing fields before posting
    if zapier_service.is_configured():
        await update.effective_message.reply_text(
            f"*📝 Generated Caption:*\n\n{caption}\n\n"
            "Now let's collect a few more details for the post.\n\n"
            "💰 What is the *asking price*? (e.g. $650,000 or 650k)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return AWAITING_PRICE

    await update.effective_message.reply_text(
        f"*📝 Generated Caption:*\n\n{caption}\n\n"
        "Choose an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirm_post_keyboard(),
    )
    return AWAITING_CONFIRM


async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the price and ask for location."""
    context.user_data[CTX_PRICE] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "📍 What is the *location / city*? (e.g. Ottawa, ON)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return AWAITING_LOCATION


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the location and ask for bedroom count."""
    context.user_data[CTX_LOCATION] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "🛏 How many *bedrooms*? (e.g. 3)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return AWAITING_BEDROOMS


async def handle_bedrooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the bedroom count and ask for bathroom count."""
    context.user_data[CTX_BEDROOMS] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "🚿 How many *bathrooms*? (e.g. 2)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return AWAITING_BATHROOMS


async def handle_bathrooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the bathroom count and ask for contact phone."""
    context.user_data[CTX_BATHROOMS] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "📞 What is the *contact phone number*? (e.g. 613-555-1234)",
        parse_mode=ParseMode.MARKDOWN,
    )
    return AWAITING_CONTACT_PHONE


async def handle_contact_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the contact phone and show the final confirmation."""
    context.user_data[CTX_CONTACT_PHONE] = update.effective_message.text or ""
    caption = context.user_data.get(CTX_CAPTION, "")

    summary = (
        f"*📋 Listing Summary:*\n\n"
        f"📝 *Caption:* {caption}\n"
        f"💰 *Price:* {context.user_data.get(CTX_PRICE, '—')}\n"
        f"📍 *Location:* {context.user_data.get(CTX_LOCATION, '—')}\n"
        f"🛏 *Bedrooms:* {context.user_data.get(CTX_BEDROOMS, '—')}\n"
        f"🚿 *Bathrooms:* {context.user_data.get(CTX_BATHROOMS, '—')}\n"
        f"📞 *Phone:* {context.user_data.get(CTX_CONTACT_PHONE, '—')}\n\n"
        "Confirm to post this to Facebook & Instagram via Zapier:"
    )
    await update.effective_message.reply_text(
        summary,
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

    if query.data == "cancel":
        await query.answer("❌ Cancelled")
        _cleanup_media(context)
        await query.edit_message_text("❌ Post cancelled.")
        return ConversationHandler.END

    if query.data == "edit_caption":
        await query.answer("✏️ Edit mode")
        await query.edit_message_text("✏️ Please type your new caption:")
        return AWAITING_CAPTION_EDIT

    if query.data == "confirm_post":
        # ── Zapier path (preferred) ───────────────────────────────────────────
        if zapier_service.is_configured():
            await query.answer("🚀 Sending to Zapier…")
            await query.edit_message_text("🚀 Uploading photo & sending to Zapier…")

            image_path = context.user_data.get(CTX_MEDIA_PATH)
            media_type = context.user_data.get(CTX_MEDIA_TYPE, "photo")

            # Upload image to Cloudinary to get a public URL
            image_url = ""
            if image_path and media_type == "photo":
                uploaded_url = cloudinary_upload.upload_image(image_path)
                if uploaded_url:
                    image_url = uploaded_url
                elif not cloudinary_upload.is_configured():
                    image_url = ""  # Cloudinary not set up – omit the field
                else:
                    # Upload failed – warn but continue
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="⚠️ Photo upload to Cloudinary failed. Posting without image.",
                    )

            # Build the structured listing payload
            description = (
                context.user_data.get(CTX_DESCRIPTION)
                or context.user_data.get(CTX_CAPTION)
                or ""
            )
            listing: dict = {
                "description":   description,
                "price":         context.user_data.get(CTX_PRICE, ""),
                "location":      context.user_data.get(CTX_LOCATION, ""),
                "bedrooms":      context.user_data.get(CTX_BEDROOMS, ""),
                "bathrooms":     context.user_data.get(CTX_BATHROOMS, ""),
                "contact_phone": context.user_data.get(CTX_CONTACT_PHONE, ""),
            }
            if image_url:
                listing["image_url"] = image_url

            res = zapier_service.post_listing(listing)
            result_text = (
                "✅ Zapier: Post sent! Zapier will publish it to Facebook & Instagram."
                if res.get("success")
                else f"❌ Zapier: {res.get('error', 'Unknown error')}"
            )
            _cleanup_media(context)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"*Post Results:*\n{result_text}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        # ── GHL path ─────────────────────────────────────────────────────────
        if ghl_service.is_configured():
            await query.answer("🚀 Posting via GHL Social Planner…")
            caption = context.user_data.get(CTX_CAPTION, "")
            image_path = context.user_data.get(CTX_MEDIA_PATH)
            media_type = context.user_data.get(CTX_MEDIA_TYPE, "photo")
            await query.edit_message_text("🚀 Posting via GHL Social Planner…")
            res = ghl_service.post_to_social_planner(
                caption,
                image_path if media_type == "photo" else None,
            )
            result_text = (
                f"✅ GHL: Post published! (id: {res.get('post_id', '—')})"
                if res.get("success")
                else f"❌ GHL: {res.get('error', 'Unknown error')}"
            )
            _cleanup_media(context)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"*Post Results:*\n{result_text}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        # ── Fallback: let agent choose platform (direct API) ──────────────────
        await query.answer("📱 Choosing platform…")
        await query.edit_message_text(
            "📱 Select which platform(s) to post to:",
            reply_markup=posting_platform_keyboard(),
        )
        return AWAITING_PLATFORM

    await query.answer()
    return AWAITING_CONFIRM


async def handle_platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    if query.data == "cancel":
        await query.answer("❌ Cancelled")
        _cleanup_media(context)
        await query.edit_message_text("❌ Post cancelled.")
        return ConversationHandler.END

    platform = query.data.replace("platform_", "")
    await query.answer(f"🚀 Posting to {platform.title()}…")
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
    context.user_data.pop(CTX_PRICE, None)
    context.user_data.pop(CTX_LOCATION, None)
    context.user_data.pop(CTX_BEDROOMS, None)
    context.user_data.pop(CTX_BATHROOMS, None)
    context.user_data.pop(CTX_CONTACT_PHONE, None)


# ── Lead action callbacks ─────────────────────────────────────────────────────

async def handle_lead_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = query.data.split("_")
    if len(parts) < 3:
        await query.answer()
        return
    action = parts[1]            # contacted | closed | lost
    index = int(parts[2])        # 0-based display index
    status_map = {"contacted": "contacted", "closed": "closed", "lost": "lost"}
    status = status_map.get(action, "new")
    await query.answer(f"✅ Marked as {status.title()}")
    sheets.update_lead_status(index + 1, status)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ Lead #{index + 1} marked as *{status.title()}*.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Stop / Start Bot ─────────────────────────────────────────────────────────

async def cmd_stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause the bot – all agent-only commands will return a paused message."""
    global _bot_paused
    if not _is_agent(update):
        return
    _bot_paused = True
    await update.effective_message.reply_text(
        "⏹ *Bot Paused*\n\n"
        "All bot functions are now disabled.\n"
        "Tap *▶️ Start Bot* below to resume.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=start_bot_keyboard(),
    )


async def cmd_start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume the bot after it has been paused."""
    global _bot_paused
    if not _is_agent(update):
        return
    _bot_paused = False
    await update.effective_message.reply_text(
        "✅ *Bot is Running!*\n\n"
        "All functions are active. How can I help?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── Main menu callback ────────────────────────────────────────────────────────

# Toast messages shown instantly when a menu button is tapped
_MENU_TOASTS: dict[str, str] = {
    "post_listing":    "📸 Starting post flow…",
    "qualify_lead":    "🔍 Opening qualify flow…",
    "qualified_leads": "🎯 Loading qualified leads…",
    "all_leads":       "📋 Loading all leads…",
    "performance":     "📊 Loading performance…",
    "weekly_report":   "📈 Generating report…",
    "zapier_status":   "📡 Loading Zapier status…",
    "ghl_status":      "🔗 Loading GHL status…",
    "notes_info":      "📝 Opening notes guide…",
    "help":            "❓ Loading help…",
    "stop_bot":        "⏹ Pausing bot…",
    "start_bot":       "▶️ Starting bot…",
}


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _bot_paused
    query = update.callback_query

    # ── start_bot: must work even while paused ─────────────────────────────
    if query.data == "start_bot":
        if _is_agent(update):
            _bot_paused = False
            await query.answer("▶️ Bot started!")
            await query.edit_message_text(
                "✅ *Bot is Running!*\n\nAll functions are active. How can I help?",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
        else:
            await query.answer()
        return

    # ── stop_bot ──────────────────────────────────────────────────────────
    if query.data == "stop_bot":
        if _is_agent(update):
            _bot_paused = True
            await query.answer("⏹ Bot paused")
            await query.edit_message_text(
                "⏹ *Bot Paused*\n\nTap *▶️ Start Bot* to resume.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=start_bot_keyboard(),
            )
        else:
            await query.answer()
        return

    # ── All other callbacks: blocked when paused ──────────────────────────
    if _bot_paused:
        await query.answer("⏹ Bot is paused")
        await query.edit_message_text(
            "⏹ *Bot is paused.*\n\nTap the button below to resume.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=start_bot_keyboard(),
        )
        return

    toast = _MENU_TOASTS.get(query.data, "Loading…")
    await query.answer(toast)

    cmd_map = {
        "qualify_lead":    cmd_qualify,
        "qualified_leads": cmd_leads,
        "all_leads":       cmd_leads,
        "performance":     cmd_performance,
        "weekly_report":   cmd_report,
        "zapier_status":   cmd_zapier,
        "ghl_status":      cmd_ghl,
        "help":            cmd_help,
        "notes_info":      _cmd_notes_info,
    }
    handler = cmd_map.get(query.data)
    if handler:
        await handler(update, context)


async def _cmd_notes_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Invoked via the 'notes_info' menu button callback.
    Explains how to use the /notes command with examples, then re-shows the main menu.
    """
    await update.effective_message.reply_text(
        "*📝 Adding Notes to a Lead*\n\n"
        "Use the `/notes` command from the chat:\n\n"
        "`/notes <lead_number> <your note>`\n\n"
        "*Examples:*\n"
        "• `/notes 3 Called back – viewing Saturday 2pm`\n"
        "• `/notes 1 Pre-approved for $550k, very motivated`\n\n"
        "The lead number matches the number shown next to the lead in `/leads`.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


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
            AWAITING_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price),
            ],
            AWAITING_LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_location),
            ],
            AWAITING_BEDROOMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bedrooms),
            ],
            AWAITING_BATHROOMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_bathrooms),
            ],
            AWAITING_CONTACT_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contact_phone),
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

    # Qualify lead conversation
    qualify_conv = ConversationHandler(
        entry_points=[CommandHandler("qualify", cmd_qualify)],
        states={
            AWAITING_QUALIFY_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_qualify_message),
            ],
            AWAITING_QUALIFY_SAVE: [
                CallbackQueryHandler(
                    handle_qualify_save_callback,
                    pattern="^qualify_",
                ),
            ],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
    )
    app.add_handler(qualify_conv)

    # Simple commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("performance", cmd_performance))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("notes", cmd_notes))
    app.add_handler(CommandHandler("ghl", cmd_ghl))
    app.add_handler(CommandHandler("zapier", cmd_zapier))
    app.add_handler(CommandHandler("stopbot", cmd_stop_bot))
    app.add_handler(CommandHandler("startbot", cmd_start_bot))

    # Callback query handlers
    app.add_handler(
        CallbackQueryHandler(handle_lead_action, pattern="^lead_")
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_menu_callback,
            pattern="^(qualify_lead|performance|qualified_leads|all_leads|weekly_report|zapier_status|ghl_status|notes_info|help|stop_bot|start_bot)$",
        )
    )

    return app
