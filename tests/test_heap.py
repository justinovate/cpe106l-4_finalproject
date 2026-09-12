"""
MapuaQ: Unit Tests for Binary Min-Heap Priority Queue & Strategy Pattern
Follows strict Arrange-Act-Assert (AAA) pattern.
"""

import time
import unittest
from heap_queue import (
    StandardRegistrarStrategy,
    RegistrarMinHeapQueue,
    StudentTicket
)


class TestMapuaQEngine(unittest.TestCase):
    def setUp(self):
        self.strategy = StandardRegistrarStrategy()
        self.queue = RegistrarMinHeapQueue(self.strategy)

    def test_min_heap_root_invariant(self):
        """Verifies O(1) peek lookup invariant at index 0 root node containing lowest score."""
        # Arrange
        t_low = StudentTicket(1, "2024-001", "Bob", "Inquiry", 9, "Freshman", 9)
        t_mid = StudentTicket(2, "2022-002", "Charlie", "TOR Pickup", 6, "Junior", 5)
        t_high = StudentTicket(3, "2021-003", "Alice", "Graduation Clearance", 1, "Graduating Senior", 1)

        # Act
        self.queue.push(t_low)
        self.queue.push(t_mid)
        self.queue.push(t_high)

        # Assert
        root = self.queue.peek()
        self.assertIsNotNone(root)
        self.assertEqual(root.ticket_id, 3)
        self.assertEqual(root.name, "Alice")
        self.assertEqual(self.queue._heap[0], root)

    def test_priority_formula_exact_calculation(self):
        """Verifies formula S = (W_request * 0.60) + (W_standing * 0.40) - (delta_t / 15.0)."""
        # Arrange
        req_weight = 3  # Prerequisite Override
        standing_weight = 5  # Junior
        arrival_ts = time.time()  # delta_t = 0

        # Act
        calculated_score = self.strategy.calculate_score(req_weight, standing_weight, arrival_ts)

        # Assert: (3 * 0.6) + (5 * 0.4) = 1.8 + 2.0 = 3.8
        self.assertEqual(calculated_score, 3.8)

    def test_dynamic_aging_starvation_prevention(self):
        """Verifies dynamic aging decreases score over elapsed time and prevents starvation."""
        # Arrange
        now = time.time()
        two_hours_ago = now - (120 * 60)  # 120 mins elapsed -> aging discount = 120/15 = 8.0

        # Ticket A: Freshman Inquiry (Base = 9.0), but waited 2 hours -> Score = max(0.1, 9.0 - 8.0) = 1.0
        t_aged_freshman = StudentTicket(10, "2024-999", "Old Waiting Student", "Inquiry", 9, "Freshman", 9, arrival_timestamp=two_hours_ago)
        
        # Ticket B: Junior Override (Base = 3.8), just arrived -> Score = 3.8
        t_new_junior = StudentTicket(11, "2023-111", "New Arrival", "Prerequisite Override", 3, "Junior", 5, arrival_timestamp=now)

        # Act
        self.queue.push(t_new_junior)
        self.queue.push(t_aged_freshman)
        self.queue.refresh_scores()

        # Assert: Aged freshman ticket has score 1.0 vs new junior's score 3.8, popping first!
        first_dispatched = self.queue.pop_highest_priority()
        self.assertEqual(first_dispatched.ticket_id, 10)
        self.assertEqual(first_dispatched.name, "Old Waiting Student")
        self.assertEqual(first_dispatched.priority_score, 1.0)

    def test_tie_breaking_by_arrival_timestamp(self):
        """Verifies that tickets with identical priority scores break ties by earlier arrival timestamp."""
        # Arrange
        t1 = StudentTicket(100, "2022-01", "First Arrival", "TOR Pickup", 6, "Junior", 5, arrival_timestamp=1000.0)
        t2 = StudentTicket(101, "2022-02", "Second Arrival", "TOR Pickup", 6, "Junior", 5, arrival_timestamp=1005.0)

        # Act
        self.queue.push(t2)
        self.queue.push(t1)

        # Assert
        first_out = self.queue.pop_highest_priority()
        second_out = self.queue.pop_highest_priority()
        self.assertEqual(first_out.ticket_id, 100)
        self.assertEqual(second_out.ticket_id, 101)


if __name__ == "__main__":
    unittest.main()