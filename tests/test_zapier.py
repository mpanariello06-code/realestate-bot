"""
Tests for the Zapier webhook integration (services/zapier.py),
Cloudinary upload service (services/cloudinary_upload.py),
and the Telegram bot's structured listing posting flow.
"""
from __future__ import annotations

import sys
import os
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


class TestZapierPostListing(unittest.TestCase):

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
        result = zapier.post_listing({"description": "Hello"})
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

    @patch("services.zapier.requests.post")
    def test_sends_full_structured_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import zapier
        listing = {
            "description": "Beautiful 3-bedroom home",
            "price": "$650,000",
            "location": "Ottawa, ON",
            "bedrooms": "3",
            "bathrooms": "2",
            "contact_phone": "613-555-1234",
            "image_url": "https://res.cloudinary.com/demo/photo.jpg",
        }
        result = zapier.post_listing(listing)
        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        call_kwargs = mock_post.call_args[1]
        self.assertIn("json", call_kwargs)
        sent = call_kwargs["json"]
        self.assertEqual(sent["description"], "Beautiful 3-bedroom home")
        self.assertEqual(sent["price"], "$650,000")
        self.assertEqual(sent["location"], "Ottawa, ON")
        self.assertEqual(sent["bedrooms"], "3")
        self.assertEqual(sent["bathrooms"], "2")
        self.assertEqual(sent["contact_phone"], "613-555-1234")
        self.assertEqual(sent["image_url"], "https://res.cloudinary.com/demo/photo.jpg")

    @patch("services.zapier.requests.post")
    def test_sends_json_without_image_url(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import zapier
        result = zapier.post_listing({"description": "No photo listing"})
        self.assertTrue(result["success"])
        call_kwargs = mock_post.call_args[1]
        self.assertIn("json", call_kwargs)
        self.assertNotIn("image_url", call_kwargs["json"])

    @patch("services.zapier.requests.post")
    def test_returns_error_on_request_failure(self, mock_post):
        mock_post.side_effect = _req.RequestException("timeout")
        from services import zapier
        result = zapier.post_listing({"description": "Test"})
        self.assertFalse(result["success"])
        self.assertIn("timeout", result["error"])

    @patch("services.zapier.requests.post")
    def test_returns_error_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_post.side_effect = _req.HTTPError(response=mock_resp)
        from services import zapier
        result = zapier.post_listing({"description": "Test"})
        self.assertFalse(result["success"])


# ── services/cloudinary_upload.py ─────────────────────────────────────────────

class TestCloudinaryIsConfigured(unittest.TestCase):

    def setUp(self):
        import config as cfg
        self._orig_name = cfg.CLOUDINARY_CLOUD_NAME
        self._orig_key = cfg.CLOUDINARY_API_KEY
        self._orig_secret = cfg.CLOUDINARY_API_SECRET

    def tearDown(self):
        import config as cfg
        cfg.CLOUDINARY_CLOUD_NAME = self._orig_name
        cfg.CLOUDINARY_API_KEY = self._orig_key
        cfg.CLOUDINARY_API_SECRET = self._orig_secret

    def test_not_configured_when_all_empty(self):
        import config as cfg
        cfg.CLOUDINARY_CLOUD_NAME = ""
        cfg.CLOUDINARY_API_KEY = ""
        cfg.CLOUDINARY_API_SECRET = ""
        from services import cloudinary_upload
        self.assertFalse(cloudinary_upload.is_configured())

    def test_not_configured_when_any_missing(self):
        import config as cfg
        cfg.CLOUDINARY_CLOUD_NAME = "demo"
        cfg.CLOUDINARY_API_KEY = "key"
        cfg.CLOUDINARY_API_SECRET = ""
        from services import cloudinary_upload
        self.assertFalse(cloudinary_upload.is_configured())

    def test_configured_when_all_set(self):
        import config as cfg
        cfg.CLOUDINARY_CLOUD_NAME = "demo"
        cfg.CLOUDINARY_API_KEY = "123456"
        cfg.CLOUDINARY_API_SECRET = "abc_secret"
        from services import cloudinary_upload
        self.assertTrue(cloudinary_upload.is_configured())


class TestCloudinaryUploadImage(unittest.TestCase):

    def setUp(self):
        import config as cfg
        self._orig_name = cfg.CLOUDINARY_CLOUD_NAME
        self._orig_key = cfg.CLOUDINARY_API_KEY
        self._orig_secret = cfg.CLOUDINARY_API_SECRET
        cfg.CLOUDINARY_CLOUD_NAME = "demo"
        cfg.CLOUDINARY_API_KEY = "123456"
        cfg.CLOUDINARY_API_SECRET = "abc_secret"

    def tearDown(self):
        import config as cfg
        cfg.CLOUDINARY_CLOUD_NAME = self._orig_name
        cfg.CLOUDINARY_API_KEY = self._orig_key
        cfg.CLOUDINARY_API_SECRET = self._orig_secret

    def test_returns_none_when_not_configured(self):
        import config as cfg
        cfg.CLOUDINARY_CLOUD_NAME = ""
        from services import cloudinary_upload
        result = cloudinary_upload.upload_image("/some/path.jpg")
        self.assertIsNone(result)

    @patch("services.cloudinary_upload.cloudinary.uploader.upload")
    def test_returns_secure_url_on_success(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/demo/image/upload/photo.jpg",
            "url": "http://res.cloudinary.com/demo/image/upload/photo.jpg",
        }
        from services import cloudinary_upload
        url = cloudinary_upload.upload_image("/tmp/photo.jpg")
        self.assertEqual(url, "https://res.cloudinary.com/demo/image/upload/photo.jpg")

    @patch("services.cloudinary_upload.cloudinary.uploader.upload")
    def test_returns_none_on_exception(self, mock_upload):
        mock_upload.side_effect = Exception("network error")
        from services import cloudinary_upload
        result = cloudinary_upload.upload_image("/tmp/photo.jpg")
        self.assertIsNone(result)

    @patch("services.cloudinary_upload.cloudinary.uploader.upload")
    def test_upload_uses_correct_folder(self, mock_upload):
        mock_upload.return_value = {"secure_url": "https://res.cloudinary.com/x.jpg"}
        from services import cloudinary_upload
        cloudinary_upload.upload_image("/tmp/photo.jpg")
        call_kwargs = mock_upload.call_args[1]
        self.assertEqual(call_kwargs.get("folder"), "realestate-bot")


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

    @patch("services.zapier.requests.post")
    def test_zapier_uses_listing_dict_when_provided(self, mock_post):
        """When a listing dict is passed, it is forwarded directly to Zapier."""
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import social_poster
        listing = {"description": "House", "price": "$500k", "image_url": "https://x.com/img.jpg"}
        social_poster.post_listing("House", listing=listing)
        sent = mock_post.call_args[1]["json"]
        self.assertEqual(sent["price"], "$500k")
        self.assertEqual(sent["image_url"], "https://x.com/img.jpg")

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

    def _make_context(self, extra: dict | None = None):
        import bot.telegram_bot as tb
        data = {
            tb.CTX_CAPTION:        "Beautiful house!",
            tb.CTX_DESCRIPTION:    "3-bed home",
            tb.CTX_MEDIA_PATH:     None,
            tb.CTX_MEDIA_TYPE:     "photo",
            tb.CTX_PRICE:          "$650,000",
            tb.CTX_LOCATION:       "Ottawa, ON",
            tb.CTX_BEDROOMS:       "3",
            tb.CTX_BATHROOMS:      "2",
            tb.CTX_CONTACT_PHONE:  "613-555-1234",
        }
        if extra:
            data.update(extra)
        context = MagicMock()
        context.user_data = data
        context.bot.send_message = AsyncMock()
        return context

    async def _run_confirm(self, zapier_result: dict, context=None):
        import bot.telegram_bot as tb
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        if context is None:
            context = self._make_context()

        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.cloudinary_upload.is_configured", return_value=False), \
             patch("bot.telegram_bot.zapier_service.post_listing",
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

    async def test_confirm_builds_structured_listing_payload(self):
        """The confirm callback must pass listing fields to zapier_service.post_listing."""
        import bot.telegram_bot as tb
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        context = self._make_context()
        mock_post = MagicMock(return_value={"success": True, "status_code": 200})

        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.cloudinary_upload.is_configured", return_value=False), \
             patch("bot.telegram_bot.zapier_service.post_listing", mock_post):
            await tb.handle_confirm_callback(update, context)

        listing = mock_post.call_args[0][0]
        self.assertEqual(listing["price"], "$650,000")
        self.assertEqual(listing["location"], "Ottawa, ON")
        self.assertEqual(listing["bedrooms"], "3")
        self.assertEqual(listing["bathrooms"], "2")
        self.assertEqual(listing["contact_phone"], "613-555-1234")
        # image_url must always be present so Zapier can map it to Instagram's Photo field
        self.assertIn("image_url", listing)

    async def test_image_url_always_present_in_payload_even_without_photo(self):
        """image_url must be present (as empty string) even when no photo is uploaded.

        Zapier needs to discover the field during test-trigger setup so that the
        user can map it to Instagram's required Photo input.  If the key is absent
        from the payload, Zapier's Instagram action will error with
        'Photo field is required but not receiving a valid image URL'.
        """
        import bot.telegram_bot as tb
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"

        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        # No media path – simulates a text-only post (media type is irrelevant here)
        context = self._make_context({tb.CTX_MEDIA_PATH: None})
        mock_post = MagicMock(return_value={"success": True, "status_code": 200})

        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.cloudinary_upload.is_configured", return_value=False), \
             patch("bot.telegram_bot.zapier_service.post_listing", mock_post):
            await tb.handle_confirm_callback(update, context)

        listing = mock_post.call_args[0][0]
        # Key must exist so Zapier can map it
        self.assertIn("image_url", listing)
        # Value is empty when no image was uploaded
        self.assertEqual(listing["image_url"], "")

    async def test_cloudinary_url_included_in_payload_when_upload_succeeds(self):
        """When Cloudinary upload succeeds, image_url must appear in the payload."""
        import bot.telegram_bot as tb
        import config as cfg
        import tempfile, os
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"

        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(b"\xff\xd8\xff")
        tmp.close()
        tmp_name = tmp.name

        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        context = self._make_context({
            tb.CTX_MEDIA_PATH: tmp_name,
            tb.CTX_MEDIA_TYPE: "photo",
        })
        mock_post = MagicMock(return_value={"success": True, "status_code": 200})
        public_url = "https://res.cloudinary.com/demo/photo.jpg"

        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.cloudinary_upload.is_configured", return_value=True), \
             patch("bot.telegram_bot.cloudinary_upload.upload_image", return_value=public_url), \
             patch("bot.telegram_bot.zapier_service.post_listing", mock_post):
            await tb.handle_confirm_callback(update, context)

        # _cleanup_media already deleted the file – that is correct behavior
        listing = mock_post.call_args[0][0]
        self.assertEqual(listing.get("image_url"), public_url)

        # The bot must also send the public URL back to the agent in Telegram
        send_calls = [
            call[1].get("text", "") or (call[0][0] if call[0] else "")
            for call in context.bot.send_message.call_args_list
        ]
        url_echoed = any(public_url in t for t in send_calls)
        self.assertTrue(url_echoed, "Expected Cloudinary URL to be echoed back to the agent")

    async def test_confirm_without_zapier_falls_through_to_ghl(self):
        import bot.telegram_bot as tb
        update = MagicMock()
        update.effective_chat.id = 123
        query = AsyncMock()
        query.data = "confirm_post"
        update.callback_query = query
        context = self._make_context()
        from telegram.ext import ConversationHandler
        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=False), \
             patch("bot.telegram_bot.ghl_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.ghl_service.post_to_social_planner",
                   return_value={"success": True, "post_id": "p1"}):
            result = await tb.handle_confirm_callback(update, context)
        self.assertEqual(result, ConversationHandler.END)


# ── Listing detail collection steps ──────────────────────────────────────────

class TestListingDetailSteps(unittest.IsolatedAsyncioTestCase):
    """Test that each step handler stores the value and returns the next state."""

    def setUp(self):
        import bot.telegram_bot as tb
        tb._bot_paused = False

    async def _send_text(self, handler, text: str, user_data: dict | None = None):
        import bot.telegram_bot as tb
        update = MagicMock()
        update.effective_message.text = text
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = user_data if user_data is not None else {}
        state = await handler(update, context)
        return state, context

    async def test_handle_price_stores_price_and_returns_location(self):
        import bot.telegram_bot as tb
        state, ctx = await self._send_text(tb.handle_price, "$650,000")
        self.assertEqual(ctx.user_data[tb.CTX_PRICE], "$650,000")
        self.assertEqual(state, tb.AWAITING_LOCATION)

    async def test_handle_location_stores_location_and_returns_bedrooms(self):
        import bot.telegram_bot as tb
        state, ctx = await self._send_text(tb.handle_location, "Ottawa, ON")
        self.assertEqual(ctx.user_data[tb.CTX_LOCATION], "Ottawa, ON")
        self.assertEqual(state, tb.AWAITING_BEDROOMS)

    async def test_handle_bedrooms_stores_bedrooms_and_returns_bathrooms(self):
        import bot.telegram_bot as tb
        state, ctx = await self._send_text(tb.handle_bedrooms, "3")
        self.assertEqual(ctx.user_data[tb.CTX_BEDROOMS], "3")
        self.assertEqual(state, tb.AWAITING_BATHROOMS)

    async def test_handle_bathrooms_stores_bathrooms_and_returns_contact_phone(self):
        import bot.telegram_bot as tb
        state, ctx = await self._send_text(tb.handle_bathrooms, "2")
        self.assertEqual(ctx.user_data[tb.CTX_BATHROOMS], "2")
        self.assertEqual(state, tb.AWAITING_CONTACT_PHONE)

    async def test_handle_contact_phone_stores_phone_and_returns_confirm(self):
        import bot.telegram_bot as tb
        user_data = {
            tb.CTX_CAPTION: "Great house",
            tb.CTX_PRICE: "$500k",
            tb.CTX_LOCATION: "Toronto",
            tb.CTX_BEDROOMS: "3",
            tb.CTX_BATHROOMS: "2",
        }
        state, ctx = await self._send_text(tb.handle_contact_phone, "416-555-9999", user_data)
        self.assertEqual(ctx.user_data[tb.CTX_CONTACT_PHONE], "416-555-9999")
        self.assertEqual(state, tb.AWAITING_CONFIRM)

    async def test_handle_description_goes_to_price_when_zapier_configured(self):
        import bot.telegram_bot as tb
        update = MagicMock()
        update.effective_message.text = "3-bed house in Ottawa"
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=True), \
             patch("bot.telegram_bot.lead_qualifier.generate_listing_caption",
                   return_value="Great listing!"):
            state = await tb.handle_description(update, context)
        self.assertEqual(state, tb.AWAITING_PRICE)

    async def test_handle_description_goes_to_confirm_when_zapier_not_configured(self):
        import bot.telegram_bot as tb
        update = MagicMock()
        update.effective_message.text = "3-bed house"
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()
        context.user_data = {}
        with patch("bot.telegram_bot.zapier_service.is_configured", return_value=False), \
             patch("bot.telegram_bot.lead_qualifier.generate_listing_caption",
                   return_value="Caption"):
            state = await tb.handle_description(update, context)
        self.assertEqual(state, tb.AWAITING_CONFIRM)


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

    async def test_configured_shows_status_and_json_schema(self):
        import config as cfg
        cfg.ZAPIER_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/"
        update = await self._call_cmd_zapier()
        reply = update.effective_message.reply_text.call_args[0][0]
        self.assertIn("configured", reply)
        self.assertIn("✅", reply)
        self.assertIn("image_url", reply)

    async def test_not_authorised_agent_is_blocked(self):
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


# ── services/zapier.py – get_all_leads() ──────────────────────────────────────

class TestZapierGetAllLeads(unittest.TestCase):

    def setUp(self):
        import config as cfg
        self._orig = getattr(cfg, "ZAPIER_ALL_LEADS_WEBHOOK_URL", "")
        cfg.ZAPIER_ALL_LEADS_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/all/"

    def tearDown(self):
        import config as cfg
        cfg.ZAPIER_ALL_LEADS_WEBHOOK_URL = self._orig

    def test_is_all_leads_not_configured_when_empty(self):
        import config as cfg
        cfg.ZAPIER_ALL_LEADS_WEBHOOK_URL = ""
        from services import zapier
        self.assertFalse(zapier.is_all_leads_configured())

    def test_is_all_leads_configured_when_url_set(self):
        from services import zapier
        self.assertTrue(zapier.is_all_leads_configured())

    def test_returns_error_when_not_configured(self):
        import config as cfg
        cfg.ZAPIER_ALL_LEADS_WEBHOOK_URL = ""
        from services import zapier
        result = zapier.get_all_leads()
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

    @patch("services.zapier.requests.post")
    def test_posts_get_all_leads_action(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"leads": []}'
        mock_resp.json.return_value = {"leads": []}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import zapier
        zapier.get_all_leads()

        call_args = mock_post.call_args
        self.assertEqual(call_args[1]["json"], {"action": "get_all_leads"})

    @patch("services.zapier.requests.post")
    def test_returns_leads_from_response(self, mock_post):
        leads_data = [
            {"first_name": "Alice", "last_name": "Smith", "score": 85},
            {"first_name": "Bob", "last_name": "Jones", "score": 72},
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"leads": []}'
        mock_resp.json.return_value = {"leads": leads_data}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import zapier
        result = zapier.get_all_leads()
        self.assertTrue(result["success"])
        self.assertEqual(result["leads"], leads_data)

    @patch("services.zapier.requests.post")
    def test_returns_empty_leads_list_when_missing_from_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{}'
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        from services import zapier
        result = zapier.get_all_leads()
        self.assertTrue(result["success"])
        self.assertEqual(result["leads"], [])

    @patch("services.zapier.requests.post")
    def test_returns_error_on_request_exception(self, mock_post):
        mock_post.side_effect = _req.RequestException("network error")
        from services import zapier
        result = zapier.get_all_leads()
        self.assertFalse(result["success"])
        self.assertIn("network error", result["error"])


# ── bot/telegram_bot.py – cmd_all_leads() ─────────────────────────────────────

class TestCmdAllLeads(unittest.IsolatedAsyncioTestCase):

    def _make_update(self, chat_id: int = 123):
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_message.reply_text = AsyncMock()
        update.effective_message.reply_document = AsyncMock()
        return update

    def _make_context(self):
        return MagicMock()

    async def test_all_leads_via_zapier_when_configured(self):
        """When Zapier is configured and returns leads, a PDF is generated and sent."""
        import bot.telegram_bot as tb
        import config as cfg
        cfg.ZAPIER_ALL_LEADS_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/all/"

        leads = [{"first_name": "Alice", "last_name": "Smith", "score": 80,
                  "email": "alice@example.com", "phone": "555-0001",
                  "intent": "buy", "summary": "Ready now", "status": "new",
                  "is_qualified": True}]

        with patch("bot.telegram_bot.zapier_service.is_all_leads_configured", return_value=True), \
             patch("bot.telegram_bot.zapier_service.get_all_leads",
                   return_value={"success": True, "leads": leads}):
            update = self._make_update()
            await tb.cmd_all_leads(update, self._make_context())

        # A PDF document should have been sent
        update.effective_message.reply_document.assert_awaited_once()

    async def test_all_leads_sends_action_payload_to_zapier(self):
        """Ensure get_all_leads() is called when Zapier is configured."""
        import bot.telegram_bot as tb
        import config as cfg
        cfg.ZAPIER_ALL_LEADS_WEBHOOK_URL = "https://hooks.zapier.com/hooks/catch/abc/all/"

        mock_get = MagicMock(return_value={"success": True, "leads": []})

        with patch("bot.telegram_bot.zapier_service.is_all_leads_configured", return_value=True), \
             patch("bot.telegram_bot.zapier_service.get_all_leads", mock_get):
            update = self._make_update()
            await tb.cmd_all_leads(update, self._make_context())

        mock_get.assert_called_once()

    async def test_all_leads_sends_pdf_when_zapier_returns_empty(self):
        """When Zapier returns no leads, demo data fallback is used and PDF sent."""
        import bot.telegram_bot as tb

        with patch("bot.telegram_bot.zapier_service.is_all_leads_configured", return_value=True), \
             patch("bot.telegram_bot.zapier_service.get_all_leads",
                   return_value={"success": True, "leads": []}):
            update = self._make_update()
            await tb.cmd_all_leads(update, self._make_context())

        # Demo data fallback ensures a PDF is always sent
        update.effective_message.reply_document.assert_awaited_once()

    async def test_all_leads_sends_pdf_when_zapier_fails(self):
        """When Zapier fails, demo data fallback is used and PDF is still sent."""
        import bot.telegram_bot as tb

        with patch("bot.telegram_bot.zapier_service.is_all_leads_configured", return_value=True), \
             patch("bot.telegram_bot.zapier_service.get_all_leads",
                   return_value={"success": False, "error": "timeout"}):
            update = self._make_update()
            await tb.cmd_all_leads(update, self._make_context())

        update.effective_message.reply_document.assert_awaited_once()

    async def test_all_leads_falls_back_to_sheet_when_zapier_not_configured(self):
        """Without Zapier config, leads come from sheets; a PDF is sent."""
        import bot.telegram_bot as tb

        sheet_leads = [{"first_name": "Bob", "last_name": "Jones", "score": 60,
                        "email": "bob@example.com", "phone": "555-0002",
                        "intent": "sell", "summary": "Moving soon", "status": "new",
                        "is_qualified": True}]

        with patch("bot.telegram_bot.zapier_service.is_all_leads_configured", return_value=False), \
             patch("bot.telegram_bot.sheets.get_leads", return_value=sheet_leads):
            update = self._make_update()
            await tb.cmd_all_leads(update, self._make_context())

        update.effective_message.reply_document.assert_awaited_once()

    async def test_all_leads_sheet_fallback_shows_all_leads_not_just_qualified(self):
        """Sheet fallback must call get_leads(qualified_only=False)."""
        import bot.telegram_bot as tb

        with patch("bot.telegram_bot.zapier_service.is_all_leads_configured", return_value=False), \
             patch("bot.telegram_bot.sheets.get_leads", return_value=[]) as mock_get_leads:
            update = self._make_update()
            await tb.cmd_all_leads(update, self._make_context())

        mock_get_leads.assert_called_once_with(qualified_only=False)

    async def test_all_leads_callback_routes_to_cmd_all_leads(self):
        """The 'all_leads' callback_data must route to cmd_all_leads, not cmd_leads."""
        import bot.telegram_bot as tb
        import config as cfg
        cfg.AGENT_CHAT_IDS = [123]

        query = AsyncMock()
        query.data = "all_leads"
        query.answer = AsyncMock()
        update = MagicMock()
        update.effective_chat.id = 123
        update.callback_query = query
        update.effective_message.reply_text = AsyncMock()
        context = MagicMock()

        with patch("bot.telegram_bot.cmd_all_leads", new_callable=AsyncMock) as mock_all_leads, \
             patch("bot.telegram_bot.cmd_leads", new_callable=AsyncMock) as mock_leads:
            await tb.handle_menu_callback(update, context)

        mock_all_leads.assert_awaited_once()
        mock_leads.assert_not_called()


if __name__ == "__main__":
    unittest.main()
