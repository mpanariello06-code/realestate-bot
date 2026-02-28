"""Tests for reporting service."""
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.agent import Agent
from app.models.lead import Lead, LeadSource, LeadStatus
from app.models.performance import PerformanceMetric
from app.services.reporting import format_report_message, generate_weekly_report

TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _make_agent_and_data():
    db = TestingSessionLocal()
    agent = Agent(
        name="Report Agent",
        email="report@example.com",
        phone="+5555555555",
        whatsapp_number="whatsapp:+5555555555",
    )
    db.add(agent)
    db.flush()

    # Add some leads
    for i in range(5):
        lead = Lead(
            agent_id=agent.id,
            first_name=f"Lead{i}",
            last_name="Test",
            source=LeadSource.WHATSAPP,
            status=LeadStatus.QUALIFIED if i < 2 else LeadStatus.NEW,
        )
        db.add(lead)

    # Add a performance metric for the current week
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    metric = PerformanceMetric(
        agent_id=agent.id,
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        total_leads=5,
        qualified_leads=2,
        deals_closed=1,
        total_posts=3,
        total_engagements=120,
        facebook_followers=500,
        instagram_followers=300,
        tiktok_followers=100,
        avg_response_time_minutes=4.5,
    )
    db.add(metric)
    db.commit()
    agent_id = agent.id
    db.close()
    return agent_id


class TestGenerateWeeklyReport:
    def test_report_contains_required_keys(self):
        agent_id = _make_agent_and_data()
        db = TestingSessionLocal()
        report = generate_weekly_report(agent_id, db)
        db.close()

        for key in ("period", "total_leads", "qualified_leads", "deals_closed",
                    "total_posts", "total_engagements", "facebook_followers",
                    "instagram_followers", "tiktok_followers", "avg_response_time_minutes"):
            assert key in report, f"Missing key: {key}"

    def test_report_uses_performance_metric_when_available(self):
        agent_id = _make_agent_and_data()
        db = TestingSessionLocal()
        report = generate_weekly_report(agent_id, db)
        db.close()

        assert report["total_leads"] == 5
        assert report["qualified_leads"] == 2
        assert report["deals_closed"] == 1
        assert report["facebook_followers"] == 500

    def test_report_falls_back_to_db_counts_when_no_metric(self):
        db = TestingSessionLocal()
        agent = Agent(
            name="No Metric Agent",
            email="nometric@example.com",
            phone="+6666666666",
            whatsapp_number="whatsapp:+6666666666",
        )
        db.add(agent)
        db.flush()
        for i in range(3):
            lead = Lead(
                agent_id=agent.id,
                first_name=f"L{i}",
                last_name="Test",
                source=LeadSource.OTHER,
            )
            db.add(lead)
        db.commit()
        agent_id = agent.id

        report = generate_weekly_report(agent_id, db)
        db.close()

        assert report["total_leads"] == 3

    def test_report_for_unknown_agent_returns_zeros(self):
        db = TestingSessionLocal()
        report = generate_weekly_report(99999, db)
        db.close()

        assert report["total_leads"] == 0
        assert report["deals_closed"] == 0


class TestFormatReportMessage:
    def test_format_message_contains_agent_name(self):
        report = {
            "period": "2024-01-01 to 2024-01-07",
            "total_leads": 10,
            "qualified_leads": 4,
            "deals_closed": 1,
            "active_listings": 2,
            "total_posts": 5,
            "total_engagements": 80,
            "facebook_followers": 200,
            "instagram_followers": 150,
            "tiktok_followers": 50,
            "avg_response_time_minutes": 6.0,
            "trends": {},
        }
        message = format_report_message(report, "Jane Doe")

        assert "Jane Doe" in message
        assert "10" in message
        assert "4" in message

    def test_format_message_includes_trend_arrows(self):
        report = {
            "period": "2024-01-08 to 2024-01-14",
            "total_leads": 12,
            "qualified_leads": 5,
            "deals_closed": 2,
            "active_listings": 3,
            "total_posts": 6,
            "total_engagements": 100,
            "facebook_followers": 210,
            "instagram_followers": 160,
            "tiktok_followers": 60,
            "avg_response_time_minutes": 5.0,
            "trends": {
                "leads": "▲ 20.0%",
                "qualified": "▲ 25.0%",
            },
        }
        message = format_report_message(report, "John Smith")

        assert "▲" in message
