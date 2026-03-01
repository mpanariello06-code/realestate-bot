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
        # The reply must contain the numeric chat ID
        self.assertIn("987654321", reply_text)

    async def test_myid_accessible_without_agent_auth(self):
        """
        /myid must work even when the caller is NOT in AGENT_CHAT_IDS,
        so they can discover their ID before being added to the allow-list.
        """
        from bot.telegram_bot import cmd_myid
        # Use a chat ID that is NOT in the configured AGENT_CHAT_IDS ("123")
        update = _make_update(chat_id=999999999)
        context = MagicMock()

        await cmd_myid(update, context)

        # Should still reply (no auth check)
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
        # Chat ID 999 is not in AGENT_CHAT_IDS (which is "123")
        update = _make_update(chat_id=999)
        context = MagicMock()

        result = await _agent_only(update, context)

        self.assertFalse(result)
        reply_text = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("/myid", reply_text)


if __name__ == "__main__":
    unittest.main()
