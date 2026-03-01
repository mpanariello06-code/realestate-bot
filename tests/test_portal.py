"""
Tests for the Flask web portal.
"""
from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")


MOCK_LEADS = [
    {
        "timestamp": "2025-01-06 10:00:00",
        "platform": "facebook",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john@example.com",
        "phone": "555-1234",
        "message": "I want to buy",
        "score": 85,
        "intent": "buy",
        "budget": "$500k",
        "timeline": "3 months",
        "location": "Miami",
        "is_qualified": "TRUE",
        "summary": "Serious buyer",
        "status": "new",
        "agent_notes": "",
    }
]

MOCK_PERF = [
    {
        "week_start": "2025-01-06",
        "platform": "instagram",
        "followers": 1200,
        "new_leads": 10,
        "qualified_leads": 3,
        "deals_closed": 1,
        "avg_response_time": 10,
        "engagement_rate": 3.2,
    }
]


class TestPortal(unittest.TestCase):

    def setUp(self):
        from portal.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")

    @patch("services.sheets.get_performance", return_value=MOCK_PERF)
    @patch("services.sheets.get_leads", return_value=MOCK_LEADS)
    def test_dashboard_loads(self, _mock_leads, _mock_perf):
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Dashboard", resp.data)

    @patch("services.sheets.get_leads", return_value=MOCK_LEADS)
    def test_leads_page_loads(self, _mock_leads):
        resp = self.client.get("/leads")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"John", resp.data)

    @patch("services.sheets.get_leads", return_value=MOCK_LEADS)
    def test_leads_api(self, _mock_leads):
        resp = self.client.get("/api/leads")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["first_name"], "John")

    @patch("services.sheets.get_leads", return_value=MOCK_LEADS)
    def test_api_qualified_leads(self, _mock_leads):
        resp = self.client.get("/api/leads?qualified=true")
        self.assertEqual(resp.status_code, 200)

    @patch("services.sheets.get_performance", return_value=MOCK_PERF)
    def test_performance_api(self, _mock_perf):
        resp = self.client.get("/api/performance")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertGreater(len(data), 0)

    @patch("services.sheets.update_lead_status", return_value=True)
    def test_update_lead_status_api(self, _mock_update):
        resp = self.client.post(
            "/api/leads/1/status",
            json={"status": "contacted", "notes": "Called"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])

    def test_update_lead_status_invalid(self):
        resp = self.client.post(
            "/api/leads/1/status",
            json={"status": "invalid_status"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_connect_socials_page(self):
        resp = self.client.get("/connect-socials")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Connect", resp.data)


if __name__ == "__main__":
    unittest.main()
