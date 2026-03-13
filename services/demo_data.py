"""
Hard-coded realistic data used as the fallback data source when Google Sheets
is not configured or returns no records.

All names, phone numbers, and e-mail addresses are fictional.
"""
from __future__ import annotations

# ── Leads ─────────────────────────────────────────────────────────────────────

DEMO_LEADS: list[dict] = [
    {
        "timestamp":    "2025-03-10 09:14:22",
        "platform":     "instagram",
        "first_name":   "Sarah",
        "last_name":    "Johnson",
        "email":        "sarah.johnson@email.com",
        "phone":        "+1 (416) 555-0182",
        "message": (
            "Hi, I'm looking to buy a 3-bedroom home in North York. "
            "Budget around $850k. We're ready to move within 2 months."
        ),
        "score":        88,
        "intent":       "buy",
        "budget":       "$850,000",
        "timeline":     "2 months",
        "location":     "North York, Toronto",
        "is_qualified": True,
        "summary": (
            "Serious buyer with clear budget and timeline, "
            "looking for 3-bed in North York."
        ),
        "status":       "new",
        "agent_notes":  "",
    },
    {
        "timestamp":    "2025-03-10 11:32:45",
        "platform":     "facebook",
        "first_name":   "Michael",
        "last_name":    "Chen",
        "email":        "m.chen@gmail.com",
        "phone":        "+1 (647) 555-0247",
        "message": (
            "We want to sell our detached home in Etobicoke. "
            "4 beds, 2 baths. Expecting around $1.1M. Can you help?"
        ),
        "score":        82,
        "intent":       "sell",
        "budget":       "$1,100,000",
        "timeline":     "1–3 months",
        "location":     "Etobicoke, Toronto",
        "is_qualified": True,
        "summary": (
            "Homeowner ready to list a 4-bed detached "
            "in Etobicoke at $1.1M."
        ),
        "status":       "contacted",
        "agent_notes":  "Booked valuation call for Thursday 2 pm",
    },
    {
        "timestamp":    "2025-03-10 14:05:11",
        "platform":     "telegram",
        "first_name":   "Emily",
        "last_name":    "Rodriguez",
        "email":        "emily.r@hotmail.com",
        "phone":        "+1 (905) 555-0139",
        "message": (
            "Looking to rent a 2-bed condo near downtown. "
            "Max $2,800/month. Need pet-friendly. Move-in April."
        ),
        "score":        74,
        "intent":       "rent",
        "budget":       "$2,800/month",
        "timeline":     "April 2025",
        "location":     "Downtown Toronto",
        "is_qualified": True,
        "summary": (
            "Renter seeking 2-bed pet-friendly condo downtown, "
            "move-in April, budget $2,800/mo."
        ),
        "status":       "new",
        "agent_notes":  "",
    },
    {
        "timestamp":    "2025-03-11 08:22:33",
        "platform":     "instagram",
        "first_name":   "James",
        "last_name":    "Wilson",
        "email":        "jwilson@outlook.com",
        "phone":        "+1 (416) 555-0314",
        "message": (
            "Pre-approved for $675k. First-time buyer. "
            "Looking for semi-detached in Scarborough or East York."
        ),
        "score":        91,
        "intent":       "buy",
        "budget":       "$675,000",
        "timeline":     "3 months",
        "location":     "Scarborough / East York",
        "is_qualified": True,
        "summary": (
            "Pre-approved first-time buyer, $675k budget, "
            "targeting Scarborough / East York."
        ),
        "status":       "contacted",
        "agent_notes":  "Sent 3 listings, viewing booked Saturday",
    },
    {
        "timestamp":    "2025-03-11 10:47:59",
        "platform":     "facebook",
        "first_name":   "Aisha",
        "last_name":    "Patel",
        "email":        "aisha.patel@yahoo.com",
        "phone":        "+1 (647) 555-0421",
        "message": (
            "Hi, interested in investment properties in Mississauga. "
            "ROI-focused. Budget $500k–$600k range."
        ),
        "score":        79,
        "intent":       "buy",
        "budget":       "$500,000–$600,000",
        "timeline":     "6 months",
        "location":     "Mississauga",
        "is_qualified": True,
        "summary": (
            "Investor seeking income-generating property "
            "in Mississauga, $500k–$600k budget."
        ),
        "status":       "new",
        "agent_notes":  "",
    },
    {
        "timestamp":    "2025-03-12 09:03:17",
        "platform":     "instagram",
        "first_name":   "David",
        "last_name":    "O'Brien",
        "email":        "",
        "phone":        "",
        "message":      "Do you have any condos available? Just browsing for now.",
        "score":        28,
        "intent":       "unknown",
        "budget":       None,
        "timeline":     None,
        "location":     None,
        "is_qualified": False,
        "summary":      "Casual inquiry; no specific requirements or contact details provided.",
        "status":       "new",
        "agent_notes":  "",
    },
    {
        "timestamp":    "2025-03-12 13:41:08",
        "platform":     "facebook",
        "first_name":   "Lisa",
        "last_name":    "Thompson",
        "email":        "l.thompson@gmail.com",
        "phone":        "+1 (905) 555-0288",
        "message": (
            "Looking for apartments to rent. "
            "Not sure about the area yet. Maybe $1,500–$1,800."
        ),
        "score":        42,
        "intent":       "rent",
        "budget":       "$1,500–$1,800/month",
        "timeline":     None,
        "location":     None,
        "is_qualified": False,
        "summary":      "Potential renter; no defined location or timeline, lower budget range.",
        "status":       "new",
        "agent_notes":  "",
    },
    {
        "timestamp":    "2025-03-13 07:18:55",
        "platform":     "telegram",
        "first_name":   "Robert",
        "last_name":    "Martinez",
        "email":        "rob.martinez@business.com",
        "phone":        "+1 (416) 555-0567",
        "message": (
            "We're relocating from Vancouver. Need a 4+ bed detached with a backyard "
            "in Oakville or Burlington. Budget $1.2M–$1.5M. Timeline: 60 days."
        ),
        "score":        95,
        "intent":       "buy",
        "budget":       "$1,200,000–$1,500,000",
        "timeline":     "60 days",
        "location":     "Oakville / Burlington",
        "is_qualified": True,
        "summary": (
            "High-priority relocating buyer, $1.2M–$1.5M budget, "
            "60-day timeline, targeting Oakville / Burlington."
        ),
        "status":       "new",
        "agent_notes":  "",
    },
]

# ── Today's key performance metrics ───────────────────────────────────────────

DEMO_PERFORMANCE_TODAY: dict = {
    "new_leads":              3,
    "qualified_leads":        2,
    "messages_handled":       47,
    "avg_response_min":       4.2,
    "instagram_followers":    2_847,
    "instagram_engagement":   4.8,
    "facebook_followers":     5_214,
    "facebook_engagement":    3.1,
    "posts_today":            2,
    "views_today":            1_840,
    "response_rate_pct":      100,
}

# ── Weekly platform performance records ───────────────────────────────────────

DEMO_PERFORMANCE_WEEKLY: list[dict] = [
    {
        "week_start":       "2025-03-10",
        "platform":         "instagram",
        "followers":        2_847,
        "new_leads":        11,
        "qualified_leads":  7,
        "deals_closed":     2,
        "avg_response_time": 4,
        "engagement_rate":  4.8,
    },
    {
        "week_start":       "2025-03-10",
        "platform":         "facebook",
        "followers":        5_214,
        "new_leads":        7,
        "qualified_leads":  4,
        "deals_closed":     1,
        "avg_response_time": 6,
        "engagement_rate":  3.1,
    },
]
