"""
MapuaQ Email Notification Subsystem Tests
Isolated environment preventing live network calls and dev DB pollution.
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TEST_DB_PATH = os.path.join(PROJECT_ROOT, "tests", "test_students_queue.db")
os.environ["DB_NAME"] = TEST_DB_PATH

from config import Config
import notifier


class MapuaQNotifierTestCase(unittest.TestCase):
    def setUp(self):
        Config.DB_NAME = TEST_DB_PATH
        Config.EMAIL_DEV_MODE = True

    def test_notify_ticket_created_mock_dispatch(self):
        ticket_data = {
            "id": 101,
            "full_name": "Test Student",
            "email": "test@mymail.mapua.edu.ph",
            "request_type": "Application for Graduation",
            "estimated_wait_mins": 5
        }
        success = notifier.notify_ticket_created(ticket_data)
        self.assertTrue(success)

    def test_notify_student_called_mock_dispatch(self):
        ticket_data = {
            "id": 102,
            "full_name": "Called Student",
            "email": "called@mymail.mapua.edu.ph",
            "request_type": "Course Completion"
        }
        success = notifier.notify_student_called(ticket_data, counter_number="Counter 1")
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()