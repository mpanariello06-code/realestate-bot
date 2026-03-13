"""
Tests for services/tasks.py
"""
from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from services.tasks import format_task_line, get_tasks


def _make_lead(status="new", score=80, intent="buy",
               first_name="Alice", last_name="Smith",
               budget="$600k", timeline="2 months", notes=""):
    return {
        "first_name":   first_name,
        "last_name":    last_name,
        "status":       status,
        "score":        score,
        "intent":       intent,
        "budget":       budget,
        "timeline":     timeline,
        "agent_notes":  notes,
    }


class TestGetTasks(unittest.TestCase):

    def test_new_qualified_lead_is_high_priority(self):
        lead = _make_lead(status="new", score=80)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["priority"], "high")

    def test_contacted_lead_is_medium_priority(self):
        lead = _make_lead(status="contacted", score=80)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["priority"], "medium")

    def test_new_below_threshold_is_low_priority(self):
        lead = _make_lead(status="new", score=40)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["priority"], "low")

    def test_closed_lead_generates_no_task(self):
        lead = _make_lead(status="closed", score=90)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(len(tasks), 0)

    def test_lost_lead_generates_no_task(self):
        lead = _make_lead(status="lost", score=85)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(len(tasks), 0)

    def test_tasks_sorted_high_before_medium(self):
        leads = [
            _make_lead(status="contacted", score=80),   # medium
            _make_lead(status="new", score=85),         # high
        ]
        tasks = get_tasks(leads, threshold=60)
        self.assertEqual(tasks[0]["priority"], "high")
        self.assertEqual(tasks[1]["priority"], "medium")

    def test_high_medium_low_order(self):
        leads = [
            _make_lead(status="new", score=30),         # low
            _make_lead(status="contacted", score=70),   # medium
            _make_lead(status="new", score=90),         # high
        ]
        tasks = get_tasks(leads, threshold=60)
        priorities = [t["priority"] for t in tasks]
        self.assertEqual(priorities, ["high", "medium", "low"])

    def test_lead_num_is_1_based(self):
        lead = _make_lead(status="new", score=80)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(tasks[0]["lead_num"], 1)

    def test_lead_name_in_task(self):
        lead = _make_lead(status="new", score=80, first_name="Eve", last_name="Green")
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(tasks[0]["lead_name"], "Eve Green")

    def test_budget_in_detail_field(self):
        lead = _make_lead(status="new", score=80, budget="$500k")
        tasks = get_tasks([lead], threshold=60)
        self.assertIn("$500k", tasks[0]["detail"])

    def test_empty_leads_returns_empty(self):
        self.assertEqual(get_tasks([], threshold=60), [])

    def test_notes_in_medium_action(self):
        lead = _make_lead(status="contacted", score=80, notes="Viewing Saturday 10am")
        tasks = get_tasks([lead], threshold=60)
        self.assertIn("Viewing Saturday", tasks[0]["action"])

    def test_score_exactly_at_threshold_is_high(self):
        lead = _make_lead(status="new", score=60)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(tasks[0]["priority"], "high")

    def test_score_one_below_threshold_is_low(self):
        lead = _make_lead(status="new", score=59)
        tasks = get_tasks([lead], threshold=60)
        self.assertEqual(tasks[0]["priority"], "low")


class TestFormatTaskLine(unittest.TestCase):

    def test_high_priority_label(self):
        task = {
            "priority":  "high",
            "lead_num":  1,
            "lead_name": "Alice Smith",
            "action":    "First contact",
            "detail":    "Budget: $600k",
        }
        line = format_task_line(task, idx=1)
        self.assertIn("[ ! ]", line)
        self.assertIn("Alice Smith", line)
        self.assertIn("First contact", line)
        self.assertIn("$600k", line)

    def test_medium_priority_label(self):
        task = {
            "priority":  "medium",
            "lead_num":  2,
            "lead_name": "Bob Jones",
            "action":    "Follow up",
            "detail":    "",
        }
        line = format_task_line(task, idx=2)
        self.assertIn("[ + ]", line)

    def test_low_priority_label(self):
        task = {
            "priority":  "low",
            "lead_num":  3,
            "lead_name": "Carol White",
            "action":    "Nurture",
            "detail":    "",
        }
        line = format_task_line(task, idx=3)
        self.assertIn("[ · ]", line)

    def test_lead_num_in_line(self):
        task = {
            "priority": "high", "lead_num": 7, "lead_name": "Dan",
            "action": "Call", "detail": ""
        }
        line = format_task_line(task, idx=1)
        self.assertIn("Lead #7", line)

    def test_no_detail_doesnt_crash(self):
        task = {
            "priority": "medium", "lead_num": 2, "lead_name": "Eve",
            "action": "Follow up",
        }
        line = format_task_line(task, idx=1)
        self.assertIn("Eve", line)


if __name__ == "__main__":
    unittest.main()
