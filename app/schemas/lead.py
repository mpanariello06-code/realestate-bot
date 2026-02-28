from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.lead import LeadSource, LeadStatus


class LeadBase(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    source: LeadSource = LeadSource.OTHER
    notes: Optional[str] = None


class LeadCreate(LeadBase):
    agent_id: int


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[LeadSource] = None
    status: Optional[LeadStatus] = None
    qualification_score: Optional[float] = None
    conversation_text: Optional[str] = None
    ai_analysis: Optional[str] = None
    is_serious: Optional[bool] = None
    notes: Optional[str] = None


class LeadResponse(LeadBase):
    id: int
    agent_id: int
    status: LeadStatus
    qualification_score: float
    ai_analysis: Optional[str] = None
    is_serious: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
