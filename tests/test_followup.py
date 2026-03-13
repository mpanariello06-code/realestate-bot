"""
Tests for services/followup.py
"""
from __future__ import annotations

import sys
import os
import unittest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from services.followup import (
    build_nudge_message,
    get_due_today,
    get_overdue,
    summarise,
)


def _make_lead(
    status="new",
    score=80,
    intent="buy",
    first_name="Alice",
    last_name="Smith",
    budget="$600k",
    location="Toronto",
    hours_ago=72,
):
    """Build a minimal lead dict for testing."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return {
        "first_name": first_name,
        "last_name": last_name,
        "status": status,
        "score": score,
        "intent": intent,
        "budget": budget,
        "location": location,
        "timestamp": ts,
    }


class TestGetDueToday(unittest.TestCase):

    def test_new_qualified_lead_is_due(self):
        lead = _make_lead(status="new", score=80)
        result = get_due_today([lead], threshold=60)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 1)  # 1-based index

    def test_contacted_lead_not_due(self):
        lead = _make_lead(status="contacted", score=80)
        result = get_due_today([lead], threshold=60)
        self.assertEqual(len(result), 0)

    def test_below_threshold_not_due(self):
        lead = _make_lead(status="new", score=40)
        result = get_due_today([lead], threshold=60)
        self.assertEqual(len(result), 0)

    def test_exactly_at_threshold_is_due(self):
        lead = _make_lead(status="new", score=60)
        result = get_due_today([lead], threshold=60)
        self.assertEqual(len(result), 1)

    def test_index_is_correct_for_multiple_leads(self):
        leads = [
            _make_lead(status="contacted", score=90),
            _make_lead(status="new", score=75),
            _make_lead(status="new", score=55),
        ]
        result = get_due_today(leads, threshold=60)
        # Only lead at index 2 (score=75, new) is due
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 2)

    def test_empty_leads_returns_empty(self):
        self.assertEqual(get_due_today([], threshold=60), [])


class TestGetOverdue(unittest.TestCase):

    def test_old_new_qualified_lead_is_overdue(self):
        lead = _make_lead(status="new", score=80, hours_ago=72)
        result = get_overdue([lead], threshold=60, overdue_hours=48)
        self.assertEqual(len(result), 1)

    def test_recent_new_qualified_lead_not_overdue(self):
        lead = _make_lead(status="new", score=80, hours_ago=12)
        result = get_overdue([lead], threshold=60, overdue_hours=48)
        self.assertEqual(len(result), 0)

    def test_contacted_lead_never_overdue(self):
        lead = _make_lead(status="contacted", score=80, hours_ago=120)
        result = get_overdue([lead], threshold=60, overdue_hours=48)
        self.assertEqual(len(result), 0)

    def test_lead_with_no_timestamp_treated_as_overdue(self):
        lead = {"status": "new", "score": 80}
        result = get_overdue([lead], threshold=60, overdue_hours=48)
        self.assertEqual(len(result), 1)

    def test_below_threshold_not_overdue(self):
        lead = _make_lead(status="new", score=30, hours_ago=120)
        result = get_overdue([lead], threshold=60, overdue_hours=48)
        self.assertEqual(len(result), 0)

    def test_exactly_at_cutoff_boundary(self):
        # Lead arrived exactly overdue_hours ago — should be overdue (<=)
        lead = _make_lead(status="new", score=80, hours_ago=48)
        result = get_overdue([lead], threshold=60, overdue_hours=48)
        self.assertEqual(len(result), 1)


class TestBuildNudgeMessage(unittest.TestCase):

    def test_buy_intent_contains_name(self):
        lead = {"first_name": "John", "intent": "buy", "location": "Ottawa", "budget": "$500k"}
        msg = build_nudge_message(lead)
        self.assertIn("John", msg)

    def test_buy_intent_mentions_location(self):
        lead = {"first_name": "John", "intent": "buy", "location": "Ottawa", "budget": ""}
        msg = build_nudge_message(lead)
        self.assertIn("Ottawa", msg)

    def test_sell_intent_message(self):
        lead = {"first_name": "Jane", "intent": "sell", "location": "Etobicoke", "budget": ""}
        msg = build_nudge_message(lead)
        self.assertIn("Jane", msg)
        self.assertIn("valuation", msg.lower())

    def test_rent_intent_message(self):
        lead = {"first_name": "Bob", "intent": "rent", "location": "Downtown", "budget": "$2k/month"}
        msg = build_nudge_message(lead)
        self.assertIn("Bob", msg)
        self.assertIn("rental", msg.lower())

    def test_unknown_intent_fallback(self):
        lead = {"first_name": "Sam", "intent": "unknown"}
        msg = build_nudge_message(lead)
        self.assertIn("Sam", msg)

    def test_missing_first_name_uses_there(self):
        lead = {"intent": "buy"}
        msg = build_nudge_message(lead)
        self.assertIn("there", msg)


class TestSummarise(unittest.TestCase):

    def test_returns_both_buckets(self):
        leads = [
            _make_lead(status="new", score=85, hours_ago=10),   # due today, not overdue
            _make_lead(status="new", score=90, hours_ago=72),   # due today + overdue
            _make_lead(status="contacted", score=80),           # neither
        ]
        result = summarise(leads, threshold=60, overdue_hours=48)
        self.assertIn("due_today", result)
        self.assertIn("overdue", result)
        self.assertEqual(len(result["due_today"]), 2)
        self.assertEqual(len(result["overdue"]), 1)


if __name__ == "__main__":
    unittest.main()
