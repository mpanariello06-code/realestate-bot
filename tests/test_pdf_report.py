"""
Tests for services/pdf_report.py and services/weekly_report.py.
Uses unittest.mock to avoid real Sheets / Telegram API calls.
"""
from __future__ import annotations

import io
import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

MOCK_LEADS = [
    {
        "first_name": "Alice", "last_name": "Smith",
        "intent": "buy", "budget": "$500k",
        "score": 90, "is_qualified": "TRUE", "status": "contacted",
    },
    {
        "first_name": "Bob", "last_name": "Jones",
        "intent": "sell", "budget": "$400k",
        "score": 55, "is_qualified": "FALSE", "status": "new",
    },
    {
        "first_name": "Carol", "last_name": "Lee",
        "intent": "rent", "budget": None,
        "score": 75, "is_qualified": "TRUE", "status": "closed",
    },
]

MOCK_PERF = [
    {
        "week_start": "2025-01-06",
        "platform": "instagram",
        "followers": 1200,
        "new_leads": 10,
        "qualified_leads": 3,
        "deals_closed": 1,
        "avg_response_time": 10,
        "engagement_rate": 3.2,
    }
]


class TestBuildReportPdf(unittest.TestCase):

    def test_returns_bytes(self):
        from services.pdf_report import build_report_pdf
        pdf = build_report_pdf(MOCK_LEADS, MOCK_PERF)
        self.assertIsInstance(pdf, bytes)

    def test_pdf_has_valid_header(self):
        from services.pdf_report import build_report_pdf
        pdf = build_report_pdf(MOCK_LEADS, MOCK_PERF)
        # Valid PDFs start with the %PDF magic bytes
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_non_empty_output(self):
        from services.pdf_report import build_report_pdf
        pdf = build_report_pdf(MOCK_LEADS, MOCK_PERF)
        self.assertGreater(len(pdf), 1024)  # at least 1 KB

    def test_empty_data_does_not_raise(self):
        from services.pdf_report import build_report_pdf
        # Should gracefully handle zero leads and no perf records
        pdf = build_report_pdf([], [])
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_no_perf_records_does_not_raise(self):
        from services.pdf_report import build_report_pdf
        pdf = build_report_pdf(MOCK_LEADS, [])
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_top_leads_truncated_to_five(self):
        """PDF builder should handle more than 5 qualified leads without error."""
        from services.pdf_report import build_report_pdf
        many_leads = [
            {
                "first_name": f"Lead{i}", "last_name": "",
                "intent": "buy", "budget": "$300k",
                "score": 70 + i, "is_qualified": "TRUE", "status": "new",
            }
            for i in range(10)
        ]
        pdf = build_report_pdf(many_leads, [])
        self.assertTrue(pdf.startswith(b"%PDF"))


class TestSendWeeklyReport(unittest.IsolatedAsyncioTestCase):

    @patch("services.weekly_report.get_performance", return_value=MOCK_PERF)
    @patch("services.weekly_report.get_leads", return_value=MOCK_LEADS)
    async def test_send_calls_send_message_and_send_document(
        self, _mock_leads, _mock_perf
    ):
        from services.weekly_report import send_weekly_report
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.send_document = AsyncMock()

        await send_weekly_report(bot)

        bot.send_message.assert_awaited_once()
        bot.send_document.assert_awaited_once()

    @patch("services.weekly_report.get_performance", return_value=MOCK_PERF)
    @patch("services.weekly_report.get_leads", return_value=MOCK_LEADS)
    async def test_send_document_filename_contains_date(
        self, _mock_leads, _mock_perf
    ):
        from services.weekly_report import send_weekly_report
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.send_document = AsyncMock()

        await send_weekly_report(bot)

        kwargs = bot.send_document.call_args[1]
        self.assertIn("weekly_report_", kwargs["filename"])
        self.assertTrue(kwargs["filename"].endswith(".pdf"))

    @patch("services.weekly_report.get_performance", return_value=MOCK_PERF)
    @patch("services.weekly_report.get_leads", return_value=MOCK_LEADS)
    async def test_send_document_sends_bytes_io(self, _mock_leads, _mock_perf):
        from services.weekly_report import send_weekly_report
        bot = MagicMock()
        bot.send_message = AsyncMock()
        bot.send_document = AsyncMock()

        await send_weekly_report(bot)

        kwargs = bot.send_document.call_args[1]
        self.assertIsInstance(kwargs["document"], io.IOBase)

    @patch("services.weekly_report.get_performance", return_value=MOCK_PERF)
    @patch("services.weekly_report.get_leads", return_value=MOCK_LEADS)
    async def test_report_text_contains_pdf_note(self, _mock_leads, _mock_perf):
        from services.weekly_report import _build_report_text
        text = _build_report_text()
        self.assertIn("PDF", text)


if __name__ == "__main__":
    unittest.main()
