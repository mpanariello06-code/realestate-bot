"""
Telegram bot for the real estate agent automation system.

Supports both private chats and group workspaces.
Uses python-telegram-bot v20+ (async).
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
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

from database import Agent, Lead, Listing, SessionLocal

load_dotenv()

logger = logging.getLogger(__name__)

ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------

(
    POST_MEDIA,
    POST_TITLE,
    POST_PRICE,
    POST_LOCATION,
    POST_BEDROOMS,
    POST_BATHROOMS,
    POST_DESCRIPTION,
    POST_CONFIRM,
) = range(8)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_or_create_agent(telegram_id: str, username: Optional[str], name: str) -> Agent:
    """Get an existing agent or register a new one."""
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.telegram_id == telegram_id).first()
        if not agent:
            agent = Agent(
                telegram_id=telegram_id,
                telegram_username=username,
                name=name,
            )
            db.add(agent)
            db.commit()
            db.refresh(agent)
            logger.info("Registered new agent: %s (%s)", name, telegram_id)
        return agent
    finally:
        db.close()


def _is_admin(update: Update) -> bool:
    """Return True if the sender is the configured admin."""
    if not ADMIN_CHAT_ID:
        return False
    user = update.effective_user
    return user is not None and str(user.id) == str(ADMIN_CHAT_ID)


def _leads_keyboard(leads: list, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Build an inline keyboard for a leads list page."""
    buttons = [
        [InlineKeyboardButton(
            f"#{lead.id} – {lead.name or 'Unknown'} ({lead.qualification_status})",
            callback_data=f"lead_detail:{lead.id}",
        )]
        for lead in leads
    ]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"leads_page:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"leads_page:{page + 1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def _lead_detail_keyboard(lead_id: int) -> InlineKeyboardMarkup:
    """Build an inline keyboard for a single lead's detail view."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📞 Call Now", callback_data=f"lead_call:{lead_id}"),
            InlineKeyboardButton("✅ Qualify", callback_data=f"lead_qualify:{lead_id}"),
        ],
        [
            InlineKeyboardButton("❌ Unqualify", callback_data=f"lead_unqualify:{lead_id}"),
            InlineKeyboardButton("🔙 Back", callback_data="leads_page:0"),
        ],
    ])


def _listing_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    """Build an inline keyboard for a listing's management view."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats", callback_data=f"listing_stats:{listing_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"listing_edit:{listing_id}"),
        ],
        [
            InlineKeyboardButton("📦 Archive", callback_data=f"listing_archive:{listing_id}"),
        ],
    ])


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Register the agent and greet them."""
    user = update.effective_user
    if user is None:
        return

    agent = _get_or_create_agent(
        telegram_id=str(user.id),
        username=user.username,
        name=user.full_name,
    )

    await update.message.reply_text(
        f"👋 Welcome, *{agent.name}*!\n\n"
        "I'm your Real Estate Agent Assistant. Here's what I can do:\n\n"
        "🏠 /post – Create & post a new listing\n"
        "👥 /leads – View your leads\n"
        "⭐ /qualified – View qualified leads\n"
        "📊 /performance – This week's performance\n"
        "📋 /report – Request weekly report\n"
        "🔗 /connect_facebook – Link Facebook\n"
        "🔗 /connect_instagram – Link Instagram\n"
        "👤 /profile – Your profile\n"
        "❓ /help – Help\n\n"
        "_Send a photo or video with a caption to quickly create a listing!_",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show available commands."""
    help_text = (
        "📖 *Available Commands*\n\n"
        "*/start* – Register / welcome screen\n"
        "*/post* – Create a new property listing\n"
        "*/leads* – View all leads (paginated)\n"
        "*/qualified* – View qualified leads only\n"
        "*/performance* – Current week's stats\n"
        "*/report* – Request your weekly report\n"
        "*/connect_facebook* – Connect your Facebook Page\n"
        "*/connect_instagram* – Connect Instagram\n"
        "*/postads* – Paid advertising options\n"
        "*/profile* – View/edit your profile\n\n"
        "📷 _You can also send a photo/video with a caption to auto-create a listing._"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the agent's profile summary."""
    user = update.effective_user
    if user is None:
        return

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.telegram_id == str(user.id)).first()
        if not agent:
            await update.message.reply_text("Please /start first.")
            return

        fb = "✅ Connected" if agent.facebook_token else "❌ Not connected"
        ig = "✅ Connected" if agent.instagram_token else "❌ Not connected"
        tt = "✅ Connected" if agent.tiktok_token else "❌ Not connected"

        await update.message.reply_text(
            f"👤 *Your Profile*\n\n"
            f"*Name:* {agent.name}\n"
            f"*Email:* {agent.email or 'N/A'}\n"
            f"*Phone:* {agent.phone or 'N/A'}\n"
            f"*Plan:* {agent.plan.capitalize()}\n\n"
            f"*Social Connections:*\n"
            f"  Facebook: {fb}\n"
            f"  Instagram: {ig}\n"
            f"  TikTok: {tt}",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        db.close()


async def cmd_performance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current week performance metrics."""
    from datetime import datetime, timedelta, timezone

    user = update.effective_user
    if user is None:
        return

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.telegram_id == str(user.id)).first()
        if not agent:
            await update.message.reply_text("Please /start first.")
            return

        from database import Performance

        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        perf = (
            db.query(Performance)
            .filter(Performance.agent_id == agent.id, Performance.week_start >= week_start)
            .first()
        )

        if not perf:
            await update.message.reply_text(
                "📊 No performance data for this week yet. "
                "Data is updated as leads come in."
            )
            return

        await update.message.reply_text(
            f"📊 *This Week's Performance*\n\n"
            f"📥 Total Leads: *{perf.leads_count}*\n"
            f"⭐ Qualified: *{perf.qualified_leads}*\n"
            f"🤝 Deals Closed: *{perf.deals_closed}*\n"
            f"⏱ Avg Response: *{perf.avg_response_time_minutes:.1f} min*\n\n"
            f"👥 *Followers*\n"
            f"  Facebook: {perf.followers_facebook}\n"
            f"  Instagram: {perf.followers_instagram}\n"
            f"  TikTok: {perf.followers_tiktok}",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        db.close()


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Request/display the weekly performance report."""
    user = update.effective_user
    if user is None:
        return

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.telegram_id == str(user.id)).first()
        if not agent:
            await update.message.reply_text("Please /start first.")
            return

        from scheduler import generate_agent_report

        report = await generate_agent_report(agent, db)
        await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)
    except Exception as exc:
        logger.error("Error generating report: %s", exc)
        await update.message.reply_text("⚠️ Could not generate report. Please try again later.")
    finally:
        db.close()


async def cmd_connect_facebook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guide the agent through connecting their Facebook Page."""
    await update.message.reply_text(
        "🔗 *Connect Your Facebook Page*\n\n"
        "To connect your Facebook Page, follow these steps:\n\n"
        "1️⃣ Go to [Facebook Developer Portal](https://developers.facebook.com/)\n"
        "2️⃣ Create an app and add the *Pages API* product\n"
        "3️⃣ Generate a *Page Access Token* for your Page\n"
        "4️⃣ Send your token to the admin or enter it via the Electron app\n\n"
        "📌 Your Page ID and token will be linked to your account by the admin.",
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def cmd_connect_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Guide the agent through connecting their Instagram Business account."""
    await update.message.reply_text(
        "🔗 *Connect Your Instagram Business Account*\n\n"
        "1️⃣ Make sure your Instagram is a *Business* or *Creator* account\n"
        "2️⃣ Connect it to your Facebook Page in Instagram settings\n"
        "3️⃣ Use the same Facebook Page Access Token (it covers Instagram too)\n"
        "4️⃣ Provide your *Instagram Business Account ID* – found in Instagram's API settings\n\n"
        "📌 Contact the admin to complete the setup.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_postads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show paid advertising options."""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Facebook Ads", callback_data="ads_facebook")],
        [InlineKeyboardButton("📸 Instagram Ads", callback_data="ads_instagram")],
        [InlineKeyboardButton("🎵 TikTok Ads", callback_data="ads_tiktok")],
    ])
    await update.message.reply_text(
        "📢 *Paid Advertising*\n\n"
        "Boost your listings with paid ads. Choose a platform:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


async def cmd_leads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show paginated leads list."""
    await _show_leads_page(update, context, page=0, qualified_only=False)


async def cmd_qualified(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show only qualified leads."""
    await _show_leads_page(update, context, page=0, qualified_only=True)


async def _show_leads_page(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    qualified_only: bool = False,
) -> None:
    """Display a paginated leads list."""
    user = update.effective_user
    if user is None:
        return

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.telegram_id == str(user.id)).first()
        if not agent:
            msg = update.message or (update.callback_query and update.callback_query.message)
            if msg:
                await msg.reply_text("Please /start first.")
            return

        query = db.query(Lead).filter(Lead.agent_id == agent.id)
        if qualified_only:
            query = query.filter(Lead.qualification_status == "qualified")
        query = query.order_by(Lead.created_at.desc())

        page_size = 5
        total = query.count()
        leads = query.offset(page * page_size).limit(page_size).all()

        total_pages = max(1, (total + page_size - 1) // page_size)
        header = "⭐ *Qualified Leads*" if qualified_only else "👥 *Your Leads*"
        text = f"{header} (Page {page + 1}/{total_pages}, Total: {total})\n\n"

        if not leads:
            text += "_No leads found._"
            markup = None
        else:
            for lead in leads:
                name = f"{lead.name or '?'} {lead.last_name or ''}".strip()
                text += f"• #{lead.id} {name} – _{lead.qualification_status}_\n"
            markup = _leads_keyboard(leads, page, total_pages)

        msg = update.message
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup
            )
        elif msg:
            await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Listing creation conversation
# ---------------------------------------------------------------------------


async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the listing creation wizard."""
    context.user_data.clear()
    context.user_data["photos"] = []
    await update.message.reply_text(
        "🏠 *New Listing Wizard*\n\n"
        "Step 1/7: Send me the property *photos* (one or more).\n"
        "When done, send /done to continue.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_MEDIA


async def post_receive_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect photos/videos from the agent."""
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data.setdefault("photos", []).append(file_id)
        await update.message.reply_text(
            f"📷 Photo received ({len(context.user_data['photos'])} so far). "
            "Send more or /done to continue."
        )
    elif update.message.video:
        context.user_data["video"] = update.message.video.file_id
        await update.message.reply_text("🎬 Video received. Send /done to continue.")
    return POST_MEDIA


async def post_done_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finish media collection and ask for title."""
    if not context.user_data.get("photos") and not context.user_data.get("video"):
        await update.message.reply_text(
            "Please send at least one photo or video first."
        )
        return POST_MEDIA

    await update.message.reply_text(
        "✅ Media saved!\n\nStep 2/7: What is the *property title*?\n"
        "_(e.g. '3BR House in Miami Beach')_",
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_TITLE


async def post_receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 3/7: What is the *asking price*?\n_(e.g. '$450,000' or '$2,500/mo')_",
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_PRICE


async def post_receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["price"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 4/7: What is the *location / address*?\n_(City, neighbourhood, or full address)_",
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_LOCATION


async def post_receive_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["location"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 5/7: How many *bedrooms*? _(Enter a number or 0)_",
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_BEDROOMS


async def post_receive_bedrooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["bedrooms"] = int(update.message.text.strip())
    except ValueError:
        context.user_data["bedrooms"] = None
    await update.message.reply_text(
        "Step 6/7: How many *bathrooms*? _(Enter a number or 0)_",
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_BATHROOMS


async def post_receive_bathrooms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["bathrooms"] = int(update.message.text.strip())
    except ValueError:
        context.user_data["bathrooms"] = None
    await update.message.reply_text(
        "Step 7/7: Write the *property description*:\n"
        "_(Features, amenities, highlights…)_",
        parse_mode=ParseMode.MARKDOWN,
    )
    return POST_DESCRIPTION


async def post_receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Collect description and ask for confirmation."""
    context.user_data["description"] = update.message.text.strip()
    d = context.user_data
    confirm_text = (
        f"📋 *Listing Summary*\n\n"
        f"*Title:* {d.get('title')}\n"
        f"*Price:* {d.get('price')}\n"
        f"*Location:* {d.get('location')}\n"
        f"*Bedrooms:* {d.get('bedrooms')}\n"
        f"*Bathrooms:* {d.get('bathrooms')}\n"
        f"*Photos:* {len(d.get('photos', []))}\n"
        f"*Video:* {'Yes' if d.get('video') else 'No'}\n\n"
        f"*Description:*\n{d.get('description')}\n\n"
        "Post this listing to your connected social platforms?"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Post Now", callback_data="post_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="post_cancel"),
        ]
    ])
    await update.message.reply_text(
        confirm_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
    )
    return POST_CONFIRM


async def post_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the Post Now / Cancel inline button."""
    query = update.callback_query
    await query.answer()

    if query.data == "post_cancel":
        await query.edit_message_text("❌ Listing creation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    user = update.effective_user
    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.telegram_id == str(user.id)).first()
        if not agent:
            await query.edit_message_text("Agent not found. Please /start again.")
            return ConversationHandler.END

        import json

        d = context.user_data
        listing = Listing(
            agent_id=agent.id,
            title=d.get("title", "Untitled"),
            description=d.get("description"),
            price=d.get("price"),
            location=d.get("location"),
            bedrooms=d.get("bedrooms"),
            bathrooms=d.get("bathrooms"),
            photos=json.dumps(d.get("photos", [])),
            video_file_id=d.get("video"),
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)

        await query.edit_message_text(
            f"✅ Listing *#{listing.id}* saved!\n\n"
            "🚀 Posting to your connected platforms…",
            parse_mode=ParseMode.MARKDOWN,
        )

        # Post to social media
        results = await _post_listing_to_socials(listing, agent, db)
        status_text = _format_post_results(listing.id, results)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=status_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_listing_keyboard(listing.id),
        )
    except Exception as exc:
        logger.error("Error saving listing: %s", exc)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ An error occurred while saving the listing.",
        )
    finally:
        db.close()
        context.user_data.clear()

    return ConversationHandler.END


async def _post_listing_to_socials(listing: Listing, agent: Agent, db) -> dict:
    """Post a listing to all connected social platforms and update the DB."""
    from social_service import post_to_facebook, post_to_instagram, post_to_tiktok

    results: dict = {}

    fb_post_id = await post_to_facebook(listing, agent.facebook_token)
    if fb_post_id:
        listing.posted_to_facebook = True
        listing.facebook_post_id = fb_post_id
        results["facebook"] = fb_post_id

    ig_post_id = await post_to_instagram(listing, agent.instagram_token)
    if ig_post_id:
        listing.posted_to_instagram = True
        listing.instagram_post_id = ig_post_id
        results["instagram"] = ig_post_id

    tt_post_id = await post_to_tiktok(listing, agent.tiktok_token)
    if tt_post_id:
        listing.posted_to_tiktok = True
        results["tiktok"] = tt_post_id

    db.commit()
    return results


def _format_post_results(listing_id: int, results: dict) -> str:
    lines = [f"📣 *Listing #{listing_id} Post Results:*\n"]
    for platform in ("facebook", "instagram", "tiktok"):
        post_id = results.get(platform)
        icon = {"facebook": "📘", "instagram": "📸", "tiktok": "🎵"}[platform]
        status = f"✅ Posted (ID: {post_id})" if post_id else "⚠️ Not posted / not connected"
        lines.append(f"{icon} {platform.capitalize()}: {status}")
    return "\n".join(lines)


async def post_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the listing wizard."""
    await update.message.reply_text("❌ Listing creation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Quick-post: photo/video sent directly without /post command
# ---------------------------------------------------------------------------


async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle a photo/video sent directly to the bot (outside the wizard).

    If the message has a caption, use it as the description and auto-create
    a listing with placeholder fields.
    """
    user = update.effective_user
    if user is None:
        return

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.telegram_id == str(user.id)).first()
        if not agent:
            await update.message.reply_text("Please /start to register first.")
            return

        import json

        caption = update.message.caption or ""
        photos = []
        video_id = None

        if update.message.photo:
            photos.append(update.message.photo[-1].file_id)
        elif update.message.video:
            video_id = update.message.video.file_id

        listing = Listing(
            agent_id=agent.id,
            title=caption[:80] or "New Property",
            description=caption or None,
            photos=json.dumps(photos),
            video_file_id=video_id,
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)

        await update.message.reply_text(
            f"📷 Quick listing *#{listing.id}* created!\n\n"
            "🚀 Posting to your connected platforms…",
            parse_mode=ParseMode.MARKDOWN,
        )

        results = await _post_listing_to_socials(listing, agent, db)
        status_text = _format_post_results(listing.id, results)

        await update.message.reply_text(
            status_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_listing_keyboard(listing.id),
        )
    except Exception as exc:
        logger.error("Error in quick post: %s", exc)
        await update.message.reply_text("⚠️ An error occurred. Please try /post instead.")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Callback query handlers
# ---------------------------------------------------------------------------


async def callback_leads_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle leads pagination callbacks."""
    query = update.callback_query
    await query.answer()
    page = int(query.data.split(":")[1])
    await _show_leads_page(update, context, page=page)


async def callback_lead_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a lead's full details."""
    query = update.callback_query
    await query.answer()
    lead_id = int(query.data.split(":")[1])

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            await query.edit_message_text("Lead not found.")
            return

        name = f"{lead.name or '?'} {lead.last_name or ''}".strip()
        text = (
            f"👤 *Lead #{lead.id}*\n\n"
            f"*Name:* {name}\n"
            f"*Email:* {lead.email or 'N/A'}\n"
            f"*Phone:* {lead.phone or 'N/A'}\n"
            f"*Platform:* {lead.platform or 'N/A'}\n"
            f"*Status:* {lead.qualification_status}\n"
            f"*Score:* {lead.qualification_score}/100\n\n"
            f"*Message:*\n_{lead.message or 'N/A'}_\n\n"
            f"*Notes:*\n{lead.qualification_notes or 'N/A'}"
        )
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_lead_detail_keyboard(lead_id),
        )
    finally:
        db.close()


async def callback_lead_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle qualify / unqualify / call actions on a lead."""
    query = update.callback_query
    await query.answer()
    action, lead_id_str = query.data.split(":")
    lead_id = int(lead_id_str)

    db = SessionLocal()
    try:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            await query.answer("Lead not found.", show_alert=True)
            return

        if action == "lead_qualify":
            lead.qualification_status = "qualified"
            db.commit()
            await query.answer("✅ Lead marked as qualified.", show_alert=True)

        elif action == "lead_unqualify":
            lead.qualification_status = "unqualified"
            db.commit()
            await query.answer("❌ Lead marked as unqualified.", show_alert=True)

        elif action == "lead_call":
            agent = db.query(Agent).filter(Agent.id == lead.agent_id).first()
            if agent:
                from call_service import trigger_ghl_call, trigger_twilio_call

                success = await trigger_ghl_call(lead, agent)
                if not success:
                    success = await trigger_twilio_call(lead, agent)

                lead.qualification_status = "called"
                db.commit()
                msg = "📞 Call triggered!" if success else "⚠️ Call failed. Check credentials."
                await query.answer(msg, show_alert=True)
    finally:
        db.close()


async def callback_listing_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle listing management inline button actions."""
    query = update.callback_query
    await query.answer()
    action, listing_id_str = query.data.split(":")
    listing_id = int(listing_id_str)

    db = SessionLocal()
    try:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if not listing:
            await query.answer("Listing not found.", show_alert=True)
            return

        if action == "listing_archive":
            listing.status = "pending"
            db.commit()
            await query.answer("📦 Listing archived.", show_alert=True)

        elif action == "listing_stats":
            lead_count = db.query(Lead).filter(Lead.listing_id == listing_id).count()
            qualified = (
                db.query(Lead)
                .filter(
                    Lead.listing_id == listing_id,
                    Lead.qualification_status == "qualified",
                )
                .count()
            )
            await query.answer(
                f"Listing #{listing_id}: {lead_count} leads, {qualified} qualified",
                show_alert=True,
            )

        elif action == "listing_edit":
            await query.answer(
                "To edit a listing, please use the Electron desktop app.", show_alert=True
            )
    finally:
        db.close()


async def callback_ads(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ads platform selection."""
    query = update.callback_query
    await query.answer()
    platform = query.data.split("_")[1]
    await query.edit_message_text(
        f"📢 *{platform.capitalize()} Ads*\n\n"
        f"To run paid ads on {platform.capitalize()}, please use the Electron desktop app "
        "where you can set your budget, audience, and ad creative.\n\n"
        "Contact your admin for more information.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------


async def admin_clients(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: list all registered agents."""
    if not _is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    db = SessionLocal()
    try:
        agents = db.query(Agent).order_by(Agent.created_at.desc()).limit(20).all()
        if not agents:
            await update.message.reply_text("No agents registered yet.")
            return

        lines = ["👥 *Registered Agents:*\n"]
        for a in agents:
            status = "✅" if a.is_active else "❌"
            lines.append(f"{status} #{a.id} {a.name} (@{a.telegram_username or 'N/A'}) – {a.plan}")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    finally:
        db.close()


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: show global statistics."""
    if not _is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    db = SessionLocal()
    try:
        from database import Invoice, Lead, Listing

        agent_count = db.query(Agent).count()
        listing_count = db.query(Listing).count()
        lead_count = db.query(Lead).count()
        qualified_count = (
            db.query(Lead).filter(Lead.qualification_status == "qualified").count()
        )
        pending_invoices = (
            db.query(Invoice).filter(Invoice.status == "pending").count()
        )

        await update.message.reply_text(
            f"📊 *Global Stats*\n\n"
            f"👤 Agents: {agent_count}\n"
            f"🏠 Listings: {listing_count}\n"
            f"📥 Total Leads: {lead_count}\n"
            f"⭐ Qualified Leads: {qualified_count}\n"
            f"💳 Pending Invoices: {pending_invoices}",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        db.close()


async def admin_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: create an invoice for an agent. Usage: /admin_invoice <agent_id> <amount>"""
    if not _is_admin(update):
        await update.message.reply_text("⛔ Admin only.")
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Usage: /admin_invoice <agent_id> <amount>\nExample: /admin_invoice 3 299.00"
        )
        return

    try:
        agent_id = int(args[0])
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid arguments. agent_id must be an integer, amount a number.")
        return

    from datetime import datetime, timedelta, timezone

    from database import Invoice

    db = SessionLocal()
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            await update.message.reply_text(f"Agent #{agent_id} not found.")
            return

        invoice = Invoice(
            agent_id=agent_id,
            amount=amount,
            due_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        await update.message.reply_text(
            f"✅ Invoice #{invoice.id} created for {agent.name}: ${amount:.2f} USD\n"
            f"Due: {invoice.due_date.strftime('%Y-%m-%d')}",
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Bot application factory
# ---------------------------------------------------------------------------


def build_application(token: str) -> Application:
    """Build and configure the Telegram bot Application."""
    app = Application.builder().token(token).build()

    # Listing creation conversation
    post_conv = ConversationHandler(
        entry_points=[CommandHandler("post", cmd_post)],
        states={
            POST_MEDIA: [
                MessageHandler(filters.PHOTO | filters.VIDEO, post_receive_media),
                CommandHandler("done", post_done_media),
            ],
            POST_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_title)],
            POST_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_price)],
            POST_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_location)],
            POST_BEDROOMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_bedrooms)],
            POST_BATHROOMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_bathrooms)],
            POST_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_description)],
            POST_CONFIRM: [CallbackQueryHandler(post_confirm_callback, pattern="^post_")],
        },
        fallbacks=[CommandHandler("cancel", post_cancel)],
        allow_reentry=True,
    )

    app.add_handler(post_conv)

    # Basic commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("leads", cmd_leads))
    app.add_handler(CommandHandler("qualified", cmd_qualified))
    app.add_handler(CommandHandler("performance", cmd_performance))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("connect_facebook", cmd_connect_facebook))
    app.add_handler(CommandHandler("connect_instagram", cmd_connect_instagram))
    app.add_handler(CommandHandler("postads", cmd_postads))
    app.add_handler(CommandHandler("profile", cmd_profile))

    # Admin commands
    app.add_handler(CommandHandler("admin_clients", admin_clients))
    app.add_handler(CommandHandler("admin_stats", admin_stats))
    app.add_handler(CommandHandler("admin_invoice", admin_invoice))

    # Callback queries
    app.add_handler(CallbackQueryHandler(callback_leads_page, pattern="^leads_page:"))
    app.add_handler(CallbackQueryHandler(callback_lead_detail, pattern="^lead_detail:"))
    app.add_handler(
        CallbackQueryHandler(callback_lead_action, pattern="^lead_(qualify|unqualify|call):")
    )
    app.add_handler(CallbackQueryHandler(callback_listing_action, pattern="^listing_"))
    app.add_handler(CallbackQueryHandler(callback_ads, pattern="^ads_"))

    # Direct media messages (quick post)
    app.add_handler(
        MessageHandler(
            (filters.PHOTO | filters.VIDEO) & ~filters.COMMAND,
            handle_media_message,
        )
    )

    return app
