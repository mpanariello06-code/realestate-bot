import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class ListingStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SOLD = "sold"
    WITHDRAWN = "withdrawn"


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    address = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    description = Column(Text, nullable=False)
    media_urls = Column(Text, default="[]")  # JSON list of URLs
    status = Column(Enum(ListingStatus), default=ListingStatus.DRAFT, nullable=False)
    posted_platforms = Column(Text, default="[]")  # JSON list of platforms posted to
    facebook_post_id = Column(String, nullable=True)
    instagram_post_id = Column(String, nullable=True)
    tiktok_post_id = Column(String, nullable=True)
    target_demographic = Column(Text, nullable=True)  # JSON description for ad targeting
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="listings")
