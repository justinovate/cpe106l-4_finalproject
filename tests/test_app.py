"""
MapuaQ: Integration Route Unit Tests (Flask Client & Endpoints)
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
        self.client = app.test_client()
        
        # Re-initialize test database
        init_db()
        conn = sqlite3.connect(DB)
        conn.execute("DELETE FROM tickets")
        conn.commit()
        conn.close()

    def test_student_checkin_route_post(self):
        """Verifies student check-in POST request inserts ticket into SQLite with WAITING status."""
        # Arrange
        form_data = {
            "student_id": "2024109876",
            "full_name": "Maria Santos",
            "request_type": "Graduation Clearance / Drop Deadline",
            "grade_level": "Graduating Senior"
        }

        # Act
        response = self.client.post("/", data=form_data, follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ticket Issued!", response.data)
        
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, full_name, priority_score, status FROM tickets WHERE student_id = '2024109876'")
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "2024109876")
        self.assertEqual(row[1], "Maria Santos")
        self.assertEqual(row[2], 1.0)  # (1 * 0.6) + (1 * 0.4) = 1.0
        self.assertEqual(row[3], "WAITING")

    def test_dashboard_route_get(self):
        """Verifies GET /dashboard loads Min-Heap ordered tickets."""
        # Arrange
        conn = sqlite3.connect(DB)
        conn.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2024001', 'Juan Dela Cruz', 'Inquiry', 9, 'Freshman', 9, ?, 9.0, 'WAITING')
        """, (time.time(),))
        conn.commit()
        conn.close()

        # Act
        response = self.client.get("/dashboard")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Registrar Priority Queue Monitor", response.data)
        self.assertIn(b"Juan Dela Cruz", response.data)

    def test_call_next_ticket_post(self):
        """Verifies POST /call-next pops root ticket and updates status to SERVED."""
        # Arrange
        conn = sqlite3.connect(DB)
        conn.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES ('2021001', 'Alex Senior', 'Graduation Clearance / Drop Deadline', 1, 'Graduating Senior', 1, ?, 1.0, 'WAITING')
        """, (time.time(),))
        conn.commit()
        conn.close()

        # Act
        response = self.client.post("/call-next", follow_redirects=True)

        # Assert
        self.assertEqual(response.status_code, 200)
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM tickets WHERE student_id = '2021001'")
        row = cursor.fetchone()
        conn.close()
        self.assertEqual(row[0], "SERVED")

    def test_analytics_dashboard_route_get(self):
        """Verifies GET /analytics renders metrics cards and chart endpoints."""
        # Act
        response = self.client.get("/analytics")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Queue Volume & Priority Analytics", response.data)
        self.assertIn(b"/api/analytics/volume.png", response.data)


if __name__ == "__main__":
    unittest.main()
