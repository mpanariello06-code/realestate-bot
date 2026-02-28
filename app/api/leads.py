import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.lead import Lead, LeadStatus
from app.schemas.lead import LeadCreate, LeadResponse, LeadUpdate
from app.services.ai_receptionist import initiate_qualification_call
from app.services.lead_qualifier import qualify_lead
from app.services.notifications import notify_agent_qualified_lead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("/", response_model=LeadResponse, status_code=201)
def create_lead(payload: LeadCreate, db: Session = Depends(get_db)):
    from app.models.agent import Agent

    agent = db.query(Agent).filter(Agent.id == payload.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    lead = Lead(**payload.model_dump())
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.get("/", response_model=List[LeadResponse])
def list_leads(
    agent_id: int = None,
    status: LeadStatus = None,
    db: Session = Depends(get_db),
):
    query = db.query(Lead)
    if agent_id:
        query = query.filter(Lead.agent_id == agent_id)
    if status:
        query = query.filter(Lead.status == status)
    return query.order_by(Lead.created_at.desc()).all()


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead, field, value)

    db.commit()
    db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=204)
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.delete(lead)
    db.commit()


@router.post("/{lead_id}/qualify", response_model=LeadResponse)
def qualify_lead_endpoint(lead_id: int, db: Session = Depends(get_db)):
    """Run AI qualification on a lead's conversation text."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.conversation_text:
        raise HTTPException(status_code=400, detail="No conversation text to qualify")

    result = qualify_lead(lead.conversation_text)
    lead.qualification_score = float(result.get("qualification_score", 0))
    lead.is_serious = bool(result.get("is_serious", False))
    lead.ai_analysis = result.get("reasoning", "")

    if lead.is_serious:
        lead.status = LeadStatus.QUALIFIED
        from app.models.agent import Agent
        agent = db.query(Agent).filter(Agent.id == lead.agent_id).first()
        if agent:
            notify_agent_qualified_lead(agent, lead, db)

    db.commit()
    db.refresh(lead)
    return lead


@router.post("/{lead_id}/call")
def call_lead(lead_id: int, db: Session = Depends(get_db)):
    """Initiate an AI qualification call to the lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if not lead.phone:
        raise HTTPException(status_code=400, detail="Lead has no phone number")

    from app.models.agent import Agent
    agent = db.query(Agent).filter(Agent.id == lead.agent_id).first()
    agent_name = agent.name if agent else "Your Agent"

    call_sid = initiate_qualification_call(lead.phone, agent_name, lead.id)
    lead.status = LeadStatus.CONTACTED
    db.commit()

    return {"lead_id": lead_id, "call_sid": call_sid, "status": "initiated"}
