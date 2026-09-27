# MapuaQ — Sprint 3 Report & Technical Documentation

**Course & Section:** CPE106L-4 / Section B2 (Software Design Laboratory)  
**Institution:** Mapúa University, School of AI, EE, CE, and ECE (AIECEE)  
**Lead Architect & Developer:** Justin Andre De Leon  
**Sprint Period:** Sprint 3 (System Integration, Email Dispatch, Security & Lifecycle Controls)  
**Test Suite Status:** 40 AAA Tests Executed — 100% PASS Rate  

---

## 1. Executive Summary

During **Sprint 3**, the MapuaQ Priority Queuing System underwent major production-grade enhancements, expanding from core heap-based queue operations into a fully integrated communications, security, analytics, and lifecycle management platform.

### Key Achievements in Sprint 3:
1. **Automated Dual-Mode Email Notification Subsystem (`notifier.py`)**: Real outbound SMTP email sending with a zero-network-dependency offline terminal fallback (`EMAIL_DEV_MODE=True`).
2. **Student Account Email Verification Workflow**: Token-based email verification (`/verify-email/<token>`) for newly provisioned accounts.
3. **Security & Password Recovery Engine**: Self-service student password recovery (`/forgot-password`) and Admin-initiated temporary password resets with automated email notification and forced password change flag (`must_change_password`).
4. **Student Service Quality Rating Survey & Analytics**: Post-service 1–5 star rating submission (`/ticket/<id>/feedback`) integrated into Matplotlib visualization (`analytics.py`), computing Net Satisfaction Score (NSS), average rating, and rating distributions.
5. **Ticket Lifecycle Controls (Soft & Hard Delete)**: Operational soft-delete (voiding tickets with mandatory staff remarks) for Staff/Admins, and permanent hard-delete strictly restricted to Administrators.
6. **Brand Identity Styling**: Seamless integration of the transparent Mapúa Thinker emblem (`/static/images/mapua_thinker_transparent.png`) across authentication views.
7. **Comprehensive AAA Test Suite Expansion**: Extended test coverage to **40 automated test cases** across `tests/`, verifying heap math, authentication security, lifecycle endpoints, feedback guards, and email fallback engines.

---

## 2. Comprehensive Sprint 3 Feature Specifications

### 2.1 Automated Dual-Mode Email Notification Engine (`notifier.py`)
- **Dual-Mode Switch**:
  - `EMAIL_DEV_MODE = True`: Formats email payloads cleanly and logs them directly to the terminal stdout (`[MOCK EMAIL DISPATCH]`). Eliminates network socket dependencies during offline presentations.
  - `EMAIL_DEV_MODE = False`: Establishes TLS socket connection to `SMTP_SERVER` (port 587) and dispatches multipart HTML/Plain-Text emails to recipient inboxes.
- **Graceful Fallback**: If live SMTP delivery encounters an error (e.g., internet disconnection or invalid credentials), the system catches the exception and logs a formatted `[SMTP ERROR FALLBACK]` terminal output, ensuring zero application crashes.
- **Triggers & Templates**:
  - `notify_ticket_created()`: Instant ticket confirmation with live tracking link and estimated wait time.
  - `notify_student_called()`: Urgent alert when a student's ticket is called to a counter, highlighting the 5-minute grace window.
  - `notify_student_skipped()`: Notice sent when a ticket is skipped, providing a 15-minute re-join link (+2.0 priority score penalty offset).
  - `notify_ticket_served()`: Transaction completion receipt with counter remarks and feedback survey link.
  - `send_password_reset_notice()`: Temporary password delivery notice with login security instructions.
  - `send_welcome_account_notice()`: New account credentials welcome email with token verification link.

### 2.2 Account Email Verification Workflow
- **Verification Tokens**: Generated using URL-safe tokens (`secrets.token_urlsafe(32)`).
- **Verification Endpoint**: `GET /verify-email/<token>` checks the `students` and `staff_users` tables, updates `email_verified=1`, clears `verification_token`, and displays a green confirmation alert on the login screen.
- **Account Safeguard**: Verification state is tracked in the database (`email_verified`), allowing administrative policy enforcement.

### 2.3 Password Recovery & Security Tools
- **Admin Password Reset**: Inside `/admin/users`, Administrators can reset any user's password. The system generates a temporary password (e.g. `Mapua#835873`), sets `must_change_password=1`, displays the temporary password directly in the success modal to the admin, and dispatches it via email to the recipient.
- **Self-Service Forgot Password**: `GET, POST /forgot-password` allows students to request a password reset via their registered Mapúa MyMail email.
- **Forced Password Change Guard**: Upon logging in with `must_change_password=1`, users are automatically redirected to `/change-password` and blocked from accessing other views until they update their password.

### 2.4 Student Service Feedback & Rating Analytics
- **Feedback Route**: `GET, POST /ticket/<int:ticket_id>/feedback` allows students to submit a 1 to 5 star rating and optional comments.
- **Guards**: Ticket must be in `'SERVED'` status, and duplicate ratings are prevented (`feedback_rating IS NULL`).
- **Analytics Metrics (`analytics.py`)**:
  - **Average Rating**: Computed across all completed ratings.
  - **Net Satisfaction Score (NSS)**: Calculated as `% Promoters (4-5 stars) - % Detractors (1-2 stars)`.
  - **Rating Breakdown Chart**: Headless Matplotlib PNG rendering a 5-bar rating distribution histogram.

### 2.5 Operational Soft-Delete (Void) & Permanent Hard-Delete
- **Soft-Delete / Void (`POST /tickets/<int:ticket_id>/void`)**: Accessible by Staff and Admins. Updates ticket status to `'CANCELLED'` and prepends mandatory void remarks (e.g. `"Voided: Duplicate entry (by registrar@mapua.edu.ph)"`). Preserves historical audit records in SQLite.
- **Hard-Delete (`POST /tickets/<int:ticket_id>/delete`)**: Restricted strictly to the Administrator role. Permanently removes accidental or test ticket rows from `tickets`.
- **Dashboard Filter Tab**: Added an `"Archived / Voided"` tab (`/dashboard?filter=archived`) to inspect voided and cancelled tickets.

---

## 3. Database Schema Updates (`schema.sql`)

```sql
CREATE TABLE IF NOT EXISTS staff_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT CHECK(role IN ('staff', 'admin')) NOT NULL DEFAULT 'staff',
    program_dept TEXT NULL,
    phone_number TEXT NULL,
    avatar_url TEXT DEFAULT '/static/uploads/avatars/default.png',
    avatar_position TEXT DEFAULT 'center',
    must_change_password INTEGER DEFAULT 0,
    email_verified INTEGER DEFAULT 1,
    verification_token TEXT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    program_dept TEXT NULL,
    phone_number TEXT NULL,
    avatar_url TEXT DEFAULT '/static/uploads/avatars/default.png',
    avatar_position TEXT DEFAULT 'center',
    must_change_password INTEGER DEFAULT 0,
    email_verified INTEGER DEFAULT 0,
    verification_token TEXT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NULL,
    student_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    request_type TEXT NOT NULL,
    request_weight INTEGER NOT NULL,
    grade_level TEXT NOT NULL,
    level_weight INTEGER NOT NULL,
    arrival_timestamp REAL NOT NULL,
    priority_score REAL NOT NULL,
    penalty_offset REAL DEFAULT 0.0,
    status TEXT CHECK(status IN ('WAITING', 'CALLED', 'SERVED', 'SKIPPED', 'CANCELLED', 'INVALID')) DEFAULT 'WAITING',
    called_at REAL NULL,
    skipped_at REAL NULL,
    served_at REAL NULL,
    served_by TEXT NULL,
    rejoin_used INTEGER DEFAULT 0,
    remarks TEXT NULL,
    feedback_rating INTEGER NULL CHECK(feedback_rating BETWEEN 1 AND 5),
    feedback_comment TEXT NULL,
    feedback_submitted_at REAL NULL,
    FOREIGN KEY (user_id) REFERENCES students (id),
    FOREIGN KEY (served_by) REFERENCES staff_users (email)
);
```

---

## 4. API Routes Summary

| Method | Endpoint | Access Level | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Public | Kiosk home & quick service selection portal. |
| `GET, POST` | `/checkin` | Student / Public | Submits priority check-in ticket & sends confirmation email. |
| `GET` | `/ticket/<int:id>` | Public / Student | Live status screen with 10s auto-refresh & re-join button. |
| `GET, POST` | `/ticket/<int:id>/feedback` | Student | Submits post-service 1–5 star rating & feedback. |
| `GET, POST` | `/login` | Public | Institutional authentication portal with transparent Thinker logo. |
| `GET` | `/logout` | Authenticated | Clears user session. |
| `GET, POST` | `/forgot-password` | Public | Self-service password recovery request via MyMail email. |
| `GET, POST` | `/change-password` | Authenticated | Forces password updates when `must_change_password=1`. |
| `GET` | `/verify-email/<token>` | Public | Verifies student/staff email via URL-safe token. |
| `GET` | `/dashboard` | Staff / Admin | Main queue monitor with Waiting, Called, Served, and Archived tabs. |
| `POST` | `/tickets/<id>/call` | Staff / Admin | Calls top-priority waiting ticket to counter & sends urgent email. |
| `POST` | `/tickets/<id>/serve` | Staff / Admin | Completes transaction with remarks & sends survey link. |
| `POST` | `/tickets/<id>/skip` | Staff / Admin | Marks ticket as SKIPPED (No-Show) & triggers 15-min re-join window. |
| `POST` | `/tickets/<id>/rejoin` | Student / Staff | Re-enters skipped ticket with +2.0 priority score penalty offset. |
| `POST` | `/tickets/<id>/void` | Staff / Admin | Soft-deletes ticket with mandatory remarks (`status='CANCELLED'`). |
| `POST` | `/tickets/<id>/delete` | Admin Only | Permanently deletes accidental/test ticket row from SQLite. |
| `GET, POST` | `/admin/users` | Admin Only | Provisions accounts & triggers temporary password resets. |
| `GET` | `/analytics` | Staff / Admin | Displays queue volume metrics, NSS KPIs, and Matplotlib charts. |

---

## 5. Automated Verification & Testing Results

The test suite was executed using Python's standard `unittest` framework:

```bash
python -m unittest discover -s tests
```

### Execution Log Summary:
```text
----------------------------------------------------------------------
Ran 40 tests in 21.864s

OK
```

- **Heap Core Invariants (`test_heap.py`)**: Verified Min-Heap root ordering, $O(N)$ dynamic score aging recalculation, tie-breaking by arrival time, and penalty offsets.
- **Web Controller & Security (`test_app.py`)**: Verified session authentication, RBAC role enforcement, student ticket check-in, live status tracking, rating feedback submission guards, operational voiding, admin hard-deletes, password reset workflows, and email notification dispatch fallbacks.

---

## 6. How to Run Locally & Toggle Email Modes

### Local Execution:
```bash
# Activate Virtual Environment
source venv/bin/activate  # On Linux/WSL
# or: venv\Scripts\activate on Windows

# Install Dependencies
pip install -r requirements.txt

# Run Flask Development Server
python app.py
```
Open browser at: `http://127.0.0.1:5000`

### Toggling Email Modes:
1. **Development Mode (Default - 100% Offline)**:
   In `.env` or `config.py`:
   ```env
   EMAIL_DEV_MODE=True
   ```
   Emails will be logged to terminal console (`[MOCK EMAIL DISPATCH]`).

2. **Live Outbound SMTP Delivery**:
   In `.env`:
   ```env
   EMAIL_DEV_MODE=False
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USE_TLS=True
   SMTP_USERNAME=your_email@gmail.com
   SMTP_PASSWORD=your_16_digit_app_password
   ```

---

## 7. Production Deployment Recommendations

For production deployment of MapuaQ, the platform choice depends on how the persistent SQLite database (`students_queue.db`) and uploaded avatar files (`static/uploads/avatars/`) are hosted:

### Recommended Hosting Options:

1. **Option 1: Render (with Persistent Disk Volume) — Recommended for SQLite**
   - **Architecture**: Deploy container or Python Web Service on Render.
   - **Storage**: Attach a persistent volume mounted at `/data`. Configure `DB_NAME=/data/students_queue.db`.
   - **Pros**: Simple setup, automatic SSL certificate, cost-effective ($7/mo for service + $1/mo for volume).

2. **Option 2: Fly.io (with Persistent Fly Volumes)**
   - **Architecture**: Docker container with Fly Volume attached.
   - **Storage**: SQLite stored on Fly Volume. Can be paired with `Litestream` for continuous background replication to S3/GCS.
   - **Pros**: Global edge routing, ultra-fast response times, built-in persistent volume support.

3. **Option 3: VPS Host (DigitalOcean / Linode / Vultr / Hetzner)**
   - **Architecture**: Ubuntu 24.04 LTS VM running Gunicorn + Nginx reverse proxy + Systemd process manager.
   - **Storage**: Full POSIX filesystem access; SQLite database and avatar uploads persist directly on disk.
   - **Pros**: Maximum control, low fixed cost ($4–$6/month), zero container ephemeral storage issues.

4. **Option 4: Google Cloud Run / AWS ECS (with Managed PostgreSQL & Cloud Storage)**
   - **Architecture**: Scalable container deployment.
   - **Database Upgrade**: Replace SQLite with Google Cloud SQL (PostgreSQL) or Supabase.
   - **Storage**: Move filesystem avatar uploads to Google Cloud Storage (GCS) or AWS S3.
   - **Pros**: Enterprise multi-region scalability and zero server management.
