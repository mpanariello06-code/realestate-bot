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
