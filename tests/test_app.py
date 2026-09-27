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
        conn.execute("DROP TABLE IF EXISTS staff_users")
        conn.execute("DROP TABLE IF EXISTS students")
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

    def test_admin_provision_student_account_and_login(self):
        """Verifies admin POST /admin/users provisions student account and student logs in."""
        # Act 1: Admin provisions student account
        self._login_as_admin()
        prov_res = self.client.post("/admin/users", data={
            "student_id": "2024000001",
            "email": "jdelacruz@mymail.mapua.edu.ph",
            "full_name": "Juan Dela Cruz",
            "program_dept": "BS Computer Engineering",
            "password": "StudentPass2026!",
            "role": "student"
        }, follow_redirects=True)

        self.assertEqual(prov_res.status_code, 200)
        self.assertIn(b"jdelacruz@mymail.mapua.edu.ph", prov_res.data)

        # Act 2: Log out admin and log in as provisioned student
        self.client.get("/logout")
        login_res = self.client.post("/login", data={
            "identifier": "2024000001",
            "password": "StudentPass2026!"
        }, follow_redirects=True)

        # Assert: Student login redirects to checkin kiosk
        self.assertEqual(login_res.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["user"]["student_id"], "2024000001")
            self.assertEqual(sess["user"]["role"], "student")

    def test_student_checkin_route_post_and_redirect(self):
        """Verifies authenticated student check-in POST inserts ticket into SQLite and redirects to /ticket/<id>."""
        # Arrange: Provision student and log in
        self._login_as_admin()
        self.client.post("/admin/users", data={
            "student_id": "2024000002",
            "email": "msantos@mymail.mapua.edu.ph",
            "full_name": "Maria Santos",
            "program_dept": "BS Electrical Engineering",
            "password": "StudentPass2026!",
            "role": "student"
        })
        self.client.get("/logout")
        self.client.post("/login", data={
            "identifier": "2024000002",
            "password": "StudentPass2026!"
        })

        form_data = {
            "student_id": "2024000002",
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
        cursor.execute("SELECT id, student_id, full_name, priority_score, status FROM tickets WHERE student_id = '2024000002'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[1], "2024000002")
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

    def test_skip_ticket_route(self):
        """Verifies POST /tickets/<id>/skip transitions ticket to SKIPPED with reason remarks."""
        # Arrange
        self._login_as_admin()
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2021002', 'Bob Junior', 'bob@mymail.mapua.edu.ph', 'General Inquiry', 9, 'Junior', 5, ?, 5.0, 'CALLED')
        """, (time.time(),))
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Act
        res = self.client.post(f"/tickets/{ticket_id}/skip", data={"skip_reason": "No-show after 3 calls"}, follow_redirects=True)

        # Assert
        self.assertEqual(res.status_code, 200)
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT status, remarks FROM tickets WHERE id = ?", (ticket_id,))
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "SKIPPED")
        self.assertEqual(row[1], "No-show after 3 calls")

    def test_call_ticket_concurrency_prevention(self):
        """Verifies system prevents calling a second ticket when a ticket is already CALLED."""
        # Arrange: create one CALLED ticket and one WAITING ticket
        self._login_as_admin()
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2021003', 'Active Student', 'active@mymail.mapua.edu.ph', 'TOR', 4, 'Senior', 3, ?, 3.0, 'CALLED')
        """, (time.time(),))
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2021004', 'Waiting Student', 'waiting@mymail.mapua.edu.ph', 'Overload', 2, 'Senior', 3, ?, 2.0, 'WAITING')
        """, (time.time(),))
        waiting_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Act: try calling second ticket
        res = self.client.post(f"/tickets/{waiting_id}/call", follow_redirects=True)

        # Assert: warning flash message prevents duplicate call
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Counter currently has an active called ticket", res.data)

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
        cursor.execute("SELECT email, full_name, role FROM staff_users WHERE email = 'jsmith@mapua.edu.ph'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "jsmith@mapua.edu.ph")
        self.assertEqual(row[1], "John Smith")
        self.assertEqual(row[2], "staff")

    def test_admin_delete_student_account_with_confirmation(self):
        """Verifies POST /admin/users/delete permanently removes student account when typing DELETE."""
        # Arrange: Provision student account
        self._login_as_admin()
        self.client.post("/admin/users", data={
            "student_id": "2024777001",
            "email": "delstudent@mymail.mapua.edu.ph",
            "full_name": "Delete Me",
            "password": "StudentPass2026!",
            "role": "student"
        })

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM students WHERE email = 'delstudent@mymail.mapua.edu.ph'")
        std_id = cursor.fetchone()[0]
        conn.close()

        # Act: Submit delete form with confirm_text = 'DELETE'
        res = self.client.post("/admin/users/delete", data={
            "target_type": "student",
            "user_id": std_id,
            "confirm_text": "DELETE"
        }, follow_redirects=True)

        # Assert: Student account removed from database
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"permanently deleted", res.data)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students WHERE id = ?", (std_id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_admin_delete_user_canceled_without_delete_confirmation(self):
        """Verifies account deletion is canceled if user fails to type DELETE in confirmation box."""
        # Arrange: Provision student account
        self._login_as_admin()
        self.client.post("/admin/users", data={
            "student_id": "2024777002",
            "email": "keepstudent@mymail.mapua.edu.ph",
            "full_name": "Keep Me",
            "password": "StudentPass2026!",
            "role": "student"
        })

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM students WHERE email = 'keepstudent@mymail.mapua.edu.ph'")
        std_id = cursor.fetchone()[0]
        conn.close()

        # Act: Submit delete form with incorrect confirm_text
        res = self.client.post("/admin/users/delete", data={
            "target_type": "student",
            "user_id": std_id,
            "confirm_text": "cancel"
        }, follow_redirects=True)

        # Assert: Warning flashed and student account remains in database
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Deletion canceled", res.data)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students WHERE id = ?", (std_id,))
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)

    def test_admin_reset_queue_route(self):
        """Verifies admin POST /admin/reset-queue purges tickets from database."""
        # Arrange: Login as admin and create a ticket
        self._login_as_admin()
        self.client.post("/checkin", data={
            "student_id": "2024888888",
            "full_name": "Test Reset Student",
            "email": "reset@mymail.mapua.edu.ph",
            "request_type": "General Inquiry",
            "grade_level": "Freshman"
        })

        # Act
        response = self.client.post("/admin/reset-queue", data={"scope": "all"}, follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tickets")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_student_dashboard_route_and_name_reflection(self):
        """Verifies student login reflects real full_name (not password hash) and renders /student portal."""
        # Arrange: Provision student
        self._login_as_admin()
        self.client.post("/admin/users", data={
            "student_id": "2024180029",
            "email": "jaddeleon@mymail.mapua.edu.ph",
            "full_name": "Jad De Leon",
            "program_dept": "BS Computer Engineering",
            "password": "StudentPass2026!",
            "role": "student"
        })
        self.client.get("/logout")

        # Act: Log in as student
        res = self.client.post("/login", data={
            "identifier": "2024180029",
            "password": "StudentPass2026!"
        }, follow_redirects=True)

        # Assert: Lands on Student Portal (/student) with full_name reflecting correctly
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Welcome back, Jad De Leon!", res.data)
        self.assertNotIn(b"scrypt:", res.data)
        
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["user"]["full_name"], "Jad De Leon")
            self.assertEqual(sess["user"]["email"], "jaddeleon@mymail.mapua.edu.ph")
            self.assertEqual(sess["user"]["role"], "student")


if __name__ == "__main__":
    unittest.main()
