# MapuaQ: A Priority-Based Student Queuing System Using Min-Heap Algorithm and Dynamic Priority Aging

**Course Code & Section:** CPE106L-4 / Section B2 (Software Design Laboratory)  
**Institution:** Mapúa University, School of Artificial Intelligence, Electrical, Computer, and Electronics Engineering (AIECEE)  
**Instructor:** Dr. John De Guzman Tarampi  
**Academic Term:** 1st Term, AY 2026-2027  

**Project Author & Lead Architect:**
- **Justin Andre De Leon** — Sole Lead Software Architect, Core Systems Engineer & Full-Stack Developer  
  *Responsibilities: Full end-to-end system design, Flask web controller architecture (`app.py`), Binary Min-Heap algorithm mechanics (`heap_queue.py`), Strategy Design Pattern dynamic priority aging formula implementation, decoupled counter lifecycle workflow, SQLite relational database schema with WAL mode concurrency (`schema.sql`), Bootstrap 5 responsive UI templates, and automated unit test suite (`tests/`).*

---

## 1. Executive Summary

**MapuaQ** is an algorithmic, web-based student priority queuing system designed for the Mapúa University Registrar Office. Traditional First-Come, First-Served (FCFS) queuing mechanisms fail during peak academic periods because routine inquiries block time-sensitive institutional requests (such as graduation clearances and subject dropping deadlines). Conversely, static priority queues introduce severe **queue starvation**, where lower-priority tickets are repeatedly preempted by incoming higher-priority tickets and never served.

MapuaQ resolves both operational challenges by integrating an in-memory **Binary Min-Heap** data structure ($O(\log N)$ insertions/deletions and $O(1)$ root lookup) with **Dynamic Priority Aging**. Utilizing the **Strategy Design Pattern**, MapuaQ evaluates priority scores based on a weighted formula ($60\%$ service request urgency and $40\%$ academic standing) while continuously deducting priority score points as waiting time elapses ($\Delta t$).

In Sprint 4, MapuaQ is refactored into a high-reliability local demonstration sandbox (`http://127.0.0.1:5000`) featuring:
1. **Decoupled Registrar Counter Workflow**: Clear operational transitions (`WAITING` $\rightarrow$ `CALLED` $\rightarrow$ `IN_SERVICE` $\rightarrow$ `SERVED`), allowing staff to mark student arrival at the counter independently.
2. **SQLite Write-Ahead Logging (WAL Mode)**: Enforces high-concurrency database reads/writes (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`) to eliminate database lock conflicts.
3. **In-App "On-Deck" Proactive Notification Alert**: Real-time evaluation on `/ticket/<id>` alerting the Rank #1 waiting student when another student has arrived and is being served at Counter 1.
4. **Real Account Portal & Zero Email Verification Gating**: Direct student self-registration (`/register`) with immediate active access, enabling team members to provision their own actual student records.

---

## 2. Background and Problem Statement

### 2.1 The Limitations of First-Come, First-Served (FCFS) Queuing
In standard registrar operations at Mapúa University, students receive sequential paper or digital tickets upon arrival. FCFS treats all queue entries homogenously regardless of the urgency or institutional impact of the transaction. During critical academic windows—such as deadline days for course dropping, grade dispute submissions, or graduation clearance processing—students facing immediate, hard deadlines are forced to wait behind routine transactions such as certificate requests or general inquiries.

### 2.2 The Vulnerability of Static Priority Queuing: Queue Starvation
To address FCFS inefficiencies, traditional systems implement static priority queues where transactions are assigned fixed numerical ranks. However, static priority systems suffer from **queue starvation** (also known as indefinite postponement). In a busy registrar environment, lower-priority tickets (e.g., a Freshman requesting a Certificate of Enrollment) are continuously pushed back as higher-priority tickets (e.g., Graduating Seniors submitting clearance) enter the queue. Under high transaction volume, lower-priority students may wait indefinitely without ever reaching the front of the queue.

### 2.3 The MapuaQ Algorithmic & Architectural Solution
MapuaQ introduces **Dynamic Priority Aging** into a **Binary Min-Heap** queue engine. By computing a student's priority score as a function of static request weights, academic standing weights, and elapsed waiting time ($\Delta t$), the system dynamically decreases a ticket's numerical score over time. Because the Min-Heap maintains the lowest numerical score at index 0 (root node), waiting tickets gradually age up in priority. This hybrid approach ensures that urgent requests receive high initial priority while guaranteeing that long-waiting students eventually reach root priority, eliminating starvation.

---

## 3. Objectives

### 3.1 Primary Objective
To design, implement, and validate **MapuaQ**, a 3-tier local web-based student priority queuing system for Mapúa University Registrar that optimizes service scheduling by combining a Binary Min-Heap algorithm with dynamic priority aging, Strategy Design Pattern architecture, institutional account authentication, decoupled counter workflow management, SQLite WAL mode concurrency, live ticket tracking, and proactive "On-Deck" heads-up notifications.

### 3.2 Specific Measurable Objectives
1. **Algorithmic Scheduling Engine**: Implement an in-memory Binary Min-Heap priority queue achieving $O(1)$ root lookup for the top-priority ticket (lowest numerical score) and $O(\log N)$ push/pop time complexity.
2. **Strategy Design Pattern Architecture**: Implement the behavioral Strategy Pattern to decouple priority calculation formulas from heap queue operations, allowing modular rule updates.
3. **Institutional Authentication & Account Registration**: Implement secure authentication (`werkzeug.security` password hashing) accepting Student ID or email, allowing immediate student self-registration without email verification bottlenecks.
4. **Decoupled Registrar Counter Workflow**: Support explicit counter state transitions (`WAITING` $\rightarrow$ `CALLED` $\rightarrow$ `IN_SERVICE` $\rightarrow$ `SERVED`), recording arrival timestamps (`arrived_at`) and completion metrics.
5. **Proactive "On-Deck" Notification Alert**: Evaluate real-time queue states on `/ticket/<id>` and `/api/ticket/<id>/status` to display an On-Deck alert card and web push notifications to the Rank #1 waiting student when another student is currently in service.
6. **SQLite Concurrency & Lock Elimination**: Implement Write-Ahead Logging (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`) and automatic table migration handling concurrent staff operations without database lock failures.
7. **Automated Testing Suite**: Maintain a 9-test AAA automated test suite in `unittest` (`tests/`) verifying heap root invariants, dynamic score aging, starvation prevention, database WAL mode, lifecycle transitions, and On-Deck alert logic (100% OK pass rate).

---

## 4. Target Users

| User Role | Interface / View | Key Responsibilities & Capabilities |
| :--- | :--- | :--- |
| **Student** | Check-In (`/checkin`), Ticket Tracker (`/ticket/<id>`), Student Portal (`/student_portal`), Profile (`/profile`) | Registers student account; issues priority tickets for registrar transactions; tracks live queue status; receives On-Deck preparation alerts; re-joins queue if skipped. |
| **Registrar Staff** | Staff Dashboard (`/dashboard`) | Monitors live queue ordered by Min-Heap priority; executes ticket controls (`/staff/call-next`, `/staff/mark-arrived/<id>`, `/staff/complete-service/<id>`, `/staff/skip/<id>`); inspects active serving status. |
| **Administrator** | Dashboard (`/dashboard`), User Management | Oversees counter operations; provisions staff/admin credentials; inspects system status. |

---

## 5. Scope and Deliverables

### 5.1 In-Scope Deliverables
- **Binary Min-Heap Queue Engine**: In-memory priority queue (`RegistrarMinHeapQueue`) enforcing $O(1)$ root element inspection and $O(\log N)$ heap updates.
- **Dynamic Priority Scoring Engine**: Weighted multi-criteria calculation ($60\%$ request weight, $40\%$ standing weight) combined with dynamic aging discounts ($-1.0$ point per 15 elapsed minutes).
- **Decoupled Counter Servicing Lifecycle**: Distinct counter states for `WAITING`, `CALLED`, `IN_SERVICE` (Mark Arrived), `SERVED`, and `SKIPPED`.
- **Proactive In-App On-Deck Alert**: Real-time status evaluation warning the Rank #1 waiting student to proceed to the lobby and prepare documents.
- **SQLite Concurrency Architecture**: WAL mode and 5000ms busy timeout in `get_db_connection()` to prevent locking errors.
- **Student Registration & Direct Login**: Self-service registration (`/register`) with immediate active status.
- **Pre-Seeded Credentials**:
  - Lead Admin: `admin@mapua.edu.ph` / `MapuaAdmin2026!`
  - Registrar Staff: `registrar@mapua.edu.ph` / `StaffPass2026!`
- **Automated Test Suite**: 9 passing automated test cases in `tests/` verifying system correctness.

---

## 6. Tools and Technologies

| Component | Technology / Library | Selection Rationale & Purpose |
| :--- | :--- | :--- |
| **Programming Language** | Python 3.12+ | Primary language for object-oriented architecture and algorithms. |
| **Web Framework** | Flask 3.1.3 | Lightweight WSGI web framework for HTTP routing and controller logic. |
| **Data Structure** | Python `heapq` / OOP | Provides efficient C-optimized binary heap algorithms for queue management. |
| **Design Pattern** | Strategy Pattern | Decouples scoring calculation formulas from queue data structures. |
| **Security & Auth** | Werkzeug Security | PBKDF2 password hashing and session management. |
| **Database Engine** | SQLite3 (WAL Mode) | Embedded zero-configuration SQL database engine (`students_queue.db`) with Write-Ahead Logging. |
| **Frontend UI** | HTML5 / Bootstrap 5 | Responsive UI styled with Mapúa Cardinal Red accents (`#990000`) & Gold accents (`#D4AF37`). |
| **Testing Framework** | `unittest` | Standard Python testing framework executing 9 AAA unit/integration tests. |

---

## 7. Automated Test Suite Metrics

```text
test_database_isolation_and_schema (test_app.MapuaQIsolatedAppTestCase.test_database_isolation_and_schema) ... ok
test_default_seeded_accounts_login (test_app.MapuaQIsolatedAppTestCase.test_default_seeded_accounts_login) ... ok
test_full_ticket_lifecycle_with_mark_arrived (test_app.MapuaQIsolatedAppTestCase.test_full_ticket_lifecycle_with_mark_arrived) ... ok
test_on_deck_notification_logic (test_app.MapuaQIsolatedAppTestCase.test_on_deck_notification_logic) ... ok
test_user_registration_and_login_without_email_verification (test_app.MapuaQIsolatedAppTestCase.test_user_registration_and_login_without_email_verification) ... ok
test_dynamic_aging_starvation_prevention (test_heap.TestMapuaQEngine.test_dynamic_aging_starvation_prevention) ... ok
test_min_heap_root_invariant (test_heap.TestMapuaQEngine.test_min_heap_root_invariant) ... ok
test_priority_formula_exact_calculation (test_heap.TestMapuaQEngine.test_priority_formula_exact_calculation) ... ok
test_tie_breaking_by_arrival_timestamp (test_heap.TestMapuaQEngine.test_tie_breaking_by_arrival_timestamp) ... ok

----------------------------------------------------------------------
Ran 9 tests in 5.467s

OK (100% Passing, 0 Failures, 0 Errors)
```
