"""
CPE106L-4 Software Design Laboratory
Sprint 1 Working Proof of Concept (POC)
Modules: Strategy Pattern Scoring & Binary Min-Heap Priority Queue
"""

import time
import heapq


class PriorityCalculationStrategy:
    """Strategy interface for computing student priority scores."""
    def calculate_score(self, request_weight: int, standing_weight: int, arrival_timestamp: float) -> float:
        raise NotImplementedError("Subclasses must implement calculate_score().")


class StandardRegistrarStrategy(PriorityCalculationStrategy):
    """
    Standard Priority Formula:
    Score = (W_request * 0.60) + (W_standing * 0.40) - Dynamic Aging
    Lower score = Higher priority.
    """
    def calculate_score(self, request_weight: int, standing_weight: int, arrival_timestamp: float) -> float:
        elapsed_minutes = (time.time() - arrival_timestamp) / 60.0
        aging_discount = elapsed_minutes / 15.0  # Deduct 1.0 point every 15 mins of waiting
        base_score = (request_weight * 0.60) + (standing_weight * 0.40)
        final_score = max(0.1, base_score - aging_discount)
        return round(final_score, 2)


class StudentTicket:
    """Represents an individual student ticket entity."""
    def __init__(self, ticket_id: int, student_id: str, name: str,
                 request_name: str, request_weight: int,
                 standing_name: str, standing_weight: int,
                 arrival_timestamp: float = None):
        self.ticket_id = ticket_id
        self.student_id = student_id
        self.name = name
        self.request_name = request_name
        self.request_weight = request_weight
        self.standing_name = standing_name
        self.standing_weight = standing_weight
        self.arrival_timestamp = arrival_timestamp if arrival_timestamp is not None else time.time()
        self.priority_score = 0.0

    @property
    def elapsed_minutes(self) -> float:
        return max(0.0, round((time.time() - self.arrival_timestamp) / 60.0, 1))

    def update_score(self, strategy: PriorityCalculationStrategy):
        self.priority_score = strategy.calculate_score(
            self.request_weight, self.standing_weight, self.arrival_timestamp
        )

    # Invariant: Lowest priority score sits at index 0 (root of min-heap)
    def __lt__(self, other):
        if self.priority_score == other.priority_score:
            return self.arrival_timestamp < other.arrival_timestamp
        return self.priority_score < other.priority_score


class RegistrarMinHeapQueue:
    """Binary Min-Heap Priority Queue."""
    def __init__(self, strategy: PriorityCalculationStrategy):
        self._heap = []
        self.strategy = strategy

    def push(self, ticket: StudentTicket):
        ticket.update_score(self.strategy)
        heapq.heappush(self._heap, ticket)

    def refresh_scores(self):
        """Recalculate dynamic aging scores for all tickets and re-heapify."""
        for ticket in self._heap:
            ticket.update_score(self.strategy)
        heapq.heapify(self._heap)

    def pop_highest_priority(self) -> StudentTicket:
        return heapq.heappop(self._heap) if self._heap else None

    def peek(self) -> StudentTicket:
        return self._heap[0] if self._heap else None

    def size(self) -> int:
        return len(self._heap)

    def get_sorted_list(self):
        return sorted(self._heap)


if __name__ == "__main__":
    strategy = StandardRegistrarStrategy()
    queue = RegistrarMinHeapQueue(strategy)

    # Test Sample 1: Low urgency Freshman (Expect high score = low priority)
    t1 = StudentTicket(101, "2024-1001", "Mark Reyes", "General Inquiry", 9, "Freshman", 9)
    # Test Sample 2: Critical deadline Graduating Senior (Expect low score = high priority)
    t2 = StudentTicket(102, "2021-1042", "Juan Dela Cruz", "Graduation Clearance", 1, "Graduating Senior", 1)
    # Test Sample 3: Mid-tier Junior with Prereq Override
    t3 = StudentTicket(103, "2022-1090", "Maria Santos", "Prerequisite Override", 3, "Junior", 5)

    queue.push(t1)
    queue.push(t2)
    queue.push(t3)

    called = queue.pop_highest_priority()
    print(f"[PASS] Top ticket called: #{called.ticket_id} {called.name} (Score: {called.priority_score})")
    assert called.ticket_id == 102, "Assertion failed: Ticket 102 was not prioritized!"