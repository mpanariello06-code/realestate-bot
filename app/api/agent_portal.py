import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Lead, LeadStatus
from app.models.listing import Listing, ListingStatus
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate, ConnectSocialRequest
from app.services.reporting import generate_weekly_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal/agent", tags=["agent-portal"])

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── REST endpoints ──────────────────────────────────────────────────────────

@router.post("/", response_model=AgentResponse, status_code=201)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    if db.query(Agent).filter(Agent.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    agent = Agent(**payload.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(agent_id: int, payload: AgentUpdate, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)

    db.commit()
    db.refresh(agent)
    return agent


@router.post("/{agent_id}/connect-social")
def connect_social(agent_id: int, payload: ConnectSocialRequest, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    platform = payload.platform.lower()
    if platform == "facebook":
        agent.facebook_token = payload.access_token
    elif platform == "instagram":
        agent.instagram_token = payload.access_token
    elif platform == "tiktok":
        agent.tiktok_token = payload.access_token
    else:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    db.commit()
    return {"message": f"{platform} connected successfully"}


@router.get("/{agent_id}/report")
def agent_report(agent_id: int, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    return generate_weekly_report(agent_id, db)


# ── HTML portal endpoints ────────────────────────────────────────────────────

@router.get("/{agent_id}/dashboard", response_class=HTMLResponse)
def agent_dashboard(agent_id: int, request: Request, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    total_leads = db.query(Lead).filter(Lead.agent_id == agent_id).count()
    qualified_leads = (
        db.query(Lead).filter(Lead.agent_id == agent_id, Lead.status == LeadStatus.QUALIFIED).count()
    )
    deals_closed = (
        db.query(Lead).filter(Lead.agent_id == agent_id, Lead.status == LeadStatus.CLOSED).count()
    )
    recent_leads = (
        db.query(Lead).filter(Lead.agent_id == agent_id).order_by(Lead.created_at.desc()).limit(10).all()
    )
    recent_listings = (
        db.query(Listing).filter(Listing.agent_id == agent_id).order_by(Listing.created_at.desc()).limit(5).all()
    )

    return templates.TemplateResponse(
        "agent/dashboard.html",
        {
            "request": request,
            "agent": agent,
            "total_leads": total_leads,
            "qualified_leads": qualified_leads,
            "deals_closed": deals_closed,
            "recent_leads": recent_leads,
            "recent_listings": recent_listings,
        },
    )


@router.get("/{agent_id}/listings", response_class=HTMLResponse)
def agent_listings_page(agent_id: int, request: Request, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    listings = (
        db.query(Listing).filter(Listing.agent_id == agent_id).order_by(Listing.created_at.desc()).all()
    )
    return templates.TemplateResponse(
        "agent/listings.html",
        {"request": request, "agent": agent, "listings": listings},
    )


@router.get("/{agent_id}/leads", response_class=HTMLResponse)
def agent_leads_page(agent_id: int, request: Request, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    leads = (
        db.query(Lead).filter(Lead.agent_id == agent_id).order_by(Lead.created_at.desc()).all()
    )
    return templates.TemplateResponse(
        "agent/leads.html",
        {"request": request, "agent": agent, "leads": leads},
    )


@router.get("/{agent_id}/performance", response_class=HTMLResponse)
def agent_performance_page(agent_id: int, request: Request, db: Session = Depends(get_db)):
    from app.models.agent import Agent
    from app.models.performance import PerformanceMetric

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    metrics = (
        db.query(PerformanceMetric)
        .filter(PerformanceMetric.agent_id == agent_id)
        .order_by(PerformanceMetric.week_start.desc())
        .limit(12)
        .all()
    )
    report = generate_weekly_report(agent_id, db)

    return templates.TemplateResponse(
        "agent/performance.html",
        {"request": request, "agent": agent, "metrics": metrics, "report": report},
    )
