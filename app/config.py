from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./realestate.db"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = "whatsapp:+14155238886"
    OPENAI_API_KEY: str = ""
    FACEBOOK_APP_ID: str = ""
    FACEBOOK_APP_SECRET: str = ""
    INSTAGRAM_ACCESS_TOKEN: str = ""
    TIKTOK_ACCESS_TOKEN: str = ""
    SECRET_KEY: str = "changeme-secret-key"
    ADMIN_WHATSAPP_NUMBER: str = ""
    BASE_URL: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
