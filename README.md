# RealEstate Bot 🏠

An end-to-end automation platform that helps real estate agents close more deals by automating lead capture, qualification, social media posting, and performance tracking.

## What It Does

- **Telegram Group Bot** — Agents send photos/videos + a description directly in a Telegram group; the bot posts the listing to Facebook, Instagram, and TikTok automatically.
- **AI Lead Qualification** — Incoming leads (from social media or manual entry) are scored 0–100 by GPT-4o-mini. Leads scoring ≥ 70 are marked *Qualified* and the agent is notified immediately.
- **AI Receptionist Calls** — Qualified leads can trigger an automated outbound phone call via GoHighLevel or Twilio that asks pre-qualification questions.
- **Performance Tracking** — Follower counts, lead volume, deal closings, and response time are tracked daily and delivered as a weekly report every Monday morning.
- **Desktop Portals (Windows EXE)** — Two Electron-based desktop portals:
  - **Client Portal** — Agents manage listings, view leads, connect socials, and review performance metrics.
  - **Admin Portal** — System admin sees all clients, payments, invoices, and can drill into any client's data.

---

## Architecture

```
realestate-bot/
├── backend/        # Python 3 — FastAPI REST API + Telegram bot + Scheduler
└── desktop/        # Electron — Client Portal + Admin Portal (builds to .exe)
```

The backend and desktop app communicate over a local HTTP API (`http://localhost:8000` by default).

---

## Backend Setup

### Prerequisites
- Python 3.10+
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))
- OpenAI API key

### Installation

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in your secrets
cp .env.example .env
nano .env                       # add TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, etc.
```

### Running

```bash
python run.py
```

This starts **both** the FastAPI server (port 8000) and the Telegram bot polling loop in the same process.

### Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Register as an agent |
| `/post` | Start the 8-step listing wizard (photos → details → social post) |
| `/leads` | Browse paginated leads with inline keyboard actions |
| `/qualified` | View only qualified leads |
| `/performance` | Current week stats |
| `/report` | Request your weekly performance report |
| `/connect_facebook` | Instructions for linking Facebook |
| `/connect_instagram` | Instructions for linking Instagram |
| `/postads` | Paid advertising options |
| `/profile` | View / update your profile |

**Admin-only commands** (restricted to `TELEGRAM_ADMIN_CHAT_ID`):

| Command | Description |
|---------|-------------|
| `/admin_clients` | List all registered agents |
| `/admin_stats` | Platform-wide statistics |
| `/admin_invoice <id> <amount>` | Create an invoice for a client |

### REST API

The API is documented interactively at `http://localhost:8000/docs` (Swagger UI) once the backend is running.

Key endpoint groups:
- `POST /auth/login` — Obtain a JWT token
- `GET /agents` — Admin: list all agents
- `GET/POST /listings` — Manage property listings
- `GET/POST /leads` — Manage leads; `POST /leads/{id}/qualify` to trigger AI scoring
- `POST /leads/{id}/call` — Trigger AI receptionist call
- `GET /performance` — Weekly performance data
- `GET/POST /invoices` — Admin: invoice management
- `POST /webhook/lead` — Receive leads from social media webhooks

### Scheduler

Three automatic jobs run in the background:

| Job | Schedule | Action |
|-----|----------|--------|
| Weekly Report | Monday 08:00 | Send performance summary to each agent via Telegram |
| Lead Nudge | Daily 10:00 | Alert agent if a lead has not been responded to in > 2 hours |
| Performance Snapshot | Daily 23:50 | Record daily metrics for trending |

---

## Desktop App Setup

### Prerequisites
- Node.js 18+
- npm

### Development

```bash
cd desktop
npm install
cp .env.example .env          # set BACKEND_URL if backend is on a different machine
npm start
```

### Build Windows EXE

```bash
cd desktop
npm run build
# Output: desktop/dist/RealEstate Bot Setup 1.0.0.exe
```

The installer is built with NSIS and includes an auto-update skeleton.

### Portals

On launch a **portal selector** screen lets you choose:

| Portal | Credentials | Purpose |
|--------|-------------|---------|
| Client Portal | Agent email + password | Manage listings, leads, performance, social connections |
| Admin Portal | `ADMIN_USERNAME` / `ADMIN_PASSWORD` from `.env` | Manage all clients, invoices, view any agent's data |

#### Client Portal Pages
- **Dashboard** — Live stats cards, recent leads, recent listings, performance chart
- **Leads** — Filter/search table, lead detail modal with AI notes, qualify/call actions
- **Listings** — Grid view, create/edit listings, social posting status per platform
- **Performance** — KPI cards, line charts, follower counts, weekly report downloads
- **Settings** — Connect Facebook/Instagram/TikTok, update profile, notification preferences

#### Admin Portal Pages
- **Dashboard** — Aggregate stats, top clients, revenue chart, activity log
- **Clients** — Full client list with search/filter, add/suspend/create-invoice actions
- **Invoices** — Create invoices, mark paid, track overdue payments
- **Client Detail** — 5-tab deep-dive into any client (overview, leads, listings, performance, invoices)

---

## Configuration Reference

### Backend `.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | From @BotFather |
| `TELEGRAM_ADMIN_CHAT_ID` | ✅ | Your personal or group chat ID |
| `OPENAI_API_KEY` | ✅ | For AI lead qualification |
| `FACEBOOK_ACCESS_TOKEN` | Optional | Default FB token (agents supply their own) |
| `FACEBOOK_PAGE_ID` | Optional | Default FB page |
| `INSTAGRAM_ACCOUNT_ID` | Optional | IG business account ID |
| `TIKTOK_ACCESS_TOKEN` | Optional | TikTok Content Posting API token |
| `GHL_API_KEY` | Optional | GoHighLevel for AI receptionist |
| `GHL_WORKFLOW_ID` | Optional | GHL workflow to trigger on qualified lead |
| `TWILIO_ACCOUNT_SID` | Optional | Twilio fallback for calls |
| `TWILIO_AUTH_TOKEN` | Optional | Twilio auth |
| `TWILIO_PHONE_NUMBER` | Optional | Twilio caller ID |
| `API_PORT` | Optional | Default `8000` |
| `SECRET_KEY` | ✅ | Random string for JWT signing |
| `ADMIN_USERNAME` | ✅ | Admin login username |
| `ADMIN_PASSWORD` | ✅ | Admin login password |

### Desktop `.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_URL` | `http://localhost:8000` | URL of the Python backend |

---

## Lead Qualification Flow

```
Social media / webhook → POST /webhook/lead
         ↓
  AI scores lead (GPT-4o-mini, 0–100)
         ↓
  score < 70 → marked "Unqualified", no action
         ↓
  score ≥ 70 → marked "Qualified"
         ↓
  Telegram notification to agent (name, phone, email, AI notes)
         ↓
  (Optional) GHL workflow / Twilio call triggered automatically
```

---

## Weekly Report (sample)

```
📊 Weekly Performance Report — Feb 24–Mar 1

👤 Agent: Jane Smith

📣 Social Reach
  Facebook followers: 1,240 (+18)
  Instagram followers: 892 (+34)

🎯 Leads
  New leads this week:     23
  Qualified leads:         8  (35%)
  Deals closed:            1

⚡ Response time
  Average: 47 min  ✅ (target < 60 min)

🏠 Active listings: 5
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Telegram bot | python-telegram-bot v21 (async) |
| REST API | FastAPI + uvicorn |
| Database | SQLite via SQLAlchemy ORM |
| AI qualification | OpenAI GPT-4o-mini |
| Social posting | Facebook/Instagram Graph API, TikTok Content API |
| AI calls | GoHighLevel workflows / Twilio |
| Scheduler | APScheduler |
| Desktop app | Electron v28 |
| Desktop packaging | electron-builder (NSIS for Windows) |
| Auth | JWT (PyJWT) + bcrypt |

---

## Contributing

1. Fork the repo
2. Create a feature branch
3. Submit a PR — CI will run linting and syntax checks automatically
