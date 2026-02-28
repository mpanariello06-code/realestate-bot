"""
Pydantic v2 models (schemas) for API request/response validation.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------


class _ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AgentCreate(BaseModel):
    telegram_id: str
    telegram_username: Optional[str] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    plan: str = "basic"


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    facebook_token: Optional[str] = None
    instagram_token: Optional[str] = None
    tiktok_token: Optional[str] = None
    ghl_contact_id: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None


class AgentResponse(_ORMBase):
    id: int
    telegram_id: str
    telegram_username: Optional[str]
    name: str
    email: Optional[str]
    phone: Optional[str]
    plan: str
    is_active: bool
    created_at: datetime
    last_active: datetime


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


class ListingCreate(BaseModel):
    agent_id: int
    title: str
    description: Optional[str] = None
    price: Optional[str] = None
    location: Optional[str] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_sqft: Optional[float] = None
    photos: list[str] = Field(default_factory=list)
    video_file_id: Optional[str] = None


class ListingResponse(_ORMBase):
    id: int
    agent_id: int
    title: str
    description: Optional[str]
    price: Optional[str]
    location: Optional[str]
    bedrooms: Optional[int]
    bathrooms: Optional[int]
    area_sqft: Optional[float]
    photos: list[str] = Field(default_factory=list)
    video_file_id: Optional[str]
    status: str
    posted_to_facebook: bool
    posted_to_instagram: bool
    posted_to_tiktok: bool
    facebook_post_id: Optional[str]
    instagram_post_id: Optional[str]
    created_at: datetime

    @classmethod
    def from_orm_with_photos(cls, obj: Any) -> "ListingResponse":
        """Build response, deserializing the JSON photos field."""
        data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        import json

        data["photos"] = json.loads(data.get("photos") or "[]")
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------


class LeadCreate(BaseModel):
    agent_id: int
    listing_id: Optional[int] = None
    platform: Optional[str] = None
    name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    message: Optional[str] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    qualification_status: Optional[str] = None
    qualification_score: Optional[int] = None
    qualification_notes: Optional[str] = None
    is_notified: Optional[bool] = None


class LeadResponse(_ORMBase):
    id: int
    agent_id: int
    listing_id: Optional[int]
    platform: Optional[str]
    name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    message: Optional[str]
    qualification_score: int
    qualification_status: str
    qualification_notes: Optional[str]
    is_notified: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------


class PerformanceResponse(_ORMBase):
    id: int
    agent_id: int
    week_start: datetime
    followers_facebook: int
    followers_instagram: int
    followers_tiktok: int
    leads_count: int
    qualified_leads: int
    deals_closed: int
    avg_response_time_minutes: float
    report_sent: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


class InvoiceCreate(BaseModel):
    agent_id: int
    amount: float
    currency: str = "USD"
    due_date: Optional[datetime] = None
    stripe_invoice_id: Optional[str] = None


class InvoiceResponse(_ORMBase):
    id: int
    agent_id: int
    amount: float
    currency: str
    status: str
    due_date: Optional[datetime]
    paid_date: Optional[datetime]
    stripe_invoice_id: Optional[str]
    created_at: datetime


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------


class QualificationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    status: str  # qualified | unqualified
    notes: str
    suggested_response: str


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class WeeklyReport(BaseModel):
    agent_id: int
    agent_name: str
    week_start: datetime
    leads_count: int
    qualified_leads: int
    deals_closed: int
    avg_response_time_minutes: float
    followers_facebook: int
    followers_instagram: int
    followers_tiktok: int
    top_listing_title: Optional[str] = None
    report_text: str
