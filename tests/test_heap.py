"""
Unit tests for Min-Heap Priority Queue and Strategy Pattern
"""

import unittest
from heap_queue import (
    StandardRegistrarStrategy,
    RegistrarMinHeapQueue,
    StudentTicket
)


class TestQueueEngine(unittest.TestCase):
    def setUp(self):
        self.strategy = StandardRegistrarStrategy()
        self.queue = RegistrarMinHeapQueue(self.strategy)

    def test_min_heap_prioritization(self):
        # Arrange
        low_pri = StudentTicket(1, "2024-01", "Bob", "Inquiry", 9, "Freshman", 9)
        high_pri = StudentTicket(2, "2021-01", "Alice", "Graduation", 1, "Graduating Senior", 1)

        # Act
        self.queue.push(low_pri)
        self.queue.push(high_pri)

        # Assert: Lowest score (Alice) must pop first
        dispatched = self.queue.pop_highest_priority()
        self.assertEqual(dispatched.ticket_id, 2)
        self.assertEqual(dispatched.name, "Alice")

    def test_score_calculation(self):
        # Arrange: Weights 1 and 1 -> (1 * 0.6) + (1 * 0.4) = 1.0
        score = self.strategy.calculate_score(1, 1, arrival_timestamp=1000000000)
        self.assertLessEqual(score, 1.0)


if __name__ == "__main__":
    unittest.main()