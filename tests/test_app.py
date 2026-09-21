"""
MapuaQ: Integration Route Unit Tests (Flask Client, Session Auth & Endpoints)
Follows strict Arrange-Act-Assert (AAA) pattern.
"""

import os
import sqlite3
import unittest
import time
from app import app, init_db, DB


class TestMapuaQRoutes(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret'
        self.client = app.test_client()
        
        # Clean & re-initialize test database
        conn = sqlite3.connect(DB)
        conn.execute("DROP TABLE IF EXISTS tickets")
        conn.execute("DROP TABLE IF EXISTS users")
        conn.commit()
        conn.close()
        
        init_db()

    def _login_as_admin(self):
        """Helper to authenticate test client session as Admin."""
        return self.client.post("/login", data={
            "username": "admin",
            "password": "MapuaAdmin2026!"
        }, follow_redirects=True)

    def test_admin_login_success(self):
        """Verifies login authentication with seeded admin credentials."""
        # Act
        response = self._login_as_admin()

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Queue Monitor", response.data)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["user"]["username"], "admin")
            self.assertEqual(sess["user"]["role"], "admin")

    def test_student_checkin_route_post_and_redirect(self):
        """Verifies student check-in POST request inserts ticket into SQLite and redirects to /ticket/<id>."""
        # Arrange
        form_data = {
            "student_id": "2024109876",
            "full_name": "Maria Santos",
            "request_type": "Application for Graduation",
            "grade_level": "Graduating Senior"
        }

        # Act
        response = self.client.post("/checkin", data=form_data, follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ticket", response.data)
        self.assertIn(b"Maria Santos", response.data)
        
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT id, student_id, full_name, priority_score, status FROM tickets WHERE student_id = '2024109876'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[1], "2024109876")
        self.assertEqual(row[2], "Maria Santos")
        self.assertEqual(row[3], 1.0)  # (1 * 0.6) + (1 * 0.4) = 1.0
        self.assertEqual(row[4], "WAITING")

    def test_ticket_status_route_get(self):
        """Verifies /ticket/<id> renders live tracking info for students."""
        # Arrange
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2024001', 'Juan Dela Cruz', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
        """, (time.time(),))
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Act
        response = self.client.get(f"/ticket/{ticket_id}")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Juan Dela Cruz", response.data)
        self.assertIn(b"In Queue (Waiting)", response.data)

    def test_dashboard_route_authenticated_get(self):
        """Verifies GET /dashboard loads Min-Heap ordered tickets for authenticated staff."""
        # Arrange
        self._login_as_admin()
        conn = sqlite3.connect(DB)
        conn.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2024001', 'Juan Dela Cruz', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
        """, (time.time(),))
        conn.commit()
        conn.close()

        # Act
        response = self.client.get("/dashboard")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Queue Monitor", response.data)
        self.assertIn(b"Juan Dela Cruz", response.data)

    def test_call_next_ticket_post_with_audit_trail(self):
        """Verifies POST /call-next pops root ticket and updates status to SERVED with audit timestamp & served_by."""
        # Arrange
        self._login_as_admin()
        conn = sqlite3.connect(DB)
        conn.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2021001', 'Alex Senior', 'Application for Graduation', 1, 'Graduating Senior', 1, ?, 1.0, 'WAITING')
        """, (time.time(),))
        conn.commit()
        conn.close()

        # Act
        response = self.client.post("/call-next", follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT status, served_by, served_at FROM tickets WHERE student_id = '2021001'")
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "SERVED")
        self.assertEqual(row[1], "admin")
        self.assertIsNotNone(row[2])

    def test_analytics_dashboard_route_authenticated_get(self):
        """Verifies GET /analytics renders metrics cards for authenticated staff."""
        # Arrange
        self._login_as_admin()

        # Act
        response = self.client.get("/analytics")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Queue Volume & Priority Analytics", response.data)

    def test_admin_provision_new_staff_account(self):
        """Verifies admin POST /admin/users provisions new staff user account."""
        # Arrange
        self._login_as_admin()

        # Act
        response = self.client.post("/admin/users", data={
            "username": "jsmith",
            "password": "StaffPassword2026!",
            "full_name": "John Smith",
            "role": "staff"
        }, follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"jsmith", response.data)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT username, full_name, role FROM users WHERE username = 'jsmith'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "jsmith")
        self.assertEqual(row[1], "John Smith")
        self.assertEqual(row[2], "staff")


if __name__ == "__main__":
    unittest.main()
