"""Tests for Telegram webhook handler and telegram_service utilities."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.agent import Agent

from tests.conftest import TestingSessionLocal

client = TestClient(app)


def _make_agent(db, telegram_chat_id: str = "111222333") -> Agent:
    agent = Agent(
        name="Telegram Agent",
        email="tgagent@example.com",
        phone="+1234567890",
        whatsapp_number="whatsapp:+1234567890",
        telegram_chat_id=telegram_chat_id,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _post_update(text: str, chat_id: str = "111222333", media: bool = False):
    body = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": int(chat_id), "first_name": "Test", "last_name": "User"},
            "chat": {"id": int(chat_id), "type": "private"},
            "text": text,
        },
    }
    if media:
        body["message"]["photo"] = [
            {"file_id": "FILEID123", "file_unique_id": "x", "width": 100, "height": 100, "file_size": 1000},
        ]
        body["message"]["caption"] = text
        del body["message"]["text"]
    return client.post("/webhook/telegram", json=body)


# ── parse_telegram_update ─────────────────────────────────────────────────────

class TestParseTelegramUpdate:
    def test_plain_text_message(self):
        from app.services.telegram_service import parse_telegram_update

        body = {
            "update_id": 42,
            "message": {
                "message_id": 7,
                "from": {"id": 999, "first_name": "Alice", "last_name": "Smith"},
                "chat": {"id": 999, "type": "private"},
                "text": "Hello",
            },
        }
        result = parse_telegram_update(body)
        assert result["chat_id"] == "999"
        assert result["text"] == "Hello"
        assert result["first_name"] == "Alice"
        assert result["media_file_ids"] == []

    def test_photo_with_caption(self):
        from app.services.telegram_service import parse_telegram_update

        body = {
            "update_id": 43,
            "message": {
                "message_id": 8,
                "from": {"id": 999, "first_name": "Bob", "last_name": ""},
                "chat": {"id": 999, "type": "private"},
                "photo": [
                    {"file_id": "small", "file_unique_id": "a", "width": 90, "height": 90, "file_size": 100},
                    {"file_id": "large", "file_unique_id": "b", "width": 800, "height": 600, "file_size": 50000},
                ],
                "caption": "POST Nice house",
            },
        }
        result = parse_telegram_update(body)
        assert result["text"] == "POST Nice house"
        assert result["media_file_ids"] == ["large"]

    def test_empty_body(self):
        from app.services.telegram_service import parse_telegram_update

        result = parse_telegram_update({})
        assert result["chat_id"] == ""
        assert result["text"] == ""
        assert result["media_file_ids"] == []


# ── send_telegram_message ─────────────────────────────────────────────────────

class TestSendTelegramMessage:
    def test_returns_false_when_no_token(self):
        from app.services.telegram_service import send_telegram_message
        from app import config

        original = config.settings.TELEGRAM_BOT_TOKEN
        config.settings.TELEGRAM_BOT_TOKEN = ""
        result = send_telegram_message("123", "hello")
        config.settings.TELEGRAM_BOT_TOKEN = original
        assert result is False

    def test_sends_message_successfully(self):
        from app.services.telegram_service import send_telegram_message
        from app import config

        original = config.settings.TELEGRAM_BOT_TOKEN
        config.settings.TELEGRAM_BOT_TOKEN = "test-token"
        try:
            mock_resp = MagicMock()
            mock_resp.ok = True
            with patch("app.services.telegram_service.requests.post", return_value=mock_resp) as mock_post:
                result = send_telegram_message("123", "hello")
            assert result is True
            mock_post.assert_called_once()
        finally:
            config.settings.TELEGRAM_BOT_TOKEN = original


# ── Telegram webhook endpoint ─────────────────────────────────────────────────

class TestTelegramWebhook:
    def test_help_command_from_agent(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message") as mock_send:
            resp = _post_update("HELP")

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_send.assert_called_once()
        sent_text = mock_send.call_args[0][1]
        assert "command" in sent_text.lower()

    def test_start_command_shows_help(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message") as mock_send:
            resp = _post_update("/start")

        assert resp.status_code == 200
        sent_text = mock_send.call_args[0][1]
        assert "POST" in sent_text

    def test_list_command_no_listings(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message") as mock_send:
            resp = _post_update("LIST")

        assert resp.status_code == 200
        sent_text = mock_send.call_args[0][1]
        assert "listing" in sent_text.lower()

    def test_leads_command_no_leads(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message") as mock_send:
            resp = _post_update("LEADS")

        assert resp.status_code == 200
        mock_send.assert_called_once()

    def test_performance_command(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message") as mock_send:
            resp = _post_update("PERFORMANCE")

        assert resp.status_code == 200
        sent_text = mock_send.call_args[0][1]
        assert "Performance" in sent_text or "performance" in sent_text.lower()

    def test_unknown_agent_command(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message") as mock_send:
            resp = _post_update("FOOBAR")

        assert resp.status_code == 200
        sent_text = mock_send.call_args[0][1]
        assert "HELP" in sent_text

    def test_post_command_creates_listing(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message"), \
             patch("app.services.social_media.post_listing_to_all_platforms", return_value={}):
            resp = _post_update("POST 3-bed house in Sydney")

        assert resp.status_code == 200

        db = TestingSessionLocal()
        from app.models.listing import Listing
        listing = db.query(Listing).first()
        db.close()
        assert listing is not None
        assert "3-bed house" in listing.description

    def test_lead_message_from_unknown_number(self):
        with patch("app.services.lead_qualifier.qualify_lead", return_value={
            "is_serious": False,
            "qualification_score": 20,
            "reasoning": "just browsing",
            "lead_type": "unknown",
            "urgency": "just_browsing",
            "recommended_action": "nurture",
        }), patch("app.services.lead_qualifier.get_auto_reply", return_value="Thanks!"), \
             patch("app.api.telegram.send_telegram_message"):
            resp = _post_update("I want to buy a house", chat_id="999888777")

        assert resp.status_code == 200

    def test_missing_chat_id_returns_ok(self):
        """Empty update (no message) should return ok without crashing."""
        resp = client.post("/webhook/telegram", json={"update_id": 1})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_webhook_returns_json(self):
        db = TestingSessionLocal()
        _make_agent(db)
        db.close()

        with patch("app.api.telegram.send_telegram_message"):
            resp = _post_update("HELP")

        assert "application/json" in resp.headers.get("content-type", "")
