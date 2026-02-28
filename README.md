# 🏠 Real Estate Bot Platform

An AI-powered real estate agent automation platform that turns WhatsApp into a full social-media publishing and lead-qualification engine.

---

## Features

- **WhatsApp Bot** — agents send photos/videos + a description; the bot posts to all connected social platforms automatically and replies to inbound leads
- **AI Lead Qualification** — OpenAI GPT analyses every conversation and scores leads 0-100
- **AI Receptionist** — Twilio Programmable Voice calls leads with a configurable qualification script
- **Social Media Publishing** — one-tap posting to Facebook, Instagram, and TikTok via their Graph/Open APIs
- **Agent Portal** — web UI to connect social accounts, view listings, manage leads, and read performance reports
- **Admin Portal** — platform-owner UI to manage all clients, create invoices, and monitor aggregate performance
- **Performance Tracking** — weekly follower counts, deals closed, average response time, and trend arrows
- **WhatsApp Notifications** — agents receive instant alerts for qualified leads

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    FastAPI Application                │
│                                                      │
│  /webhook/whatsapp  →  WhatsApp Handler              │
│  /listings          →  Listings CRUD                 │
│  /leads             →  Leads CRUD + AI Qualify       │
│  /portal/agent/*    →  Agent Portal (HTML + REST)    │
│  /admin/*           →  Admin Portal (HTML + REST)    │
└───────────┬──────────────────────────────────────────┘
            │
     ┌──────▼──────┐      ┌───────────────┐
     │  SQLAlchemy │      │    Services    │
     │  SQLite/PG  │      │               │
     └─────────────┘      │ whatsapp_svc  │──▶ Twilio
                          │ lead_qualifier│──▶ OpenAI
                          │ social_media  │──▶ FB/IG/TikTok
                          │ ai_receptionist──▶ Twilio Voice
                          │ reporting     │
                          │ notifications │
                          └───────────────┘
```

---

## Quick Start

### 1. Clone and install

```bash
git clone <repo-url>
cd realestate-bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

The API docs are available at `http://localhost:8000/docs`.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./realestate.db` |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | — |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | — |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp sender number | `whatsapp:+14155238886` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `FACEBOOK_APP_ID` | Facebook app ID | — |
| `FACEBOOK_APP_SECRET` | Facebook app secret | — |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API token | — |
| `TIKTOK_ACCESS_TOKEN` | TikTok API access token | — |
| `SECRET_KEY` | App secret key | `changeme-secret-key` |
| `ADMIN_WHATSAPP_NUMBER` | Admin WhatsApp number | — |
| `BASE_URL` | Public base URL (for Twilio callbacks) | `http://localhost:8000` |

---

## WhatsApp Bot Commands (for agents)

| Command | Action |
|---|---|
| `POST <description>` + attach media | Creates listing and posts to all connected social platforms |
| `LIST` | Shows your 5 most recent active listings |
| `LEADS` | Shows recent leads with qualification scores |
| `PERFORMANCE` | Shows this week's performance summary |
| `HELP` | Shows all available commands |

Any other inbound message from an **unregistered** number is treated as a lead inquiry — the AI qualifies it and sends an auto-reply.

---

## API Endpoints

### WhatsApp
| Method | Path | Description |
|---|---|---|
| POST | `/webhook/whatsapp` | Twilio webhook receiver |

### Listings
| Method | Path | Description |
|---|---|---|
| GET | `/listings/` | List listings (filter by agent, status) |
| POST | `/listings/` | Create listing |
| GET | `/listings/{id}` | Get listing |
| PATCH | `/listings/{id}` | Update listing |
| DELETE | `/listings/{id}` | Delete listing |
| POST | `/listings/{id}/post-to-social` | Trigger social posting |

### Leads
| Method | Path | Description |
|---|---|---|
| GET | `/leads/` | List leads |
| POST | `/leads/` | Create lead |
| GET | `/leads/{id}` | Get lead |
| PATCH | `/leads/{id}` | Update lead |
| DELETE | `/leads/{id}` | Delete lead |
| POST | `/leads/{id}/qualify` | Run AI qualification |
| POST | `/leads/{id}/call` | Initiate AI receptionist call |

### Agent Portal
| Method | Path | Description |
|---|---|---|
| GET | `/portal/agent/{id}/dashboard` | HTML dashboard |
| GET | `/portal/agent/{id}/listings` | HTML listings page |
| GET | `/portal/agent/{id}/leads` | HTML leads page |
| GET | `/portal/agent/{id}/performance` | HTML performance page |
| POST | `/portal/agent/{id}/connect-social` | Connect social account |
| GET | `/portal/agent/{id}/report` | JSON weekly report |

### Admin Portal
| Method | Path | Description |
|---|---|---|
| GET | `/admin/dashboard` | HTML admin dashboard |
| GET | `/admin/clients` | HTML clients list |
| GET | `/admin/invoices` | HTML invoices list |
| GET | `/admin/api/clients` | JSON clients list |
| POST | `/admin/api/clients` | Create client |
| GET | `/admin/api/invoices` | JSON invoices list |
| POST | `/admin/api/invoices` | Create invoice |
| PATCH | `/admin/api/invoices/{id}/mark-paid` | Mark invoice paid |
| GET | `/admin/api/performance` | All agents performance |

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Project Structure

```
app/
├── main.py               # FastAPI app + router registration
├── config.py             # Pydantic settings
├── database.py           # SQLAlchemy setup
├── models/               # SQLAlchemy ORM models
├── schemas/              # Pydantic request/response schemas
├── api/                  # FastAPI routers
│   ├── whatsapp.py       # WhatsApp webhook
│   ├── listings.py       # Listings CRUD
│   ├── leads.py          # Leads CRUD + AI
│   ├── agent_portal.py   # Agent web portal
│   └── admin_portal.py   # Admin web portal
├── services/             # Business logic
│   ├── whatsapp_service.py
│   ├── lead_qualifier.py
│   ├── social_media.py
│   ├── ai_receptionist.py
│   ├── reporting.py
│   └── notifications.py
└── templates/            # Jinja2 HTML templates
    ├── agent/
    └── admin/
tests/                    # pytest test suite
```
