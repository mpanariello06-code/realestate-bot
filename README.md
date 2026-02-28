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

> **Three commands and the server is live at `http://localhost:8000`.**

```bash
# 1. Clone and enter the repo
git clone https://github.com/mpanariello06-code/realestate-bot.git
cd realestate-bot

# 2. Install dependencies  (Python 3.11+ required)
pip install -r requirements.txt

# 3. Start the server
python run.py
```

That's it — **no environment variables or API keys are needed to start**. The database (`realestate.db`) is created automatically on first run. Features that require external services (Twilio, OpenAI, Facebook, etc.) simply log a warning and skip gracefully when keys are not set.

| URL | What you'll find |
|---|---|
| `http://localhost:8000/docs` | Interactive API docs (Swagger UI) |
| `http://localhost:8000/admin/dashboard` | Admin portal |
| `http://localhost:8000/portal/agent/1/dashboard` | Agent portal (after creating an agent) |

> Want to enable WhatsApp messaging, AI qualification, or social posting?  
> Copy `.env.example` to `.env`, fill in the relevant keys, then restart the server.

---

## Prerequisites

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | **3.11** | 3.12 recommended |
| pip | 23+ | bundled with Python |
| Twilio account | — | For WhatsApp messaging and AI calls — [sign up free](https://www.twilio.com/try-twilio) |
| OpenAI account | — | For lead qualification — [sign up](https://platform.openai.com/signup) |
| Facebook/Instagram account | — | Optional — only needed for social posting |
| TikTok developer account | — | Optional — only needed for TikTok posting |

> **No external accounts needed to run locally.** The server starts and all portals work without any API keys. Features that require an external service (WhatsApp send, AI calls, social posting) log a warning and return a graceful fallback instead of crashing.

---

## Setup & Run

### 1. Clone the repository

```bash
git clone https://github.com/mpanariello06-code/realestate-bot.git
cd realestate-bot
```

### 2. Create and activate a virtual environment

```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables (optional)

The server starts fine without any `.env` file — all external-service features (WhatsApp, AI, social posting) are disabled automatically when keys are missing and log a warning instead of crashing.

To enable those features later:

```bash
cp .env.example .env
# then open .env in any text editor and fill in the relevant keys
```

See the [Environment Variables](#environment-variables) table below for details.

### 5. Start the server

```bash
python run.py
```

Or, if you prefer the uvicorn command directly:

```bash
uvicorn app.main:app --reload
```

The database file (`realestate.db`) is created automatically on first startup — no migrations needed.

| URL | What you'll find |
|---|---|
| `http://localhost:8000/docs` | Interactive Swagger API docs |
| `http://localhost:8000/redoc` | ReDoc API reference |
| `http://localhost:8000/admin/dashboard` | Admin portal |
| `http://localhost:8000/` | Health check / version |

---

## First Steps After Setup

### Register your first agent

Use the interactive docs at `/docs` or run this curl command:

```bash
curl -s -X POST http://localhost:8000/portal/agent/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Smith",
    "email": "jane@example.com",
    "phone": "+15550001234",
    "whatsapp_number": "whatsapp:+15550001234"
  }' | python3 -m json.tool
```

The response includes the agent's `id` (e.g. `1`).

### Open the agent portal

Navigate to `http://localhost:8000/portal/agent/1/dashboard` to see the agent dashboard.

### Connect social accounts (optional)

```bash
curl -s -X POST http://localhost:8000/portal/agent/1/connect-social \
  -H "Content-Type: application/json" \
  -d '{"platform": "facebook", "access_token": "YOUR_PAGE_ACCESS_TOKEN"}'
```

Repeat for `instagram` and `tiktok` platforms.

---

## Connecting the WhatsApp Bot (Twilio)

The bot receives messages via a Twilio webhook. Twilio needs a **publicly accessible HTTPS URL** pointing to `/webhook/whatsapp`.

### Local development with ngrok

1. Install ngrok: https://ngrok.com/download  
2. Start ngrok in a separate terminal while the server is running:

   ```bash
   ngrok http 8000
   ```

3. Copy the `https://` forwarding URL from ngrok output (e.g. `https://abc123.ngrok.io`).

4. Set it in your `.env`:

   ```env
   BASE_URL=https://abc123.ngrok.io
   ```

5. Log in to [Twilio Console](https://console.twilio.com) → **Messaging** → **Senders** → **WhatsApp Senders** → click your sandbox number → set the **"When a message comes in"** webhook to:

   ```
   https://abc123.ngrok.io/webhook/whatsapp
   ```

   Method: `HTTP POST`

### Production

Set `BASE_URL` to your server's public domain (e.g. `https://yourapp.com`) and point the Twilio webhook to `https://yourapp.com/webhook/whatsapp`.

---

## Environment Variables

### Required to enable WhatsApp messaging

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID — found at [console.twilio.com](https://console.twilio.com) |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token — same page |
| `TWILIO_WHATSAPP_NUMBER` | The Twilio WhatsApp sender in `whatsapp:+1…` format |

### Required to enable AI lead qualification

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI secret key — found at [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

### Required to enable social media posting

| Variable | Description |
|---|---|
| `FACEBOOK_APP_ID` | Facebook app ID from [developers.facebook.com](https://developers.facebook.com) |
| `FACEBOOK_APP_SECRET` | Facebook app secret |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API long-lived token |
| `TIKTOK_ACCESS_TOKEN` | TikTok API access token |

### Always set in production

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `changeme-secret-key` | Random secret used for signing — **change this** |
| `BASE_URL` | `http://localhost:8000` | Public base URL sent to Twilio for callbacks |
| `ADMIN_WHATSAPP_NUMBER` | — | Your WhatsApp number in `whatsapp:+1…` format for admin alerts |
| `DATABASE_URL` | `sqlite:///./realestate.db` | SQLAlchemy URL — use `postgresql://user:pass@host/db` for production |

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

First install the dev dependencies (adds `pytest` on top of the regular requirements):

```bash
pip install -r requirements-dev.txt
```

Then run:

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_lead_qualifier.py -v
```

Tests use an in-memory SQLite database and mock all external services (Twilio, OpenAI, social APIs), so they run fully offline with no credentials needed.

---

## Project Structure

```
app/
├── main.py               # FastAPI app + router registration
├── config.py             # App settings (reads env vars / .env file)
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
