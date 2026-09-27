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
            "identifier": "admin@mapua.edu.ph",
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
            self.assertEqual(sess["user"]["email"], "admin@mapua.edu.ph")
            self.assertEqual(sess["user"]["role"], "admin")

    def test_student_registration_and_login(self):
        """Verifies student account registration with MyMail validation and login."""
        # Act 1: Register Student
        reg_response = self.client.post("/register", data={
            "full_name": "Juan Dela Cruz",
            "student_id": "2024180029",
            "email": "jdelacruz@mymail.mapua.edu.ph",
            "program_dept": "BS Computer Engineering",
            "password": "StudentPass2026!",
            "confirm_password": "StudentPass2026!"
        }, follow_redirects=True)

        self.assertEqual(reg_response.status_code, 200)
        self.assertIn(b"Registration successful!", reg_response.data)

        # Act 2: Log in as registered student
        login_response = self.client.post("/login", data={
            "identifier": "2024180029",
            "password": "StudentPass2026!"
        }, follow_redirects=True)

        # Assert
        self.assertEqual(login_response.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["user"]["student_id"], "2024180029")
            self.assertEqual(sess["user"]["role"], "student")

    def test_student_checkin_route_post_and_redirect(self):
        """Verifies student check-in POST request inserts ticket into SQLite and redirects to /ticket/<id>."""
        # Arrange
        form_data = {
            "student_id": "2024109876",
            "full_name": "Maria Santos",
            "email": "msantos@mymail.mapua.edu.ph",
            "request_type": "Application for Graduation",
            "grade_level": "Graduating Senior"
        }

        # Act
        response = self.client.post("/checkin", data=form_data, follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
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
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2024001', 'Juan Dela Cruz', 'jdc@mymail.mapua.edu.ph', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
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
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2024001', 'Juan Dela Cruz', 'jdc@mymail.mapua.edu.ph', 'General Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
        """, (time.time(),))
        conn.commit()
        conn.close()

        # Act
        response = self.client.get("/dashboard")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Queue Monitor", response.data)
        self.assertIn(b"Juan Dela Cruz", response.data)

    def test_call_and_mark_serve_ticket_with_audit_trail(self):
        """Verifies calling and serving a ticket updates status to CALLED then SERVED with audit timestamp & served_by."""
        # Arrange
        self._login_as_admin()
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2021001', 'Alex Senior', 'alex@mymail.mapua.edu.ph', 'Application for Graduation', 1, 'Graduating Senior', 1, ?, 1.0, 'WAITING')
        """, (time.time(),))
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Act 1: Call ticket
        call_res = self.client.post("/call-next", follow_redirects=True)
        self.assertEqual(call_res.status_code, 200)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT status, called_at FROM tickets WHERE id = ?", (ticket_id,))
        row1 = cursor.fetchone()
        conn.close()
        self.assertEqual(row1[0], "CALLED")
        self.assertIsNotNone(row1[1])

        # Act 2: Mark served
        serve_res = self.client.post(f"/ticket/{ticket_id}/serve", follow_redirects=True)
        self.assertEqual(serve_res.status_code, 200)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT status, served_by, served_at FROM tickets WHERE id = ?", (ticket_id,))
        row2 = cursor.fetchone()
        conn.close()
        self.assertEqual(row2[0], "SERVED")
        self.assertEqual(row2[1], "admin@mapua.edu.ph")
        self.assertIsNotNone(row2[2])

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
            "student_id": "2024990011",
            "email": "jsmith@mapua.edu.ph",
            "password": "StaffPassword2026!",
            "full_name": "John Smith",
            "role": "staff",
            "program_dept": "Registrar Counter 2"
        }, follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"jsmith@mapua.edu.ph", response.data)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT email, full_name, role FROM users WHERE email = 'jsmith@mapua.edu.ph'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "jsmith@mapua.edu.ph")
        self.assertEqual(row[1], "John Smith")
        self.assertEqual(row[2], "staff")


if __name__ == "__main__":
    unittest.main()
