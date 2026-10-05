# MapuaQ: Priority-Based Student Queuing System

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Flask 3.1](https://img.shields.io/badge/Flask-3.1.3-green.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 9 Passed](https://img.shields.io/badge/Tests-9%20Passed%20(100%25)-brightgreen.svg)](tests/)

**Course & Section:** CPE106L-4 / Section B2 (Software Design Laboratory)  
**Institution:** Mapúa University, School of Artificial Intelligence, Electrical, Computer, and Electronics Engineering (AIECEE)  
**Instructor:** Dr. John De Guzman Tarampi  
**Academic Term:** 1st Term, AY 2026-2027

---

## Quick Navigation

- 📄 **Proposal Document**: [PROPOSAL.md](PROPOSAL.md)
- ⚙️ **Database DDL**: [schema.sql](schema.sql)
- 🧪 **Automated Test Suite**: [tests/](tests/)

---

## About MapuaQ

**MapuaQ** is an algorithmic web application designed for the Mapúa University Registrar Office. It solves the critical problem of **queue starvation** during peak enrollment and clearance periods by combining an in-memory **Binary Min-Heap** data structure ($O(1)$ top lookup, $O(\log N)$ updates) with **Dynamic Priority Aging** based on the behavioral **Strategy Design Pattern**.

### Sprint 4 Architecture Highlights

- ⚡ **Binary Min-Heap Priority Queue (`heap_queue.py`)**: Priority score calculation evaluating request urgency ($60\%$), academic standing ($40\%$), dynamic aging discounts ($-1.0$ point per 15 minutes elapsed), and penalty offsets.
- 🔄 **Decoupled Registrar Counter Workflow**: Operational lifecycle transition: `WAITING` $\rightarrow$ `CALLED` $\rightarrow$ `IN_SERVICE` (Mark Arrived) $\rightarrow$ `SERVED` (Complete Service).
- 🔒 **SQLite Concurrency & Lock Prevention**: Write-Ahead Logging (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`) with automatic table migration handling concurrent staff actions without database lock failures.
- 🔔 **Proactive In-App "On-Deck" Notification Alert**: Real-time evaluation on `/ticket/<id>` alerting the Rank #1 waiting student when another student is being served at Counter 1:
  > *"Notice: The student ahead of you has arrived and is currently being served at Counter 1. Please proceed to the registrar lobby and prepare your necessary documents."*
- 👤 **Real Account Portal & Zero Email Gating**: Direct student self-registration (`/register`) with immediate active access (no email verification bottlenecks). Students provision their own actual academic records.
- 🔁 **Single-Use Queue Rejoin**: 1-chance queue re-entry for skipped tickets (`/ticket/rejoin/<id>`).

---

## Quick Start (Running Locally)

```bash
# 1. Clone repository & navigate to project root
cd cpe106l-4_finalproject

# 2. Set up virtual environment (Windows or Linux/Mac)
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Launch local demonstration server
python app.py
```

Access the application in your browser at: **`http://127.0.0.1:5000`**

### Pre-Seeded Access Credentials:

| Role | Email / Identifier | Password | Student / Employee ID |
| :--- | :--- | :--- | :--- |
| **Lead Admin** | `admin@mapua.edu.ph` | `MapuaAdmin2026!` | `ADM-001` |
| **Registrar Staff** | `registrar@mapua.edu.ph` | `StaffPass2026!` | `EMP-001` |
| **Student Accounts** | *(Self-Registered)* | *(Self-Registered)* | Team members register via `/register` portal |

---

## Running Automated Tests

MapuaQ features an automated test suite verifying heap invariants, priority calculations, status lifecycle transitions, database WAL mode, and On-Deck alert detection:

```bash
python -m unittest discover -s tests -v
```

### Test Metrics (Sprint 4 Audit):
- **Passing Test Cases**: **9 / 9 (100% OK)**
- **Test Modules**: `tests/test_app.py`, `tests/test_heap.py`

---

## License

Developed for Mapúa University CPE106L-4 Software Design Laboratory. All rights reserved.
