"""
Tests for the lead_qualifier service.
Uses unittest.mock to avoid real OpenAI API calls.
"""
from __future__ import annotations

import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Patch config before importing the module under test
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


class TestLeadQualifier(unittest.TestCase):

    def _make_openai_response(self, payload: dict) -> MagicMock:
        choice = MagicMock()
        choice.message.content = json.dumps(payload)
        response = MagicMock()
        response.choices = [choice]
        return response

    @patch("services.lead_qualifier._get_client")
    def test_qualified_lead_returns_correct_fields(self, mock_get_client):
        payload = {
            "score": 85,
            "intent": "buy",
            "budget": "$500,000",
            "timeline": "3 months",
            "location": "Miami",
            "is_qualified": True,
            "summary": "Serious buyer looking for a 3-bed home in Miami.",
            "follow_up_questions": ["What is your pre-approval status?"],
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._make_openai_response(payload)
        mock_get_client.return_value = mock_client

        from services.lead_qualifier import qualify_lead
        result = qualify_lead("I want to buy a house in Miami for around $500k within 3 months.")

        self.assertTrue(result["is_qualified"])
        self.assertEqual(result["score"], 85)
        self.assertEqual(result["intent"], "buy")
        self.assertEqual(result["location"], "Miami")
        self.assertIsInstance(result["follow_up_questions"], list)

    @patch("services.lead_qualifier._get_client")
    def test_unqualified_lead(self, mock_get_client):
        payload = {
            "score": 15,
            "intent": "unknown",
            "budget": None,
            "timeline": None,
            "location": None,
            "is_qualified": False,
            "summary": "Vague inquiry with no details.",
            "follow_up_questions": ["What type of property are you looking for?"],
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = self._make_openai_response(payload)
        mock_get_client.return_value = mock_client

        from services.lead_qualifier import qualify_lead
        result = qualify_lead("hi")

        self.assertFalse(result["is_qualified"])
        self.assertLess(result["score"], 60)

    @patch("services.lead_qualifier._get_client")
    def test_api_failure_returns_safe_defaults(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        mock_get_client.return_value = mock_client

        from services.lead_qualifier import qualify_lead
        result = qualify_lead("some message")

        self.assertFalse(result["is_qualified"])
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["intent"], "unknown")

    @patch("services.lead_qualifier._get_client")
    def test_caption_generation(self, mock_get_client):
        mock_client = MagicMock()
        choice = MagicMock()
        choice.message.content = "🏠 Stunning 3-bed home in Miami! Pool, renovated kitchen. $450k. #realestate"
        mock_client.chat.completions.create.return_value = MagicMock(choices=[choice])
        mock_get_client.return_value = mock_client

        from services.lead_qualifier import generate_listing_caption
        caption = generate_listing_caption("3-bed house in Miami, $450k, pool, renovated kitchen")

        self.assertIsInstance(caption, str)
        self.assertGreater(len(caption), 0)

    @patch("services.lead_qualifier._get_client")
    def test_caption_generation_fallback_on_error(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")
        mock_get_client.return_value = mock_client

        from services.lead_qualifier import generate_listing_caption
        description = "3-bed house in Miami"
        caption = generate_listing_caption(description)

        # Should return the original description on failure
        self.assertEqual(caption, description)


if __name__ == "__main__":
    unittest.main()
