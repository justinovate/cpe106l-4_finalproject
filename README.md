# MapuaQ: Priority-Based Student Queuing System

[![Python 3.14+](https://img.shields.io/badge/Python-3.14%2B-blue.svg)](https://www.python.org/)
[![Flask 3.1](https://img.shields.io/badge/Flask-3.1.3-green.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 13 Passed](https://img.shields.io/badge/Tests-13%20Passed%20(100%25)-brightgreen.svg)](tests/)

**Course & Section:** CPE106L-4 / Section B2 (Software Design Laboratory)  
**Institution:** Mapúa University, School of Artificial Intelligence, Electrical, Computer, and Electronics Engineering (AIECEE)  
**Instructor:** Dr. John De Guzman Tarampi  
**Academic Term:** 1st Term, AY 2026-2027

---

## Quick Navigation

- 📄 **Proposal Document**: [PROPOSAL.md](PROPOSAL.md)
- 🚀 **Sprint 3 Report & Technical Documentation**: [README_SPRINT3.md](README_SPRINT3.md)
- ⚙️ **Database DDL**: [schema.sql](schema.sql)
- 🧪 **Automated Test Suite**: [tests/](tests/)

---

## About MapuaQ

**MapuaQ** is an algorithmic web application designed for the Mapúa University Registrar Office. It solves the critical problem of **queue starvation** during peak enrollment and clearance periods by combining an in-memory **Binary Min-Heap** data structure ($O(1)$ top lookup, $O(\log N)$ updates) with **Dynamic Priority Aging** based on the behavioral **Strategy Design Pattern**.

### Core Features (Sprint 4 Architecture):
- **Binary Min-Heap Priority Queue (`heap_queue.py`)**: Priority score calculation evaluating request urgency ($60\%$), academic standing ($40\%$), dynamic aging discounts ($-1.0$ point per 15 minutes elapsed), and penalty offsets.
- **Decoupled Registrar Counter Workflow**: Four-stage ticket status lifecycle: `WAITING` $\rightarrow$ `CALLED` $\rightarrow$ `IN_SERVICE` (Mark Arrived) $\rightarrow$ `SERVED` (or `SKIPPED`).
- **In-App Queue Tracking & "On-Deck" Alerts**: Real-time ticket status tracking (`/ticket/<id>`), 5-minute arrival grace countdown, 1-chance 15-minute re-join window (+2.0 penalty offset), and proactive "On-Deck" heads-up alert for the student next in line (Rank #1).
- **Authentication & Self-Registration**: Student self-registration portal (`/register`) with immediate active access (`email_verified = 1`), pre-seeded Lead Admin and Registrar Staff credentials, profile avatar management, and self-service password updates.
- **Ticket Lifecycle & Audit Trail**: Operational soft-delete (voiding tickets with mandatory remarks) for Staff/Admins, and permanent hard-delete strictly restricted to Lead Administrators.
- **Visual Analytics Module (`analytics.py`)**: Headless Matplotlib PNG rendering for queue volume breakdowns, priority score distributions, Net Satisfaction Score (NSS), and customer rating distributions.

---

## Quick Start

```bash
# 1. Navigate to project root
cd mapuaq

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize database & seed initial credentials
python app.py
```

Access the application in your browser at: `http://127.0.0.1:5000`

### Pre-Seeded Access Credentials:
- **Lead Admin**: `admin@mapua.edu.ph` / `MapuaAdmin2026!` (Employee ID: `ADM-001`)
- **Registrar Staff**: `registrar@mapua.edu.ph` / `StaffPass2026!` (Employee ID: `EMP-001`)
- **Student Accounts**: Team members register their own student accounts via `/register`.

---

## Running Automated Tests

MapuaQ features an isolated **13-test AAA suite** verifying heap invariants, dynamic priority aging, decoupled counter lifecycle, On-Deck flags, registration, and administrative void/delete guards:

```bash
python -m unittest discover -s tests -v
```

---

## License

Developed for Mapúa University CPE106L-4 Software Design Laboratory. All rights reserved.
