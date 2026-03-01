"""
Tests for the sheets service.
Uses unittest.mock to avoid real Google API calls.
"""
from __future__ import annotations

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


class TestSheets(unittest.TestCase):

    @patch("services.sheets._get_worksheet")
    def test_save_lead_calls_append_row(self, mock_get_ws):
        mock_ws = MagicMock()
        mock_get_ws.return_value = mock_ws

        from services.sheets import save_lead
        lead = {
            "platform": "facebook",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone": "555-1234",
            "message": "I want to buy a house",
            "score": 80,
            "intent": "buy",
            "budget": "$500k",
            "timeline": "3 months",
            "location": "Miami",
            "is_qualified": True,
            "summary": "Serious buyer",
            "status": "new",
        }
        result = save_lead(lead)

        self.assertTrue(result)
        mock_ws.append_row.assert_called_once()
        row = mock_ws.append_row.call_args[0][0]
        self.assertEqual(row[1], "facebook")
        self.assertEqual(row[2], "John")
        self.assertEqual(row[3], "Doe")

    @patch("services.sheets._get_worksheet")
    def test_save_lead_returns_false_on_error(self, mock_get_ws):
        mock_get_ws.side_effect = Exception("Connection error")

        from services.sheets import save_lead
        result = save_lead({"platform": "test", "message": "hello"})
        self.assertFalse(result)

    @patch("services.sheets._get_worksheet")
    def test_get_leads_all(self, mock_get_ws):
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {"first_name": "Alice", "is_qualified": "TRUE", "status": "new"},
            {"first_name": "Bob", "is_qualified": "FALSE", "status": "new"},
        ]
        mock_get_ws.return_value = mock_ws

        from services.sheets import get_leads
        leads = get_leads(qualified_only=False)
        self.assertEqual(len(leads), 2)

    @patch("services.sheets._get_worksheet")
    def test_get_leads_qualified_only(self, mock_get_ws):
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {"first_name": "Alice", "is_qualified": "TRUE", "status": "new"},
            {"first_name": "Bob", "is_qualified": "FALSE", "status": "new"},
        ]
        mock_get_ws.return_value = mock_ws

        from services.sheets import get_leads
        leads = get_leads(qualified_only=True)
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["first_name"], "Alice")

    @patch("services.sheets._get_worksheet")
    def test_get_leads_returns_empty_on_error(self, mock_get_ws):
        mock_get_ws.side_effect = Exception("API error")

        from services.sheets import get_leads
        leads = get_leads()
        self.assertEqual(leads, [])

    @patch("services.sheets._get_worksheet")
    def test_save_performance(self, mock_get_ws):
        mock_ws = MagicMock()
        mock_get_ws.return_value = mock_ws

        from services.sheets import save_performance
        result = save_performance({
            "week_start": "2025-01-06",
            "platform": "instagram",
            "followers": 1200,
            "new_leads": 15,
            "qualified_leads": 4,
            "deals_closed": 1,
            "avg_response_time": 12,
            "engagement_rate": 3.5,
        })
        self.assertTrue(result)
        mock_ws.append_row.assert_called_once()

    @patch("services.sheets._get_worksheet")
    def test_update_lead_status(self, mock_get_ws):
        mock_ws = MagicMock()
        mock_get_ws.return_value = mock_ws

        from services.sheets import update_lead_status
        result = update_lead_status(1, "contacted", "Called on Monday")
        self.assertTrue(result)
        self.assertEqual(mock_ws.update_cell.call_count, 2)

    @patch("services.sheets._get_worksheet")
    def test_save_lead_notes(self, mock_get_ws):
        mock_ws = MagicMock()
        mock_get_ws.return_value = mock_ws

        from services.sheets import save_lead_notes, LEADS_HEADERS
        result = save_lead_notes(3, "Viewing booked for Saturday")
        self.assertTrue(result)
        mock_ws.update_cell.assert_called_once()
        # row_index=3 (1-based lead number) + 1 (header row) = sheet row 4
        call_args = mock_ws.update_cell.call_args[0]
        self.assertEqual(call_args[0], 4)
        self.assertEqual(call_args[1], LEADS_HEADERS.index("agent_notes") + 1)
        self.assertEqual(call_args[2], "Viewing booked for Saturday")

    @patch("services.sheets._get_worksheet")
    def test_save_lead_notes_returns_false_on_error(self, mock_get_ws):
        mock_get_ws.side_effect = Exception("API error")

        from services.sheets import save_lead_notes
        result = save_lead_notes(1, "some note")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
