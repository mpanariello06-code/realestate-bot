from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.listing import ListingStatus


class ListingBase(BaseModel):
    address: str
    price: float
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    description: str
    target_demographic: Optional[str] = None


class ListingCreate(ListingBase):
    agent_id: int
    media_urls: List[str] = []


class ListingUpdate(BaseModel):
    address: Optional[str] = None
    price: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    description: Optional[str] = None
    media_urls: Optional[List[str]] = None
    status: Optional[ListingStatus] = None
    target_demographic: Optional[str] = None


class ListingResponse(ListingBase):
    id: int
    agent_id: int
    media_urls: str  # raw JSON string
    status: ListingStatus
    posted_platforms: str  # raw JSON string
    facebook_post_id: Optional[str] = None
    instagram_post_id: Optional[str] = None
    tiktok_post_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
