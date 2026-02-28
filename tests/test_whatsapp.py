"""Tests for WhatsApp webhook handler."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agent import Agent

from tests.conftest import TestingSessionLocal

client = TestClient(app)


def _make_agent(db) -> Agent:
    agent = Agent(
        name="Test Agent",
        email="agent@example.com",
        phone="+1234567890",
        whatsapp_number="whatsapp:+1234567890",
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


# ── parse_incoming_message ────────────────────────────────────────────────────

class TestParseIncomingMessage:
    def test_basic_message(self):
        from app.services.whatsapp_service import parse_incoming_message

        form = {
            "From": "whatsapp:+1999999999",
            "To": "whatsapp:+14155238886",
            "Body": "Hello",
            "NumMedia": "0",
            "MessageSid": "SM123",
        }
        result = parse_incoming_message(form)

        assert result["from"] == "whatsapp:+1999999999"
        assert result["body"] == "Hello"
        assert result["num_media"] == 0
        assert result["media_urls"] == []

    def test_message_with_media(self):
        from app.services.whatsapp_service import parse_incoming_message

        form = {
            "From": "whatsapp:+1999999999",
            "Body": "Check this out",
            "NumMedia": "2",
            "MediaUrl0": "https://example.com/photo1.jpg",
            "MediaContentType0": "image/jpeg",
            "MediaUrl1": "https://example.com/photo2.jpg",
            "MediaContentType1": "image/jpeg",
        }
        result = parse_incoming_message(form)

        assert result["num_media"] == 2
        assert len(result["media_urls"]) == 2
        assert result["media_urls"][0]["url"] == "https://example.com/photo1.jpg"

    def test_empty_form_data(self):
        from app.services.whatsapp_service import parse_incoming_message

        result = parse_incoming_message({})

        assert result["from"] == ""
        assert result["body"] == ""
        assert result["num_media"] == 0


# ── WhatsApp webhook endpoint ─────────────────────────────────────────────────

class TestWhatsAppWebhook:
    def _post_webhook(self, from_number: str, body: str):
        return client.post(
            "/webhook/whatsapp",
            data={"From": from_number, "Body": body, "NumMedia": "0"},
        )

    def test_help_command_from_agent(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        resp = self._post_webhook("whatsapp:+1234567890", "HELP")
        assert resp.status_code == 200
        assert "Command" in resp.text or "command" in resp.text.lower()

    def test_list_command_no_listings(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        resp = self._post_webhook("whatsapp:+1234567890", "LIST")
        assert resp.status_code == 200
        assert "no active listings" in resp.text.lower() or "listings" in resp.text.lower()

    def test_leads_command_no_leads(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        resp = self._post_webhook("whatsapp:+1234567890", "LEADS")
        assert resp.status_code == 200

    def test_unknown_agent_command(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        resp = self._post_webhook("whatsapp:+1234567890", "FOOBAR")
        assert resp.status_code == 200
        assert "HELP" in resp.text

    def test_lead_message_from_unknown_number(self):
        # Unknown number → treated as lead
        with patch("app.services.lead_qualifier.qualify_lead", return_value={
            "is_serious": False,
            "qualification_score": 20,
            "reasoning": "just browsing",
            "lead_type": "unknown",
            "urgency": "just_browsing",
            "recommended_action": "nurture",
        }), patch("app.services.lead_qualifier.get_auto_reply", return_value="Thank you!"):
            resp = self._post_webhook("whatsapp:+9999999999", "I am looking for a house")

        assert resp.status_code == 200

    def test_webhook_returns_xml(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        resp = self._post_webhook("whatsapp:+1234567890", "HELP")
        assert "application/xml" in resp.headers.get("content-type", "")
