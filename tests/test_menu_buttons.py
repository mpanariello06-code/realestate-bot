"""
Tests for the expanded Telegram menu buttons and toast auto-replies.
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


# ── Keyboard layout tests ─────────────────────────────────────────────────────

class TestMainMenuKeyboard(unittest.TestCase):

    def _all_callback_data(self):
        from bot.keyboards import main_menu_keyboard
        kb = main_menu_keyboard()
        return [btn.callback_data for row in kb.inline_keyboard for btn in row]

    def test_post_listing_button_present(self):
        self.assertIn("post_listing", self._all_callback_data())

    def test_qualify_lead_button_present(self):
        self.assertIn("qualify_lead", self._all_callback_data())

    def test_zapier_status_button_present(self):
        self.assertIn("zapier_status", self._all_callback_data())

    def test_weekly_report_button_present(self):
        self.assertIn("weekly_report", self._all_callback_data())

    def test_performance_button_present(self):
        self.assertIn("performance", self._all_callback_data())

    def test_qualified_leads_button_present(self):
        self.assertIn("qualified_leads", self._all_callback_data())

    def test_all_leads_button_present(self):
        self.assertIn("all_leads", self._all_callback_data())

    def test_notes_info_button_present(self):
        self.assertIn("notes_info", self._all_callback_data())

    def test_help_button_present(self):
        self.assertIn("help", self._all_callback_data())

    def test_posting_platform_keyboard_has_facebook_and_instagram(self):
        from bot.keyboards import posting_platform_keyboard
        data = [btn.callback_data
                for row in posting_platform_keyboard().inline_keyboard
                for btn in row]
        self.assertIn("platform_facebook", data)
        self.assertIn("platform_instagram", data)
        self.assertIn("platform_all", data)
        self.assertNotIn("platform_linkedin", data)


# ── handle_menu_callback toast tests ─────────────────────────────────────────

def _make_callback_update(callback_data: str, chat_id: int = 123) -> MagicMock:
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_message.reply_text = AsyncMock()
    query = AsyncMock()
    query.data = callback_data
    update.callback_query = query
    return update


class TestMenuCallbackToasts(unittest.IsolatedAsyncioTestCase):
    """Every menu button must call query.answer(text=…) so the agent sees a toast."""

    async def _run_callback(self, callback_data: str):
        from bot.telegram_bot import handle_menu_callback
        update = _make_callback_update(callback_data)
        context = MagicMock()
        context.user_data = {}
        with patch("bot.telegram_bot.cmd_performance"), \
             patch("bot.telegram_bot.cmd_leads"), \
             patch("bot.telegram_bot.cmd_all_leads"), \
             patch("bot.telegram_bot.cmd_report"), \
             patch("bot.telegram_bot.cmd_ghl"), \
             patch("bot.telegram_bot.cmd_help"), \
             patch("bot.telegram_bot.cmd_qualify"), \
             patch("bot.telegram_bot._cmd_notes_info"):
            await handle_menu_callback(update, context)
        return update.callback_query.answer

    async def test_performance_toast(self):
        answer = await self._run_callback("performance")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertTrue(text)  # non-empty toast

    async def test_qualify_lead_toast(self):
        answer = await self._run_callback("qualify_lead")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertIn("🔍", text)

    async def test_ghl_status_toast(self):
        answer = await self._run_callback("ghl_status")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertIn("GHL", text)

    async def test_weekly_report_toast(self):
        answer = await self._run_callback("weekly_report")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertTrue(text)

    async def test_help_toast(self):
        answer = await self._run_callback("help")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertIn("❓", text)

    async def test_notes_info_toast(self):
        answer = await self._run_callback("notes_info")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertTrue(text)

    async def test_all_leads_toast(self):
        answer = await self._run_callback("all_leads")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertTrue(text)

    async def test_qualified_leads_toast(self):
        answer = await self._run_callback("qualified_leads")
        answer.assert_awaited_once()
        text = answer.call_args[0][0] if answer.call_args[0] else ""
        self.assertTrue(text)


# ── handle_menu_callback routing tests ───────────────────────────────────────

class TestMenuCallbackRouting(unittest.IsolatedAsyncioTestCase):
    """Each menu callback must route to the correct command handler."""

    async def _assert_routes_to(self, callback_data: str, expected_handler_name: str):
        from bot.telegram_bot import handle_menu_callback
        update = _make_callback_update(callback_data)
        context = MagicMock()
        context.user_data = {}

        handlers = {
            "cmd_performance": AsyncMock(),
            "cmd_leads": AsyncMock(),
            "cmd_all_leads": AsyncMock(),
            "cmd_report": AsyncMock(),
            "cmd_ghl": AsyncMock(),
            "cmd_help": AsyncMock(),
            "cmd_qualify": AsyncMock(),
            "_cmd_notes_info": AsyncMock(),
        }
        with patch("bot.telegram_bot.cmd_performance", handlers["cmd_performance"]), \
             patch("bot.telegram_bot.cmd_leads", handlers["cmd_leads"]), \
             patch("bot.telegram_bot.cmd_all_leads", handlers["cmd_all_leads"]), \
             patch("bot.telegram_bot.cmd_report", handlers["cmd_report"]), \
             patch("bot.telegram_bot.cmd_ghl", handlers["cmd_ghl"]), \
             patch("bot.telegram_bot.cmd_help", handlers["cmd_help"]), \
             patch("bot.telegram_bot.cmd_qualify", handlers["cmd_qualify"]), \
             patch("bot.telegram_bot._cmd_notes_info", handlers["_cmd_notes_info"]):
            await handle_menu_callback(update, context)

        handlers[expected_handler_name].assert_awaited_once()

    async def test_qualify_lead_routes_to_cmd_qualify(self):
        await self._assert_routes_to("qualify_lead", "cmd_qualify")

    async def test_ghl_status_routes_to_cmd_ghl(self):
        await self._assert_routes_to("ghl_status", "cmd_ghl")

    async def test_help_routes_to_cmd_help(self):
        await self._assert_routes_to("help", "cmd_help")

    async def test_notes_info_routes_to_notes_info(self):
        await self._assert_routes_to("notes_info", "_cmd_notes_info")

    async def test_performance_routes_to_cmd_performance(self):
        await self._assert_routes_to("performance", "cmd_performance")

    async def test_weekly_report_routes_to_cmd_report(self):
        await self._assert_routes_to("weekly_report", "cmd_report")


# ── confirm-post / platform-select toast tests ────────────────────────────────

class TestConfirmPostToasts(unittest.IsolatedAsyncioTestCase):

    async def test_cancel_toast(self):
        from bot.telegram_bot import handle_confirm_callback
        update = MagicMock()
        query = AsyncMock()
        query.data = "cancel"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {}
        await handle_confirm_callback(update, context)
        query.answer.assert_awaited_once()
        text = query.answer.call_args[0][0] if query.answer.call_args[0] else ""
        self.assertIn("Cancel", text)

    async def test_edit_caption_toast(self):
        from bot.telegram_bot import handle_confirm_callback
        update = MagicMock()
        query = AsyncMock()
        query.data = "edit_caption"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {}
        await handle_confirm_callback(update, context)
        text = query.answer.call_args[0][0] if query.answer.call_args[0] else ""
        self.assertIn("Edit", text)

    async def test_confirm_post_toast(self):
        from bot.telegram_bot import handle_confirm_callback
        update = MagicMock()
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {}
        await handle_confirm_callback(update, context)
        text = query.answer.call_args[0][0] if query.answer.call_args[0] else ""
        self.assertIn("platform", text.lower())


class TestPlatformCallbackToasts(unittest.IsolatedAsyncioTestCase):

    async def _platform_answer_text(self, platform_data: str) -> str:
        from bot.telegram_bot import handle_platform_callback
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = platform_data
        update.callback_query = query
        context = MagicMock()
        context.user_data = {}
        with patch("bot.telegram_bot.social_poster.post_to_facebook",
                   return_value={"success": True, "post_id": "123"}), \
             patch("bot.telegram_bot.social_poster.post_to_instagram",
                   return_value={"success": True, "post_id": "456"}), \
             patch("bot.telegram_bot.social_poster.post_listing",
                   return_value={"facebook": {"success": True, "post_id": "fb1"},
                                 "instagram": {"success": True, "post_id": "ig1"}}), \
             patch.object(context, "bot", AsyncMock()):
            context.bot.send_message = AsyncMock()
            await handle_platform_callback(update, context)
        return query.answer.call_args[0][0] if query.answer.call_args[0] else ""

    async def test_facebook_toast_contains_facebook(self):
        text = await self._platform_answer_text("platform_facebook")
        self.assertIn("Facebook", text)

    async def test_instagram_toast_contains_instagram(self):
        text = await self._platform_answer_text("platform_instagram")
        self.assertIn("Instagram", text)

    async def test_all_platforms_toast(self):
        text = await self._platform_answer_text("platform_all")
        self.assertIn("All", text)


# ── notes_info button reply test ──────────────────────────────────────────────

class TestNotesInfoButton(unittest.IsolatedAsyncioTestCase):

    async def test_notes_info_reply_contains_command_syntax(self):
        from bot.telegram_bot import _cmd_notes_info
        update = MagicMock()
        update.effective_chat.id = 123
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        await _cmd_notes_info(update, context)
        text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("/notes", text)
        self.assertIn("lead_number", text)

    async def test_notes_info_reply_includes_example(self):
        from bot.telegram_bot import _cmd_notes_info
        update = MagicMock()
        update.effective_chat.id = 123
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        await _cmd_notes_info(update, context)
        text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("viewing", text.lower())


if __name__ == "__main__":
    unittest.main()
