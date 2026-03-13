"""
PDF Report Generator
Builds formatted PDF reports for real estate agents using ReportLab:

* build_report_pdf  – weekly performance report
* build_leads_pdf   – qualified or all-leads contact sheet
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Colour palette ─────────────────────────────────────────────────────────────
_BRAND_DARK  = colors.HexColor("#1a2e4a")   # navy
_BRAND_MID   = colors.HexColor("#2563eb")   # blue
_BRAND_LIGHT = colors.HexColor("#eff6ff")   # ice blue
_GREEN       = colors.HexColor("#16a34a")
_AMBER       = colors.HexColor("#d97706")
_RED         = colors.HexColor("#dc2626")
_GREY_LIGHT  = colors.HexColor("#f1f5f9")
_GREY_MID    = colors.HexColor("#94a3b8")


def _styles():
    base = getSampleStyleSheet()
    extra = {
        "ReportTitle": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontSize=22,
            textColor=_BRAND_DARK,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "SubTitle": ParagraphStyle(
            "SubTitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=_GREY_MID,
            spaceAfter=12,
        ),
        "SectionHeader": ParagraphStyle(
            "SectionHeader",
            parent=base["Normal"],
            fontSize=13,
            textColor=_BRAND_DARK,
            spaceBefore=16,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "BodyText": ParagraphStyle(
            "BodyText",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#334155"),
            spaceAfter=4,
        ),
        "Highlight": ParagraphStyle(
            "Highlight",
            parent=base["Normal"],
            fontSize=11,
            textColor=_BRAND_MID,
            fontName="Helvetica-Bold",
            spaceAfter=4,
        ),
        "Footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontSize=8,
            textColor=_GREY_MID,
            alignment=1,  # centre
        ),
    }
    return extra


def _metric_table(rows: list[tuple]) -> Table:
    """Render a two-column metric table (Label, Value)."""
    col_widths = [9 * cm, 7 * cm]
    tbl = Table(rows, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_DARK),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_GREY_LIGHT, colors.white]),
        ("GRID",       (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("ALIGN",      (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _perf_table(records: list[dict]) -> Table:
    """Render the platform performance records as a table."""
    headers = ["Platform", "Followers", "New Leads", "Qualified", "Deals Closed",
               "Avg Response", "Engagement"]
    rows = [headers]
    for rec in records:
        rows.append([
            rec.get("platform", "—").title(),
            f"{rec.get('followers', 0):,}",
            str(rec.get("new_leads", 0)),
            str(rec.get("qualified_leads", 0)),
            str(rec.get("deals_closed", 0)),
            f"{rec.get('avg_response_time', 0)} min",
            f"{rec.get('engagement_rate', 0)}%",
        ])

    tbl = Table(rows, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), _BRAND_DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_GREY_LIGHT, colors.white]),
        ("GRID",         (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _pct(part: int, total: int) -> str:
    """Return 'X.Y%' of part/total, or '0%' when total is zero."""
    return f"{round(part / total * 100, 1) if total else 0}%"


def _pipeline_table(total: int, qualified: int, contacted: int, closed: int) -> Table:
    """Render a sales-pipeline summary as a colour-coded table."""
    rows = [
        ["Stage", "Count", "% of Total"],
        ["📥 Total Leads",     str(total),     "100%"],
        ["🎯 Qualified",       str(qualified), _pct(qualified, total)],
        ["📞 Contacted",       str(contacted), _pct(contacted, total)],
        ["🏆 Deals Closed",    str(closed),    _pct(closed, total)],
    ]
    tbl = Table(rows, colWidths=[8 * cm, 4 * cm, 4 * cm])
    stage_colours = [_BRAND_DARK, _BRAND_MID, _AMBER, _GREEN]
    style_cmds = [
        ("BACKGROUND",   (0, 0), (-1, 0), _BRAND_DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 10),
        ("GRID",         (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]
    for row_i, col in enumerate(stage_colours, start=1):
        style_cmds.append(("TEXTCOLOR", (0, row_i), (0, row_i), col))
        style_cmds.append(("FONTNAME",  (0, row_i), (0, row_i), "Helvetica-Bold"))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def build_report_pdf(leads: list[dict], perf_records: list[dict]) -> bytes:
    """
    Build a formatted PDF performance report.

    Parameters
    ----------
    leads       : list of lead dicts from sheets.get_leads()
    perf_records: list of performance dicts from sheets.get_performance()

    Returns
    -------
    bytes – raw PDF content ready to be sent as a Telegram document.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Real Estate Weekly Report",
        author="Real Estate Agent Bot",
    )

    st = _styles()
    today     = datetime.now(timezone.utc)
    week_start = (today - timedelta(days=today.weekday())).strftime("%d %b %Y")
    week_end   = today.strftime("%d %b %Y")

    # ── Compute metrics ────────────────────────────────────────────────────────
    total_leads = len(leads)
    n_qualified = sum(1 for l in leads if str(l.get("is_qualified", "")).upper() == "TRUE")
    n_contacted = sum(1 for l in leads if l.get("status") in ("contacted", "closed"))
    n_closed    = sum(1 for l in leads if l.get("status") == "closed")
    conversion  = round(n_closed / total_leads * 100, 1) if total_leads else 0
    pending_contact = max(n_qualified - n_contacted, 0)

    # ── Build story ────────────────────────────────────────────────────────────
    story = []

    # Header
    story.append(Paragraph("🏠 Real Estate Performance Report", st["ReportTitle"]))
    story.append(Paragraph(f"Week: {week_start} – {week_end}", st["SubTitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=_BRAND_MID, spaceAfter=12))

    # ── Lead Summary ──────────────────────────────────────────────────────────
    story.append(Paragraph("Lead Summary", st["SectionHeader"]))
    metric_rows = [
        ["Metric", "Value"],
        ["Total Leads Received",  str(total_leads)],
        ["Qualified Leads",       str(n_qualified)],
        ["Leads Contacted",       str(n_contacted)],
        ["Deals Closed",          str(n_closed)],
        ["Overall Conversion Rate", f"{conversion}%"],
        ["Still Awaiting Contact", str(pending_contact)],
    ]
    story.append(_metric_table(metric_rows))
    story.append(Spacer(1, 0.4 * cm))

    # ── Sales Pipeline ────────────────────────────────────────────────────────
    story.append(Paragraph("Sales Pipeline", st["SectionHeader"]))
    story.append(_pipeline_table(total_leads, n_qualified, n_contacted, n_closed))
    story.append(Spacer(1, 0.4 * cm))

    # ── Platform Performance ──────────────────────────────────────────────────
    story.append(Paragraph("Platform Performance", st["SectionHeader"]))
    if perf_records:
        story.append(_perf_table(perf_records))
    else:
        story.append(Paragraph("No platform data recorded yet.", st["BodyText"]))
    story.append(Spacer(1, 0.4 * cm))

    # ── Top Leads ─────────────────────────────────────────────────────────────
    qualified_leads = [
        l for l in leads if str(l.get("is_qualified", "")).upper() == "TRUE"
    ]
    top_leads = sorted(qualified_leads, key=lambda l: l.get("score", 0), reverse=True)[:5]
    if top_leads:
        story.append(Paragraph("Top Qualified Leads", st["SectionHeader"]))
        lead_headers = ["Name", "Intent", "Budget", "Score", "Status"]
        lead_rows = [lead_headers]
        for lead in top_leads:
            name = (
                f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
                or "Unknown"
            )
            lead_rows.append([
                name,
                lead.get("intent", "—").title(),
                lead.get("budget") or "—",
                f"{lead.get('score', 0)}/100",
                lead.get("status", "new").title(),
            ])
        lead_tbl = Table(lead_rows, repeatRows=1)
        lead_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), _BRAND_DARK),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_GREY_LIGHT, colors.white]),
            ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
            ("ALIGN",         (3, 0), (4, -1), "CENTER"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(lead_tbl)
        story.append(Spacer(1, 0.4 * cm))

    # ── Key Takeaway ──────────────────────────────────────────────────────────
    story.append(Paragraph("Key Takeaway", st["SectionHeader"]))
    story.append(HRFlowable(width="100%", thickness=1, color=_BRAND_LIGHT, spaceAfter=6))
    if pending_contact > 0:
        story.append(Paragraph(
            f"You have <b>{pending_contact}</b> qualified lead(s) still waiting to be "
            "contacted. Follow up now to close more deals! 🚀",
            st["Highlight"],
        ))
    else:
        story.append(Paragraph(
            "Great work! All qualified leads have been contacted. "
            "Keep posting to generate more opportunities. 🏆",
            st["Highlight"],
        ))
    story.append(Spacer(1, 0.8 * cm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=_GREY_MID, spaceAfter=4))
    story.append(Paragraph(
        f"Generated on {today.strftime('%d %b %Y at %H:%M UTC')} · Real Estate Agent Bot",
        st["Footer"],
    ))

    doc.build(story)
    return buf.getvalue()


# ── Leads PDF ─────────────────────────────────────────────────────────────────

def _score_colour(score: int) -> colors.Color:
    """Return a colour reflecting lead quality."""
    if score >= 80:
        return _GREEN
    if score >= 60:
        return _AMBER
    return _RED


def build_leads_pdf(leads: list[dict], title: str, subtitle: str) -> bytes:
    """
    Build a professional leads contact-sheet PDF.

    Parameters
    ----------
    leads    : list of lead dicts (same shape as sheets.get_leads())
    title    : document heading (e.g. "Qualified Leads Report")
    subtitle : one-line description shown under the title

    Returns
    -------
    bytes – raw PDF content ready to be sent as a Telegram document.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title,
        author="Real Estate Agent Bot",
    )

    st  = _styles()
    now = datetime.now(timezone.utc)

    # ── Summary stats ─────────────────────────────────────────────────────────
    total      = len(leads)
    n_qual     = sum(1 for l in leads if l.get("is_qualified") in (True, "TRUE"))
    n_new      = sum(1 for l in leads if l.get("status", "new") == "new")
    n_cont     = sum(1 for l in leads if l.get("status") == "contacted")
    n_closed   = sum(1 for l in leads if l.get("status") == "closed")

    story: list = []

    # Header
    story.append(Paragraph(f"🏠 {title}", st["ReportTitle"]))
    story.append(Paragraph(subtitle, st["SubTitle"]))
    story.append(HRFlowable(width="100%", thickness=2, color=_BRAND_MID, spaceAfter=10))

    # Summary bar
    summary_rows = [
        ["Total Leads", "Qualified", "New", "Contacted", "Closed"],
        [str(total), str(n_qual), str(n_new), str(n_cont), str(n_closed)],
    ]
    col_w = [3.4 * cm] * 5
    summary_tbl = Table(summary_rows, colWidths=col_w)
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _BRAND_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND",    (0, 1), (-1, 1), _BRAND_LIGHT),
        ("FONTNAME",      (0, 1), (-1, 1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (0, 1), (-1, 1), _BRAND_DARK),
        ("FONTSIZE",      (0, 0), (-1, -1), 10),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 0.5 * cm))

    # ── Leads table ───────────────────────────────────────────────────────────
    story.append(Paragraph("Lead Details", st["SectionHeader"]))

    headers = ["#", "Name", "Contact", "Intent", "Budget / Timeline", "Score", "Status"]
    rows    = [headers]

    for idx, lead in enumerate(leads, 1):
        name    = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip() or "—"
        phone   = lead.get("phone") or ""
        email   = lead.get("email") or ""
        contact = "\n".join(filter(None, [phone, email])) or "—"
        intent  = (lead.get("intent") or "unknown").title()
        budget  = lead.get("budget") or "—"
        tline   = lead.get("timeline") or "—"
        bud_tl  = f"{budget}\n{tline}" if budget != "—" or tline != "—" else "—"
        score   = int(lead.get("score") or 0)
        status  = (lead.get("status") or "new").title()

        rows.append([
            str(idx),
            Paragraph(name, st["BodyText"]),
            Paragraph(contact.replace("\n", "<br/>"), st["BodyText"]),
            intent,
            Paragraph(bud_tl.replace("\n", "<br/>"), st["BodyText"]),
            Paragraph(
                f'<font color="{_score_colour(score).hexval()}">'
                f"<b>{score}/100</b></font>",
                st["BodyText"],
            ),
            status,
        ])

    col_widths = [1 * cm, 3.5 * cm, 4 * cm, 2 * cm, 4 * cm, 2 * cm, 2.5 * cm]
    leads_tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    leads_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _BRAND_DARK),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_GREY_LIGHT, colors.white]),
        ("GRID",          (0, 0), (-1, -1), 0.4, _GREY_MID),
        ("ALIGN",         (0, 0), (0, -1), "CENTER"),   # #
        ("ALIGN",         (3, 0), (3, -1), "CENTER"),   # Intent
        ("ALIGN",         (5, 0), (5, -1), "CENTER"),   # Score
        ("ALIGN",         (6, 0), (6, -1), "CENTER"),   # Status
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(leads_tbl)
    story.append(Spacer(1, 0.8 * cm))

    # ── Agent notes section (only if any lead has notes) ─────────────────────
    noted = [(i + 1, l) for i, l in enumerate(leads) if l.get("agent_notes")]
    if noted:
        story.append(Paragraph("Agent Notes", st["SectionHeader"]))
        story.append(HRFlowable(width="100%", thickness=1, color=_BRAND_LIGHT, spaceAfter=4))
        for num, lead in noted:
            name  = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
            note  = lead.get("agent_notes", "")
            story.append(Paragraph(f"<b>#{num} {name}:</b> {note}", st["BodyText"]))
        story.append(Spacer(1, 0.5 * cm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=_GREY_MID, spaceAfter=4))
    story.append(Paragraph(
        f"Generated on {now.strftime('%d %b %Y at %H:%M UTC')} · Real Estate Agent Bot",
        st["Footer"],
    ))

    doc.build(story)
    return buf.getvalue()
