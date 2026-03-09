# 🏠 RealEstate Bot

An all-in-one automation system that helps real estate agents close more deals by automating lead generation, qualification, social media posting, and performance reporting.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Telegram Bot** | Send photos/videos + description → auto-posts to Facebook, Instagram & TikTok |
| **AI Lead Qualification** | OpenAI analyses every incoming lead message, scores it 0-100, and flags serious buyers/sellers |
| **Auto Qualifying Questions** | The bot DMs qualified leads with tailored questions to confirm intent |
| **Agent Notifications** | Instant Telegram notification with lead name, email, phone, and details |
| **Google Sheets CRM** | All leads and performance data stored in a connected spreadsheet |
| **Weekly Reports** | Automated weekly Telegram report: followers, response time, deals closed, conversion rate |
| **Web Portal** | Connect socials, view dashboard metrics, browse and update leads |

---

## 🖥 Web Portal

![Dashboard](https://github.com/user-attachments/assets/e399e8ff-ac83-4d7b-87b0-e46df3d66167)

The portal shows:
- **Dashboard** – KPI cards (total leads, qualified leads, deals closed, conversion rate) + weekly performance table
- **Leads** – Full lead list with score badges, contact details, intent, budget, timeline, and status
- **Connect Socials** – Step-by-step instructions to link Facebook, Instagram, TikTok, and Google Sheets

---

## 🤖 Telegram Bot Commands

| Command | Description |
|---|---|
| `/start` | Show main menu with inline buttons |
| `/post` | Start the listing-post flow (send photo/video + description) |
| `/leads` | List your top 10 qualified leads with action buttons |
| `/performance` | Show recent performance stats |
| `/report` | Trigger the weekly report immediately |
| `/myid` | **Show your Telegram chat ID** – use this during setup to find the value for `AGENT_CHAT_IDS` |
| `/help` | Command reference |

---

## 🗂 Project Structure

```
realestate-bot/
├── .env                          # ← Fill in your credentials (no rename needed)
├── requirements.txt
├── config.py                     # Centralised settings loader
├── main.py                       # Entry point: starts bot + portal + scheduler
├── bot/
│   ├── telegram_bot.py           # All Telegram handlers & conversation flows
│   └── keyboards.py              # Inline keyboard builders
├── services/
│   ├── lead_qualifier.py         # OpenAI-powered lead scoring & caption generation
│   ├── social_poster.py          # Facebook / Instagram / TikTok posting
│   ├── sheets.py                 # Google Sheets read/write
│   └── weekly_report.py          # Weekly report builder & sender
├── portal/
│   ├── app.py                    # Flask application factory
│   ├── routes.py                 # Web portal routes + JSON API
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       ├── leads.html
│       └── connect_socials.html
└── tests/
    ├── test_lead_qualifier.py
    ├── test_sheets.py
    └── test_portal.py
```

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your `.env`

The `.env` file is already named correctly — just open it and fill in your credentials:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
AGENT_CHAT_IDS=123456789          # your Telegram chat ID (see step below)
OPENAI_API_KEY=sk-...
FACEBOOK_PAGE_ACCESS_TOKEN=...
FACEBOOK_PAGE_ID=...
INSTAGRAM_ACCOUNT_ID=...
TIKTOK_ACCESS_TOKEN=...
TIKTOK_OPEN_ID=...
GOOGLE_CREDENTIALS_FILE=google_credentials.json
GOOGLE_SPREADSHEET_NAME=RealEstate Bot Leads
FLASK_SECRET_KEY=change-me
```

> **How to find your Telegram chat ID:**
> 1. Set only `TELEGRAM_BOT_TOKEN` in `.env` and leave `AGENT_CHAT_IDS` blank for now.
> 2. Start the bot: `python main.py`
> 3. Open Telegram and send `/myid` to your bot.
> 4. The bot replies with your exact chat ID (e.g. `123456789`).
> 5. Copy that number into `AGENT_CHAT_IDS` in `.env`, then restart the bot.
>
> For multiple agents, separate each ID with a comma: `AGENT_CHAT_IDS=111111111,222222222`

### 3. Set up Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable **Google Sheets API** and **Google Drive API**.
3. Create a **Service Account** and download the JSON key.
4. Save the key as `google_credentials.json` in the project root.
5. Share your Google Sheet with the service account email.

### 4. Run the bot

```bash
python main.py
```

This starts:
- The **Telegram bot** (polling)
- The **web portal** at `http://localhost:5000`
- The **weekly report scheduler**

---

## 🧪 Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

All tests use mocks — no real API keys needed to run tests.

---

## 📊 Google Sheets Layout

**Worksheet: Leads**

| Column | Description |
|---|---|
| timestamp | When the lead was recorded |
| platform | facebook / instagram / tiktok / telegram |
| first_name, last_name | Lead's name |
| email, phone | Contact details |
| message | Original message |
| score | 0-100 qualification score |
| intent | buy / sell / rent / unknown |
| budget, timeline, location | Extracted from message |
| is_qualified | TRUE / FALSE |
| summary | AI one-line summary |
| status | new / contacted / closed / lost |
| agent_notes | Your notes |

**Worksheet: Performance**

| Column | Description |
|---|---|
| week_start | Week start date (YYYY-MM-DD) |
| platform | Platform name |
| followers | Follower count |
| new_leads / qualified_leads | Lead counts |
| deals_closed | Number of deals closed |
| avg_response_time | Average response time (minutes) |
| engagement_rate | Engagement rate (%) |

---

## 🔌 API Endpoints (Web Portal)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/dashboard` | Dashboard page |
| `GET` | `/leads` | Leads page (`?qualified=true` to filter) |
| `GET` | `/api/leads` | JSON list of leads |
| `GET` | `/api/performance` | JSON performance records (`?weeks=4`) |
| `POST` | `/api/leads/<id>/status` | Update lead status (`{"status": "contacted"}`) |
| `GET` | `/connect-socials` | Social integration guide |

---

## 🛡 Security Notes

- API tokens are loaded exclusively from `.env` — never hardcoded.
- `google_credentials.json` is listed in `.gitignore` to prevent accidental commits.
- Agent-only commands are protected by a `AGENT_CHAT_IDS` whitelist.
