import logging
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Lead
from app.models.performance import Invoice, PerformanceMetric
from app.schemas.agent import AgentCreate, AgentResponse
from app.schemas.performance import InvoiceCreate, InvoiceResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-portal"])

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ── HTML portal ──────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    total_clients = db.query(Agent).count()
    active_clients = db.query(Agent).filter(Agent.is_active.is_(True)).count()
    total_leads = db.query(Lead).count()
    pending_invoices = db.query(Invoice).filter(Invoice.status == "pending").all()
    revenue_this_month = sum(
        inv.amount
        for inv in db.query(Invoice).filter(Invoice.status == "paid").all()
        if inv.paid_at and inv.paid_at.month == datetime.utcnow().month
    )
    recent_clients = db.query(Agent).order_by(Agent.created_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "total_clients": total_clients,
            "active_clients": active_clients,
            "total_leads": total_leads,
            "revenue_this_month": revenue_this_month,
            "pending_invoices": pending_invoices,
            "recent_clients": recent_clients,
        },
    )


@router.get("/clients", response_class=HTMLResponse)
def admin_clients_page(request: Request, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    clients = db.query(Agent).order_by(Agent.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/clients.html",
        {"request": request, "clients": clients},
    )


@router.get("/invoices", response_class=HTMLResponse)
def admin_invoices_page(request: Request, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    agents = {a.id: a for a in db.query(Agent).all()}
    return templates.TemplateResponse(
        "admin/invoices.html",
        {"request": request, "invoices": invoices, "agents": agents},
    )


# ── REST endpoints ────────────────────────────────────────────────────────────

@router.get("/api/clients", response_model=List[AgentResponse])
def list_clients(db: Session = Depends(get_db)):
    from app.models.agent import Agent

    return db.query(Agent).order_by(Agent.created_at.desc()).all()


@router.get("/api/clients/{agent_id}", response_model=AgentResponse)
def get_client(agent_id: int, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Client not found")
    return agent


@router.post("/api/clients", response_model=AgentResponse, status_code=201)
def create_client(payload: AgentCreate, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    if db.query(Agent).filter(Agent.email == payload.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    agent = Agent(**payload.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/api/invoices", response_model=List[InvoiceResponse])
def list_invoices(db: Session = Depends(get_db)):
    return db.query(Invoice).order_by(Invoice.created_at.desc()).all()


@router.post("/api/invoices", response_model=InvoiceResponse, status_code=201)
def create_invoice(payload: InvoiceCreate, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    if not db.query(Agent).filter(Agent.id == payload.agent_id).first():
        raise HTTPException(status_code=404, detail="Agent not found")

    invoice = Invoice(**payload.model_dump())
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.patch("/api/invoices/{invoice_id}/mark-paid", response_model=InvoiceResponse)
def mark_invoice_paid(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice.status = "paid"
    invoice.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/api/performance")
def all_performance(db: Session = Depends(get_db)):
    from app.models.agent import Agent
    from app.services.reporting import generate_weekly_report

    agents = db.query(Agent).filter(Agent.is_active.is_(True)).all()
    return [
        {"agent_id": a.id, "agent_name": a.name, **generate_weekly_report(a.id, db)}
        for a in agents
    ]
