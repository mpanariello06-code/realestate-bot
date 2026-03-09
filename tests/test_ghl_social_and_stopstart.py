"""
Tests for:
  1. GHL Social Planner posting (upload_media, get_social_accounts,
     post_to_social_planner)
  2. social_poster.post_listing() routing through GHL
  3. Stop Bot / Start Bot buttons and _agent_only pause guard
  4. handle_confirm_callback GHL direct-post path
  5. keyboards: start_bot_keyboard and Stop Bot button in main menu
"""
from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


def _make_update(chat_id: int = 123) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_message.reply_text = AsyncMock()
    return update


def _make_callback_update(callback_data: str, chat_id: int = 123) -> MagicMock:
    update = _make_update(chat_id)
    query = AsyncMock()
    query.data = callback_data
    update.callback_query = query
    return update


# ── GHL Social Planner – service layer ───────────────────────────────────────

class TestGhlSocialPlanner(unittest.TestCase):

    def setUp(self):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        cfg.GHL_SOCIAL_ACCOUNT_IDS = ""

    def tearDown(self):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        cfg.GHL_SOCIAL_ACCOUNT_IDS = ""

    def test_post_to_social_planner_returns_error_when_not_configured(self):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        from services import ghl
        result = ghl.post_to_social_planner("Hello world")
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

    @patch("services.ghl.get_social_accounts")
    @patch("services.ghl.requests.post")
    def test_post_to_social_planner_success(self, mock_post, mock_accounts):
        mock_accounts.return_value = [
            {"accountId": "fb1", "type": "facebook"},
            {"accountId": "ig1", "type": "instagram"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "post_abc123"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import ghl
        result = ghl.post_to_social_planner("Amazing 3-bed house!")
        self.assertTrue(result["success"])
        self.assertEqual(result["post_id"], "post_abc123")

    @patch("services.ghl.get_social_accounts")
    @patch("services.ghl.requests.post")
    def test_post_includes_accounts_from_api(self, mock_post, mock_accounts):
        """When GHL_SOCIAL_ACCOUNT_IDS is blank, discovered accounts are used."""
        mock_accounts.return_value = [
            {"accountId": "fb_id", "type": "facebook"},
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "pid"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import ghl
        ghl.post_to_social_planner("Caption")
        payload = mock_post.call_args[1]["json"]
        self.assertIn("accounts", payload)
        self.assertEqual(payload["accounts"][0]["accountId"], "fb_id")

    @patch("services.ghl.get_social_accounts")
    @patch("services.ghl.requests.post")
    def test_post_uses_configured_account_ids_when_set(self, mock_post, mock_accounts):
        """When GHL_SOCIAL_ACCOUNT_IDS is set, those IDs are used directly."""
        import config as cfg
        cfg.GHL_SOCIAL_ACCOUNT_IDS = "fb:myaccount1,ig:myaccount2"
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "pid2"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import ghl
        ghl.post_to_social_planner("Caption")
        mock_accounts.assert_not_called()  # should not call API when IDs are configured
        payload = mock_post.call_args[1]["json"]
        account_map = {a["accountId"]: a["type"] for a in payload["accounts"]}
        self.assertEqual(account_map.get("myaccount1"), "facebook")
        self.assertEqual(account_map.get("myaccount2"), "instagram")

    @patch("services.ghl.get_social_accounts")
    @patch("services.ghl.requests.post")
    def test_post_to_social_planner_failure(self, mock_post, mock_accounts):
        mock_accounts.return_value = []
        import requests as _req
        mock_post.side_effect = _req.RequestException("timeout")

        from services import ghl
        result = ghl.post_to_social_planner("caption")
        self.assertFalse(result["success"])
        self.assertIn("timeout", result["error"])

    @patch("services.ghl.requests.get")
    def test_get_social_accounts_returns_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "accounts": [
                {"accountId": "fb1", "type": "facebook"},
                {"accountId": "ig1", "type": "instagram"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        from services import ghl
        accounts = ghl.get_social_accounts()
        self.assertEqual(len(accounts), 2)
        self.assertEqual(accounts[0]["type"], "facebook")

    @patch("services.ghl.requests.get")
    def test_get_social_accounts_returns_empty_on_error(self, mock_get):
        import requests as _req
        mock_get.side_effect = _req.RequestException("err")

        from services import ghl
        accounts = ghl.get_social_accounts()
        self.assertEqual(accounts, [])

    def test_get_social_accounts_returns_empty_when_not_configured(self):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        from services import ghl
        self.assertEqual(ghl.get_social_accounts(), [])

    @patch("services.ghl.requests.post")
    def test_upload_media_returns_url_on_success(self, mock_post):
        import tempfile, os as _os
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"url": "https://cdn.ghl.com/img.jpg"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(b"\xff\xd8\xff")
        tmp.close()
        try:
            from services import ghl
            url = ghl.upload_media(tmp.name)
            self.assertEqual(url, "https://cdn.ghl.com/img.jpg")
        finally:
            _os.unlink(tmp.name)

    def test_upload_media_returns_none_when_not_configured(self):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        from services import ghl
        self.assertIsNone(ghl.upload_media("/tmp/fake.jpg"))


# ── social_poster.post_listing() routing ─────────────────────────────────────

class TestSocialPosterGhlRouting(unittest.TestCase):

    def setUp(self):
        import config as cfg
        self._orig_key = cfg.GHL_API_KEY
        self._orig_loc = cfg.GHL_LOCATION_ID

    def tearDown(self):
        import config as cfg
        cfg.GHL_API_KEY = self._orig_key
        cfg.GHL_LOCATION_ID = self._orig_loc

    @patch("services.ghl.post_to_social_planner")
    def test_post_listing_routes_through_ghl_when_configured(self, mock_ghl_post):
        import config as cfg
        cfg.GHL_API_KEY = "key"
        cfg.GHL_LOCATION_ID = "loc"
        mock_ghl_post.return_value = {"success": True, "post_id": "p1"}

        from services import social_poster
        results = social_poster.post_listing("Great property!")
        mock_ghl_post.assert_called_once()
        self.assertIn("ghl", results)
        self.assertTrue(results["ghl"]["success"])

    @patch("services.social_poster.post_to_facebook")
    def test_post_listing_falls_back_to_direct_api_when_ghl_not_configured(
        self, mock_fb
    ):
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""
        mock_fb.return_value = {"success": True, "post_id": "fb1"}

        from services import social_poster
        results = social_poster.post_listing("Great property!")
        mock_fb.assert_called_once()
        self.assertIn("facebook", results)


# ── LinkedIn social poster ────────────────────────────────────────────────────

class TestLinkedInSocialPoster(unittest.TestCase):

    def setUp(self):
        import config as cfg
        self._orig_token = cfg.LINKEDIN_ACCESS_TOKEN
        self._orig_urn = cfg.LINKEDIN_AUTHOR_URN

    def tearDown(self):
        import config as cfg
        cfg.LINKEDIN_ACCESS_TOKEN = self._orig_token
        cfg.LINKEDIN_AUTHOR_URN = self._orig_urn

    def test_returns_error_when_not_configured(self):
        import config as cfg
        cfg.LINKEDIN_ACCESS_TOKEN = ""
        cfg.LINKEDIN_AUTHOR_URN = ""
        from services.social_poster import post_to_linkedin
        result = post_to_linkedin("Hello!")
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

    @patch("services.social_poster.requests.post")
    def test_text_post_success(self, mock_post):
        import config as cfg
        cfg.LINKEDIN_ACCESS_TOKEN = "token"
        cfg.LINKEDIN_AUTHOR_URN = "urn:li:organization:123"

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"x-restli-id": "urn:li:share:99"}
        mock_post.return_value = mock_response

        from services.social_poster import post_to_linkedin
        result = post_to_linkedin("Amazing property!")
        self.assertTrue(result["success"])
        self.assertEqual(result["post_id"], "urn:li:share:99")

    @patch("services.social_poster.requests.post")
    def test_text_post_failure(self, mock_post):
        import config as cfg
        import requests as req
        cfg.LINKEDIN_ACCESS_TOKEN = "token"
        cfg.LINKEDIN_AUTHOR_URN = "urn:li:organization:123"

        mock_post.side_effect = req.RequestException("network error")

        from services.social_poster import post_to_linkedin
        result = post_to_linkedin("Caption")
        self.assertFalse(result["success"])
        self.assertIn("network error", result["error"])

    def test_post_listing_includes_linkedin_in_direct_api_fallback(self):
        """post_listing() direct-API fallback always calls post_to_linkedin."""
        import config as cfg
        cfg.GHL_API_KEY = ""
        cfg.GHL_LOCATION_ID = ""

        with patch("services.social_poster.zapier_service.is_configured",
                   return_value=False), \
             patch("services.social_poster.ghl_service.is_configured",
                   return_value=False), \
             patch("services.social_poster.post_to_facebook",
                   return_value={"success": True, "post_id": "fb1"}), \
             patch("services.social_poster.post_to_instagram",
                   return_value={"success": False, "error": "no url"}), \
             patch("services.social_poster.post_to_linkedin",
                   return_value={"success": True, "post_id": "li1"}) as mock_li:
            from services import social_poster
            results = social_poster.post_listing("Caption")

        mock_li.assert_called_once()
        self.assertIn("linkedin", results)


# ── Stop Bot / Start Bot ──────────────────────────────────────────────────────

class TestStopStartBot(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Reset pause state before each test
        import bot.telegram_bot as tb
        tb._bot_paused = False

    async def test_cmd_stop_bot_sets_paused_flag(self):
        import bot.telegram_bot as tb
        update = _make_update(chat_id=123)
        context = MagicMock()
        await tb.cmd_stop_bot(update, context)
        self.assertTrue(tb._bot_paused)

    async def test_cmd_stop_bot_shows_start_button(self):
        import bot.telegram_bot as tb
        update = _make_update(chat_id=123)
        context = MagicMock()
        await tb.cmd_stop_bot(update, context)
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Paused", reply_text)
        kwargs = update.effective_message.reply_text.call_args[1]
        from bot.keyboards import start_bot_keyboard
        self.assertEqual(
            kwargs["reply_markup"].inline_keyboard,
            start_bot_keyboard().inline_keyboard,
        )

    async def test_cmd_start_bot_clears_paused_flag(self):
        import bot.telegram_bot as tb
        tb._bot_paused = True
        update = _make_update(chat_id=123)
        context = MagicMock()
        await tb.cmd_start_bot(update, context)
        self.assertFalse(tb._bot_paused)

    async def test_cmd_start_bot_shows_main_menu(self):
        import bot.telegram_bot as tb
        tb._bot_paused = True
        update = _make_update(chat_id=123)
        context = MagicMock()
        await tb.cmd_start_bot(update, context)
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Running", reply_text)

    async def test_cmd_stop_bot_unauthorised_user_does_nothing(self):
        import bot.telegram_bot as tb
        tb._bot_paused = False
        update = _make_update(chat_id=9999)  # not in AGENT_CHAT_IDS
        context = MagicMock()
        await tb.cmd_stop_bot(update, context)
        # Unauthorised user: paused should remain False
        self.assertFalse(tb._bot_paused)
        update.effective_message.reply_text.assert_not_awaited()


class TestAgentOnlyPauseGuard(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        import bot.telegram_bot as tb
        tb._bot_paused = False

    async def test_agent_only_returns_false_when_paused(self):
        import bot.telegram_bot as tb
        tb._bot_paused = True
        update = _make_update(chat_id=123)
        context = MagicMock()
        result = await tb._agent_only(update, context)
        self.assertFalse(result)

    async def test_agent_only_sends_paused_message_with_start_button(self):
        import bot.telegram_bot as tb
        tb._bot_paused = True
        update = _make_update(chat_id=123)
        context = MagicMock()
        await tb._agent_only(update, context)
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("paused", reply_text.lower())
        kwargs = update.effective_message.reply_text.call_args[1]
        from bot.keyboards import start_bot_keyboard
        self.assertEqual(
            kwargs["reply_markup"].inline_keyboard,
            start_bot_keyboard().inline_keyboard,
        )

    async def test_agent_only_returns_true_when_running(self):
        import bot.telegram_bot as tb
        tb._bot_paused = False
        update = _make_update(chat_id=123)
        context = MagicMock()
        result = await tb._agent_only(update, context)
        self.assertTrue(result)


class TestMenuCallbackStopStart(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        import bot.telegram_bot as tb
        tb._bot_paused = False

    async def test_stop_bot_callback_sets_paused(self):
        import bot.telegram_bot as tb
        update = _make_callback_update("stop_bot", chat_id=123)
        context = MagicMock()
        await tb.handle_menu_callback(update, context)
        self.assertTrue(tb._bot_paused)
        update.callback_query.answer.assert_awaited()

    async def test_start_bot_callback_clears_paused(self):
        import bot.telegram_bot as tb
        tb._bot_paused = True
        update = _make_callback_update("start_bot", chat_id=123)
        context = MagicMock()
        await tb.handle_menu_callback(update, context)
        self.assertFalse(tb._bot_paused)

    async def test_start_bot_callback_works_while_paused(self):
        """start_bot must succeed even when the bot is currently paused."""
        import bot.telegram_bot as tb
        tb._bot_paused = True
        update = _make_callback_update("start_bot", chat_id=123)
        context = MagicMock()
        await tb.handle_menu_callback(update, context)
        # Bot should be un-paused now
        self.assertFalse(tb._bot_paused)

    async def test_other_callbacks_blocked_when_paused(self):
        import bot.telegram_bot as tb
        tb._bot_paused = True
        update = _make_callback_update("performance", chat_id=123)
        context = MagicMock()
        with patch("bot.telegram_bot.cmd_performance") as mock_perf:
            await tb.handle_menu_callback(update, context)
            mock_perf.assert_not_called()
        update.callback_query.answer.assert_awaited()


# ── handle_confirm_callback GHL direct-post path ─────────────────────────────

class TestConfirmCallbackGhlPath(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        import bot.telegram_bot as tb
        tb._bot_paused = False

    async def _run_confirm(self, ghl_configured: bool, ghl_result: dict):
        import bot.telegram_bot as tb
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {
            tb.CTX_CAPTION: "Amazing house!",
            tb.CTX_MEDIA_PATH: None,
            tb.CTX_MEDIA_TYPE: "photo",
        }
        context.bot.send_message = AsyncMock()

        with patch("bot.telegram_bot.ghl_service.is_configured",
                   return_value=ghl_configured), \
             patch("bot.telegram_bot.ghl_service.post_to_social_planner",
                   return_value=ghl_result):
            from telegram.ext import ConversationHandler
            result = await tb.handle_confirm_callback(update, context)
        return result, context

    async def test_confirm_via_ghl_returns_end(self):
        from telegram.ext import ConversationHandler
        result, _ = await self._run_confirm(
            True, {"success": True, "post_id": "p1"}
        )
        self.assertEqual(result, ConversationHandler.END)

    async def test_confirm_via_ghl_sends_success_message(self):
        _, context = await self._run_confirm(
            True, {"success": True, "post_id": "p1"}
        )
        context.bot.send_message.assert_awaited_once()
        text = context.bot.send_message.call_args[1]["text"]
        self.assertIn("GHL", text)
        self.assertIn("✅", text)

    async def test_confirm_via_ghl_sends_error_on_failure(self):
        _, context = await self._run_confirm(
            True, {"success": False, "error": "API down"}
        )
        text = context.bot.send_message.call_args[1]["text"]
        self.assertIn("❌", text)
        self.assertIn("API down", text)

    async def test_confirm_without_ghl_goes_to_platform_step(self):
        import bot.telegram_bot as tb
        from telegram.ext import ConversationHandler
        result, _ = await self._run_confirm(
            False, {}
        )
        self.assertEqual(result, tb.AWAITING_PLATFORM)


# ── keyboards.py ─────────────────────────────────────────────────────────────

class TestKeyboards(unittest.TestCase):

    def test_main_menu_has_stop_bot_button(self):
        from bot.keyboards import main_menu_keyboard
        data = [btn.callback_data
                for row in main_menu_keyboard().inline_keyboard
                for btn in row]
        self.assertIn("stop_bot", data)

    def test_start_bot_keyboard_has_start_button(self):
        from bot.keyboards import start_bot_keyboard
        data = [btn.callback_data
                for row in start_bot_keyboard().inline_keyboard
                for btn in row]
        self.assertIn("start_bot", data)

    def test_start_bot_keyboard_has_only_one_button(self):
        from bot.keyboards import start_bot_keyboard
        buttons = [btn for row in start_bot_keyboard().inline_keyboard for btn in row]
        self.assertEqual(len(buttons), 1)


# ── _on_startup ───────────────────────────────────────────────────────────────

class TestOnStartup(unittest.IsolatedAsyncioTestCase):

    async def test_startup_sends_welcome_to_each_agent(self):
        """_on_startup should send one message per configured agent chat ID."""
        import config as cfg
        orig_ids = cfg.AGENT_CHAT_IDS
        cfg.AGENT_CHAT_IDS = [111, 222]
        try:
            from bot.telegram_bot import _on_startup
            app = MagicMock()
            app.bot.set_my_commands = AsyncMock()
            app.bot.send_message = AsyncMock()
            await _on_startup(app)
            assert app.bot.send_message.await_count == 2
            chat_ids_called = [
                c.kwargs["chat_id"] for c in app.bot.send_message.await_args_list
            ]
            self.assertIn(111, chat_ids_called)
            self.assertIn(222, chat_ids_called)
        finally:
            cfg.AGENT_CHAT_IDS = orig_ids

    async def test_startup_registers_command_menu(self):
        """_on_startup should call set_my_commands with the bot command list."""
        import config as cfg
        orig_ids = cfg.AGENT_CHAT_IDS
        cfg.AGENT_CHAT_IDS = []
        try:
            from bot.telegram_bot import _on_startup, _BOT_COMMANDS
            app = MagicMock()
            app.bot.set_my_commands = AsyncMock()
            app.bot.send_message = AsyncMock()
            await _on_startup(app)
            app.bot.set_my_commands.assert_awaited_once_with(_BOT_COMMANDS)
        finally:
            cfg.AGENT_CHAT_IDS = orig_ids

    async def test_startup_welcome_contains_menu_keyboard(self):
        """The startup message must include the main menu inline keyboard."""
        import config as cfg
        orig_ids = cfg.AGENT_CHAT_IDS
        cfg.AGENT_CHAT_IDS = [555]
        try:
            from bot.telegram_bot import _on_startup
            from bot.keyboards import main_menu_keyboard
            app = MagicMock()
            app.bot.set_my_commands = AsyncMock()
            app.bot.send_message = AsyncMock()
            await _on_startup(app)
            kwargs = app.bot.send_message.await_args_list[0].kwargs
            self.assertEqual(
                kwargs["reply_markup"].inline_keyboard,
                main_menu_keyboard().inline_keyboard,
            )
        finally:
            cfg.AGENT_CHAT_IDS = orig_ids

    async def test_startup_skips_send_when_no_agent_ids(self):
        """If AGENT_CHAT_IDS is empty, no messages should be sent."""
        import config as cfg
        orig_ids = cfg.AGENT_CHAT_IDS
        cfg.AGENT_CHAT_IDS = []
        try:
            from bot.telegram_bot import _on_startup
            app = MagicMock()
            app.bot.set_my_commands = AsyncMock()
            app.bot.send_message = AsyncMock()
            await _on_startup(app)
            app.bot.send_message.assert_not_awaited()
        finally:
            cfg.AGENT_CHAT_IDS = orig_ids


if __name__ == "__main__":
    unittest.main()
