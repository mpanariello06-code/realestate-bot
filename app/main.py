from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.api import whatsapp, listings, leads, agent_portal, admin_portal

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Real Estate Bot Platform",
    description="AI-powered real estate agent automation platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(whatsapp.router)
app.include_router(listings.router)
app.include_router(leads.router)
app.include_router(agent_portal.router)
app.include_router(admin_portal.router)


@app.get("/")
def root():
    return {
        "service": "Real Estate Bot Platform",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
