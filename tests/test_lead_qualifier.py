"""Tests for lead_qualifier service."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.lead_qualifier import _DEFAULT_QUALIFICATION, get_auto_reply, qualify_lead


SERIOUS_RESPONSE = json.dumps({
    "is_serious": True,
    "qualification_score": 85,
    "reasoning": "Has budget, ready to buy within 3 months",
    "lead_type": "buyer",
    "urgency": "within_3_months",
    "recommended_action": "call_immediately",
})

BROWSING_RESPONSE = json.dumps({
    "is_serious": False,
    "qualification_score": 15,
    "reasoning": "Just browsing, no clear intent",
    "lead_type": "unknown",
    "urgency": "just_browsing",
    "recommended_action": "nurture",
})


def _mock_openai_response(content: str):
    """Build a minimal mock that mimics the OpenAI ChatCompletion response."""
    choice = MagicMock()
    choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [choice]
    return mock_resp


# ── qualify_lead ─────────────────────────────────────────────────────────────

class TestQualifyLead:
    def test_serious_lead_gets_high_score(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(SERIOUS_RESPONSE)

        with patch("app.services.lead_qualifier._get_openai_client", return_value=mock_client):
            result = qualify_lead("I want to buy a 3-bedroom house for $500k within 3 months.")

        assert result["is_serious"] is True
        assert result["qualification_score"] >= 70
        assert result["recommended_action"] == "call_immediately"

    def test_browsing_lead_gets_low_score(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(BROWSING_RESPONSE)

        with patch("app.services.lead_qualifier._get_openai_client", return_value=mock_client):
            result = qualify_lead("Just looking around, no rush.")

        assert result["is_serious"] is False
        assert result["qualification_score"] < 30
        assert result["recommended_action"] == "nurture"

    def test_returns_default_when_openai_unavailable(self):
        with patch("app.services.lead_qualifier._get_openai_client", return_value=None):
            result = qualify_lead("I need a house")

        assert result["qualification_score"] == _DEFAULT_QUALIFICATION["qualification_score"]
        assert result["is_serious"] == _DEFAULT_QUALIFICATION["is_serious"]

    def test_handles_invalid_json_from_openai(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response("not valid json {{")

        with patch("app.services.lead_qualifier._get_openai_client", return_value=mock_client):
            result = qualify_lead("some conversation")

        # Should return default qualification gracefully
        assert isinstance(result, dict)
        assert "qualification_score" in result

    def test_handles_openai_api_exception(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API error")

        with patch("app.services.lead_qualifier._get_openai_client", return_value=mock_client):
            result = qualify_lead("some conversation")

        assert result == dict(_DEFAULT_QUALIFICATION)

    def test_result_contains_required_keys(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(SERIOUS_RESPONSE)

        with patch("app.services.lead_qualifier._get_openai_client", return_value=mock_client):
            result = qualify_lead("I want to buy")

        for key in ("is_serious", "qualification_score", "reasoning", "lead_type", "urgency", "recommended_action"):
            assert key in result, f"Missing key: {key}"


# ── get_auto_reply ────────────────────────────────────────────────────────────

class TestGetAutoReply:
    def test_returns_string(self):
        mock_client = MagicMock()
        choice = MagicMock()
        choice.message.content = "Thank you for your interest! We will contact you shortly."
        mock_client.chat.completions.create.return_value = MagicMock(choices=[choice])

        with patch("app.services.lead_qualifier._get_openai_client", return_value=mock_client):
            reply = get_auto_reply("I want to buy a house")

        assert isinstance(reply, str)
        assert len(reply) > 0

    def test_returns_fallback_when_no_client(self):
        with patch("app.services.lead_qualifier._get_openai_client", return_value=None):
            reply = get_auto_reply("Hello")

        assert isinstance(reply, str)
        assert len(reply) > 10
