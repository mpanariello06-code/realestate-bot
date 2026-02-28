from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    phone = Column(String, nullable=False)
    whatsapp_number = Column(String, unique=True, nullable=False, index=True)
    telegram_chat_id = Column(String, unique=True, nullable=True, index=True)
    facebook_token = Column(String, nullable=True)
    instagram_token = Column(String, nullable=True)
    tiktok_token = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    leads = relationship("Lead", back_populates="agent", cascade="all, delete-orphan")
    listings = relationship("Listing", back_populates="agent", cascade="all, delete-orphan")
    performance_metrics = relationship("PerformanceMetric", back_populates="agent", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="agent", cascade="all, delete-orphan")
