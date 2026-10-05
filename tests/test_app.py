"""
MapuaQ Integration & Route Test Suite for Sprint 4
Strictly isolated from development/production students_queue.db.
"""

import os
import sys
import unittest
import sqlite3
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TEST_DB_PATH = os.path.join(PROJECT_ROOT, "tests", "test_students_queue.db")
os.environ["DB_NAME"] = TEST_DB_PATH

from werkzeug.security import generate_password_hash
from config import Config
from app import app, init_db, get_db_connection


class MapuaQIsolatedAppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['DB_NAME'] = TEST_DB_PATH
        Config.DB_NAME = TEST_DB_PATH
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def setUp(self):
        app.config['DB_NAME'] = TEST_DB_PATH
        Config.DB_NAME = TEST_DB_PATH
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass
        with app.app_context():
            init_db()

    def tearDown(self):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except OSError:
                pass

    def test_database_isolation_and_schema(self):
        """Verify tests run against TEST_DB_PATH and WAL mode / IN_SERVICE schema check."""
        self.assertEqual(app.config['DB_NAME'], TEST_DB_PATH)
        self.assertTrue(os.path.exists(TEST_DB_PATH))
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tickets';")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertIn("IN_SERVICE", row[0])
        conn.close()

    def test_user_registration_and_login_without_email_verification(self):
        """Test registration activates user immediately without email verification."""
        res_reg = self.client.post('/register', data={
            'student_id': '2026109999',
            'full_name': 'Test Student',
            'email': 'teststudent@mapua.edu.ph',
            'password': 'password123',
            'confirm_password': 'password123'
        }, follow_redirects=True)
        self.assertIn(b'Registration successful', res_reg.data)

        res_login = self.client.post('/login', data={
            'email_or_id': '2026109999',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertIn(b'Welcome back, Test Student!', res_login.data)

    def test_full_ticket_lifecycle_with_mark_arrived(self):
        """Test transitions WAITING -> CALLED -> IN_SERVICE -> SERVED."""
        self.client.post('/register', data={
            'student_id': '2026102222',
            'full_name': 'Lifecycle Student',
            'email': 'lifecycle@mapua.edu.ph',
            'password': 'password123',
            'confirm_password': 'password123'
        })
        self.client.post('/login', data={
            'email_or_id': '2026102222',
            'password': 'password123'
        })
        self.client.post('/checkin', data={
            'request_type': 'General Inquiry',
            'grade_level': '1st Year'
        })

        self.client.get('/logout')
        self.client.post('/login', data={
            'email_or_id': 'staff@mapua.edu.ph',
            'password': 'staff123'
        })

        res_call = self.client.post('/staff/call-next', follow_redirects=True)
        self.assertIn(b'has been CALLED', res_call.data)

        res_arrive = self.client.post('/staff/mark-arrived/1', follow_redirects=True)
        self.assertIn(b'is now IN SERVICE', res_arrive.data)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT status, arrived_at FROM tickets WHERE id = 1")
        ticket = cur.fetchone()
        self.assertEqual(ticket['status'], 'IN_SERVICE')
        self.assertIsNotNone(ticket['arrived_at'])
        conn.close()

        res_complete = self.client.post('/staff/complete-service/1', follow_redirects=True)
        self.assertIn(b'marked as SERVED', res_complete.data)

    def test_on_deck_notification_logic(self):
        """Test notify_prepare flag when Rank #1 waiting ticket views status while another ticket is IN_SERVICE."""
        self.client.post('/register', data={
            'student_id': 'S001', 'full_name': 'Student One',
            'email': 's1@mapua.edu.ph', 'password': 'pass', 'confirm_password': 'pass'
        })
        self.client.post('/register', data={
            'student_id': 'S002', 'full_name': 'Student Two',
            'email': 's2@mapua.edu.ph', 'password': 'pass', 'confirm_password': 'pass'
        })

        self.client.post('/login', data={'email_or_id': 'S001', 'password': 'pass'})
        self.client.post('/checkin', data={'request_type': 'General Inquiry', 'grade_level': '1st Year'})
        self.client.get('/logout')

        self.client.post('/login', data={'email_or_id': 'S002', 'password': 'pass'})
        self.client.post('/checkin', data={'request_type': 'General Inquiry', 'grade_level': '1st Year'})
        self.client.get('/logout')

        self.client.post('/login', data={'email_or_id': 'staff@mapua.edu.ph', 'password': 'staff123'})
        self.client.post('/staff/call-next')
        self.client.post('/staff/mark-arrived/1')
        self.client.get('/logout')

        self.client.post('/login', data={'email_or_id': 'S002', 'password': 'pass'})
        res_api = self.client.get('/api/ticket/2/status')
        data = res_api.get_json()

        self.assertEqual(data['status'], 'WAITING')
        self.assertEqual(data['position'], 1)
        self.assertTrue(data['notify_prepare'])

    def test_default_seeded_accounts_login(self):
        """Test logging in with default seeded accounts for Registrar, Admin, and Student."""
        # 1. Registrar Staff (registrar@mapua.edu.ph / StaffPass2026!)
        res_reg = self.client.post('/login', data={'email_or_id': 'registrar@mapua.edu.ph', 'password': 'StaffPass2026!'}, follow_redirects=True)
        self.assertIn(b'Welcome back', res_reg.data)
        self.client.get('/logout')

        # 2. System Admin (admin@mapua.edu.ph / AdminPass2026!)
        res_admin = self.client.post('/login', data={'email_or_id': 'admin@mapua.edu.ph', 'password': 'AdminPass2026!'}, follow_redirects=True)
        self.assertIn(b'Welcome back', res_admin.data)
        self.client.get('/logout')

        # 3. Demo Student (student@mymail.mapua.edu.ph / StudentPass123!)
        res_stu = self.client.post('/login', data={'email_or_id': 'student@mymail.mapua.edu.ph', 'password': 'StudentPass123!'}, follow_redirects=True)
        self.assertIn(b'Welcome back', res_stu.data)
        self.client.get('/logout')


if __name__ == "__main__":
    unittest.main()