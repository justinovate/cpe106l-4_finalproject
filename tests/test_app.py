"""
MapuaQ Integration & Route Test Suite
Strictly isolated from development/production students_queue.db.
Import ordering enforced via os.environ['DB_NAME'] to eliminate race conditions.
"""

import os
import sys
import unittest
import sqlite3
import time

# 1. Resolve project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 2. MUST set environment variable BEFORE importing Config or app
TEST_DB_PATH = os.path.join(PROJECT_ROOT, "tests", "test_students_queue.db")
os.environ["DB_NAME"] = TEST_DB_PATH

# 3. Now import Config and app safely
from werkzeug.security import generate_password_hash
from config import Config
from app import app, init_db


class MapuaQIsolatedAppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Configure test environment once for class."""
        Config.DB_NAME = TEST_DB_PATH
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def setUp(self):
        """Set up an isolated test database for each test case."""
        Config.DB_NAME = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass
        init_db()

    def tearDown(self):
        """Clean up isolated test database file after each test case."""
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass

    def test_database_isolation_does_not_touch_dev_db(self):
        """Verify tests run against TEST_DB_PATH and dev DB is untouched."""
        self.assertEqual(Config.DB_NAME, TEST_DB_PATH)
        self.assertTrue(os.path.exists(TEST_DB_PATH))
        self.assertNotEqual(os.path.basename(TEST_DB_PATH), "students_queue.db")

    def test_kiosk_checkin_flow(self):
        """Test student check-in route when authenticated."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO students (student_id, email, password_hash, full_name, program_dept, created_at, email_verified)
            VALUES ('2024180099', 'testisolated@mymail.mapua.edu.ph', ?, 'Test Isolated Student', 'BS CS', ?, 1)
        """, (generate_password_hash("StudentPass123!"), time.time()))
        conn.commit()
        conn.close()

        self.client.post("/login", data={
            "identifier": "2024180099",
            "password": "StudentPass123!"
        })

        response = self.client.post("/checkin", data={
            "student_id": "2024180099",
            "full_name": "Test Isolated Student",
            "email": "testisolated@mymail.mapua.edu.ph",
            "request_type": "Application for Graduation",
            "grade_level": "Graduating Senior"
        }, follow_redirects=False)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ticket/", response.location)

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, status FROM tickets WHERE email = ?", ("testisolated@mymail.mapua.edu.ph",))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "2024180099")
        self.assertEqual(row[1], "WAITING")

    def test_staff_login_and_dashboard_access(self):
        """Test staff authentication and dashboard authorization guard."""
        login_resp = self.client.post("/login", data={
            "identifier": "registrar@mapua.edu.ph",
            "password": "StaffPass2026!"
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

        dash_resp = self.client.get("/dashboard")
        self.assertEqual(dash_resp.status_code, 200)

    def test_ticket_soft_void_endpoint(self):
        """Test soft-delete / void route for staff."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2024180088', 'Void Student', 'void@mymail.mapua.edu.ph', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
        """, (time.time(),))
        t_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Login staff
        self.client.post("/login", data={"identifier": "registrar@mapua.edu.ph", "password": "StaffPass2026!"})

        # Void ticket
        void_resp = self.client.post(f"/tickets/{t_id}/void", data={"void_reason": "Duplicate check-in entry"}, follow_redirects=True)
        self.assertEqual(void_resp.status_code, 200)

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, remarks FROM tickets WHERE id = ?", (t_id,))
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "CANCELLED")
        self.assertIn("Voided: Duplicate check-in entry", row[1])


if __name__ == "__main__":
    unittest.main()