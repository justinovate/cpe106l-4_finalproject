# MapuaQ: Priority-Based Student Queuing System

[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Flask 3.1](https://img.shields.io/badge/Flask-3.1.3-green.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests: 40 Passed](https://img.shields.io/badge/Tests-40%20Passed%20(100%25)-brightgreen.svg)](tests/)

**Course & Section:** CPE106L-4 / Section B2 (Software Design Laboratory)  
**Institution:** Mapúa University, School of AI, EE, CE, and ECE (AIECEE)  
**Instructor:** Dr. John De Guzman Tarampi  
**Academic Term:** 1st Term, AY 2026-2027  
**Lead Software Architect:** Justin Andre De Leon  

---

## Quick Navigation

- 📄 **Proposal Document**: [PROPOSAL.md](PROPOSAL.md)
- 🚀 **Sprint 3 Report & Technical Documentation**: [README_SPRINT3.md](README_SPRINT3.md)
- ⚙️ **Database DDL**: [schema.sql](schema.sql)
- 🧪 **Automated Test Suite**: [tests/](tests/)

---

## About MapuaQ

**MapuaQ** is an algorithmic web application designed for the Mapúa University Registrar Office. It solves the critical problem of **queue starvation** during peak enrollment and clearance periods by combining an in-memory **Binary Min-Heap** data structure ($O(1)$ top lookup, $O(\log N)$ updates) with **Dynamic Priority Aging** based on the behavioral **Strategy Design Pattern**.

### Core Features:
- ⚡ **Binary Min-Heap Priority Queue (`heap_queue.py`)**: Priority score calculation evaluating request urgency ($60\%$), academic standing ($40\%$), dynamic aging discounts ($-1.0$ point per 15 minutes elapsed), and penalty offsets.
- ✉️ **Automated Dual-Mode Email Notification Engine (`notifier.py`)**: Genuine outbound SMTP sending (Gmail / MyMail) with zero-network-dependency offline terminal fallback (`EMAIL_DEV_MODE=True`).
- 🔐 **Authentication, Email Verification & Security**: Institutional MyMail authentication (`@mymail.mapua.edu.ph`), token-based email verification (`/verify-email/<token>`), profile avatar uploads (`static/uploads/avatars/`), self-service password recovery (`/forgot-password`), and Admin temporary password resets.
- 📱 **Student Live Ticket Status Tracker**: Auto-refreshing status view (`/ticket/<id>`) displaying position ahead counters, estimated wait times, 1-chance 15-minute re-join window (+2.0 penalty offset), and post-service 1–5 star rating feedback submission.
- 🛠️ **Ticket Lifecycle Management**: Operational soft-delete (voiding tickets with mandatory remarks) for Staff/Admins, and permanent hard-delete strictly restricted to Administrators.
- 📊 **Visual Analytics Module (`analytics.py`)**: Headless Matplotlib PNG rendering for queue volume breakdowns, priority score distributions, Net Satisfaction Score (NSS), and customer rating distributions.

---

## Quick Start

```bash
# 1. Clone repository & navigate to project root
cd /home/justin/CPE106L-4/cpe106l-4_finalproject

# 2. Activate virtual environment & install requirements
source venv/bin/activate
pip install -r requirements.txt

# 3. Initialize database & seed initial credentials
python app.py
```

Access the application in your browser at: `http://127.0.0.1:5000`

### Pre-Seeded Access Credentials:
- **Lead Admin**: `admin@mapua.edu.ph` / `MapuaAdmin2026!`
- **Registrar Staff**: `registrar@mapua.edu.ph` / `StaffPass2026!`

---

## Running Automated Tests

MapuaQ features a comprehensive **40-test AAA suite** verifying heap invariants, web routes, email dispatches, ticket void/delete guards, and analytics rendering:

```bash
python -m unittest discover -s tests
```

---

## License

Developed for Mapúa University CPE106L-4 Software Design Laboratory. All rights reserved.
