"""
SQLAlchemy database models and session management for the real estate bot backend.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

DB_DIR = Path(__file__).parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_DIR / 'realestate.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that yields a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Helper: store lists as JSON text
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Agent(Base):
    """Real-estate agent registered in the system."""

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True, nullable=False)
    telegram_username = Column(String, nullable=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    # Per-agent social tokens (override global ones from env)
    facebook_token = Column(Text, nullable=True)
    instagram_token = Column(Text, nullable=True)
    tiktok_token = Column(Text, nullable=True)
    ghl_contact_id = Column(String, nullable=True)
    plan = Column(String, default="basic")  # basic | pro
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_now_utc)
    last_active = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    listings = relationship("Listing", back_populates="agent", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="agent", cascade="all, delete-orphan")
    performances = relationship("Performance", back_populates="agent", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="agent", cascade="all, delete-orphan")


class Listing(Base):
    """A property listing created by an agent."""

    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(String, nullable=True)
    location = Column(String, nullable=True)
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    area_sqft = Column(Float, nullable=True)
    # JSON-encoded list of Telegram file_ids
    photos = Column(Text, default="[]")
    video_file_id = Column(String, nullable=True)
    status = Column(String, default="active")  # active | sold | pending
    # Social post tracking
    posted_to_facebook = Column(Boolean, default=False)
    posted_to_instagram = Column(Boolean, default=False)
    posted_to_tiktok = Column(Boolean, default=False)
    facebook_post_id = Column(String, nullable=True)
    instagram_post_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_now_utc)

    agent = relationship("Agent", back_populates="listings")
    leads = relationship("Lead", back_populates="listing")

    @property
    def photos_list(self) -> list[str]:
        """Return the photos field as a Python list."""
        try:
            return json.loads(self.photos or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    @photos_list.setter
    def photos_list(self, value: list[str]) -> None:
        self.photos = json.dumps(value)


class Lead(Base):
    """A potential buyer/renter who showed interest in a listing."""

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=True)
    platform = Column(String, nullable=True)  # facebook | instagram | tiktok | direct
    name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    qualification_score = Column(Integer, default=0)  # 0-100
    qualification_status = Column(String, default="new")  # new | qualified | unqualified | called
    qualification_notes = Column(Text, nullable=True)
    is_notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now_utc)
    updated_at = Column(DateTime, default=_now_utc, onupdate=_now_utc)

    agent = relationship("Agent", back_populates="leads")
    listing = relationship("Listing", back_populates="leads")


class Performance(Base):
    """Weekly performance snapshot for an agent."""

    __tablename__ = "performances"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    week_start = Column(DateTime, nullable=False)
    followers_facebook = Column(Integer, default=0)
    followers_instagram = Column(Integer, default=0)
    followers_tiktok = Column(Integer, default=0)
    leads_count = Column(Integer, default=0)
    qualified_leads = Column(Integer, default=0)
    deals_closed = Column(Integer, default=0)
    avg_response_time_minutes = Column(Float, default=0.0)
    report_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now_utc)

    agent = relationship("Agent", back_populates="performances")


class Invoice(Base):
    """Billing invoice for an agent."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    status = Column(String, default="pending")  # pending | paid | overdue
    due_date = Column(DateTime, nullable=True)
    paid_date = Column(DateTime, nullable=True)
    stripe_invoice_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_now_utc)

    agent = relationship("Agent", back_populates="invoices")


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------


def create_tables() -> None:
    """Create all database tables (idempotent)."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified at %s", DATABASE_URL)
