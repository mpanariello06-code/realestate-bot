from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class AgentBase(BaseModel):
    name: str
    email: EmailStr
    phone: str
    whatsapp_number: str


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    facebook_token: Optional[str] = None
    instagram_token: Optional[str] = None
    tiktok_token: Optional[str] = None
    is_active: Optional[bool] = None


class AgentResponse(AgentBase):
    id: int
    facebook_token: Optional[str] = None
    instagram_token: Optional[str] = None
    tiktok_token: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConnectSocialRequest(BaseModel):
    platform: str  # facebook, instagram, tiktok
    access_token: str
