"""
Central configuration – loads values from the .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. "
            "Please check your .env file."
        )
    return value


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
AGENT_CHAT_IDS: list[int] = [
    int(cid.strip())
    for cid in os.getenv("AGENT_CHAT_IDS", "").split(",")
    if cid.strip().lstrip("-").isdigit()
]

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = _require("OPENAI_API_KEY")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# ── Google Sheets ─────────────────────────────────────────────────────────────
GOOGLE_CREDENTIALS_FILE: str = os.getenv(
    "GOOGLE_CREDENTIALS_FILE", "google_credentials.json"
)
GOOGLE_SPREADSHEET_NAME: str = os.getenv(
    "GOOGLE_SPREADSHEET_NAME", "RealEstate Bot Leads"
)

# ── Facebook / Instagram ──────────────────────────────────────────────────────
FACEBOOK_PAGE_ACCESS_TOKEN: str = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "")
FACEBOOK_PAGE_ID: str = os.getenv("FACEBOOK_PAGE_ID", "")
INSTAGRAM_ACCOUNT_ID: str = os.getenv("INSTAGRAM_ACCOUNT_ID", "")

# ── TikTok ────────────────────────────────────────────────────────────────────
TIKTOK_ACCESS_TOKEN: str = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_OPEN_ID: str = os.getenv("TIKTOK_OPEN_ID", "")

# ── LinkedIn ──────────────────────────────────────────────────────────────────
# OAuth 2.0 access token for the LinkedIn API.
# LINKEDIN_AUTHOR_URN is the full URN of the posting identity, e.g.:
#   urn:li:person:AbCdEfGhIj   (personal profile)
#   urn:li:organization:123456 (company page)
LINKEDIN_ACCESS_TOKEN: str = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_AUTHOR_URN: str = os.getenv("LINKEDIN_AUTHOR_URN", "")

# ── Flask Portal ──────────────────────────────────────────────────────────────
FLASK_SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
FLASK_ENV: str = os.getenv("FLASK_ENV", "development")

# ── Lead Qualification ────────────────────────────────────────────────────────
LEAD_QUALIFICATION_THRESHOLD: int = int(
    os.getenv("LEAD_QUALIFICATION_THRESHOLD", "60")
)

# ── Weekly Report ─────────────────────────────────────────────────────────────
WEEKLY_REPORT_DAY: str = os.getenv("WEEKLY_REPORT_DAY", "mon")
WEEKLY_REPORT_TIME: str = os.getenv("WEEKLY_REPORT_TIME", "08:00")

# ── Facebook Webhook ──────────────────────────────────────────────────────────
# Set this to any secret string and configure the same value in the Facebook
# App Dashboard under Webhooks → Verify Token.
FACEBOOK_WEBHOOK_VERIFY_TOKEN: str = os.getenv("FACEBOOK_WEBHOOK_VERIFY_TOKEN", "")
# Used to validate the X-Hub-Signature-256 header on incoming webhook payloads.
# Set to your Facebook App Secret (found in App → Settings → Basic).
FACEBOOK_APP_SECRET: str = os.getenv("FACEBOOK_APP_SECRET", "")

# ── Zapier ───────────────────────────────────────────────────────────────────
# Webhook URL from a Zapier "Catch Hook" trigger.  When set, the bot sends
# every "Post Listing" payload here so Zapier can publish it to Facebook
# and/or Instagram.  Leave blank to fall back to GHL Social Planner or the
# direct Facebook/Instagram API.
ZAPIER_WEBHOOK_URL: str = os.getenv("ZAPIER_WEBHOOK_URL", "")
# Separate "Catch Hook" URL used by the "📋 All Leads" button.  When set,
# tapping the button POSTs {"action": "get_all_leads"} to this webhook and
# the response JSON is parsed for a "leads" list to display.  Leave blank to
# fall back to showing all leads directly from the local Google Sheet.
ZAPIER_ALL_LEADS_WEBHOOK_URL: str = os.getenv("ZAPIER_ALL_LEADS_WEBHOOK_URL", "")

# ── Cloudinary ────────────────────────────────────────────────────────────────
# Cloudinary stores listing photos and returns a public URL that Zapier (and
# Instagram/Facebook) can download when publishing the post.
# Get these from cloudinary.com → Dashboard → Product Environment Credentials.
CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")

# ── Go High Level (GHL) ───────────────────────────────────────────────────────
# Private Integration Key (or Agency API key) from GHL Settings → Integrations.
GHL_API_KEY: str = os.getenv("GHL_API_KEY", "")
# The sub-account / Location ID the bot operates under.
GHL_LOCATION_ID: str = os.getenv("GHL_LOCATION_ID", "")
# Optional HMAC-SHA256 secret for validating inbound GHL webhook payloads.
GHL_WEBHOOK_SECRET: str = os.getenv("GHL_WEBHOOK_SECRET", "")
# When True, the bot will automatically DM anyone who replies to a post.
GHL_AUTO_REPLY_ENABLED: bool = os.getenv("GHL_AUTO_REPLY_ENABLED", "true").lower() == "true"
# Message sent in the auto-DM.  Use {first_name} as a placeholder.
GHL_AUTO_REPLY_MESSAGE: str = os.getenv(
    "GHL_AUTO_REPLY_MESSAGE",
    "Hi {first_name}! 👋 Thanks for your interest. "
    "One of our agents will be in touch with you shortly. "
    "In the meantime, feel free to ask any questions!",
)
# Comma-separated list of GHL Social Planner account IDs to post to.
# Leave blank to auto-discover all connected accounts for the location.
# Example: "abc123,def456"
GHL_SOCIAL_ACCOUNT_IDS: str = os.getenv("GHL_SOCIAL_ACCOUNT_IDS", "")
# OAuth2 credentials for automatic token refresh.
# GHL Private Integration access tokens expire (typically after 24 hours).
# Setting these three values enables the bot to refresh the token silently
# instead of showing a 401 error.  Obtain them by completing the GHL OAuth2
# flow for your Private Integration (GHL docs → OAuth 2.0 → Authorization Code).
GHL_CLIENT_ID: str = os.getenv("GHL_CLIENT_ID", "")
GHL_CLIENT_SECRET: str = os.getenv("GHL_CLIENT_SECRET", "")
GHL_REFRESH_TOKEN: str = os.getenv("GHL_REFRESH_TOKEN", "")

# ── Telegram Auto-Reply ───────────────────────────────────────────────────────
# When True (the default), the bot auto-replies to every incoming text message
# that is not already handled by a conversation flow.  Set to "false" in .env
# to disable the catch-all AI response and let unhandled messages pass silently.
TELEGRAM_AUTO_REPLY_ENABLED: bool = os.getenv("TELEGRAM_AUTO_REPLY_ENABLED", "true").lower() == "true"

# ── Bot Banner Image ──────────────────────────────────────────────────────────
# Path to a local image file (or a public HTTPS URL) that is attached to key
# bot messages such as the welcome screen and auto-replies.  A bundled default
# banner is provided in the assets/ folder.  Set to an empty string to send
# plain-text messages with no image attached.
#
# The default is resolved as an *absolute* path relative to this config file so
# the bot finds the image regardless of the working directory it is launched from.
_DEFAULT_BANNER: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "banner.jpg"
)
BOT_BANNER_IMAGE: str = os.getenv("BOT_BANNER_IMAGE", _DEFAULT_BANNER)
