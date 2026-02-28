"""
FastAPI application — REST API for the Electron desktop app and webhooks.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import Agent, Invoice, Lead, Listing, Performance, SessionLocal, create_tables, get_db
from models import (
    AgentCreate,
    AgentResponse,
    AgentUpdate,
    InvoiceCreate,
    InvoiceResponse,
    LeadCreate,
    LeadResponse,
    LeadUpdate,
    ListingCreate,
    ListingResponse,
    LoginRequest,
    PerformanceResponse,
    QualificationResult,
    TokenResponse,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
_ADMIN_PASSWORD_PLAIN = os.getenv("ADMIN_PASSWORD", "admin")
# Pre-hash once at import time; avoid re-hashing on every login request.
_ADMIN_PASSWORD_HASH: str = pwd_context.hash(_ADMIN_PASSWORD_PLAIN)

if _ADMIN_PASSWORD_PLAIN in ("admin", "change_this_password", ""):
    logger.warning(
        "ADMIN_PASSWORD is set to a default/weak value. "
        "Set a strong ADMIN_PASSWORD in your .env file before deploying."
    )

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Real Estate Bot API",
    description="REST API for the real estate agent automation platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module-level reference to the Telegram Application (set at startup from run.py)
_telegram_app = None


def set_telegram_app(app_instance) -> None:
    global _telegram_app
    _telegram_app = app_instance


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------


@app.on_event("startup")
async def on_startup() -> None:
    """Create DB tables on first run."""
    create_tables()
    logger.info("FastAPI startup complete")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload["exp"] = expire
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> dict:
    """Decode JWT and return {"sub": ..., "role": ...}."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub: Optional[str] = payload.get("sub")
        role: str = payload.get("role", "agent")
        if sub is None:
            raise credentials_exc
        return {"sub": sub, "role": role}
    except JWTError:
        raise credentials_exc


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return current_user


def _get_agent_by_telegram_id(db: Session, telegram_id: str) -> Optional[Agent]:
    return db.query(Agent).filter(Agent.telegram_id == telegram_id).first()


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Authenticate as admin or as an agent (using telegram_id as username)."""
    # Admin login — compare against the pre-hashed admin password
    if request.username == ADMIN_USERNAME:
        if not _verify_password(request.password, _ADMIN_PASSWORD_HASH):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = _create_access_token({"sub": "admin", "role": "admin"})
        return TokenResponse(access_token=token)

    # Agent login: username = telegram_id, password = telegram_id (simple auth)
    agent = _get_agent_by_telegram_id(db, request.username)
    if not agent or not agent.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = _create_access_token({"sub": str(agent.id), "role": "agent"})
    return TokenResponse(access_token=token)


@app.post("/auth/refresh", response_model=TokenResponse, tags=["Auth"])
async def refresh_token(current_user: dict = Depends(get_current_user)) -> TokenResponse:
    """Issue a fresh token for the currently authenticated user."""
    token = _create_access_token({"sub": current_user["sub"], "role": current_user["role"]})
    return TokenResponse(access_token=token)


# ---------------------------------------------------------------------------
# Agent endpoints (admin only)
# ---------------------------------------------------------------------------


@app.get("/agents", response_model=list[AgentResponse], tags=["Agents"])
async def list_agents(
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AgentResponse]:
    agents = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return [AgentResponse.model_validate(a) for a in agents]


@app.get("/agents/{agent_id}", response_model=AgentResponse, tags=["Agents"])
async def get_agent(
    agent_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AgentResponse:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@app.put("/agents/{agent_id}", response_model=AgentResponse, tags=["Agents"])
async def update_agent(
    agent_id: int,
    body: AgentUpdate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AgentResponse:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    return AgentResponse.model_validate(agent)


@app.delete("/agents/{agent_id}", tags=["Agents"])
async def deactivate_agent(
    agent_id: int,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.is_active = False
    db.commit()
    return {"detail": "Agent deactivated"}


# ---------------------------------------------------------------------------
# Listing endpoints
# ---------------------------------------------------------------------------


def _resolve_agent_id(current_user: dict, db: Session) -> Optional[int]:
    """Return agent DB id for the current user, or None if admin."""
    if current_user["role"] == "admin":
        return None
    return int(current_user["sub"])


@app.get("/listings", response_model=list[ListingResponse], tags=["Listings"])
async def list_listings(
    agent_id: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ListingResponse]:
    q = db.query(Listing)
    if current_user["role"] != "admin":
        q = q.filter(Listing.agent_id == int(current_user["sub"]))
    elif agent_id:
        q = q.filter(Listing.agent_id == agent_id)
    listings = q.order_by(Listing.created_at.desc()).all()
    return [ListingResponse.from_orm_with_photos(l) for l in listings]


@app.post("/listings", response_model=ListingResponse, status_code=201, tags=["Listings"])
async def create_listing(
    body: ListingCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListingResponse:
    if current_user["role"] != "admin" and body.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Cannot create listing for another agent")
    listing = Listing(
        **{k: v for k, v in body.model_dump().items() if k != "photos"},
        photos=json.dumps(body.photos),
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return ListingResponse.from_orm_with_photos(listing)


@app.get("/listings/{listing_id}", response_model=ListingResponse, tags=["Listings"])
async def get_listing(
    listing_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListingResponse:
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if current_user["role"] != "admin" and listing.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")
    return ListingResponse.from_orm_with_photos(listing)


@app.put("/listings/{listing_id}", response_model=ListingResponse, tags=["Listings"])
async def update_listing(
    listing_id: int,
    body: ListingCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ListingResponse:
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if current_user["role"] != "admin" and listing.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "photos":
            listing.photos = json.dumps(value)
        else:
            setattr(listing, field, value)
    db.commit()
    db.refresh(listing)
    return ListingResponse.from_orm_with_photos(listing)


@app.delete("/listings/{listing_id}", tags=["Listings"])
async def delete_listing(
    listing_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if current_user["role"] != "admin" and listing.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")
    db.delete(listing)
    db.commit()
    return {"detail": "Listing deleted"}


# ---------------------------------------------------------------------------
# Lead endpoints
# ---------------------------------------------------------------------------


@app.get("/leads", response_model=list[LeadResponse], tags=["Leads"])
async def list_leads(
    agent_id: Optional[int] = Query(None),
    qualification_status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LeadResponse]:
    q = db.query(Lead)
    if current_user["role"] != "admin":
        q = q.filter(Lead.agent_id == int(current_user["sub"]))
    elif agent_id:
        q = q.filter(Lead.agent_id == agent_id)
    if qualification_status:
        q = q.filter(Lead.qualification_status == qualification_status)
    leads = q.order_by(Lead.created_at.desc()).all()
    return [LeadResponse.model_validate(l) for l in leads]


@app.post("/leads", response_model=LeadResponse, status_code=201, tags=["Leads"])
async def create_lead(
    body: LeadCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeadResponse:
    lead = Lead(**body.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return LeadResponse.model_validate(lead)


@app.get("/leads/{lead_id}", response_model=LeadResponse, tags=["Leads"])
async def get_lead(
    lead_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeadResponse:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if current_user["role"] != "admin" and lead.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")
    return LeadResponse.model_validate(lead)


@app.put("/leads/{lead_id}", response_model=LeadResponse, tags=["Leads"])
async def update_lead(
    lead_id: int,
    body: LeadUpdate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeadResponse:
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if current_user["role"] != "admin" and lead.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(lead, field, value)
    lead.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(lead)
    return LeadResponse.model_validate(lead)


@app.post("/leads/{lead_id}/qualify", response_model=QualificationResult, tags=["Leads"])
async def qualify_lead_endpoint(
    lead_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QualificationResult:
    """Trigger AI qualification for a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if current_user["role"] != "admin" and lead.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")

    from ai_service import qualify_lead

    listing_info = ""
    if lead.listing_id:
        listing = db.query(Listing).filter(Listing.id == lead.listing_id).first()
        if listing:
            listing_info = (
                f"Title: {listing.title}, Price: {listing.price}, "
                f"Location: {listing.location}, Bedrooms: {listing.bedrooms}"
            )

    result = qualify_lead(lead.message or "", listing_info)
    lead.qualification_score = result.score
    lead.qualification_status = result.status
    lead.qualification_notes = result.notes
    lead.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Notify agent if qualified
    if result.status == "qualified" and not lead.is_notified:
        agent = db.query(Agent).filter(Agent.id == lead.agent_id).first()
        if agent and _telegram_app:
            from call_service import notify_agent_qualified_lead

            notified = await notify_agent_qualified_lead(lead, agent, _telegram_app)
            if notified:
                lead.is_notified = True
                db.commit()

    return result


@app.post("/leads/{lead_id}/call", tags=["Leads"])
async def call_lead(
    lead_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Trigger AI receptionist call for a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if current_user["role"] != "admin" and lead.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")

    agent = db.query(Agent).filter(Agent.id == lead.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from call_service import trigger_ghl_call, trigger_twilio_call

    success = await trigger_ghl_call(lead, agent)
    if not success:
        success = await trigger_twilio_call(lead, agent)

    if success:
        lead.qualification_status = "called"
        lead.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"detail": "Call triggered successfully"}

    raise HTTPException(status_code=502, detail="Failed to trigger call. Check service credentials.")


# ---------------------------------------------------------------------------
# Performance endpoints
# ---------------------------------------------------------------------------


@app.get("/performance", response_model=list[PerformanceResponse], tags=["Performance"])
async def get_performance(
    agent_id: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PerformanceResponse]:
    q = db.query(Performance)
    if current_user["role"] != "admin":
        q = q.filter(Performance.agent_id == int(current_user["sub"]))
    elif agent_id:
        q = q.filter(Performance.agent_id == agent_id)
    records = q.order_by(Performance.week_start.desc()).limit(12).all()
    return [PerformanceResponse.model_validate(r) for r in records]


@app.get("/performance/report", tags=["Performance"])
async def get_performance_report(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Generate and return the weekly report text for the current user."""
    if current_user["role"] == "admin":
        raise HTTPException(status_code=400, detail="Use /agents endpoint to select an agent")

    agent = db.query(Agent).filter(Agent.id == int(current_user["sub"])).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    from scheduler import generate_agent_report

    report_text = await generate_agent_report(agent, db)
    return {"report": report_text}


# ---------------------------------------------------------------------------
# Invoice endpoints
# ---------------------------------------------------------------------------


@app.get("/invoices", response_model=list[InvoiceResponse], tags=["Invoices"])
async def list_invoices(
    agent_id: Optional[int] = Query(None),
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[InvoiceResponse]:
    q = db.query(Invoice)
    if agent_id:
        q = q.filter(Invoice.agent_id == agent_id)
    invoices = q.order_by(Invoice.created_at.desc()).all()
    return [InvoiceResponse.model_validate(i) for i in invoices]


@app.post("/invoices", response_model=InvoiceResponse, status_code=201, tags=["Invoices"])
async def create_invoice(
    body: InvoiceCreate,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    invoice = Invoice(**body.model_dump())
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return InvoiceResponse.model_validate(invoice)


@app.put("/invoices/{invoice_id}", response_model=InvoiceResponse, tags=["Invoices"])
async def update_invoice(
    invoice_id: int,
    status_update: dict,
    _: dict = Depends(require_admin),
    db: Session = Depends(get_db),
) -> InvoiceResponse:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    new_status = status_update.get("status")
    if new_status:
        invoice.status = new_status
        if new_status == "paid":
            invoice.paid_date = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    return InvoiceResponse.model_validate(invoice)


# ---------------------------------------------------------------------------
# Social endpoints
# ---------------------------------------------------------------------------


@app.post("/social/post", tags=["Social"])
async def social_post_listing(
    listing_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Manually trigger posting a listing to all connected social platforms."""
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if current_user["role"] != "admin" and listing.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")

    agent = db.query(Agent).filter(Agent.id == listing.agent_id).first()

    from social_service import post_to_facebook, post_to_instagram, post_to_tiktok

    results = {}
    fb_id = await post_to_facebook(listing, agent.facebook_token if agent else None)
    if fb_id:
        listing.posted_to_facebook = True
        listing.facebook_post_id = fb_id
        results["facebook"] = fb_id

    ig_id = await post_to_instagram(listing, agent.instagram_token if agent else None)
    if ig_id:
        listing.posted_to_instagram = True
        listing.instagram_post_id = ig_id
        results["instagram"] = ig_id

    tt_id = await post_to_tiktok(listing, agent.tiktok_token if agent else None)
    if tt_id:
        listing.posted_to_tiktok = True
        results["tiktok"] = tt_id

    db.commit()
    return {"listing_id": listing_id, "results": results}


@app.get("/social/status/{listing_id}", tags=["Social"])
async def social_post_status(
    listing_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if current_user["role"] != "admin" and listing.agent_id != int(current_user["sub"]):
        raise HTTPException(status_code=403, detail="Access denied")
    return {
        "listing_id": listing_id,
        "facebook": {"posted": listing.posted_to_facebook, "post_id": listing.facebook_post_id},
        "instagram": {"posted": listing.posted_to_instagram, "post_id": listing.instagram_post_id},
        "tiktok": {"posted": listing.posted_to_tiktok},
    }


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------


@app.post("/webhook/lead", tags=["Webhooks"])
async def webhook_lead(payload: dict, db: Session = Depends(get_db)) -> dict:
    """
    Receive an inbound lead from a social media platform webhook.

    Expected payload keys: platform, name, last_name, email, phone, message,
    agent_id (or listing_id to resolve the agent).
    """
    agent_id = payload.get("agent_id")
    listing_id = payload.get("listing_id")

    if not agent_id and listing_id:
        listing = db.query(Listing).filter(Listing.id == listing_id).first()
        if listing:
            agent_id = listing.agent_id

    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id or listing_id required")

    lead = Lead(
        agent_id=agent_id,
        listing_id=listing_id,
        platform=payload.get("platform"),
        name=payload.get("name"),
        last_name=payload.get("last_name"),
        email=payload.get("email"),
        phone=payload.get("phone"),
        message=payload.get("message"),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    # Auto-qualify
    from ai_service import qualify_lead

    listing_info = ""
    if lead.listing_id:
        listing = db.query(Listing).filter(Listing.id == lead.listing_id).first()
        if listing:
            listing_info = f"Title: {listing.title}, Price: {listing.price}, Location: {listing.location}"

    result = qualify_lead(lead.message or "", listing_info)
    lead.qualification_score = result.score
    lead.qualification_status = result.status
    lead.qualification_notes = result.notes
    lead.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Notify if qualified
    if result.status == "qualified" and _telegram_app:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if agent:
            from call_service import notify_agent_qualified_lead

            notified = await notify_agent_qualified_lead(lead, agent, _telegram_app)
            if notified:
                lead.is_notified = True
                db.commit()

    return {"lead_id": lead.id, "qualification_status": result.status, "score": result.score}


@app.post("/webhook/telegram", tags=["Webhooks"])
async def webhook_telegram(payload: dict) -> dict:
    """
    Receive Telegram updates via webhook (alternative to polling).
    This endpoint should be registered with Telegram's setWebhook API.
    """
    if _telegram_app is None:
        raise HTTPException(status_code=503, detail="Telegram bot not running")
    from telegram import Update

    update = Update.de_json(payload, _telegram_app.bot)
    await _telegram_app.process_update(update)
    return {"ok": True}
