import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.listing import Listing, ListingStatus
from app.schemas.listing import ListingCreate, ListingResponse, ListingUpdate
from app.services.social_media import post_listing_to_all_platforms

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/listings", tags=["listings"])


@router.post("/", response_model=ListingResponse, status_code=201)
def create_listing(payload: ListingCreate, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == payload.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    listing = Listing(
        agent_id=payload.agent_id,
        address=payload.address,
        price=payload.price,
        bedrooms=payload.bedrooms,
        bathrooms=payload.bathrooms,
        description=payload.description,
        media_urls=json.dumps(payload.media_urls),
        target_demographic=payload.target_demographic,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@router.get("/", response_model=List[ListingResponse])
def list_listings(agent_id: int = None, status: ListingStatus = None, db: Session = Depends(get_db)):
    query = db.query(Listing)
    if agent_id:
        query = query.filter(Listing.agent_id == agent_id)
    if status:
        query = query.filter(Listing.status == status)
    return query.order_by(Listing.created_at.desc()).all()


@router.get("/{listing_id}", response_model=ListingResponse)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.patch("/{listing_id}", response_model=ListingResponse)
def update_listing(listing_id: int, payload: ListingUpdate, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "media_urls" in update_data:
        update_data["media_urls"] = json.dumps(update_data["media_urls"])
    for field, value in update_data.items():
        setattr(listing, field, value)

    db.commit()
    db.refresh(listing)
    return listing


@router.delete("/{listing_id}", status_code=204)
def delete_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    db.delete(listing)
    db.commit()


@router.post("/{listing_id}/post-to-social")
def post_to_social(listing_id: int, db: Session = Depends(get_db)):
    """Trigger posting a listing to all connected social platforms."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == listing.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    results = post_listing_to_all_platforms(listing, agent, db)
    return {"listing_id": listing_id, "results": results}
