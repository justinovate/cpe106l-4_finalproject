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

    def test_send_password_reset_notice_dev_mode(self):
        """Verifies send_password_reset_notice formats security email in Dev Mode."""
        result = notifier.send_password_reset_notice(
            to_email="studentreset@mymail.mapua.edu.ph",
            full_name="Reset Student",
            temp_password="TempPass123"
        )
        self.assertTrue(result)

    def test_send_welcome_account_notice_dev_mode(self):
        """Verifies send_welcome_account_notice formats account creation & verification email in Dev Mode."""
        result = notifier.send_welcome_account_notice(
            to_email="newstudent@mymail.mapua.edu.ph",
            full_name="New Provisioned Student",
            account_id="2026100001",
            default_password="DefaultPass123!",
            verification_token="mock_verify_token_12345",
            role="student"
        )
        self.assertTrue(result)

    def test_smtp_delivery_fallback_on_error(self):
        """Verifies SMTP delivery failure logs error and falls back without crashing."""
        Config.EMAIL_DEV_MODE = False
        Config.SMTP_USERNAME = "invalid_user@mapua.edu.ph"
        Config.SMTP_PASSWORD = "invalid_password"
        Config.SMTP_SERVER = "invalid.smtp.server.local"

        result = notifier.send_password_reset_notice(
            to_email="fallback@mymail.mapua.edu.ph",
            full_name="Fallback Student",
            temp_password="TempPass456"
        )
        self.assertTrue(result)
        Config.EMAIL_DEV_MODE = True


if __name__ == "__main__":
    unittest.main()
