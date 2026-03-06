"""
Tests for Telegram bot command handlers.
Uses unittest.mock to avoid a real Telegram connection.
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


def _make_update(chat_id: int) -> MagicMock:
    """Build a minimal fake telegram.Update with the given chat_id."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_message.reply_text = AsyncMock()
    return update


class TestCmdMyid(unittest.IsolatedAsyncioTestCase):

    async def test_myid_replies_with_chat_id(self):
        from bot.telegram_bot import cmd_myid
        update = _make_update(chat_id=987654321)
        context = MagicMock()

        await cmd_myid(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("987654321", reply_text)

    async def test_myid_accessible_without_agent_auth(self):
        """
        /myid must work even when the caller is NOT in AGENT_CHAT_IDS,
        so they can discover their ID before being added to the allow-list.
        """
        from bot.telegram_bot import cmd_myid
        update = _make_update(chat_id=999999999)
        context = MagicMock()

        await cmd_myid(update, context)

        update.effective_message.reply_text.assert_awaited_once()

    async def test_myid_reply_contains_env_instructions(self):
        from bot.telegram_bot import cmd_myid
        update = _make_update(chat_id=111222333)
        context = MagicMock()

        await cmd_myid(update, context)

        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("AGENT_CHAT_IDS", reply_text)


class TestAgentOnlyRejectionMessage(unittest.IsolatedAsyncioTestCase):

    async def test_rejection_mentions_myid(self):
        """Unauthorised users must be told to use /myid."""
        from bot.telegram_bot import _agent_only
        update = _make_update(chat_id=999)
        context = MagicMock()

        result = await _agent_only(update, context)

        self.assertFalse(result)
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("/myid", reply_text)


class TestCmdQualify(unittest.IsolatedAsyncioTestCase):

    async def test_qualify_command_prompts_for_message(self):
        from bot.telegram_bot import cmd_qualify, AWAITING_QUALIFY_MESSAGE
        update = _make_update(chat_id=123)
        context = MagicMock()

        result = await cmd_qualify(update, context)

        update.effective_message.reply_text.assert_awaited_once()
        self.assertEqual(result, AWAITING_QUALIFY_MESSAGE)

    @patch("bot.telegram_bot.lead_qualifier.qualify_lead")
    async def test_qualify_message_shows_score_and_questions(self, mock_qualify):
        from bot.telegram_bot import handle_qualify_message, AWAITING_QUALIFY_SAVE
        mock_qualify.return_value = {
            "score": 82,
            "intent": "buy",
            "budget": "$600k",
            "timeline": "2 months",
            "location": "Austin",
            "is_qualified": True,
            "summary": "Serious buyer in Austin.",
            "follow_up_questions": ["What is your pre-approval status?"],
        }
        update = _make_update(chat_id=123)
        update.effective_message.text = "I want to buy in Austin for $600k in 2 months"
        context = MagicMock()
        context.user_data = {}

        result = await handle_qualify_message(update, context)

        self.assertEqual(result, AWAITING_QUALIFY_SAVE)
        # reply_text is called twice: "Analysing…" then the full result
        calls = update.effective_message.reply_text.call_args_list
        result_text = calls[-1][0][0]
        self.assertIn("82", result_text)
        self.assertIn("Austin", result_text)
        self.assertIn("pre-approval", result_text)

    @patch("bot.telegram_bot.lead_qualifier.qualify_lead")
    async def test_qualify_stores_result_in_user_data(self, mock_qualify):
        from bot.telegram_bot import handle_qualify_message, CTX_QUALIFY_RESULT
        mock_qualify.return_value = {
            "score": 70,
            "intent": "rent",
            "budget": None,
            "timeline": None,
            "location": None,
            "is_qualified": True,
            "summary": "Wants to rent.",
            "follow_up_questions": [],
        }
        update = _make_update(chat_id=123)
        update.effective_message.text = "Looking to rent a 1-bed"
        context = MagicMock()
        context.user_data = {}

        await handle_qualify_message(update, context)

        self.assertIn(CTX_QUALIFY_RESULT, context.user_data)
        self.assertEqual(context.user_data[CTX_QUALIFY_RESULT]["score"], 70)

    @patch("bot.telegram_bot.sheets.save_lead")
    async def test_qualify_save_callback_saves_lead(self, mock_save):
        from bot.telegram_bot import handle_qualify_save_callback, CTX_QUALIFY_RESULT
        mock_save.return_value = True
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "qualify_save"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {
            CTX_QUALIFY_RESULT: {"score": 80, "intent": "buy", "summary": "x"}
        }

        from telegram.ext import ConversationHandler
        result = await handle_qualify_save_callback(update, context)

        mock_save.assert_called_once()
        saved_lead = mock_save.call_args[0][0]
        self.assertEqual(saved_lead["platform"], "telegram")
        self.assertEqual(result, ConversationHandler.END)

    async def test_qualify_discard_callback_clears_user_data(self):
        from bot.telegram_bot import handle_qualify_save_callback, CTX_QUALIFY_RESULT
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "qualify_discard"
        update.callback_query = query
        context = MagicMock()
        context.user_data = {CTX_QUALIFY_RESULT: {"score": 50}}

        from telegram.ext import ConversationHandler
        result = await handle_qualify_save_callback(update, context)

        self.assertNotIn(CTX_QUALIFY_RESULT, context.user_data)
        self.assertEqual(result, ConversationHandler.END)


class TestFormatQualifyResult(unittest.TestCase):

    def test_qualified_shows_green_indicator(self):
        from bot.telegram_bot import _format_qualify_result
        result = {
            "score": 80,
            "intent": "buy",
            "budget": "$500k",
            "timeline": "3 months",
            "location": "Miami",
            "summary": "Serious buyer.",
            "follow_up_questions": ["Budget confirmed?"],
        }
        text = _format_qualify_result(result)
        self.assertIn("🟢", text)
        self.assertIn("80", text)
        self.assertIn("Miami", text)
        self.assertIn("Budget confirmed?", text)

    def test_borderline_shows_yellow_indicator(self):
        from bot.telegram_bot import _format_qualify_result
        result = {
            "score": 40,
            "intent": "unknown",
            "budget": None,
            "timeline": None,
            "location": None,
            "summary": "Vague enquiry.",
            "follow_up_questions": [],
        }
        text = _format_qualify_result(result)
        self.assertIn("🟡", text)

    def test_not_qualified_shows_red_indicator(self):
        from bot.telegram_bot import _format_qualify_result
        result = {
            "score": 10,
            "intent": "unknown",
            "budget": None,
            "timeline": None,
            "location": None,
            "summary": "Spam.",
            "follow_up_questions": [],
        }
        text = _format_qualify_result(result)
        self.assertIn("🔴", text)

    def test_missing_optional_fields_shows_not_mentioned(self):
        from bot.telegram_bot import _format_qualify_result
        result = {
            "score": 65,
            "intent": "sell",
            "budget": None,
            "timeline": None,
            "location": None,
            "summary": "Wants to sell.",
            "follow_up_questions": [],
        }
        text = _format_qualify_result(result)
        self.assertIn("Not mentioned", text)


class TestCmdNotes(unittest.IsolatedAsyncioTestCase):

    @patch("bot.telegram_bot.sheets.save_lead_notes")
    async def test_notes_saved_successfully(self, mock_save):
        from bot.telegram_bot import cmd_notes
        mock_save.return_value = True
        update = _make_update(chat_id=123)
        context = MagicMock()
        context.args = ["3", "Called", "back", "viewing", "Saturday"]

        await cmd_notes(update, context)

        mock_save.assert_called_once_with(3, "Called back viewing Saturday")
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("3", reply_text)
        self.assertIn("✅", reply_text)

    @patch("bot.telegram_bot.sheets.save_lead_notes")
    async def test_notes_failure_shows_error(self, mock_save):
        from bot.telegram_bot import cmd_notes
        mock_save.return_value = False
        update = _make_update(chat_id=123)
        context = MagicMock()
        context.args = ["5", "Left", "voicemail"]

        await cmd_notes(update, context)

        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("❌", reply_text)

    async def test_notes_no_args_shows_usage(self):
        from bot.telegram_bot import cmd_notes
        update = _make_update(chat_id=123)
        context = MagicMock()
        context.args = []

        await cmd_notes(update, context)

        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Usage", reply_text)

    async def test_notes_non_numeric_lead_number_shows_usage(self):
        from bot.telegram_bot import cmd_notes
        update = _make_update(chat_id=123)
        context = MagicMock()
        context.args = ["abc", "some note"]

        await cmd_notes(update, context)

        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Usage", reply_text)


# ── handle_media: direct photo upload (no /post required) ─────────────────────

class TestHandleMediaDirectUpload(unittest.IsolatedAsyncioTestCase):
    """
    Verify that an authorised agent can send a photo/video directly (without
    first running /post) and receive the "✅ Media received!" confirmation.
    """

    def _make_photo_update(self, chat_id: int = 123):
        """Build a fake Update that looks like an incoming photo message."""
        photo_size = MagicMock()
        photo_size.get_file = AsyncMock(
            return_value=MagicMock(
                download_to_drive=AsyncMock()
            )
        )
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_message.photo = [photo_size]
        update.effective_message.video = None
        update.effective_message.reply_text = AsyncMock()
        return update

    async def test_photo_sent_directly_replies_media_received(self):
        """Agent sends photo outside /post flow – bot must confirm receipt."""
        from bot.telegram_bot import handle_media, AWAITING_DESCRIPTION
        import tempfile, os

        update = self._make_photo_update(chat_id=123)
        context = MagicMock()
        context.user_data = {}

        with patch("bot.telegram_bot.tempfile.NamedTemporaryFile",
                   return_value=MagicMock(name="/tmp/fake.jpg", __enter__=MagicMock(), __exit__=MagicMock())):
            result = await handle_media(update, context)

        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("Media received", reply_text)
        self.assertEqual(result, AWAITING_DESCRIPTION)

    async def test_photo_from_unauthorized_user_is_rejected(self):
        """Non-agent sending a photo must get the unauthorised message."""
        from bot.telegram_bot import handle_media
        from telegram.ext import ConversationHandler

        update = self._make_photo_update(chat_id=999999)
        context = MagicMock()
        context.user_data = {}

        result = await handle_media(update, context)

        # Should return END (not enter the conversation)
        self.assertEqual(result, ConversationHandler.END)
        # Should have told the user they are not authorised
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("not authorised", reply_text)

    async def test_media_type_stored_as_photo_in_user_data(self):
        """After receiving a photo, CTX_MEDIA_TYPE must be set to 'photo'."""
        from bot.telegram_bot import handle_media, CTX_MEDIA_TYPE

        update = self._make_photo_update(chat_id=123)
        context = MagicMock()
        context.user_data = {}

        with patch("bot.telegram_bot.tempfile.NamedTemporaryFile",
                   return_value=MagicMock(name="/tmp/fake.jpg", __enter__=MagicMock(), __exit__=MagicMock())):
            await handle_media(update, context)

        self.assertEqual(context.user_data.get(CTX_MEDIA_TYPE), "photo")

    async def test_post_conv_entry_points_include_photo_handler(self):
        """The ConversationHandler entry_points must contain a photo/video handler."""
        from bot.telegram_bot import build_application
        from telegram.ext import MessageHandler, ConversationHandler

        with patch("bot.telegram_bot.Application.builder") as mock_builder:
            mock_app = MagicMock()
            mock_builder.return_value.token.return_value.post_init.return_value.build.return_value = mock_app
            mock_app.add_handler = MagicMock()

            build_application()

        # Find the ConversationHandler that was added
        added_handlers = [
            call.args[0] for call in mock_app.add_handler.call_args_list
        ]
        conv_handlers = [h for h in added_handlers if isinstance(h, ConversationHandler)]
        self.assertTrue(conv_handlers, "No ConversationHandler was registered")

        # Check that the first ConversationHandler (post_conv) has a MessageHandler
        # entry point that handles photos/videos
        post_conv = conv_handlers[0]
        entry_msg_handlers = [
            ep for ep in post_conv.entry_points
            if isinstance(ep, MessageHandler)
        ]
        self.assertTrue(
            entry_msg_handlers,
            "post_conv must have a MessageHandler entry point for direct photo uploads"
        )


# ── handle_auto_reply ─────────────────────────────────────────────────────────

class TestHandleAutoReply(unittest.IsolatedAsyncioTestCase):
    """
    Verify that handle_auto_reply sends an AI-generated reply to any text
    message that isn't handled by an existing flow.
    """

    def _make_text_update(self, chat_id: int, text: str = "Hello!") -> MagicMock:
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_message.text = text
        update.effective_message.reply_text = AsyncMock()
        return update

    @patch("bot.telegram_bot.lead_qualifier.generate_auto_reply",
           return_value="Hi! An agent will contact you soon.")
    async def test_auto_reply_responds_to_non_agent(self, mock_reply):
        """Any user's text message must receive an AI reply."""
        from bot.telegram_bot import handle_auto_reply
        import bot.telegram_bot as tb

        tb._bot_paused = False
        update = self._make_text_update(chat_id=999999)
        context = MagicMock()

        with patch("bot.telegram_bot.config") as mock_cfg:
            mock_cfg.TELEGRAM_AUTO_REPLY_ENABLED = True
            mock_cfg.AGENT_CHAT_IDS = [123]
            await handle_auto_reply(update, context)

        update.effective_message.reply_text.assert_awaited_once_with(
            "Hi! An agent will contact you soon."
        )

    @patch("bot.telegram_bot.lead_qualifier.generate_auto_reply",
           return_value="Hi! An agent will contact you soon.")
    async def test_auto_reply_responds_to_agent_outside_flow(self, mock_reply):
        """Even an agent's unhandled text should get an auto-reply."""
        from bot.telegram_bot import handle_auto_reply
        import bot.telegram_bot as tb

        tb._bot_paused = False
        update = self._make_text_update(chat_id=123)
        context = MagicMock()

        with patch("bot.telegram_bot.config") as mock_cfg:
            mock_cfg.TELEGRAM_AUTO_REPLY_ENABLED = True
            mock_cfg.AGENT_CHAT_IDS = [123]
            await handle_auto_reply(update, context)

        update.effective_message.reply_text.assert_awaited_once()

    @patch("bot.telegram_bot.lead_qualifier.generate_auto_reply",
           return_value="Should not be sent")
    async def test_auto_reply_skips_when_disabled(self, mock_reply):
        """No reply sent when TELEGRAM_AUTO_REPLY_ENABLED is False."""
        from bot.telegram_bot import handle_auto_reply

        update = self._make_text_update(chat_id=999999)
        context = MagicMock()

        with patch("bot.telegram_bot.config") as mock_cfg:
            mock_cfg.TELEGRAM_AUTO_REPLY_ENABLED = False
            mock_cfg.AGENT_CHAT_IDS = [123]
            await handle_auto_reply(update, context)

        update.effective_message.reply_text.assert_not_called()

    @patch("bot.telegram_bot.lead_qualifier.generate_auto_reply",
           return_value="Should not be sent")
    async def test_auto_reply_skips_when_bot_paused(self, mock_reply):
        """No reply sent when the bot is paused."""
        from bot.telegram_bot import handle_auto_reply
        import bot.telegram_bot as tb

        tb._bot_paused = True
        update = self._make_text_update(chat_id=999999)
        context = MagicMock()

        with patch("bot.telegram_bot.config") as mock_cfg:
            mock_cfg.TELEGRAM_AUTO_REPLY_ENABLED = True
            mock_cfg.AGENT_CHAT_IDS = [123]
            await handle_auto_reply(update, context)

        update.effective_message.reply_text.assert_not_called()
        tb._bot_paused = False  # reset global state

    @patch("bot.telegram_bot.lead_qualifier.generate_auto_reply",
           return_value="Should not be sent")
    async def test_auto_reply_skips_empty_message(self, mock_reply):
        """No reply sent when the message text is empty/None."""
        from bot.telegram_bot import handle_auto_reply
        import bot.telegram_bot as tb

        tb._bot_paused = False
        update = self._make_text_update(chat_id=999999)
        update.effective_message.text = None
        context = MagicMock()

        with patch("bot.telegram_bot.config") as mock_cfg:
            mock_cfg.TELEGRAM_AUTO_REPLY_ENABLED = True
            mock_cfg.AGENT_CHAT_IDS = [123]
            await handle_auto_reply(update, context)

        update.effective_message.reply_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
