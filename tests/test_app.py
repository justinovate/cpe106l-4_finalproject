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

    def test_default_credentials_seeding(self):
        """Verify Admin and Registrar Staff pre-seeded credentials allow login."""
        # Test Admin login
        admin_login = self.client.post("/login", data={
            "identifier": "admin@mapua.edu.ph",
            "password": "MapuaAdmin2026!"
        }, follow_redirects=True)
        self.assertEqual(admin_login.status_code, 200)

        # Test Staff login
        staff_login = self.client.post("/login", data={
            "identifier": "registrar@mapua.edu.ph",
            "password": "StaffPass2026!"
        }, follow_redirects=True)
        self.assertEqual(staff_login.status_code, 200)

    def test_student_registration_and_active_login(self):
        """Test student self-registration and immediate active access (email_verified=1)."""
        reg_resp = self.client.post("/register", data={
            "student_id": "2026109999",
            "full_name": "Registered Student",
            "email": "registered@mymail.mapua.edu.ph",
            "program_dept": "BS CS",
            "password": "StudentPass123!",
            "confirm_password": "StudentPass123!"
        }, follow_redirects=False)
        self.assertEqual(reg_resp.status_code, 302)

        login_resp = self.client.post("/login", data={
            "identifier": "registered@mymail.mapua.edu.ph",
            "password": "StudentPass123!"
        }, follow_redirects=True)
        self.assertEqual(login_resp.status_code, 200)

    def test_kiosk_checkin_flow(self):
        """Test student check-in route when authenticated."""
        self.client.post("/register", data={
            "student_id": "2024180099",
            "full_name": "Test Isolated Student",
            "email": "testisolated@mymail.mapua.edu.ph",
            "program_dept": "BS CS",
            "password": "StudentPass123!",
            "confirm_password": "StudentPass123!"
        })

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

    def test_decoupled_counter_lifecycle_called_arrive_serve(self):
        """Test decoupled counter lifecycle: WAITING -> CALLED -> IN_SERVICE -> SERVED."""
        # Create ticket
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2026100001', 'Flow Student', 'flow@mymail.mapua.edu.ph', 'Course Completion', 2, 'Senior (Non-Graduating)', 3, ?, 2.4, 'WAITING')
        """, (time.time(),))
        t_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Login Staff
        self.client.post("/login", data={"identifier": "registrar@mapua.edu.ph", "password": "StaffPass2026!"})

        # 1. Call ticket
        call_resp = self.client.post(f"/tickets/{t_id}/call", follow_redirects=True)
        self.assertEqual(call_resp.status_code, 200)

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, called_at FROM tickets WHERE id = ?", (t_id,))
        c_row = cursor.fetchone()
        conn.close()
        self.assertEqual(c_row[0], "CALLED")
        self.assertIsNotNone(c_row[1])

        # 2. Mark Arrived
        arrive_resp = self.client.post(f"/staff/mark-arrived/{t_id}", follow_redirects=True)
        self.assertEqual(arrive_resp.status_code, 200)

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, arrived_at FROM tickets WHERE id = ?", (t_id,))
        a_row = cursor.fetchone()
        conn.close()
        self.assertEqual(a_row[0], "IN_SERVICE")
        self.assertIsNotNone(a_row[1])

        # 3. Complete Service
        serve_resp = self.client.post(f"/tickets/{t_id}/serve", data={"remarks": "Processed TOR"}, follow_redirects=True)
        self.assertEqual(serve_resp.status_code, 200)

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, served_at, remarks FROM tickets WHERE id = ?", (t_id,))
        s_row = cursor.fetchone()
        conn.close()
        self.assertEqual(s_row[0], "SERVED")
        self.assertIsNotNone(s_row[1])
        self.assertEqual(s_row[2], "Processed TOR")

    def test_counter_skip_and_rejoin_with_penalty(self):
        """Test skipping a ticket and re-joining queue with +2.0 priority penalty."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2026100002', 'Skip Student', 'skip@mymail.mapua.edu.ph', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
        """, (time.time(),))
        t_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Login Staff
        self.client.post("/login", data={"identifier": "registrar@mapua.edu.ph", "password": "StaffPass2026!"})
        self.client.post(f"/tickets/{t_id}/call")

        # Skip ticket
        self.client.post(f"/tickets/{t_id}/skip", data={"skip_reason": "No-show"})

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, skipped_at FROM tickets WHERE id = ?", (t_id,))
        sk_row = cursor.fetchone()
        conn.close()
        self.assertEqual(sk_row[0], "SKIPPED")

        # Login as student & Rejoin
        self.client.post("/register", data={
            "student_id": "2026100002",
            "full_name": "Skip Student",
            "email": "skip@mymail.mapua.edu.ph",
            "password": "StudentPass123!",
            "confirm_password": "StudentPass123!"
        })
        self.client.post("/login", data={"identifier": "2026100002", "password": "StudentPass123!"})

        rejoin_resp = self.client.post(f"/ticket/{t_id}/rejoin", follow_redirects=True)
        self.assertEqual(rejoin_resp.status_code, 200)

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, penalty_offset, rejoin_used FROM tickets WHERE id = ?", (t_id,))
        rj_row = cursor.fetchone()
        conn.close()
        self.assertEqual(rj_row[0], "WAITING")
        self.assertEqual(rj_row[1], 2.0)
        self.assertEqual(rj_row[2], 1)

    def test_on_deck_notification_flag(self):
        """Test is_on_deck flag is True when another ticket is IN_SERVICE and viewing ticket is Rank #1 waiting."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        now = time.time()
        # Ticket 1 (In Service)
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2026100010', 'In Service Student', 'inservice@mymail.mapua.edu.ph', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'IN_SERVICE')
        """, (now,))
        # Ticket 2 (Rank #1 Waiting)
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2026100011', 'On Deck Student', 'ondeck@mymail.mapua.edu.ph', 'Application for Graduation', 1, 'Graduating Senior', 1, ?, 1.0, 'WAITING')
        """, (now,))
        t2_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Check API status JSON endpoint
        api_resp = self.client.get(f"/api/ticket/{t2_id}/status")
        self.assertEqual(api_resp.status_code, 200)
        json_data = api_resp.get_json()
        self.assertTrue(json_data["is_on_deck"])

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

    def test_admin_delete_ticket_endpoint(self):
        """Test admin permanent hard deletion of ticket."""
        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2024180077', 'Delete Student', 'delete@mymail.mapua.edu.ph', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
        """, (time.time(),))
        t_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Login Admin
        self.client.post("/login", data={"identifier": "admin@mapua.edu.ph", "password": "MapuaAdmin2026!"})

        # Hard Delete
        del_resp = self.client.post(f"/tickets/{t_id}/delete", follow_redirects=True)
        self.assertEqual(del_resp.status_code, 200)

        conn = sqlite3.connect(TEST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tickets WHERE id = ?", (t_id,))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main()