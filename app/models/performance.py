from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)
    facebook_followers = Column(Integer, default=0)
    instagram_followers = Column(Integer, default=0)
    tiktok_followers = Column(Integer, default=0)
    total_leads = Column(Integer, default=0)
    qualified_leads = Column(Integer, default=0)
    deals_closed = Column(Integer, default=0)
    avg_response_time_minutes = Column(Float, default=0.0)
    total_posts = Column(Integer, default=0)
    total_engagements = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent", back_populates="performance_metrics")


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, paid, overdue
    due_date = Column(Date, nullable=False)
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    agent = relationship("Agent", back_populates="invoices")
