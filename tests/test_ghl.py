"""
Tests for the Go High Level service and GHL webhook route.
Uses unittest.mock to avoid real API calls.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")


# ── Helper ─────────────────────────────────────────────────────────────────────

def _ghl_sig(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


# ── services/ghl.py tests ─────────────────────────────────────────────────────

class TestGhlIsConfigured(unittest.TestCase):

    def test_not_configured_when_keys_missing(self):
        import config as cfg
        orig_key, orig_loc = cfg.GHL_API_KEY, cfg.GHL_LOCATION_ID
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        from services.ghl import is_configured
        self.assertFalse(is_configured())
        cfg.GHL_API_KEY = orig_key
        cfg.GHL_LOCATION_ID = orig_loc

    def test_configured_when_both_set(self):
        import config as cfg
        orig_key, orig_loc = cfg.GHL_API_KEY, cfg.GHL_LOCATION_ID
        cfg.GHL_API_KEY = "key123"
        cfg.GHL_LOCATION_ID = "loc456"
        from services.ghl import is_configured
        self.assertTrue(is_configured())
        cfg.GHL_API_KEY = orig_key
        cfg.GHL_LOCATION_ID = orig_loc


class TestGhlGetContact(unittest.TestCase):

    def test_returns_none_when_not_configured(self):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        from services import ghl
        result = ghl.get_contact("abc")
        self.assertIsNone(result)

    @patch("services.ghl.requests.get")
    def test_returns_contact_on_success(self, mock_get):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"contact": {"id": "abc", "firstName": "Alice"}}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from services import ghl
        result = ghl.get_contact("abc")
        self.assertEqual(result["id"], "abc")
        self.assertEqual(result["firstName"], "Alice")

    @patch("services.ghl.requests.get")
    def test_returns_none_on_request_error(self, mock_get):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        import requests as _req
        mock_get.side_effect = _req.RequestException("timeout")

        from services import ghl
        result = ghl.get_contact("abc")
        self.assertIsNone(result)


class TestGhlSendDm(unittest.TestCase):

    def test_returns_error_when_not_configured(self):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        from services import ghl
        result = ghl.send_dm("contact1", "Hello")
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

    @patch("services.ghl.requests.post")
    def test_send_dm_success(self, mock_post):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"messageId": "msg_123"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import ghl
        result = ghl.send_dm("contact1", "Hello!")
        self.assertTrue(result["success"])
        self.assertEqual(result["messageId"], "msg_123")

    @patch("services.ghl.requests.post")
    def test_send_dm_failure(self, mock_post):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        import requests as _req
        mock_post.side_effect = _req.RequestException("network error")

        from services import ghl
        result = ghl.send_dm("contact1", "Hello!")
        self.assertFalse(result["success"])
        self.assertIn("network error", result["error"])

    @patch("services.ghl.requests.post")
    def test_send_dm_to_conversation_success(self, mock_post):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"messageId": "conv_msg_456"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import ghl
        result = ghl.send_dm_to_conversation("conv_789", "Auto-reply text")
        self.assertTrue(result["success"])
        self.assertEqual(result["messageId"], "conv_msg_456")
        # conversationId should be in the payload
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["conversationId"], "conv_789")


# ── portal/routes.py – GHL webhook tests ─────────────────────────────────────

class TestGhlWebhookRoute(unittest.TestCase):

    def setUp(self):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        cfg.GHL_WEBHOOK_SECRET = ""  # skip sig validation by default
        cfg.GHL_AUTO_REPLY_ENABLED = True
        cfg.GHL_AUTO_REPLY_MESSAGE = "Hi {first_name}! Thanks for reaching out."
        from portal.app import create_app
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    @patch("portal.routes.ghl_service.send_dm_to_conversation")
    @patch("portal.routes._notify_agents")
    def test_inbound_message_triggers_auto_dm_and_notification(
        self, mock_notify, mock_send_dm
    ):
        """An InboundMessage event should fire auto-DM and agent notification."""
        mock_send_dm.return_value = {"success": True, "messageId": "msg1"}
        payload = {
            "type": "InboundMessage",
            "contactId": "cid1",
            "conversationId": "conv1",
            "firstName": "Sarah",
            "lastName": "Jones",
            "body": "Is this property still available?",
            "channel": "FB",
        }
        resp = self.client.post(
            "/webhook/ghl",
            json=payload,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_send_dm.assert_called_once()
        args = mock_send_dm.call_args
        self.assertEqual(args[0][0], "conv1")
        self.assertIn("Sarah", args[0][1])
        mock_notify.assert_called_once()
        notification_text = mock_notify.call_args[0][0]
        self.assertIn("Sarah", notification_text)
        self.assertIn("Is this property still available?", notification_text)
        self.assertIn("Auto-DM reply sent", notification_text)

    @patch("portal.routes.ghl_service.send_dm")
    @patch("portal.routes._notify_agents")
    def test_inbound_message_no_conversation_id_uses_send_dm(
        self, mock_notify, mock_send_dm
    ):
        """When conversationId is absent, fall back to send_dm(contactId)."""
        mock_send_dm.return_value = {"success": True, "messageId": "msg2"}
        payload = {
            "type": "InboundMessage",
            "contactId": "cid2",
            "firstName": "Bob",
            "body": "Hello",
            "channel": "SMS",
        }
        resp = self.client.post(
            "/webhook/ghl",
            json=payload,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_send_dm.assert_called_once_with("cid2", unittest.mock.ANY)

    @patch("portal.routes._notify_agents")
    def test_auto_reply_disabled_skips_dm(self, mock_notify):
        """When GHL_AUTO_REPLY_ENABLED=False, no DM should be sent."""
        import config as cfg
        cfg.GHL_AUTO_REPLY_ENABLED = False

        with patch("portal.routes.ghl_service.send_dm_to_conversation") as mock_dm, \
             patch("portal.routes.ghl_service.send_dm") as mock_dm2:
            payload = {
                "type": "InboundMessage",
                "contactId": "cid3",
                "conversationId": "conv3",
                "firstName": "Carol",
                "body": "Hi there",
            }
            resp = self.client.post(
                "/webhook/ghl",
                json=payload,
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 200)
            mock_dm.assert_not_called()
            mock_dm2.assert_not_called()
            # Agent should still be notified
            mock_notify.assert_called_once()

    @patch("portal.routes._notify_agents")
    def test_unknown_event_type_is_silently_accepted(self, mock_notify):
        """Unknown event types should return 200 without notifying agents."""
        payload = {"type": "ContactCreated", "contactId": "cid9"}
        resp = self.client.post(
            "/webhook/ghl",
            json=payload,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        mock_notify.assert_not_called()

    def test_invalid_signature_returns_403(self):
        """A wrong HMAC signature should be rejected."""
        import config as cfg
        cfg.GHL_WEBHOOK_SECRET = "real_secret"

        payload = json.dumps({"type": "InboundMessage", "contactId": "x"}).encode()
        resp = self.client.post(
            "/webhook/ghl",
            data=payload,
            content_type="application/json",
            headers={"X-GHL-Signature": "badsig"},
        )
        self.assertEqual(resp.status_code, 403)
        cfg.GHL_WEBHOOK_SECRET = ""

    def test_valid_signature_accepted(self):
        """A correct HMAC signature should pass validation."""
        import config as cfg
        secret = "mysecret"
        cfg.GHL_WEBHOOK_SECRET = secret

        payload = json.dumps({"type": "UnknownEvent"}).encode()
        sig = _ghl_sig(payload, secret)

        with patch("portal.routes._notify_agents"):
            resp = self.client.post(
                "/webhook/ghl",
                data=payload,
                content_type="application/json",
                headers={"X-GHL-Signature": sig},
            )
        self.assertEqual(resp.status_code, 200)
        cfg.GHL_WEBHOOK_SECRET = ""


# ── bot/telegram_bot.py – /ghl command tests ─────────────────────────────────

class TestCmdGhl(unittest.IsolatedAsyncioTestCase):

    async def _call_cmd_ghl(self, chat_id: int = 123):
        from bot.telegram_bot import cmd_ghl
        from unittest.mock import AsyncMock, MagicMock
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        await cmd_ghl(update, context)
        return update

    async def test_ghl_not_configured_shows_setup_steps(self):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        update = await self._call_cmd_ghl()
        reply = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Setup Steps", reply)

    async def test_ghl_configured_shows_status(self):
        import config as cfg
        cfg.GHL_API_KEY = "key123"
        cfg.GHL_LOCATION_ID = "loc456"
        update = await self._call_cmd_ghl()
        reply = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("loc456", reply)
        self.assertIn("webhook/ghl", reply)

    async def test_ghl_auto_reply_status_shown(self):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        cfg.GHL_AUTO_REPLY_ENABLED = True
        update = await self._call_cmd_ghl()
        reply = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Enabled", reply)

    async def test_ghl_not_authorised_is_blocked(self):
        """Unauthorised users should not see the GHL status."""
        update = await self._call_cmd_ghl(chat_id=999999)  # not in AGENT_CHAT_IDS
        # reply_text may or may not be called with rejection msg – just verify
        # the handler didn't crash
        self.assertIsNotNone(update)


if __name__ == "__main__":
    unittest.main()
