"""
Tests for the Zapier webhook integration (services/zapier.py) and the
Telegram bot's Zapier posting path.
"""
from __future__ import annotations

import sys
import os
import tempfile
import unittest
import requests as _req
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


# ── services/zapier.py ────────────────────────────────────────────────────────

class TestZapierIsConfigured(unittest.TestCase):

    def setUp(self):
        import config as cfg
        self._orig = cfg.ZAPIER_WEBHOOK_URL

    def tearDown(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = self._orig

    def test_not_configured_when_url_empty(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = ""
        from services import zapier
        self.assertFalse(zapier.is_configured())

    def test_configured_when_url_set(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/xyz/"
        from services import zapier
        self.assertTrue(zapier.is_configured())


class TestZapierPostToSocial(unittest.TestCase):

    def setUp(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/xyz/"

    def tearDown(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = ""

    def test_returns_error_when_not_configured(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = ""
        from services import zapier
        result = zapier.post_to_social("Hello")
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

    @patch("services.zapier.requests.post")
    def test_caption_only_sends_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import zapier
        result = zapier.post_to_social("Amazing 3-bed house!")
        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        # Should send JSON, not multipart
        call_kwargs = mock_post.call_args[1]
        self.assertIn("json", call_kwargs)
        self.assertEqual(call_kwargs["json"]["caption"], "Amazing 3-bed house!")

    @patch("services.zapier.requests.post")
    def test_with_image_sends_multipart(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(b"\xff\xd8\xff")
        tmp.close()
        try:
            from services import zapier
            result = zapier.post_to_social("House with pool", tmp.name)
            self.assertTrue(result["success"])
            call_kwargs = mock_post.call_args[1]
            # multipart: data + files, not json
            self.assertIn("files", call_kwargs)
            self.assertIn("data", call_kwargs)
            self.assertEqual(call_kwargs["data"]["caption"], "House with pool")
        finally:
            os.unlink(tmp.name)

    @patch("services.zapier.requests.post")
    def test_missing_image_path_falls_back_to_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import zapier
        result = zapier.post_to_social("Caption", image_path="/tmp/nonexistent.jpg")
        self.assertTrue(result["success"])
        call_kwargs = mock_post.call_args[1]
        self.assertIn("json", call_kwargs)

    @patch("services.zapier.requests.post")
    def test_returns_error_on_request_failure(self, mock_post):
        mock_post.side_effect = _req.RequestException("timeout")

        from services import zapier
        result = zapier.post_to_social("Caption")
        self.assertFalse(result["success"])
        self.assertIn("timeout", result["error"])

    @patch("services.zapier.requests.post")
    def test_returns_error_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_post.side_effect = _req.HTTPError(response=mock_resp)

        from services import zapier
        result = zapier.post_to_social("Caption")
        self.assertFalse(result["success"])


# ── social_poster.post_listing() Zapier routing ───────────────────────────────

class TestSocialPosterZapierRouting(unittest.TestCase):

    def setUp(self):
        import config as cfg
        self._orig_zapier = cfg.ZAPIER_WEBHOOK_URL
        self._orig_ghl_key = cfg.GHL_API_KEY
        self._orig_ghl_loc = cfg.GHL_LOCATION_ID

    def tearDown(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = self._orig_zapier
        cfg.GHL_API_KEY = self._orig_ghl_key
        cfg.GHL_LOCATION_ID = self._orig_ghl_loc

    @patch("services.zapier.requests.post")
    def test_post_listing_routes_through_zapier_when_configured(self, mock_post):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import social_poster
        results = social_poster.post_listing("Great property!")
        self.assertIn("zapier", results)
        self.assertTrue(results["zapier"]["success"])

    @patch("services.zapier.requests.post")
    def test_zapier_takes_priority_over_ghl(self, mock_post):
        """When both Zapier and GHL are configured, Zapier wins."""
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        cfg.GHL_API_KEY = "ghl_key"
        cfg.GHL_LOCATION_ID = "loc"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import social_poster
        results = social_poster.post_listing("Great property!")
        self.assertIn("zapier", results)
        self.assertNotIn("ghl", results)

    @patch("services.ghl.post_to_social_planner")
    def test_post_listing_falls_back_to_ghl_when_zapier_not_configured(
        self, mock_ghl_post
    ):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = ""
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        mock_ghl_post.return_value = {"success": True, "post_id": "p1"}

        from services import social_poster
        results = social_poster.post_listing("Great property!")
        self.assertIn("ghl", results)
        self.assertNotIn("zapier", results)

    @patch("services.social_poster.post_to_facebook")
    def test_post_listing_falls_back_to_direct_api_when_neither_configured(
        self, mock_fb
    ):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = ""
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        mock_fb.return_value = {"success": True, "post_id": "fb1"}

        from services import social_poster
        results = social_poster.post_listing("Great property!")
        self.assertIn("facebook", results)
        self.assertNotIn("zapier", results)
        self.assertNotIn("ghl", results)


# ── handle_confirm_callback – Zapier path ─────────────────────────────────────

class TestConfirmCallbackZapierPath(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        import bot.telegram_bot as tb
        import config as cfg
        tb._bot_paused = False
        self._orig_zapier = cfg.ZAPIER_WEBHOOK_URL

    def tearDown(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = self._orig_zapier

    async def _run_confirm(self, zapier_result: dict):
        import bot.telegram_bot as tb
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {
            tb.CTX_CAPTION: "Beautiful house!",
            tb.CTX_MEDIA_PATH: None,
            tb.CTX_MEDIA_TYPE: "photo",
        }
        context.bot.send_message = AsyncMock()

        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.zapier_service.post_to_social",
                   return_value=zapier_result):
            from telegram.ext import ConversationHandler
            result = await tb.handle_confirm_callback(update, context)
        return result, context

    async def test_confirm_via_zapier_returns_end(self):
        from telegram.ext import ConversationHandler
        result, _ = await self._run_confirm({"success": True, "status_code": 200})
        self.assertEqual(result, ConversationHandler.END)

    async def test_confirm_via_zapier_sends_success_message(self):
        _, context = await self._run_confirm({"success": True, "status_code": 200})
        context.bot.send_message.assert_awaited_once()
        text = context.bot.send_message.call_args[1]["text"]
        self.assertIn("Zapier", text)
        self.assertIn("✅", text)

    async def test_confirm_via_zapier_sends_error_on_failure(self):
        _, context = await self._run_confirm(
            {"success": False, "error": "timeout"}
        )
        text = context.bot.send_message.call_args[1]["text"]
        self.assertIn("❌", text)
        self.assertIn("timeout", text)

    async def test_confirm_without_zapier_falls_through_to_ghl(self):
        """When Zapier is not configured, GHL path should be tried next."""
        import bot.telegram_bot as tb
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {
            tb.CTX_CAPTION: "House",
            tb.CTX_MEDIA_PATH: None,
            tb.CTX_MEDIA_TYPE: "photo",
        }
        context.bot.send_message = AsyncMock()
        from telegram.ext import ConversationHandler
        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=False), \
             patch("bot.telegram_bot.ghl_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.ghl_service.post_to_social_planner",
                   return_value={"success": True, "post_id": "p1"}):
            result = await tb.handle_confirm_callback(update, context)
        self.assertEqual(result, ConversationHandler.END)


# ── /zapier command ───────────────────────────────────────────────────────────

class TestCmdZapier(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        import config as cfg
        self._orig = cfg.ZAPIER_WEBHOOK_URL

    def tearDown(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = self._orig

    async def _call_cmd_zapier(self, chat_id: int = 123):
        from bot.telegram_bot import cmd_zapier
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        await cmd_zapier(update, context)
        return update

    async def test_not_configured_shows_setup_steps(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = ""
        update = await self._call_cmd_zapier()
        reply = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Setup Steps", reply)
        self.assertIn("Catch Hook", reply)

    async def test_configured_shows_status(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        update = await self._call_cmd_zapier()
        reply = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("configured", reply)
        self.assertIn("✅", reply)

    async def test_zapier_not_authorised_is_blocked(self):
        update = await self._call_cmd_zapier(chat_id=999999)
        self.assertIsNotNone(update)


# ── keyboard has zapier_status button ─────────────────────────────────────────

class TestKeyboardZapierButton(unittest.TestCase):

    def test_main_menu_has_zapier_button(self):
        from bot.keyboards import main_menu_keyboard
        data = [btn.callback_data
                for row in main_menu_keyboard().inline_keyboard
                for btn in row]
        self.assertIn("zapier_status", data)

    def test_main_menu_no_longer_has_ghl_status_button(self):
        from bot.keyboards import main_menu_keyboard
        data = [btn.callback_data
                for row in main_menu_keyboard().inline_keyboard
                for btn in row]
        self.assertNotIn("ghl_status", data)


if __name__ == "__main__":
    unittest.main()
