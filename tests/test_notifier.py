"""
Unit and Integration Tests for MapuaQ Automated Email Notification Service (notifier.py)
"""

import unittest
from config import Config
import notifier


class TestNotifierModule(unittest.TestCase):
    def setUp(self):
        Config.EMAIL_DEV_MODE = True

    def test_notify_ticket_created_dev_mode(self):
        """Verifies notify_ticket_created formats mock email in Dev Mode."""
        ticket_data = {
            "id": 101,
            "student_id": "2024100001",
            "full_name": "Test Student",
            "email": "test@mymail.mapua.edu.ph",
            "request_type": "Application for Graduation",
            "estimated_wait_mins": 5
        }
        result = notifier.notify_ticket_created(ticket_data)
        self.assertTrue(result)

    def test_notify_student_called_dev_mode(self):
        """Verifies notify_student_called formats mock email in Dev Mode."""
        ticket_data = {
            "id": 102,
            "student_id": "2024100002",
            "full_name": "Called Student",
            "email": "called@mymail.mapua.edu.ph",
            "request_type": "Course Completion"
        }
        result = notifier.notify_student_called(ticket_data, counter_number="Counter 1")
        self.assertTrue(result)

    def test_notify_student_skipped_dev_mode(self):
        """Verifies notify_student_skipped formats mock email in Dev Mode."""
        ticket_data = {
            "id": 103,
            "student_id": "2024100003",
            "full_name": "Skipped Student",
            "email": "skipped@mymail.mapua.edu.ph",
            "request_type": "Transcript of Records (TOR)"
        }
        result = notifier.notify_student_skipped(ticket_data)
        self.assertTrue(result)

    def test_notify_ticket_served_dev_mode(self):
        """Verifies notify_ticket_served formats mock email in Dev Mode."""
        ticket_data = {
            "id": 104,
            "student_id": "2024100004",
            "full_name": "Served Student",
            "email": "served@mymail.mapua.edu.ph",
            "request_type": "Overload / Waiver",
            "remarks": "Approved and signed by Registrar"
        }
        result = notifier.notify_ticket_served(ticket_data)
        self.assertTrue(result)

    def test_empty_email_graceful_handling(self):
        """Verifies empty email address returns False gracefully without error."""
        ticket_data = {"id": 105, "email": "", "full_name": "No Email Student"}
        result = notifier.notify_ticket_created(ticket_data)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
