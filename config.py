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
