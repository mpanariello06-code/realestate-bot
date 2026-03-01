"""
Flask Web Portal – routes and view helpers.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, render_template, request

from services import sheets

logger = logging.getLogger(__name__)

bp = Blueprint("portal", __name__)


@bp.route("/")
def index():
    return render_template("dashboard.html", title="Dashboard")


@bp.route("/dashboard")
def dashboard():
    perf = sheets.get_performance(weeks=4)
    leads = sheets.get_leads()

    total_leads = len(leads)
    qualified = [l for l in leads if str(l.get("is_qualified", "")).upper() == "TRUE"]
    closed = [l for l in leads if l.get("status") == "closed"]

    stats = {
        "total_leads": total_leads,
        "qualified_leads": len(qualified),
        "deals_closed": len(closed),
        "conversion_rate": round(len(closed) / total_leads * 100, 1) if total_leads else 0,
    }
    return render_template(
        "dashboard.html",
        title="Dashboard",
        stats=stats,
        performance=perf,
    )


@bp.route("/leads")
def leads_view():
    qualified_only = request.args.get("qualified", "false").lower() == "true"
    leads = sheets.get_leads(qualified_only=qualified_only)
    return render_template(
        "leads.html",
        title="Leads",
        leads=leads,
        qualified_only=qualified_only,
    )


# ── JSON API ──────────────────────────────────────────────────────────────────

@bp.route("/api/leads")
def api_leads():
    qualified_only = request.args.get("qualified", "false").lower() == "true"
    return jsonify(sheets.get_leads(qualified_only=qualified_only))


@bp.route("/api/performance")
def api_performance():
    weeks = int(request.args.get("weeks", 4))
    return jsonify(sheets.get_performance(weeks=weeks))


@bp.route("/api/leads/<int:lead_index>/status", methods=["POST"])
def api_update_lead_status(lead_index: int):
    data = request.get_json(force=True)
    status = data.get("status", "")
    notes = data.get("notes", "")
    if status not in ("new", "contacted", "closed", "lost"):
        return jsonify({"error": "Invalid status"}), 400
    success = sheets.update_lead_status(lead_index, status, notes)
    return jsonify({"success": success})


@bp.route("/connect-socials")
def connect_socials():
    return render_template("connect_socials.html", title="Connect Socials")


@bp.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})
