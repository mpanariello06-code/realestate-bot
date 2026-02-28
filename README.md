# 🏠 Real Estate Bot Platform

An AI-powered real estate agent automation platform with a **Telegram bot** (and WhatsApp support) for social-media publishing, lead qualification, and performance reporting.

---

## Features

- **Telegram Bot** — agents send photos/videos + a description via Telegram; the bot posts to all connected social platforms and replies to inbound leads *(new!)*
- **WhatsApp Bot** — same features available over WhatsApp via Twilio
- **AI Lead Qualification** — OpenAI GPT analyses every conversation and scores leads 0-100
- **AI Receptionist** — Twilio Programmable Voice calls leads with a configurable qualification script
- **Social Media Publishing** — one-tap posting to Facebook, Instagram, and TikTok via their Graph/Open APIs
- **Agent Portal** — web UI to connect social accounts, view listings, manage leads, and read performance reports
- **Admin Portal** — platform-owner UI to manage all clients, create invoices, and monitor aggregate performance
- **Performance Tracking** — weekly follower counts, deals closed, average response time, and trend arrows
- **Instant Notifications** — agents receive qualified-lead alerts via Telegram and/or WhatsApp

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    FastAPI Application                │
│                                                      │
│  /webhook/telegram  →  Telegram Handler  ◀── Telegram│
│  /webhook/whatsapp  →  WhatsApp Handler  ◀── Twilio  │
│  /listings          →  Listings CRUD                 │
│  /leads             →  Leads CRUD + AI Qualify       │
│  /portal/agent/*    →  Agent Portal (HTML + REST)    │
│  /admin/*           →  Admin Portal (HTML + REST)    │
└───────────┬──────────────────────────────────────────┘
            │
     ┌──────▼──────┐      ┌───────────────────┐
     │  SQLAlchemy │      │      Services      │
     │  SQLite/PG  │      │                   │
     └─────────────┘      │ telegram_service ─│──▶ Telegram API
                          │ whatsapp_svc     ─│──▶ Twilio
                          │ lead_qualifier   ─│──▶ OpenAI
                          │ social_media     ─│──▶ FB/IG/TikTok
                          │ ai_receptionist  ─│──▶ Twilio Voice
                          │ reporting         │
                          │ notifications     │
                          └───────────────────┘
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

That's it — **no environment variables or API keys are needed to start**. The database (`realestate.db`) is created automatically on first run. Features that require external services (Telegram, Twilio, OpenAI, Facebook, etc.) simply log a warning and skip gracefully when keys are not set.

| URL | What you'll find |
|---|---|
| `http://localhost:8000/docs` | Interactive API docs (Swagger UI) |
| `http://localhost:8000/admin/dashboard` | Admin portal |
| `http://localhost:8000/portal/agent/1/dashboard` | Agent portal (after creating an agent) |

### Quick Telegram setup

After starting the server, run the interactive setup helper:

```bash
# Copy and fill in your Telegram bot token first
cp .env.example .env
# Edit .env → set TELEGRAM_BOT_TOKEN=<your token from @BotFather>

python setup_telegram.py
```

The helper will walk you through every step automatically — token verification, chat ID detection, agent registration, and webhook setup.  
See **[Connecting the Telegram Bot](#connecting-the-telegram-bot)** for the full manual walkthrough.

> Want to also enable AI qualification or social posting?  
> Fill in the remaining keys in `.env` and restart the server.

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

## How to Start Chatting with the Bot on WhatsApp

> **⚠️ WhatsApp groups are not supported.**  
> The WhatsApp Business API (which Twilio uses) only allows **1-to-1 direct messages** between the bot's number and an individual user. You cannot add the bot to a WhatsApp group — messages sent in groups are not delivered to the bot.  
> To interact with the bot, every person (agent or lead) messages the bot's Twilio number directly, in their own private chat.

---

### Step 1 — Join the Twilio WhatsApp Sandbox (testing only)

During development Twilio provides a free shared sandbox number (`+1 415 523 8886`).  
Each person who wants to message the bot must opt in once by sending a join code.

1. **Open WhatsApp** on your phone.  
2. **Save** the Twilio sandbox number in your contacts:  
   `+1 415 523 8886`  
3. **Send this exact message** to that number:  
   ```
   join <your-sandbox-keyword>
   ```  
   Find your sandbox keyword in [Twilio Console](https://console.twilio.com) → **Messaging** → **Try it out** → **Send a WhatsApp message**.  
   It looks something like `join apple-mango`.  
4. Twilio replies **"You are now connected"** — the opt-in is complete.

> The sandbox number and keyword are the same for every Twilio account.  
> In production you get your own approved WhatsApp Business number and the join step is not required.

---

### Step 2 — Register as an agent (so the bot recognises you)

The bot treats every unregistered sender as a *lead*. To send agent commands (`POST`, `LIST`, `LEADS`, etc.) your WhatsApp number must be registered as an agent first.

Use the API (while the server is running at `http://localhost:8000`):

```bash
curl -s -X POST http://localhost:8000/portal/agent/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Your Name",
    "email": "you@example.com",
    "phone": "+15550001234",
    "whatsapp_number": "whatsapp:+15550001234"
  }' | python3 -m json.tool
```

Replace `+15550001234` with your **real WhatsApp number** (the same one you used in Step 1).  
The `whatsapp:` prefix is required — e.g. `whatsapp:+447700900000`.

Or use the interactive docs at `http://localhost:8000/docs` → `POST /portal/agent/`.

---

### Step 3 — Send your first message

Open the chat with the Twilio sandbox number on your phone and type:

```
HELP
```

The bot replies with the full list of available commands.  
Try `LIST` to see listings or `POST <description>` with a photo attached to create one.

---

### Production path (approved WhatsApp Business number)

When you're ready to go live:

1. Apply for a **WhatsApp Business number** through Twilio (or directly via Meta):  
   [https://www.twilio.com/whatsapp/request-access](https://www.twilio.com/whatsapp/request-access)
2. Update `.env` with the new number:  
   ```env
   TWILIO_WHATSAPP_NUMBER=whatsapp:+<your-approved-number>
   ```
3. Users no longer need to send a join code — they simply message your business number directly.

---

## Connecting the Telegram Bot

The bot also supports Telegram, offering the same commands and lead-qualification features as WhatsApp. Unlike WhatsApp, Telegram **does support group chats** — you can add the bot to a group and agents can send commands there.

### Step 1 — Create a Telegram bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather).  
2. Send `/newbot` and follow the prompts (choose a name and username).  
3. BotFather gives you an **API token** that looks like `123456789:ABCdef…`.  
4. Add it to your `.env`:

   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdef…
   ```

### Step 2 — Register the webhook

The bot uses Telegram's webhook mode. Set your public HTTPS URL in `.env`:

```env
BASE_URL=https://yourapp.com
```

The server auto-registers `https://yourapp.com/webhook/telegram` with Telegram on startup when both `TELEGRAM_BOT_TOKEN` and a non-localhost `BASE_URL` are set.

For local development with ngrok:

```bash
ngrok http 8000
# Copy the https URL, e.g. https://abc123.ngrok.io
```

Then set in `.env`:
```env
BASE_URL=https://abc123.ngrok.io
TELEGRAM_BOT_TOKEN=123456789:ABCdef…
```

And restart the server — the webhook is registered automatically.  

Or register manually at any time:
```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://abc123.ngrok.io/webhook/telegram"
```

### Step 3 — Register your agent's Telegram chat ID

The bot identifies agents by their **Telegram chat ID**. The easiest way to find and register it is with the setup helper:

```bash
python setup_telegram.py
```

The script will:
- Send a test message from your Telegram account to the bot.
- Print your chat ID.
- Let you pick (or create) an agent from the database.
- Save the chat ID automatically.

**Manual alternative** — Send any message to your bot, then check the server logs for a line like:

```
INFO: Telegram webhook for chat 123456789
```

Then register it via the API:

```bash
curl -s -X PATCH http://localhost:8000/portal/agent/1 \
  -H "Content-Type: application/json" \
  -d '{"telegram_chat_id": "123456789"}'
```

Replace `1` with your agent's ID and `123456789` with your actual Telegram chat ID.

### Step 4 — Start chatting

Open a direct message with your bot on Telegram and send:

```
HELP
```

The bot replies with the full list of commands. To post a listing, send a photo with the caption:

```
POST 3-bedroom house in Sydney — open kitchen, stunning views
```

### Using the bot in a Telegram group

1. Add your bot to a group (search its `@username` in the "Add member" dialog).  
2. Each agent in the group must have their Telegram user ID registered (Step 3 above).  
3. Send commands directly — `POST`, `LIST`, `LEADS`, `PERFORMANCE`, `HELP`.  
4. **Lead messages from groups are currently attributed to the group's chat ID**; direct private messages are recommended for lead qualification.

---

## Environment Variables

### Required to enable WhatsApp messaging

| Variable | Description |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID — found at [console.twilio.com](https://console.twilio.com) |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token — same page |
| `TWILIO_WHATSAPP_NUMBER` | The Twilio WhatsApp sender in `whatsapp:+1…` format |

### Required to enable the Telegram bot

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) — looks like `123456:ABCdef…` |

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

## Telegram Bot Commands (for agents)

Identical to WhatsApp commands — use the same keywords in a direct message or group:

| Command | Action |
|---|---|
| `POST <description>` + optional photo/video | Creates listing and posts to all connected social platforms |
| `LIST` | Shows your 5 most recent active listings |
| `LEADS` | Shows recent leads with qualification scores |
| `PERFORMANCE` | Shows this week's performance summary |
| `HELP` or `/start` | Shows all available commands |

Any message from an **unregistered** Telegram user is treated as a lead inquiry.

---

## API Endpoints

### WhatsApp
| Method | Path | Description |
|---|---|---|
| POST | `/webhook/whatsapp` | Twilio webhook receiver |

### Telegram
| Method | Path | Description |
|---|---|---|
| POST | `/webhook/telegram` | Telegram Bot API webhook receiver |

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
