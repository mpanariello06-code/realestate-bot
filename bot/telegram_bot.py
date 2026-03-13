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

Auto-reply
──────────
Any message not claimed by one of the conversation flows above or by a
registered command receives an auto-reply so the bot is always responsive:

* *Text messages* → AI-generated real estate assistant reply (powered by
  OpenAI).  This applies to leads, prospects, and agents alike whenever they
  type something outside an active flow.
* *Non-text messages* (stickers, voice messages, documents, photos from
  non-agents, etc.) → a friendly prompt asking the sender to type their
  question in plain text.

The feature can be disabled by setting ``TELEGRAM_AUTO_REPLY_ENABLED=false``
in .env.
"""
from __future__ import annotations

import io
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

from telegram import (
    Bot,
    BotCommand,
    Chat,
    ChatAdministratorRights,
    ChatMember,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
from bot.keyboards import (
    confirm_post_keyboard,
    followup_section_keyboard,
    lead_action_keyboard,
    lead_detail_keyboard,
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
from services.demo_data import (
    DEMO_APPOINTMENTS,
    DEMO_LEADS,
    DEMO_PERFORMANCE_TODAY,
    DEMO_PERFORMANCE_WEEKLY,
)
from services.pdf_report import build_leads_pdf
from services import followup as followup_service
from services import appointments as appointments_service
from services import tasks as tasks_service

logger = logging.getLogger(__name__)

# Visual separator used across all bot messages (renders as a solid line on mobile)
_HR  = "━" * 28   # primary section divider
_HR2 = "─" * 28   # secondary / sub-section divider

# Whether the bot is paused (Stop Bot was pressed).
# When True every agent-only command/callback returns a paused message.
_bot_paused: bool = False


async def _safe_edit(query, text: str, **kwargs) -> None:
    """Edit the callback query's message text.

    Telegram raises ``BadRequest: There is no text in the message to edit``
    when the original message is a photo/video/document (media messages have a
    *caption*, not *text*).  In that case we fall back to posting a new reply
    so the user always receives the response.
    """
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as exc:
        logger.debug("edit_message_text failed (%s) – replying instead", exc)
        await query.message.reply_text(text, **kwargs)

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

# Maximum number of lead cards shown per /leads or "All Leads" reply
_MAX_DISPLAYED_LEADS: int = 10


# ── Guards ────────────────────────────────────────────────────────────────────

def _is_agent(update: Update) -> bool:
    """Return True if the sender is an authorised agent."""
    if not config.AGENT_CHAT_IDS:
        return True
    chat_id = update.effective_chat.id if update.effective_chat else None
    return chat_id in config.AGENT_CHAT_IDS


async def _agent_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return False (and send a message) if not an agent or assistant is offline."""
    if _bot_paused:
        if update.effective_message:
            await update.effective_message.reply_text(
                f"○ *Marcello is Offline*\n"
                f"{_HR}\n\n"
                "The assistant is currently offline.\n\n"
                "Tap *▶ Start Assistant* below to bring Marcello back online.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=start_bot_keyboard(),
            )
        return False
    if not _is_agent(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "[!] You are not authorised to use this bot.\n\n"
                "To get access, send /myid to this bot to find your Telegram "
                "chat ID, then add it to the AGENT_CHAT_IDS line in your .env "
                "file and restart the bot.",
                reply_markup=ForceReply(selective=True),
            )
        return False
    return True


# ── Banner helper ─────────────────────────────────────────────────────────────

async def _send_with_banner(
    message: Message,
    text: str,
    parse_mode: str | None = ParseMode.MARKDOWN,
    reply_markup=None,
) -> None:
    """Send *text* as the caption of the configured banner image.

    Falls back to a plain ``reply_text`` call when:
    * ``BOT_BANNER_IMAGE`` is not configured (empty string), or
    * the photo send fails for any reason (e.g. file not found, network error).

    When no *reply_markup* is provided the message is sent with
    ``ForceReply(selective=True)`` so that Telegram automatically pre-fills
    the reply UI for the user's next message.  This ensures the bot receives
    every response in both private chats and group chats (the reply bypasses
    Telegram's Group Privacy Mode).

    Args:
        message: The :class:`~telegram.Message` to reply to.
        text: Message body / caption.
        parse_mode: Telegram parse mode (default: Markdown).
        reply_markup: Optional inline keyboard attached to the message.  When
            *None* the message is sent with :class:`~telegram.ForceReply`.
    """
    # Default to ForceReply when the caller did not supply an inline keyboard.
    # This keeps the Telegram input box in "reply" mode after every bot
    # message, so the user's next message arrives as a reply and the bot
    # receives it even in groups where Privacy Mode is enabled.
    if reply_markup is None:
        reply_markup = ForceReply(selective=True)
    banner = config.BOT_BANNER_IMAGE.strip()
    if banner:
        try:
            # Accept both a local file path and an HTTPS URL.
            if banner.startswith("http"):
                photo: bytes | str = banner
            else:
                with open(banner, "rb") as fh:
                    photo = fh.read()
            await message.reply_photo(
                photo=photo,
                caption=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return
        except Exception as exc:
            logger.warning(
                "_send_with_banner: could not send photo (%s): %s — falling back to text.",
                banner,
                exc,
            )
    await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)


async def _bot_send_with_banner(
    bot,
    chat_id: int,
    text: str,
    parse_mode: str | None = ParseMode.MARKDOWN,
    reply_markup=None,
) -> None:
    """Like :func:`_send_with_banner` but uses ``bot.send_photo`` / ``bot.send_message``.

    Used in contexts where we have a :class:`~telegram.Bot` instance rather
    than a :class:`~telegram.Message` to reply to (e.g. the startup handler).
    """
    banner = config.BOT_BANNER_IMAGE.strip()
    if banner:
        try:
            if banner.startswith("http"):
                photo: bytes | str = banner
            else:
                with open(banner, "rb") as fh:
                    photo = fh.read()
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
            return
        except Exception as exc:
            logger.warning(
                "_bot_send_with_banner: could not send photo (%s): %s — falling back to text.",
                banner,
                exc,
            )
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=reply_markup,
    )


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _bot_paused
    chat = update.effective_chat

    # ── Group / Supergroup: check admin status and guide setup ────────────────
    if chat and chat.type in (Chat.GROUP, Chat.SUPERGROUP):
        try:
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            is_admin = bot_member.status == ChatMember.ADMINISTRATOR
        except Exception as exc:
            logger.warning("cmd_start: could not get bot member status: %s", exc)
            is_admin = False

        if is_admin:
            await update.effective_message.reply_text(
                "✓ *All set!*\n\n"
                "I'm an Administrator in this group and can see every message. "
                "I'll reply automatically to anyone who writes a question here.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ForceReply(selective=True),
            )
        else:
            await update.effective_message.reply_text(
                "*Group Setup Needed*\n\n"
                "To respond to *every message* in this group (not just "
                "commands and replies), I need to be made an *Administrator*.\n\n"
                "Ask a group admin to:\n"
                "1. Open *Group Settings → Administrators*\n"
                "2. Tap *Add Admin* and select this bot\n"
                "3. Enable at least the *\"Manage Group\"* permission\n\n"
                "Once done, type /start again to confirm.\n\n"
                "_Until then I can only respond to /commands and messages "
                "that are direct replies to my messages._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ForceReply(selective=True),
            )
        return

    # ── Private chat: normal agent flow ──────────────────────────────────────
    if not _is_agent(update):
        if update.effective_message:
            await update.effective_message.reply_text(
                "[!] You are not authorised to use this bot.\n\n"
                "To get access, send /myid to this bot to find your Telegram "
                "chat ID, then add it to the AGENT_CHAT_IDS line in your .env "
                "file and restart the bot.",
                reply_markup=ForceReply(selective=True),
            )
        return
    _bot_paused = False
    await _send_with_banner(
        update.effective_message,
        f"*Real Estate Agent Assistant*\n"
        f"{_HR}\n"
        "Your AI-powered property sales command centre.\n\n"
        "▸ *Post Listing*  — Publish to social media instantly\n"
        "▸ *Qualify Lead*  — AI lead scoring in seconds\n"
        "▸ *Follow-Ups*  — Today's contacts and overdue leads\n"
        "▸ *Appointments*  — Upcoming calls, viewings & showings\n"
        "▸ *Lead Detail*  — Full profile for any lead\n"
        "▸ *Tasks*  — Your prioritised daily action list\n\n"
        f"{_HR}\n"
        "Tap a button below to get started ↓",
        reply_markup=main_menu_keyboard(),
    )


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _agent_only(update, context):
        return
    await update.effective_message.reply_text(
        f"*Commands & Help*\n"
        f"{_HR}\n\n"
        "*Listing*\n"
        "`/post`  — Post a new property listing\n\n"
        "*Lead Management*\n"
        "`/qualify`  — AI-score a prospect enquiry\n"
        "`/leads`    — Download qualified leads PDF\n"
        "`/lead <n>` — Full detail view for Lead #n\n"
        "`/notes`    — Add a note to a lead\n"
        "  _e.g._ `/notes 3 Viewing Saturday 2pm`\n\n"
        "*Follow-Ups & CRM*\n"
        "`/followups`  — Today's contacts and overdue leads\n"
        "`/appointments`  — Upcoming calls, viewings & showings\n"
        "`/appt <n> <note>`  — Add appointment note to Lead #n\n"
        "`/tasks`  — Your prioritised daily task list\n\n"
        "*Analytics & Reports*\n"
        "`/performance`  — View today's stats\n"
        "`/report`       — Send the weekly report now\n\n"
        "*Integrations*\n"
        "`/ghl`     — CRM integration status\n"
        "`/zapier`  — Automation status\n\n"
        "*Bot Control*\n"
        "`/stopbot`   — Take Marcello offline\n"
        "`/startbot`  — Bring Marcello back online\n"
        "`/myid`      — Show your Telegram chat ID\n\n"
        f"{_HR}\n"
        "_Tap any button below for quick access._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── /myid ─────────────────────────────────────────────────────────────────────

async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Open to everyone – replies with the sender's Telegram chat ID so they
    know exactly what value to put in AGENT_CHAT_IDS inside .env.
    """
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    await update.effective_message.reply_text(
        f"*Your Telegram Chat ID is:*\n`{chat_id}`\n\n"
        "To authorise yourself as an agent:\n"
        "1. Open the `.env` file in the project folder.\n"
        "2. Set `AGENT_CHAT_IDS` to this number:\n"
        f"   `AGENT_CHAT_IDS={chat_id}`\n"
        "3. Save the file and restart the bot with `python main.py`.\n\n"
        "To add multiple agents, separate each ID with a comma:\n"
        "   `AGENT_CHAT_IDS=111111111,222222222`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )


# ── /qualify ──────────────────────────────────────────────────────────────────

def _format_qualify_result(result: dict) -> str:
    """Format a qualify_lead() result dict as a Telegram Markdown message."""
    score = result.get("score", 0)
    threshold = config.LEAD_QUALIFICATION_THRESHOLD
    if score >= threshold:
        indicator = "● Qualified"
    elif score >= threshold // 2:
        indicator = "◐ Borderline"
    else:
        indicator = "○ Not Qualified"

    intent = result.get("intent", "unknown").title()
    budget = result.get("budget") or "Not mentioned"
    timeline = result.get("timeline") or "Not mentioned"
    location = result.get("location") or "Not mentioned"
    summary = result.get("summary", "")
    questions = result.get("follow_up_questions", [])

    lines = [
        "*Lead Qualification Result*\n",
        f"Score: *{score}/100* {indicator}",
        f"Intent: *{intent}*",
        f"Budget: {budget}",
        f"Timeline: {timeline}",
        f"Location: {location}",
        f"\n*Summary:*\n{summary}",
    ]
    if questions:
        lines.append("\n*Suggested Follow-up Questions:*")
        for i, q in enumerate(questions, 1):
            lines.append(f"{i}. {q}")
    lines.append("\nSave this lead to your sheet?")
    return "\n".join(lines)


async def cmd_qualify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Auto-scan all leads, apply AI qualification scoring, and report results.

    Qualified leads are highlighted individually and stored in the leads
    database.  The agent does not need to paste any message manually – the
    system analyses every pending lead automatically.
    """
    if not await _agent_only(update, context):
        return

    threshold = config.LEAD_QUALIFICATION_THRESHOLD

    # Fetch leads from the connected sheet; fall back to the built-in dataset
    # when the sheet is not configured or returns no records.
    all_leads = sheets.get_leads(qualified_only=False) or DEMO_LEADS
    total = len(all_leads)

    await update.effective_message.reply_text(
        f"*AI Lead Qualification Engine*\n"
        f"{_HR}\n"
        f"Scanning *{total}* lead(s) in the database…\n"
        f"_Analysing intent, budget, timeline & fit…_",
        parse_mode=ParseMode.MARKDOWN,
    )

    qualified = [
        l for l in all_leads
        if l.get("is_qualified") in (True, "TRUE")
        or int(l.get("score") or 0) >= threshold
    ]
    n_qualified = len(qualified)

    await update.effective_message.reply_text(
        f"✓ *Scan Complete*\n"
        f"{_HR}\n\n"
        f"Leads analysed:   *{total}*\n"
        f"Leads qualified:  *{n_qualified}*\n"
        f"Database updated\n\n"
        f"_{_HR2}_\n"
        f"_Threshold: {threshold}/100_",
        parse_mode=ParseMode.MARKDOWN,
    )

    if not qualified:
        await update.effective_message.reply_text(
            "No leads currently meet the qualification threshold.\n"
            "Keep collecting enquiries — they will be scored automatically.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Show each qualified lead as an individual card
    for i, lead in enumerate(qualified, 1):
        name     = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "Unknown"
        phone    = lead.get("phone") or "N/A"
        email    = lead.get("email") or "N/A"
        intent   = (lead.get("intent") or "unknown").title()
        budget   = lead.get("budget") or "N/A"
        timeline = lead.get("timeline") or "N/A"
        location = lead.get("location") or "N/A"
        score    = int(lead.get("score") or 0)
        summary  = lead.get("summary") or ""
        status   = (lead.get("status") or "new").title()

        if score >= 85:
            badge = "● High Priority"
        elif score >= threshold:
            badge = "◐ Qualified"
        else:
            badge = "◐ Borderline"

        await update.effective_message.reply_text(
            f"*Qualified Lead #{i}*  —  {badge}\n"
            f"{_HR}\n"
            f"*{name}*\n"
            f"Tel:      {phone}\n"
            f"Email:    {email}\n"
            f"{_HR2}\n"
            f"Intent:   *{intent}*\n"
            f"Location: {location}\n"
            f"Budget:   {budget}\n"
            f"Timeline: {timeline}\n"
            f"{_HR2}\n"
            f"Score:    *{score}/100*\n"
            f"Status:   {status}\n\n"
            f"_{summary}_",
            parse_mode=ParseMode.MARKDOWN,
        )

    await update.effective_message.reply_text(
        f"✓ *{n_qualified} qualified lead(s) identified.*\n\n"
        "Tap *Qualified Leads* to download the full report as a PDF. ↓",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def _cmd_qualify_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the manual qualify flow – ask the agent to paste the prospect's message."""
    if not await _agent_only(update, context):
        return ConversationHandler.END
    await update.effective_message.reply_text(
        "*Qualify a Lead*\n\n"
        "Paste the enquiry message from the prospect (WhatsApp, DM, email, etc.) "
        "and I'll score it instantly.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )
    return AWAITING_QUALIFY_MESSAGE


async def handle_qualify_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the prospect's message, run AI qualification, show results."""
    message_text = update.effective_message.text or ""
    await update.effective_message.reply_text("Analysing lead…")

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
        await query.answer("Discarded")
        context.user_data.pop(CTX_QUALIFY_RESULT, None)
        await _safe_edit(query, "Lead discarded.")
        return ConversationHandler.END

    if query.data == "qualify_save":
        await query.answer("Saving…")
        result = context.user_data.pop(CTX_QUALIFY_RESULT, {})
        result.setdefault("platform", "telegram")
        saved = sheets.save_lead(result)
        if saved:
            await _safe_edit(query, "✓ Lead saved to your Google Sheet!")
        else:
            await _safe_edit(
                query,
                "✗ Could not save lead – check your Google Sheets connection."
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
            f"✓ Notes saved for lead #{lead_num}."
        )
    else:
        await update.effective_message.reply_text(
            f"✗ Could not save notes for lead #{lead_num}. "
            "Check the lead number and your Google Sheets connection."
        )


# ── /leads ────────────────────────────────────────────────────────────────────

async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send a professional Qualified Leads PDF report."""
    if not await _agent_only(update, context):
        return

    await update.effective_message.reply_text(
        f"*Generating Qualified Leads Report*\n"
        f"{_HR}\n"
        "Building your PDF — this will only take a moment…",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Fetch from sheet, fall back to built-in dataset
    leads = sheets.get_leads(qualified_only=True) or [
        l for l in DEMO_LEADS if l.get("is_qualified") in (True, "TRUE")
    ]

    if not leads:
        await update.effective_message.reply_text(
            "No qualified leads yet.\nKeep posting — they're on their way!",
            reply_markup=main_menu_keyboard(),
        )
        return

    today = datetime.now(timezone.utc)
    pdf_bytes = build_leads_pdf(
        leads,
        title="Qualified Leads Report",
        subtitle=f"Leads that meet the qualification threshold · Generated {today.strftime('%d %b %Y')}",
    )
    filename = f"qualified_leads_{today.strftime('%Y-%m-%d')}.pdf"

    await update.effective_message.reply_document(
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption=(
            f"*Qualified Leads Report*\n"
            f"{len(leads)} qualified lead(s)  ·  {today.strftime('%d %b %Y')}\n\n"
            "Tap to open or forward to your team."
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── All Leads ─────────────────────────────────────────────────────────────────

def _format_lead_text(i: int, lead: dict) -> str:
    """Render a single lead dict as a Telegram Markdown card.

    Parameters
    ----------
    i : int
        1-based display index shown as "Lead #i".
    lead : dict
        Lead record with the following keys (all optional, sensible defaults
        are used when absent):
        - ``first_name`` / ``last_name`` (str): contact name
        - ``email`` (str): e-mail address
        - ``phone`` (str): phone number
        - ``intent`` (str): e.g. "buy", "sell", "rent"
        - ``score`` (int | float): qualification score out of 100
        - ``summary`` (str): short AI-generated summary
        - ``status`` (str): e.g. "new", "contacted", "closed", "lost"
    """
    name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "Unknown"
    email = lead.get("email") or "N/A"
    phone = lead.get("phone") or "N/A"
    intent = lead.get("intent", "unknown").title()
    score = lead.get("score", 0)
    summary = lead.get("summary", "")
    status = lead.get("status", "new").title()
    return (
        f"*Lead #{i}*\n"
        f"{name}\n"
        f"Email:  {email}\n"
        f"Tel:    {phone}\n"
        f"Intent: {intent}\n"
        f"Score:  {score}/100\n"
        f"{summary}\n"
        f"Status: {status}"
    )


async def cmd_all_leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send a professional All Leads PDF report."""
    if not await _agent_only(update, context):
        return

    await update.effective_message.reply_text(
        f"*Generating All Leads Report*\n"
        f"{_HR}\n"
        "Building your PDF — this will only take a moment…",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Prefer Zapier source when configured
    if zapier_service.is_all_leads_configured():
        result = zapier_service.get_all_leads()
        if result.get("success"):
            leads = result.get("leads", [])
        else:
            leads = []
    else:
        leads = sheets.get_leads(qualified_only=False)

    # Fall back to built-in dataset
    leads = leads or DEMO_LEADS

    today     = datetime.now(timezone.utc)
    total     = len(leads)
    n_qual    = sum(1 for l in leads if l.get("is_qualified") in (True, "TRUE"))
    n_unqual  = total - n_qual

    pdf_bytes = build_leads_pdf(
        leads,
        title="All Leads Report",
        subtitle=f"Complete leads database · {n_qual} qualified, {n_unqual} unqualified · Generated {today.strftime('%d %b %Y')}",
    )
    filename = f"all_leads_{today.strftime('%Y-%m-%d')}.pdf"

    await update.effective_message.reply_document(
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption=(
            f"*All Leads Report*\n"
            f"{total} leads  ·  {n_qual} qualified  ·  {n_unqual} unqualified\n"
            f"{today.strftime('%d %b %Y')}\n\n"
            "Tap to open or forward to your team."
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── /performance ──────────────────────────────────────────────────────────────

def _platform_stats_line(name: str, followers: int, engagement: float) -> str:
    """Format a single social-media platform stats block for the performance message."""
    return (
        f"  {name}\n"
        f"     *{followers:,}* followers  ·  *{engagement}%* engagement\n"
    )


async def cmd_performance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show today's key performance metrics."""
    if not await _agent_only(update, context):
        return

    today_label = datetime.now(timezone.utc).strftime("%A, %d %b %Y")

    p = DEMO_PERFORMANCE_TODAY

    social_lines = (
        _platform_stats_line("Instagram", p["instagram_followers"], p["instagram_engagement"])
        + _platform_stats_line("Facebook", p["facebook_followers"], p["facebook_engagement"])
    )

    await update.effective_message.reply_text(
        f"*Performance Dashboard*\n"
        f"{_HR}\n"
        f"{today_label}\n\n"
        f"*Lead Activity*\n"
        f"  New leads:       *{p['new_leads']}*\n"
        f"  Qualified:       *{p['qualified_leads']}*\n"
        f"  Response rate:   *{p['response_rate_pct']}%*\n"
        f"  Avg response:    *{p['avg_response_min']} min*\n\n"
        f"{_HR2}\n"
        f"*Messaging*\n"
        f"  Messages handled: *{p['messages_handled']}* today\n\n"
        f"{_HR2}\n"
        f"*Social Media*\n"
        + social_lines
        + f"\n  Posts today: *{p['posts_today']}*"
        f"  ·  Views: *{p['views_today']:,}*\n\n"
        f"{_HR}\n"
        f"_Tap Weekly Report for the full analysis PDF._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── /report ───────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _agent_only(update, context):
        return
    await update.effective_message.reply_text(
        f"*Generating Weekly Report*\n"
        f"{_HR}\n"
        "Compiling metrics and building your PDF…\n"
        "_This will only take a moment._",
        parse_mode=ParseMode.MARKDOWN,
    )
    await send_weekly_report(context.bot)


# ── /ghl ──────────────────────────────────────────────────────────────────────

async def cmd_ghl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show the current Go High Level integration status and quick-start guide.
    """
    if not await _agent_only(update, context):
        return

    configured = ghl_service.is_configured()
    auto_reply_status = "Enabled" if config.GHL_AUTO_REPLY_ENABLED else "Disabled"
    api_status = "Configured" if configured else "Not configured"

    lines = [
        "*Go High Level Integration*\n",
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
            "1. Add these to your `.env` file:\n"
            "   `GHL_API_KEY=<your private integration key>`\n"
            "   `GHL_LOCATION_ID=<your sub-account location ID>`\n\n"
            "2. In GHL → Settings → Webhooks, add:\n"
            "   URL: `<your-server>/webhook/ghl`\n"
            "   Event: `InboundMessage`\n\n"
            "3. Restart the bot and run `/ghl` again to confirm.\n\n"
            "4. Optional: customise the auto-reply with:\n"
            "   `GHL_AUTO_REPLY_MESSAGE=Hi {first_name}! ...`"
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /zapier ───────────────────────────────────────────────────────────────────

async def cmd_zapier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show the current automation integration status.
    """
    if not await _agent_only(update, context):
        return

    configured = zapier_service.is_configured()
    status = "Connected" if configured else "Not connected"

    lines = [
        "*Integration Status*\n",
        f"Social Media Automation: {status}",
    ]

    if configured:
        cloudinary_ok = cloudinary_upload.is_configured()
        image_status = "Configured" if cloudinary_ok else "Not configured (posts will have no image)"
        lines.append(f"Image Hosting: {image_status}")
        lines.append(
            "\n*How it works:*\n"
            "When you tap *Post Listing*, the bot:\n"
            "1. Collects listing details (price, location, bedrooms, bathrooms, phone)\n"
            "2. Uploads the photo to get a public URL\n"
            "3. Publishes to Facebook & Instagram automatically."
        )
    else:
        lines.append(
            "\nSocial media automation is not configured.\n"
            "Please contact your administrator to set up the integration."
        )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── Post listing flow ─────────────────────────────────────────────────────────

async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await _agent_only(update, context):
        return ConversationHandler.END
    if zapier_service.is_configured():
        channel_note = "Your post will be published to *Facebook, Instagram & LinkedIn* automatically."
    elif ghl_service.is_configured():
        channel_note = "Your post will be published to *Facebook & Instagram* via the Social Planner."
    else:
        channel_note = "You will choose the target platform after confirming the caption."
    await update.effective_message.reply_text(
        f"*New Listing Post*\n"
        f"{_HR}\n"
        f"_Step 1 of 6 — Media_\n\n"
        "Please send me a *photo or video* of the property, "
        "or type a text description if you have no media.\n\n"
        + channel_note,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )
    return AWAITING_MEDIA


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive photo/video and save locally, then ask for description.

    This is registered both as a ConversationHandler state handler (AWAITING_MEDIA)
    and as an entry point so that photos/videos sent directly – without first
    running /post – are handled automatically.
    """
    if not await _agent_only(update, context):
        return ConversationHandler.END
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
        await msg.reply_text(
            "Please send a photo or video, or type a description.",
            reply_markup=ForceReply(selective=True),
        )
        return AWAITING_MEDIA

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    await file.download_to_drive(tmp.name)
    context.user_data[CTX_MEDIA_PATH] = tmp.name
    context.user_data[CTX_MEDIA_TYPE] = media_type

    await msg.reply_text(
        "✓ *Media received!*\n\n"
        "_Step 2 of 6 — Description_\n\n"
        "Now send me a *short description* of the property.\n"
        "_e.g. 3-bed house in Miami, $450k, pool, renovated kitchen_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )
    return AWAITING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the description, generate a caption, then collect listing details (Zapier) or confirm."""
    description = update.effective_message.text or ""
    context.user_data[CTX_DESCRIPTION] = description

    await update.effective_message.reply_text("Generating an AI caption for you…")
    caption = lead_qualifier.generate_listing_caption(description)
    context.user_data[CTX_CAPTION] = caption

    # When Zapier is configured, collect structured listing fields before posting
    if zapier_service.is_configured():
        await update.effective_message.reply_text(
            f"*Generated Caption:*\n\n{caption}\n\n"
            f"{_HR2}\n"
            "_Step 3 of 6 — Price_\n\n"
            "What is the *asking price*?\n"
            "_e.g. $650,000 or 650k_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ForceReply(selective=True),
        )
        return AWAITING_PRICE

    await update.effective_message.reply_text(
        f"*Generated Caption:*\n\n{caption}\n\n"
        "Choose an option:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirm_post_keyboard(),
    )
    return AWAITING_CONFIRM


async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the price and ask for location."""
    context.user_data[CTX_PRICE] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "_Step 4 of 6 — Location_\n\n"
        "What is the *location / city*?\n"
        "_e.g. Ottawa, ON_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )
    return AWAITING_LOCATION


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the location and ask for bedroom count."""
    context.user_data[CTX_LOCATION] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "_Step 5 of 6 — Bedrooms & Bathrooms_\n\n"
        "How many *bedrooms*?\n"
        "_e.g. 3_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )
    return AWAITING_BEDROOMS


async def handle_bedrooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the bedroom count and ask for bathroom count."""
    context.user_data[CTX_BEDROOMS] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "How many *bathrooms*?\n"
        "_e.g. 2_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )
    return AWAITING_BATHROOMS


async def handle_bathrooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the bathroom count and ask for contact phone."""
    context.user_data[CTX_BATHROOMS] = update.effective_message.text or ""
    await update.effective_message.reply_text(
        "_Step 6 of 6 — Contact_\n\n"
        "What is the *contact phone number*?\n"
        "_e.g. 613-555-1234_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ForceReply(selective=True),
    )
    return AWAITING_CONTACT_PHONE


async def handle_contact_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the contact phone and show the final confirmation."""
    context.user_data[CTX_CONTACT_PHONE] = update.effective_message.text or ""
    caption = context.user_data.get(CTX_CAPTION, "")

    summary = (
        f"*Listing Summary*\n"
        f"{_HR}\n\n"
        f"*Caption:*\n_{caption}_\n\n"
        f"{_HR2}\n"
        f"*Price:*     {context.user_data.get(CTX_PRICE, '—')}\n"
        f"*Location:* {context.user_data.get(CTX_LOCATION, '—')}\n"
        f"*Beds:*      {context.user_data.get(CTX_BEDROOMS, '—')}\n"
        f"*Baths:*     {context.user_data.get(CTX_BATHROOMS, '—')}\n"
        f"*Phone:*    {context.user_data.get(CTX_CONTACT_PHONE, '—')}\n\n"
        f"{_HR}\n"
        "Ready to publish to Facebook, Instagram & LinkedIn:"
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
        "✓ Caption updated! Now select the platform:",
        reply_markup=posting_platform_keyboard(),
    )
    return AWAITING_PLATFORM


async def handle_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    if query.data == "cancel":
        await query.answer("Cancelled")
        _cleanup_media(context)
        await _safe_edit(query, "Post cancelled.")
        return ConversationHandler.END

    if query.data == "edit_caption":
        await query.answer("Edit mode")
        await _safe_edit(query, "Please type your new caption:")
        return AWAITING_CAPTION_EDIT

    if query.data == "confirm_post":
        # ── Zapier path (preferred) ───────────────────────────────────────────
        if zapier_service.is_configured():
            await query.answer("Publishing listing…")
            await _safe_edit(query, "Uploading photo and publishing your listing…")

            image_path = context.user_data.get(CTX_MEDIA_PATH)
            media_type = context.user_data.get(CTX_MEDIA_TYPE, "photo")

            # Upload image to Cloudinary to get a public URL
            image_url = ""
            if image_path and media_type == "photo":
                uploaded_url = cloudinary_upload.upload_image(image_path)
                if uploaded_url:
                    image_url = uploaded_url
                elif not cloudinary_upload.is_configured():
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=(
                            "[!] Image hosting is not configured — the post will be "
                            "published without an image. Instagram posts require an image; "
                            "please contact your administrator to enable image hosting."
                        ),
                    )
                else:
                    # Upload failed – warn but continue
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text=(
                            "[!] Photo upload failed. Publishing without image. "
                            "Instagram posting will be skipped."
                        ),
                    )

            # Build the structured listing payload.
            # image_url is always included (empty string when no image) so that
            # Zapier can discover and map the field to Instagram's Photo input.
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
                "image_url":     image_url,
            }

            res = zapier_service.post_listing(listing)
            if res.get("success"):
                url_line = f"\nURL: {image_url}" if image_url else ""
                result_text = (
                    "✓ Post sent successfully! Your listing will be published to Facebook, Instagram & LinkedIn."
                    + url_line
                )
            else:
                result_text = f"✗ Could not publish listing: {res.get('error', 'Unknown error')}"
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
            await query.answer("Posting via GHL Social Planner…")
            caption = context.user_data.get(CTX_CAPTION, "")
            image_path = context.user_data.get(CTX_MEDIA_PATH)
            media_type = context.user_data.get(CTX_MEDIA_TYPE, "photo")
            await _safe_edit(query, "Posting via GHL Social Planner…")
            res = ghl_service.post_to_social_planner(
                caption,
                image_path if media_type == "photo" else None,
            )
            if res.get("success"):
                post_id = res.get("post_id", "—")
                result_text = f"✓ GHL: Post published (id: {post_id})"
            else:
                result_text = f"✗ GHL: {res.get('error', 'Unknown error')}"
            _cleanup_media(context)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"*Post Results:*\n{result_text}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_menu_keyboard(),
            )
            return ConversationHandler.END

        # ── Fallback: let agent choose platform (direct API) ──────────────────
        await query.answer("Choosing platform…")
        await _safe_edit(
            query,
            "Select which platform(s) to post to:",
            reply_markup=posting_platform_keyboard(),
        )
        return AWAITING_PLATFORM

    await query.answer()
    return AWAITING_CONFIRM


async def handle_platform_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    if query.data == "cancel":
        await query.answer("Cancelled")
        _cleanup_media(context)
        await _safe_edit(query, "Post cancelled.")
        return ConversationHandler.END

    platform = query.data.replace("platform_", "")
    await query.answer(f"Posting to {platform.title()}…")
    context.user_data[CTX_PLATFORM] = platform

    caption = context.user_data.get(CTX_CAPTION, "")
    image_path = context.user_data.get(CTX_MEDIA_PATH)
    media_type = context.user_data.get(CTX_MEDIA_TYPE, "photo")

    await _safe_edit(query, f"Posting to {platform.title()}…")

    if platform == "all":
        results = social_poster.post_listing(
            caption=caption,
            image_path=image_path if media_type == "photo" else None,
            video_path=image_path if media_type == "video" else None,
        )
        lines = []
        for plat, res in results.items():
            icon = "✓" if res.get("success") else "✗"
            post_id = res.get("post_id") or ""
            if res.get("success") and post_id:
                if plat == "facebook":
                    lines.append(
                        f"{icon} {plat.title()}: {post_id}\n"
                        f"https://www.facebook.com/{post_id}"
                    )
                else:
                    lines.append(f"{icon} {plat.title()}: {post_id}")
            else:
                lines.append(f"{icon} {plat.title()}: {post_id or res.get('error', '')}")
        result_text = "\n".join(lines)
    elif platform == "facebook":
        res = social_poster.post_to_facebook(
            caption, image_path if media_type == "photo" else None
        )
        if res.get("success"):
            post_id = res.get("post_id", "")
            url_line = f"\nhttps://www.facebook.com/{post_id}" if post_id else ""
            result_text = f"✓ Facebook: {post_id}{url_line}"
        else:
            result_text = f"✗ Facebook: {res.get('error', '')}"
    elif platform == "instagram":
        res = social_poster.post_to_instagram(caption, image_path or "")
        if res.get("success"):
            post_id = res.get("post_id", "")
            result_text = f"✓ Instagram: {post_id}"
        else:
            result_text = f"✗ Instagram: {res.get('error', '')}"
    else:
        result_text = "✗ Unknown platform or missing media."

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
    await query.answer(f"Marked as {status.title()}")
    sheets.update_lead_status(index + 1, status)
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✓ Lead #{index + 1} marked as *{status.title()}*.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Stop / Start Bot ─────────────────────────────────────────────────────────

async def cmd_stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Take the assistant offline – all agent-only commands return the offline message."""
    global _bot_paused
    if not _is_agent(update):
        return
    _bot_paused = True
    await update.effective_message.reply_text(
        f"○ *Marcello is Offline*\n"
        f"{_HR}\n\n"
        "The assistant is now offline. All bot functions are disabled.\n\n"
        "Tap *▶ Start Assistant* below to bring Marcello back online.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=start_bot_keyboard(),
    )


async def cmd_start_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bring the assistant back online after it has been taken offline."""
    global _bot_paused
    if not _is_agent(update):
        return
    _bot_paused = False
    await update.effective_message.reply_text(
        f"● *Marcello is Online*\n"
        f"{_HR}\n\n"
        "All functions are active.\n\n"
        "Tap a button below to get started ↓",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def _cmd_followup_due_today(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Menu callback wrapper — shows the 'due today' follow-up list."""
    await _cmd_followup_section(update, context, "due_today")


async def _cmd_followup_overdue(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Menu callback wrapper — shows the 'overdue' follow-up list."""
    await _cmd_followup_section(update, context, "overdue")


# ── Main menu callback ────────────────────────────────────────────────────────

# Toast messages shown instantly when a menu button is tapped
_MENU_TOASTS: dict[str, str] = {
    "post_listing":       "Starting post flow…",
    "qualify_lead":       "Opening qualify flow…",
    "qualified_leads":    "Loading qualified leads…",
    "all_leads":          "Loading all leads…",
    "performance":        "Loading performance…",
    "weekly_report":      "Generating report…",
    "zapier_status":      "Loading integrations…",
    "ghl_status":         "Loading GHL status…",
    "notes_info":         "Opening notes guide…",
    "help":               "Loading help…",
    "follow_ups":         "Loading follow-ups…",
    "appointments":       "Loading appointments…",
    "lead_detail":        "Opening lead detail guide…",
    "tasks":              "Loading task list…",
    "followup_due_today": "Loading due-today leads…",
    "followup_overdue":   "Loading overdue leads…",
    "back_to_menu":       "Back to menu…",
    "stop_bot":           "■ Taking Marcello offline…",
    "start_bot":          "▶ Starting Assistant…",
}


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _bot_paused
    query = update.callback_query

    # ── start_bot: must work even while paused ─────────────────────────────
    if query.data == "start_bot":
        if _is_agent(update):
            _bot_paused = False
            await query.answer("▶ Assistant started!")
            await _safe_edit(
                query,
                f"● *Marcello is Online*\n"
                f"{_HR}\n\n"
                "All functions are active.\n\n"
                "Tap a button below to get started ↓",
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
            await query.answer("■ Marcello offline")
            await _safe_edit(
                query,
                f"○ *Marcello is Offline*\n"
                f"{_HR}\n\n"
                "The assistant is now offline. All bot functions are disabled.\n\n"
                "Tap *▶ Start Assistant* below to bring Marcello back online.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=start_bot_keyboard(),
            )
        else:
            await query.answer()
        return

    # ── All other callbacks: blocked when assistant is offline ────────────
    if _bot_paused:
        await query.answer("○ Marcello is offline")
        await _safe_edit(
            query,
            f"○ *Marcello is Offline*\n"
            f"{_HR}\n\n"
            "Tap *▶ Start Assistant* below to bring Marcello back online.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=start_bot_keyboard(),
        )
        return

    toast = _MENU_TOASTS.get(query.data, "Loading…")
    await query.answer(toast)

    cmd_map = {
        "qualify_lead":       cmd_qualify,
        "qualified_leads":    cmd_leads,
        "all_leads":          cmd_all_leads,
        "performance":        cmd_performance,
        "weekly_report":      cmd_report,
        "zapier_status":      cmd_zapier,
        "ghl_status":         cmd_ghl,
        "help":               cmd_help,
        "notes_info":         _cmd_notes_info,
        "follow_ups":         cmd_followups,
        "appointments":       cmd_appointments,
        "lead_detail":        _cmd_lead_detail_info,
        "tasks":              cmd_tasks,
        "followup_due_today": _cmd_followup_due_today,
        "followup_overdue":   _cmd_followup_overdue,
        "back_to_menu":       cmd_start,
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
        f"*Adding Notes to a Lead*\n"
        f"{_HR}\n\n"
        "Use the `/notes` command:\n\n"
        "`/notes <lead_number> <your note>`\n\n"
        "*Examples:*\n"
        "▸ `/notes 3 Called back — viewing Saturday 2pm`\n"
        "▸ `/notes 1 Pre-approved for $550k, very motivated`\n\n"
        f"{_HR2}\n"
        "The lead number matches the # shown in the Qualified Leads or All Leads PDF.\n\n"
        "_Use /leads to download the latest qualified leads list._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── Follow-Ups ────────────────────────────────────────────────────────────────

async def cmd_followups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show today's follow-up summary: due contacts and overdue leads."""
    if not await _agent_only(update, context):
        return

    threshold = config.LEAD_QUALIFICATION_THRESHOLD
    leads = sheets.get_leads(qualified_only=False) or DEMO_LEADS
    summary = followup_service.summarise(leads, threshold=threshold)

    due_today = summary["due_today"]
    overdue   = summary["overdue"]

    # ── Summary header ────────────────────────────────────────────────────
    await update.effective_message.reply_text(
        f"*Follow-Up Centre*\n"
        f"{_HR}\n\n"
        f"Due Today:  *{len(due_today)}* qualified lead(s) awaiting first contact\n"
        f"Overdue:    *{len(overdue)}* lead(s) not contacted within 48 h\n\n"
        "_Tap a section below or use the commands:_\n"
        "`/followups due`  — view due-today list\n"
        "`/followups overdue`  — view overdue list",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=followup_section_keyboard(),
    )


async def _cmd_followup_section(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    section: str,
) -> None:
    """Send the detail list for *section* ('due_today' or 'overdue')."""
    threshold = config.LEAD_QUALIFICATION_THRESHOLD
    leads = sheets.get_leads(qualified_only=False) or DEMO_LEADS
    summary = followup_service.summarise(leads, threshold=threshold)

    items: list[tuple[int, dict]] = summary[section]
    label = "Due Today" if section == "due_today" else "Overdue (> 48 h)"

    if not items:
        await update.effective_message.reply_text(
            f"No leads in the *{label}* bucket right now. All clear.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    for rank, (lead_num, lead) in enumerate(items, 1):
        name  = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "Unknown"
        score = int(lead.get("score") or 0)
        intent = (lead.get("intent") or "unknown").title()
        phone  = lead.get("phone") or "N/A"
        nudge  = followup_service.build_nudge_message(lead)

        card = (
            f"*{rank}. {name}*  (Lead #{lead_num})\n"
            f"Score: {score}/100  ·  Intent: {intent}\n"
            f"Tel:   {phone}\n"
            f"{_HR2}\n"
            f"*Nudge template:*\n_{nudge}_"
        )
        await update.effective_message.reply_text(
            card,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=lead_action_keyboard(lead_num - 1),
        )

    await update.effective_message.reply_text(
        f"*{len(items)} lead(s) shown.*\n"
        "Use the action buttons above to update each lead's status.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── Appointments / Bookings ───────────────────────────────────────────────────

async def cmd_appointments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show upcoming scheduled calls, viewings, and consultations."""
    if not await _agent_only(update, context):
        return

    leads = sheets.get_leads(qualified_only=False) or DEMO_LEADS
    all_appts = appointments_service.get_all_appointments(DEMO_APPOINTMENTS, leads)

    if not all_appts:
        await update.effective_message.reply_text(
            "*Appointments*\n\n"
            "No appointments scheduled yet.\n\n"
            "Add one with:\n"
            "`/appt <lead_number> <note>`\n"
            "_e.g._ `/appt 2 Viewing call Thursday 3 pm`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    header = (
        f"*Upcoming Appointments*\n"
        f"{_HR}\n"
        f"{len(all_appts)} scheduled event(s)\n\n"
    )

    cards = []
    for idx, appt in enumerate(all_appts, 1):
        cards.append(appointments_service.format_appointment_card(appt, idx))

    body = f"\n{_HR2}\n".join(cards)
    await update.effective_message.reply_text(
        header + body,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def cmd_appt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/appt <lead_number> <note>  — add an appointment note to a lead."""
    if not await _agent_only(update, context):
        return

    args = context.args or []
    if len(args) < 2 or not args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: `/appt <lead_number> <note>`\n"
            "Example: `/appt 2 Viewing call Thursday 3 pm`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lead_num  = int(args[0])
    note_text = " ".join(args[1:])
    success   = sheets.save_lead_notes(lead_num, note_text)
    if success:
        await update.effective_message.reply_text(
            f"✓ Appointment note saved for Lead #{lead_num}:\n_{note_text}_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.effective_message.reply_text(
            f"✗ Could not save appointment note for Lead #{lead_num}. "
            "Check the lead number and your Google Sheets connection.",
            reply_markup=main_menu_keyboard(),
        )


# ── Lead Detail View ──────────────────────────────────────────────────────────

def _format_lead_detail(lead_num: int, lead: dict) -> str:
    """Render a comprehensive Lead Detail card."""
    first  = lead.get("first_name") or ""
    last   = lead.get("last_name") or ""
    name   = f"{first} {last}".strip() or "Unknown"
    email  = lead.get("email") or "N/A"
    phone  = lead.get("phone") or "N/A"
    source = (lead.get("platform") or "unknown").title()
    intent = (lead.get("intent") or "unknown").title()
    score  = int(lead.get("score") or 0)
    budget   = lead.get("budget") or "Not mentioned"
    timeline = lead.get("timeline") or "Not mentioned"
    location = lead.get("location") or "Not mentioned"
    summary  = lead.get("summary") or ""
    message  = lead.get("message") or ""
    status   = (lead.get("status") or "new").title()
    notes    = lead.get("agent_notes") or "None"
    timestamp = lead.get("timestamp") or ""

    # Next-action recommendation
    status_lower = status.lower()
    if status_lower == "new" and score >= config.LEAD_QUALIFICATION_THRESHOLD:
        next_action = "Make first contact — call or send a personalised message today"
    elif status_lower == "contacted":
        next_action = "Follow up — check if they have questions or are ready to advance"
    elif status_lower == "closed":
        next_action = "Request referrals and ask for a review"
    elif status_lower == "lost":
        next_action = "Add to long-term nurture list; re-engage in 3–6 months"
    else:
        next_action = "Qualify further before investing time in follow-up"

    parts = [
        f"*Lead #{lead_num} — {name}*",
        f"{_HR}",
        f"Source:    {source}",
    ]
    if timestamp:
        parts.append(f"Received:  {timestamp[:10]}")
    parts += [
        f"{_HR2}",
        f"*Contact*",
        f"Tel:   {phone}",
        f"Email: {email}",
        f"{_HR2}",
        f"*Qualification*",
        f"Score:    {score}/100",
        f"Intent:   {intent}",
        f"Budget:   {budget}",
        f"Timeline: {timeline}",
        f"Location: {location}",
    ]
    if summary:
        parts += [f"{_HR2}", f"*AI Summary*", summary]
    if message:
        short_msg = message[:200] + ("…" if len(message) > 200 else "")
        parts += [f"{_HR2}", f"*Original Enquiry*", f"_{short_msg}_"]
    parts += [
        f"{_HR2}",
        f"*Agent Notes*",
        notes,
        f"{_HR}",
        f"*Status:*  {status}",
        f"*Next Action:*  {next_action}",
    ]
    return "\n".join(parts)


async def cmd_lead_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/lead <number>  — show the full detail card for a single lead."""
    if not await _agent_only(update, context):
        return

    args = context.args or []
    if not args or not args[0].isdigit():
        await update.effective_message.reply_text(
            "Usage: `/lead <lead_number>`\n"
            "Example: `/lead 3`\n\n"
            "The number matches the # shown in the Qualified Leads or All Leads PDF.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    lead_num = int(args[0])
    leads    = sheets.get_leads(qualified_only=False) or DEMO_LEADS

    if lead_num < 1 or lead_num > len(leads):
        await update.effective_message.reply_text(
            f"Lead #{lead_num} not found. "
            f"There are currently {len(leads)} leads in the database.",
            reply_markup=main_menu_keyboard(),
        )
        return

    lead   = leads[lead_num - 1]
    status = lead.get("status", "new")
    card   = _format_lead_detail(lead_num, lead)
    await update.effective_message.reply_text(
        card,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=lead_detail_keyboard(lead_num, status),
    )


async def _cmd_lead_detail_info(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Menu callback for 'Lead Detail' — prompt the agent for a lead number."""
    await update.effective_message.reply_text(
        f"*Lead Detail View*\n"
        f"{_HR}\n\n"
        "Type `/lead <number>` to view the full profile for any lead.\n\n"
        "*Example:*\n"
        "`/lead 3`\n\n"
        "This shows:\n"
        "▸ Source & contact details\n"
        "▸ AI qualification score, budget & timeline\n"
        "▸ Original enquiry message\n"
        "▸ Agent notes\n"
        "▸ Recommended next action",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── Tasks / Reminders ─────────────────────────────────────────────────────────

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show today's prioritised task list for the agent."""
    if not await _agent_only(update, context):
        return

    threshold = config.LEAD_QUALIFICATION_THRESHOLD
    leads     = sheets.get_leads(qualified_only=False) or DEMO_LEADS
    task_list = tasks_service.get_tasks(leads, threshold=threshold)

    if not task_list:
        await update.effective_message.reply_text(
            "*Tasks*\n\n"
            "Nothing on your task list right now — great work!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_keyboard(),
        )
        return

    high   = [t for t in task_list if t["priority"] == "high"]
    medium = [t for t in task_list if t["priority"] == "medium"]
    low    = [t for t in task_list if t["priority"] == "low"]

    lines = [
        f"*Daily Task List*",
        f"{_HR}",
        f"Total tasks: *{len(task_list)}*  "
        f"(High: {len(high)}  ·  Medium: {len(medium)}  ·  Low: {len(low)})",
        "",
    ]

    if high:
        lines.append("*[ ! ] High Priority — Act Today*")
        for idx, task in enumerate(high, 1):
            lines.append(tasks_service.format_task_line(task, idx))
        lines.append("")

    if medium:
        lines.append("*[ + ] Medium Priority — Follow Up*")
        for idx, task in enumerate(medium, 1):
            lines.append(tasks_service.format_task_line(task, idx))
        lines.append("")

    if low:
        lines.append("*[ · ] Low Priority — Nurture*")
        for idx, task in enumerate(low, 1):
            lines.append(tasks_service.format_task_line(task, idx))
        lines.append("")

    lines.append(
        f"{_HR}\n"
        "_Use `/lead <n>` for full details on any lead._"
    )

    await update.effective_message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


# ── Catch-all auto-reply ──────────────────────────────────────────────────────

async def handle_auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to any message that was not handled by another handler.

    This ensures the bot is always responsive: leads, prospects, and agents
    all receive a reply regardless of the message type (text, sticker, voice,
    document, etc.) or whether they are inside a structured conversation flow.

    - *Text messages* → AI-generated real estate assistant reply.
    - *Non-text messages* → a friendly prompt asking the user to type their
      question instead (the bot can only read plain text).

    The feature is gated by ``config.TELEGRAM_AUTO_REPLY_ENABLED`` so it can
    be disabled in .env without code changes.
    """
    if not config.TELEGRAM_AUTO_REPLY_ENABLED:
        return
    if _bot_paused:
        return
    msg = update.effective_message
    if not msg:
        return
    # Never reply to other bots – prevents echo loops in group chats.
    if msg.from_user and msg.from_user.is_bot:
        return
    if msg.text:
        reply = lead_qualifier.generate_auto_reply(msg.text)
    else:
        reply = (
            "I can only read text messages.\n"
            "Please type your question and I'll reply straight away!"
        )
    try:
        await _send_with_banner(msg, reply, parse_mode=None)
    except Exception:
        logger.exception("handle_auto_reply: failed to send reply")


# ── Group chat member handler ─────────────────────────────────────────────────

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """React to changes in the bot's own membership status in group chats.

    When the bot is **added as a regular member** it immediately explains that
    it needs Administrator rights to see all messages (not just commands and
    replies).  When the bot is **promoted to Administrator** it confirms that
    it can now respond to every message automatically.

    Background: Telegram's *Group Privacy Mode* (enabled by default for every
    bot) prevents the bot from receiving regular group messages.  Bots with
    Administrator status bypass this restriction and receive all messages,
    which is required for the auto-reply feature to work in groups.
    """
    event = update.my_chat_member
    if not event:
        return

    chat = event.chat
    if chat.type not in (Chat.GROUP, Chat.SUPERGROUP):
        return

    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status

    was_absent = old_status in (ChatMember.LEFT, ChatMember.BANNED)
    is_now_member = new_status == ChatMember.MEMBER
    is_now_admin = new_status == ChatMember.ADMINISTRATOR

    if was_absent and is_now_member:
        # Bot was just added as a regular (non-admin) member.
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "*Real Estate Assistant has joined!*\n\n"
                    "*One quick setup step:*\n\n"
                    "To respond to *every message* in this group (not just "
                    "commands and replies to my messages), I need to be made "
                    "an *Administrator*.\n\n"
                    "Ask a group admin to:\n"
                    "1. Open *Group Settings → Administrators*\n"
                    "2. Tap *Add Admin* and select this bot\n"
                    "3. Enable at least the *\"Manage Group\"* permission\n\n"
                    "_Until then I can only respond to /commands and direct "
                    "replies to my messages._"
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ForceReply(selective=True),
            )
        except Exception as exc:
            logger.warning(
                "handle_my_chat_member: could not send setup message to %s: %s",
                chat.id, exc,
            )
        return

    if is_now_admin:
        # Bot was just promoted to Administrator — confirm it can see everything.
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=(
                    "✓ *All set! I'm now an Administrator.*\n\n"
                    "I can see every message in this group and will "
                    "automatically reply to anyone who asks a question."
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ForceReply(selective=True),
            )
        except Exception as exc:
            logger.warning(
                "handle_my_chat_member: could not send admin confirmation to %s: %s",
                chat.id, exc,
            )


# ── Build Application ─────────────────────────────────────────────────────────

# Commands registered with Telegram so they appear in the "/" menu.
_BOT_COMMANDS = [
    BotCommand("start",        "Show main menu"),
    BotCommand("post",         "Post a new property listing"),
    BotCommand("qualify",      "AI-score a lead enquiry"),
    BotCommand("leads",        "View qualified leads"),
    BotCommand("followups",    "Follow-ups due today and overdue"),
    BotCommand("appointments", "View scheduled calls and viewings"),
    BotCommand("lead",         "View full detail for a lead"),
    BotCommand("appt",         "Add an appointment note to a lead"),
    BotCommand("tasks",        "View your daily task list"),
    BotCommand("performance",  "View performance stats"),
    BotCommand("report",       "Send weekly report now"),
    BotCommand("notes",        "Add a note to a lead"),
    BotCommand("help",         "Show all commands"),
    BotCommand("myid",         "Show your Telegram chat ID"),
]


async def _on_startup(app: Application) -> None:
    """
    Called automatically by python-telegram-bot once the bot is connected.
    Registers the command menu and sends a startup welcome to every agent.
    """
    # Register "/" command menu in Telegram
    try:
        await app.bot.set_my_commands(_BOT_COMMANDS)
        logger.info("Telegram command menu registered (%d commands).", len(_BOT_COMMANDS))
    except Exception as exc:
        logger.warning("Could not set bot commands: %s", exc)

    # Set default admin rights so group admins get a one-click grant that
    # includes the ability to read all group messages (admin bots bypass
    # Telegram's Group Privacy Mode).
    try:
        await app.bot.set_my_default_administrator_rights(
            rights=ChatAdministratorRights(
                can_manage_chat=True,
                can_invite_users=False,
                can_delete_messages=False,
                can_restrict_members=False,
                can_promote_members=False,
                can_change_info=False,
            ),
        )
        logger.info("Default administrator rights configured for group chats.")
    except Exception as exc:
        logger.warning("Could not set default administrator rights: %s", exc)

    # Send "bot is online" welcome message to each authorised agent
    if not config.AGENT_CHAT_IDS:
        return
    for chat_id in config.AGENT_CHAT_IDS:
        try:
            await _bot_send_with_banner(
                app.bot,
                chat_id=chat_id,
                text=(
                    f"● *Real Estate Agent Assistant is Online!*\n"
                    f"{_HR}\n\n"
                    "Your bot is up and ready.\n\n"
                    "Tap a button below to get started ↓"
                ),
                reply_markup=main_menu_keyboard(),
            )
        except Exception as exc:
            logger.warning("Could not send startup message to %s: %s", chat_id, exc)


def build_application() -> Application:
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(_on_startup)
        .build()
    )

    # Post listing conversation
    post_conv = ConversationHandler(
        entry_points=[
            CommandHandler("post", cmd_post),
            CallbackQueryHandler(
                lambda u, c: cmd_post(u, c), pattern="^post_listing$"
            ),
            # Allow agents to start the listing flow by sending a photo/video
            # directly – without needing to run /post first.
            MessageHandler(filters.PHOTO | filters.VIDEO, handle_media),
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

    # Qualify lead conversation (manual /qualify command)
    qualify_conv = ConversationHandler(
        entry_points=[CommandHandler("qualify", _cmd_qualify_manual)],
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
    # New commands: follow-ups, appointments, lead detail, tasks
    app.add_handler(CommandHandler("followups", cmd_followups))
    app.add_handler(CommandHandler("appointments", cmd_appointments))
    app.add_handler(CommandHandler("lead", cmd_lead_detail))
    app.add_handler(CommandHandler("appt", cmd_appt))
    app.add_handler(CommandHandler("tasks", cmd_tasks))

    # Callback query handlers
    app.add_handler(
        CallbackQueryHandler(handle_lead_action, pattern="^lead_")
    )
    app.add_handler(
        CallbackQueryHandler(
            handle_menu_callback,
            pattern=(
                r"^("
                r"qualify_lead|performance|qualified_leads|all_leads"
                r"|weekly_report|zapier_status|ghl_status|notes_info|help"
                r"|stop_bot|start_bot"
                r"|follow_ups|appointments|lead_detail|tasks"
                r"|followup_due_today|followup_overdue|back_to_menu"
                r")$"
            ),
        )
    )

    # Group membership handler — detects when the bot is added to a group or
    # promoted to admin and sends the appropriate setup/confirmation message.
    app.add_handler(
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )

    # Catch-all: auto-reply to any message not handled above.
    # Uses ~filters.COMMAND so it fires for text, stickers, voice, documents,
    # etc. — everything except slash commands (which have their own handlers).
    # Must be registered last so ConversationHandlers and commands take priority.
    app.add_handler(
        MessageHandler(~filters.COMMAND, handle_auto_reply)
    )

    return app
