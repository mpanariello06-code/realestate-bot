from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class PerformanceMetricBase(BaseModel):
    week_start: date
    week_end: date
    facebook_followers: int = 0
    instagram_followers: int = 0
    tiktok_followers: int = 0
    total_leads: int = 0
    qualified_leads: int = 0
    deals_closed: int = 0
    avg_response_time_minutes: float = 0.0
    total_posts: int = 0
    total_engagements: int = 0


class PerformanceMetricCreate(PerformanceMetricBase):
    agent_id: int


class PerformanceMetricResponse(PerformanceMetricBase):
    id: int
    agent_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceBase(BaseModel):
    amount: float
    description: str
    due_date: date
    status: str = "pending"


class InvoiceCreate(InvoiceBase):
    agent_id: int


class InvoiceResponse(InvoiceBase):
    id: int
    agent_id: int
    paid_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
