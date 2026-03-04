"""
Flask Web Portal – routes and view helpers.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

import requests as http_requests
from flask import Blueprint, jsonify, render_template, request

import config
from services import sheets, ghl as ghl_service

logger = logging.getLogger(__name__)

bp = Blueprint("portal", __name__)


@bp.route("/")
def index():
    return render_template("dashboard.html", title="Dashboard")


@bp.route("/dashboard")
def dashboard():
    perf = sheets.get_performance(weeks=4)
    leads = sheets.get_leads()

    total_leads = len(leads)
    qualified = [l for l in leads if str(l.get("is_qualified", "")).upper() == "TRUE"]
    closed = [l for l in leads if l.get("status") == "closed"]

    stats = {
        "total_leads": total_leads,
        "qualified_leads": len(qualified),
        "deals_closed": len(closed),
        "conversion_rate": round(len(closed) / total_leads * 100, 1) if total_leads else 0,
    }
    return render_template(
        "dashboard.html",
        title="Dashboard",
        stats=stats,
        performance=perf,
    )


@bp.route("/leads")
def leads_view():
    qualified_only = request.args.get("qualified", "false").lower() == "true"
    leads = sheets.get_leads(qualified_only=qualified_only)
    return render_template(
        "leads.html",
        title="Leads",
        leads=leads,
        qualified_only=qualified_only,
    )


# ── JSON API ──────────────────────────────────────────────────────────────────

@bp.route("/api/leads")
def api_leads():
    qualified_only = request.args.get("qualified", "false").lower() == "true"
    return jsonify(sheets.get_leads(qualified_only=qualified_only))


@bp.route("/api/performance")
def api_performance():
    weeks = int(request.args.get("weeks", 4))
    return jsonify(sheets.get_performance(weeks=weeks))


@bp.route("/api/leads/<int:lead_index>/status", methods=["POST"])
def api_update_lead_status(lead_index: int):
    data = request.get_json(force=True)
    status = data.get("status", "")
    notes = data.get("notes", "")
    if status not in ("new", "contacted", "closed", "lost"):
        return jsonify({"error": "Invalid status"}), 400
    success = sheets.update_lead_status(lead_index, status, notes)
    return jsonify({"success": success})


@bp.route("/connect-socials")
def connect_socials():
    return render_template("connect_socials.html", title="Connect Socials")


@bp.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


# ── Facebook Webhook ──────────────────────────────────────────────────────────

def _verify_fb_signature(payload: bytes, signature_header: str) -> bool:
    """
    Validate the X-Hub-Signature-256 header sent by Facebook.
    Returns True if the signature matches, False otherwise.
    If FACEBOOK_APP_SECRET is not set, validation is skipped and True is returned.
    """
    if not config.FACEBOOK_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        config.FACEBOOK_APP_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)


def _notify_agents(text: str) -> None:
    """Send a Telegram message to all configured agent chat IDs via the Bot API."""
    if not config.TELEGRAM_BOT_TOKEN or not config.AGENT_CHAT_IDS:
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in config.AGENT_CHAT_IDS:
        try:
            http_requests.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
        except Exception as exc:
            logger.error("Failed to notify agent %s: %s", chat_id, exc)


@bp.route("/webhook/facebook", methods=["GET"])
def fb_webhook_verify():
    """
    Facebook webhook verification handshake.
    Facebook sends a GET with hub.mode=subscribe, hub.verify_token, and
    hub.challenge.  We confirm our verify token and echo back the challenge.

    To enable: set FACEBOOK_WEBHOOK_VERIFY_TOKEN in .env to a secret string
    and register <your-server>/webhook/facebook as the callback URL in the
    Facebook App Dashboard under Webhooks.
    """
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == config.FACEBOOK_WEBHOOK_VERIFY_TOKEN:
        logger.info("Facebook webhook verified successfully.")
        return challenge, 200

    logger.warning("Facebook webhook verification failed (token mismatch).")
    return jsonify({"error": "Verification failed"}), 403


@bp.route("/webhook/facebook", methods=["POST"])
def fb_webhook_event():
    """
    Receive Facebook webhook events and forward DM/comment notifications
    to every agent via Telegram.

    Supported event types that trigger a notification:
    • messages      – someone sent a DM to the Facebook Page
    • messaging_postbacks – someone tapped a CTA button on a post
    • feed (comments) – someone commented on a Page post

    Setup checklist:
    1. Set FACEBOOK_WEBHOOK_VERIFY_TOKEN and FACEBOOK_APP_SECRET in .env.
    2. In the Facebook App Dashboard → Webhooks, subscribe to the Page
       and tick: messages, messaging_postbacks, feed.
    3. Ensure your server is publicly accessible (use ngrok for local dev).
    """
    # Validate signature
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_fb_signature(request.get_data(), sig):
        logger.warning("Facebook webhook: invalid signature, rejecting request.")
        return jsonify({"error": "Invalid signature"}), 403

    data = request.get_json(force=True, silent=True) or {}

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            page_id = entry.get("id", "")

            # ── Direct messages ───────────────────────────────────────────────
            for event in entry.get("messaging", []):
                sender_id = event.get("sender", {}).get("id", "unknown")
                msg_obj   = event.get("message", {})
                msg_text  = msg_obj.get("text", "")
                # Exclude echo events where the page itself is the sender
                if msg_text and sender_id != page_id:
                    notification = (
                        "💬 *New Facebook DM on your listing!*\n\n"
                        f"👤 Sender ID: `{sender_id}`\n"
                        f"✉️ Message: {msg_text}\n\n"
                        "_Open Facebook Business Suite to reply._"
                    )
                    _notify_agents(notification)
                    logger.info("Facebook DM from %s forwarded to agents.", sender_id)

            # ── Feed events (comments) ─────────────────────────────────────────
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if change.get("field") == "feed" and value.get("item") == "comment":
                    commenter = value.get("from", {}).get("name", "Someone")
                    comment   = value.get("message", "")
                    post_id   = value.get("post_id", "")
                    if comment:
                        notification = (
                            "💬 *New comment on your Facebook post!*\n\n"
                            f"👤 {commenter}\n"
                            f"✉️ {comment}\n"
                            f"🔗 Post ID: `{post_id}`\n\n"
                            "_Open Facebook to reply._"
                        )
                        _notify_agents(notification)
                        logger.info("Facebook comment from %s forwarded to agents.", commenter)

    return jsonify({"status": "ok"}), 200


# ── Go High Level Webhook ─────────────────────────────────────────────────────

def _verify_ghl_signature(payload: bytes, signature_header: str) -> bool:
    """
    Validate the x-ghl-signature header sent by GHL.
    Returns True if the signature matches (or if no secret is configured).
    """
    if not config.GHL_WEBHOOK_SECRET:
        return True
    if not signature_header:
        return False
    import hashlib
    import hmac as _hmac
    expected = _hmac.new(
        config.GHL_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return _hmac.compare_digest(expected, signature_header)


@bp.route("/webhook/ghl", methods=["POST"])
def ghl_webhook_event():
    """
    Receive Go High Level webhook events.

    GHL sends an InboundMessage event whenever a contact replies to a post
    or sends a new message via any connected social channel (Facebook, Instagram,
    SMS, WhatsApp, Live Chat, etc.).

    On each InboundMessage the bot will:
      1. Validate the optional HMAC-SHA256 signature.
      2. Send an auto-DM reply into the same GHL conversation thread (if
         GHL_AUTO_REPLY_ENABLED=true).
      3. Forward a notification to every agent on Telegram.

    GHL setup checklist
    ───────────────────
    1. In GHL → Settings → Integrations → Webhooks, add a new webhook
       pointing to  <your-server>/webhook/ghl
    2. Subscribe to the  InboundMessage  event type.
    3. Optionally set a signing secret and add it as GHL_WEBHOOK_SECRET in .env.
    4. Set GHL_API_KEY and GHL_LOCATION_ID in .env (needed for auto-DM).
    5. Customise GHL_AUTO_REPLY_MESSAGE in .env (use {first_name} as a placeholder).

    Social Planner / post-reply flow
    ─────────────────────────────────
    When a follower comments on or DMs a post that was published through
    GHL's Social Planner, GHL creates an inbound conversation and fires this
    webhook.  The bot then auto-replies and pings the agent – no manual
    Facebook/Instagram monitoring needed.
    """
    # Signature validation
    sig = request.headers.get("X-GHL-Signature", "")
    if not _verify_ghl_signature(request.get_data(), sig):
        logger.warning("GHL webhook: invalid signature, rejecting.")
        return jsonify({"error": "Invalid signature"}), 403

    data = request.get_json(force=True, silent=True) or {}
    event_type = data.get("type", "")

    if event_type == "InboundMessage":
        contact_id      = data.get("contactId", "")
        conversation_id = data.get("conversationId", "")
        first_name      = data.get("firstName") or data.get("contactName", "").split()[0] or "there"
        last_name       = data.get("lastName", "")
        full_name       = f"{first_name} {last_name}".strip() or "Unknown"
        body            = data.get("body") or data.get("message", "")
        channel         = data.get("channel") or data.get("messageType", "unknown")
        source_url      = data.get("sourceUrl", "")  # URL of the post they replied to

        logger.info(
            "GHL InboundMessage from contact=%s conv=%s channel=%s",
            contact_id, conversation_id, channel,
        )

        # ── Auto-DM reply ──────────────────────────────────────────────────────
        if config.GHL_AUTO_REPLY_ENABLED and body and contact_id:
            reply_text = config.GHL_AUTO_REPLY_MESSAGE.format(
                first_name=first_name,
                last_name=last_name,
                full_name=full_name,
            )
            # Prefer replying into the same conversation so the reply stays
            # on the correct channel (Facebook/Instagram/SMS/etc.)
            if conversation_id:
                result = ghl_service.send_dm_to_conversation(
                    conversation_id, reply_text
                )
            else:
                result = ghl_service.send_dm(contact_id, reply_text)

            if result.get("success"):
                logger.info("GHL auto-DM sent to contact %s.", contact_id)
            else:
                logger.error("GHL auto-DM failed: %s", result.get("error"))

        # ── Telegram notification ──────────────────────────────────────────────
        channel_label = channel.replace("_", " ").title() if channel else "Social"
        post_line = f"\n🔗 Post: {source_url}" if source_url else ""
        notification = (
            f"📩 *New {channel_label} reply via GHL!*\n\n"
            f"👤 {full_name}\n"
            f"✉️ {body}{post_line}\n\n"
            + (
                "✅ _Auto-DM reply sent._"
                if config.GHL_AUTO_REPLY_ENABLED and body
                else "_Auto-reply is disabled._"
            )
        )
        _notify_agents(notification)

    return jsonify({"status": "ok"}), 200
