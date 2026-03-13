"""
Tests for services/appointments.py
"""
from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("AGENT_CHAT_IDS", "123")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from services.appointments import (
    format_appointment_card,
    get_all_appointments,
    merge_appointments,
    parse_appointments_from_leads,
)


class TestParseAppointmentsFromLeads(unittest.TestCase):

    def test_note_with_viewing_is_detected(self):
        leads = [
            {"first_name": "Alice", "last_name": "Brown", "agent_notes": "Viewing booked Saturday 10am"},
        ]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["lead_num"], 1)
        self.assertEqual(result[0]["lead_name"], "Alice Brown")
        self.assertEqual(result[0]["type"], "Property Viewing")

    def test_note_with_call_is_detected(self):
        leads = [
            {"first_name": "Bob", "last_name": "Smith", "agent_notes": "Call scheduled for Tuesday"},
        ]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "Call")

    def test_note_with_consultation_is_detected(self):
        leads = [
            {"first_name": "Carl", "last_name": "Jones", "agent_notes": "Consultation arranged"},
        ]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "Consultation")

    def test_empty_note_not_detected(self):
        leads = [{"first_name": "Dan", "last_name": "Lee", "agent_notes": ""}]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(len(result), 0)

    def test_irrelevant_note_not_detected(self):
        leads = [{"first_name": "Eva", "last_name": "Fox", "agent_notes": "Sent listings PDF"}]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(len(result), 0)

    def test_missing_notes_field_not_detected(self):
        leads = [{"first_name": "Frank", "last_name": "Bay"}]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(len(result), 0)

    def test_lead_index_is_1_based(self):
        leads = [
            {"first_name": "A", "last_name": "B", "agent_notes": ""},
            {"first_name": "C", "last_name": "D", "agent_notes": "Viewing Saturday"},
        ]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(result[0]["lead_num"], 2)

    def test_name_falls_back_when_missing(self):
        leads = [{"agent_notes": "Booked valuation"}]
        result = parse_appointments_from_leads(leads)
        self.assertEqual(result[0]["lead_name"], "Lead #1")


class TestMergeAppointments(unittest.TestCase):

    def test_demo_takes_precedence_over_notes(self):
        demo = [{"lead_num": 1, "lead_name": "Demo Lead", "type": "Call", "source": "demo"}]
        notes = [{"lead_num": 1, "lead_name": "Notes Lead", "type": "Viewing", "source": "notes"}]
        merged = merge_appointments(demo, notes)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source"], "demo")

    def test_non_overlapping_entries_are_combined(self):
        demo  = [{"lead_num": 1, "lead_name": "A", "type": "Call", "source": "demo"}]
        notes = [{"lead_num": 2, "lead_name": "B", "type": "Viewing", "source": "notes"}]
        merged = merge_appointments(demo, notes)
        self.assertEqual(len(merged), 2)

    def test_entries_with_datetime_sorted_first(self):
        demo  = [{"lead_num": 1, "lead_name": "A", "datetime_str": "2025-04-01 10:00", "source": "demo"}]
        notes = [{"lead_num": 2, "lead_name": "B", "source": "notes"}]
        merged = merge_appointments(demo, notes)
        # Entry with datetime_str should come first
        self.assertEqual(merged[0]["lead_num"], 1)


class TestFormatAppointmentCard(unittest.TestCase):

    def test_basic_card_contains_lead_info(self):
        appt = {
            "lead_num":     3,
            "lead_name":    "James Wilson",
            "type":         "Property Viewing",
            "datetime_str": "2025-03-15 10:00",
            "note":         "Saturday morning viewing",
        }
        card = format_appointment_card(appt, idx=1)
        self.assertIn("James Wilson", card)
        self.assertIn("Lead #3", card)
        self.assertIn("2025-03-15 10:00", card)
        self.assertIn("Saturday morning viewing", card)

    def test_card_without_datetime_still_renders(self):
        appt = {
            "lead_num":  1,
            "lead_name": "Sarah Johnson",
            "type":      "Consultation Call",
            "note":      "Initial call",
        }
        card = format_appointment_card(appt, idx=1)
        self.assertIn("Sarah Johnson", card)
        self.assertNotIn("When:", card)

    def test_card_index_shown(self):
        appt = {"lead_num": 2, "lead_name": "Bob", "type": "Call", "note": "Quick call"}
        card = format_appointment_card(appt, idx=5)
        self.assertIn("5.", card)


class TestGetAllAppointments(unittest.TestCase):

    def test_combines_demo_and_note_appointments(self):
        demo = [{"lead_num": 10, "lead_name": "Demo", "type": "Call", "source": "demo"}]
        leads = [
            {"first_name": "Alice", "last_name": "B", "agent_notes": "Viewing Tuesday"},
        ]
        result = get_all_appointments(demo, leads)
        lead_nums = [a["lead_num"] for a in result]
        self.assertIn(10, lead_nums)
        self.assertIn(1, lead_nums)

    def test_empty_leads_still_returns_demo(self):
        demo = [{"lead_num": 1, "lead_name": "X", "type": "Call", "source": "demo"}]
        result = get_all_appointments(demo, [])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
