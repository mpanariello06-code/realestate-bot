import os

from dotenv import load_dotenv

load_dotenv(override=False)  # load .env if present; already-set env vars take priority


class Settings:
    def __init__(self) -> None:
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./realestate.db")
        self.TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.TWILIO_WHATSAPP_NUMBER: str = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        self.FACEBOOK_APP_ID: str = os.getenv("FACEBOOK_APP_ID", "")
        self.FACEBOOK_APP_SECRET: str = os.getenv("FACEBOOK_APP_SECRET", "")
        self.INSTAGRAM_ACCESS_TOKEN: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
        self.TIKTOK_ACCESS_TOKEN: str = os.getenv("TIKTOK_ACCESS_TOKEN", "")
        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "changeme-secret-key")
        self.ADMIN_WHATSAPP_NUMBER: str = os.getenv("ADMIN_WHATSAPP_NUMBER", "")
        self.BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")


settings = Settings()
