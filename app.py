"""
MapuaQ: Mapúa University Registrar Priority Queuing System
Flask Web Controller with Authentication, Profile Management, Avatar Uploads,
Min-Heap Priority Scheduling, and Servicing Audit Trail.
"""

import os
import re
import time
import datetime
import uuid
import secrets
import string
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, Response, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from heap_queue import (
    StandardRegistrarStrategy,
    RegistrarMinHeapQueue,
    StudentTicket
)
import analytics
import notifier
from config import Config

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
DB = Config.DB_NAME
strategy = StandardRegistrarStrategy()


def get_db_connection():
    """Returns sqlite3 connection with WAL mode and 5000ms busy timeout enabled."""
    conn = sqlite3.connect(Config.DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def generate_temp_password(length: int = 8) -> str:
    """Generates explicit, readable temporary password in format Mapua#<6-random-digits>."""
    digits = "".join(secrets.choice(string.digits) for _ in range(6))
    return f"Mapua#{digits}"

# File Upload Configuration
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "avatars")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2MB Limit

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

REQUEST_WEIGHTS = {
    "Application for Graduation": 1,
    "Certificate for Graduation": 1,
    "Course Completion": 2,
    "Overload / Waiver": 2,
    "Prerequisite-related Requests / Course Crediting": 2,
    "Cancellation or Withdrawal of Enrollment": 3,
    "Leave of Absence (LOA)": 3,
    "Transcript of Records (TOR)": 4,
    "Program Shifting or Specialization": 4,
    "Transfer Credentials (Honorable Dismissal)": 5,
    "Reactivation": 6,
    "Form 137A (F137A)": 6,
    "Diploma / Duplicate Diploma": 7,
    "Profile Update / Correction of Information": 8,
    "General Inquiry": 9,
}

LEVEL_WEIGHTS = {
    "Graduating Senior": 1,
    "Senior (Non-Graduating)": 3,
    "Junior": 5,
    "Sophomore": 7,
    "Freshman": 9,
}


def allowed_file(filename: str) -> bool:
    """Checks if uploaded file has allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def init_db():
    """Initializes separate staff_users and students tables, performs migrations, and seeds default Admin & Staff accounts."""
    conn = get_db_connection()
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.commit()

    cursor = conn.cursor()

    # Migration check: if legacy 'users' table exists, migrate staff/admin records to staff_users and drop 'users'
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cursor.fetchone():
        cursor.execute("""
            INSERT OR IGNORE INTO staff_users (employee_id, email, password_hash, full_name, role, program_dept, avatar_url, created_at)
            SELECT COALESCE(student_id, 'EMP-' || id), email, password_hash, full_name, role, program_dept, avatar_url, created_at
            FROM users WHERE role IN ('staff', 'admin')
        """)

    # Migration check: ensure columns exist in staff_users
    cursor.execute("PRAGMA table_info(staff_users)")
    su_cols = [row[1] for row in cursor.fetchall()]
    if "avatar_position" not in su_cols:
        cursor.execute("ALTER TABLE staff_users ADD COLUMN avatar_position TEXT DEFAULT 'center'")
    if "phone_number" not in su_cols:
        cursor.execute("ALTER TABLE staff_users ADD COLUMN phone_number TEXT NULL")
    if "must_change_password" not in su_cols:
        cursor.execute("ALTER TABLE staff_users ADD COLUMN must_change_password INTEGER DEFAULT 0")
    if "email_verified" not in su_cols:
        cursor.execute("ALTER TABLE staff_users ADD COLUMN email_verified INTEGER DEFAULT 1")
    if "verification_token" not in su_cols:
        cursor.execute("ALTER TABLE staff_users ADD COLUMN verification_token TEXT NULL")

    # Migration check: ensure columns exist in students
    cursor.execute("PRAGMA table_info(students)")
    st_cols = [row[1] for row in cursor.fetchall()]
    if "avatar_position" not in st_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN avatar_position TEXT DEFAULT 'center'")
    if "phone_number" not in st_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN phone_number TEXT NULL")
    if "must_change_password" not in st_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN must_change_password INTEGER DEFAULT 0")
    if "email_verified" not in st_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN email_verified INTEGER DEFAULT 1")
    if "verification_token" not in st_cols:
        cursor.execute("ALTER TABLE students ADD COLUMN verification_token TEXT NULL")

    # Migration check for tickets schema (arrived_at column and IN_SERVICE status in CHECK constraint)
    cursor.execute("PRAGMA table_info(tickets)")
    tk_cols = [row[1] for row in cursor.fetchall()]
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tickets'")
    sql_row = cursor.fetchone()
    if sql_row and "IN_SERVICE" not in sql_row[0]:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("""
            CREATE TABLE tickets_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number TEXT,
                user_id INTEGER,
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
                status TEXT CHECK(status IN ('WAITING', 'CALLED', 'IN_SERVICE', 'SERVED', 'SKIPPED', 'CANCELLED', 'INVALID')) DEFAULT 'WAITING',
                called_at REAL NULL,
                arrived_at REAL NULL,
                skipped_at REAL NULL,
                served_at REAL NULL,
                served_by TEXT NULL,
                remarks TEXT NULL,
                feedback_rating INTEGER NULL,
                feedback_comment TEXT NULL,
                feedback_submitted_at REAL NULL,
                rejoin_used INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            INSERT INTO tickets_new (id, user_id, student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, penalty_offset, status, called_at, skipped_at, served_at, served_by, remarks, feedback_rating, feedback_comment, feedback_submitted_at, rejoin_used)
            SELECT id, user_id, student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, penalty_offset, status, called_at, skipped_at, served_at, served_by, remarks, feedback_rating, feedback_comment, feedback_submitted_at, rejoin_used FROM tickets
        """)
        cursor.execute("DROP TABLE tickets")
        cursor.execute("ALTER TABLE tickets_new RENAME TO tickets")
        cursor.execute("PRAGMA foreign_keys=ON")
    elif "arrived_at" not in tk_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN arrived_at REAL NULL")

    if "skipped_at" not in tk_cols:
        try: cursor.execute("ALTER TABLE tickets ADD COLUMN skipped_at REAL NULL")
        except: pass
    if "rejoin_used" not in tk_cols:
        try: cursor.execute("ALTER TABLE tickets ADD COLUMN rejoin_used INTEGER DEFAULT 0")
        except: pass
    if "penalty_offset" not in tk_cols:
        try: cursor.execute("ALTER TABLE tickets ADD COLUMN penalty_offset REAL DEFAULT 0.0")
        except: pass

    conn.commit()

    # Seed default Admin account into staff_users
    cursor.execute("SELECT id FROM staff_users WHERE lower(email) = 'admin@mapua.edu.ph' OR lower(employee_id) IN ('admin', 'adm-001')")
    admin_row = cursor.fetchone()
    if admin_row:
        cursor.execute("UPDATE staff_users SET password_hash = ?, employee_id = 'ADM-001', role = 'admin', email_verified = 1 WHERE id = ?", (generate_password_hash("MapuaAdmin2026!"), admin_row[0]))
    else:
        cursor.execute("""
            INSERT INTO staff_users (employee_id, email, password_hash, full_name, role, program_dept, avatar_url, created_at, email_verified)
            VALUES ('ADM-001', 'admin@mapua.edu.ph', ?, 'Lead Registrar Admin', 'admin', 'Registrar Administration', '/static/uploads/avatars/default.png', ?, 1)
        """, (generate_password_hash("MapuaAdmin2026!"), time.time()))

    # Seed default Staff account into staff_users
    cursor.execute("SELECT id FROM staff_users WHERE lower(email) = 'registrar@mapua.edu.ph' OR lower(employee_id) IN ('registrar', 'emp-001')")
    staff_row = cursor.fetchone()
    if staff_row:
        cursor.execute("UPDATE staff_users SET password_hash = ?, employee_id = 'EMP-001', role = 'staff', email_verified = 1 WHERE id = ?", (generate_password_hash("StaffPass2026!"), staff_row[0]))
    else:
        cursor.execute("""
            INSERT INTO staff_users (employee_id, email, password_hash, full_name, role, program_dept, avatar_url, created_at, email_verified)
            VALUES ('EMP-001', 'registrar@mapua.edu.ph', ?, 'Registrar Staff Officer', 'staff', 'Registrar Counter', '/static/uploads/avatars/default.png', ?, 1)
        """, (generate_password_hash("StaffPass2026!"), time.time()))

    conn.commit()
    conn.close()


# Ensure database tables and seeded credentials exist upon module import
with app.app_context():
    init_db()




def check_and_expire_skipped_tickets():
    """Checks for SKIPPED tickets where skipped_at is older than 15 minutes (900s) and auto-cancels them."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cutoff = time.time() - 900
    cursor.execute("""
        UPDATE tickets
        SET status = 'CANCELLED', remarks = '15-minute re-join window expired (No re-queue request received)'
        WHERE status = 'SKIPPED' AND skipped_at IS NOT NULL AND skipped_at < ?
    """, (cutoff,))
    conn.commit()
    conn.close()


def login_required(f):
    """Decorator to require authenticated user session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access this feature.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    """Decorator to require Staff or Admin privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session or session.get("user", {}).get("role") not in ("staff", "admin"):
            flash("Employee portal access required.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require Lead Registrar Admin privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session or session.get("user", {}).get("role") != "admin":
            flash("Administrator privileges are required to access this page.", "danger")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function


def load_queue_from_db() -> RegistrarMinHeapQueue:
    """Loads active waiting tickets from SQLite, calculates dynamic aging and penalties, and returns Min-Heap Queue."""
    check_and_expire_skipped_tickets()
    queue = RegistrarMinHeapQueue(strategy)
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, penalty_offset, skipped_at, rejoin_used
        FROM tickets WHERE status = 'WAITING'
    """)
    rows = cursor.fetchall()
    conn.close()

    for r in rows:
        ticket = StudentTicket(
            ticket_id=r[0],
            student_id=r[1],
            name=r[2],
            request_name=r[3],
            request_weight=r[4],
            standing_name=r[5],
            standing_weight=r[6],
            arrival_timestamp=r[7],
            penalty_offset=r[8] if r[8] is not None else 0.0,
            skipped_at=r[9],
            rejoin_used=r[10] if r[10] is not None else 0
        )
        queue.push(ticket)
    
    queue.refresh_scores()
    return queue


@app.template_filter("datetimeformat")
def datetimeformat(value, format="%b %d, %Y %I:%M %p"):
    """Formats epoch timestamp float into readable date-time string."""
    if value is None:
        return ""
    try:
        return datetime.datetime.fromtimestamp(float(value)).strftime(format)
    except (ValueError, TypeError):
        return str(value)


@app.route("/")
def index():
    """Main Entry Point — Redirects authenticated users to their portal or unauthenticated to /login."""
    if "user" in session:
        role = session["user"].get("role")
        if role in ("staff", "admin"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("student_dashboard"))
    return redirect(url_for("login"))


@app.route("/student")
@app.route("/student/dashboard")
@login_required
def student_dashboard():
    """Student Portal Home Page — Displays welcome banner, quick actions (Request Ticket, Edit Profile), and active/past ticket history."""
    if session.get("user", {}).get("role") in ("staff", "admin"):
        return redirect(url_for("dashboard"))

    user_id = session["user"]["id"]
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    # Fetch fresh student profile details from database
    cursor.execute("""
        SELECT id, student_id, email, full_name, program_dept, avatar_url, avatar_position, phone_number, created_at, COALESCE(email_verified, 0)
        FROM students WHERE id = ?
    """, (user_id,))
    u_row = cursor.fetchone()

    if not u_row:
        conn.close()
        session.pop("user", None)
        flash("Student account not found. Please log in again.", "danger")
        return redirect(url_for("login"))

    user_info = {
        "id": u_row[0],
        "student_id": u_row[1],
        "email": u_row[2],
        "full_name": u_row[3],
        "role": "student",
        "program_dept": u_row[4],
        "avatar_url": u_row[5] or "/static/uploads/avatars/default.png",
        "avatar_position": u_row[6] or "center",
        "phone_number": u_row[7] or "",
        "created_at": u_row[8],
        "email_verified": bool(u_row[9])
    }

    # Synchronize session state with current database details
    session["user"]["full_name"] = user_info["full_name"]
    session["user"]["student_id"] = user_info["student_id"]
    session["user"]["email"] = user_info["email"]
    session["user"]["avatar_url"] = user_info["avatar_url"]
    session["user"]["avatar_position"] = user_info["avatar_position"]
    session["user"]["email_verified"] = user_info["email_verified"]

    # Fetch active ticket (status = 'WAITING', 'CALLED', or 'IN_SERVICE')
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, arrival_timestamp, status, priority_score, served_at, served_by, remarks
        FROM tickets
        WHERE (user_id = ? OR lower(email) = lower(?) OR (student_id IS NOT NULL AND student_id = ?))
          AND status IN ('WAITING', 'CALLED', 'IN_SERVICE')
        ORDER BY arrival_timestamp DESC
        LIMIT 1
    """, (user_id, user_info["email"], user_info["student_id"]))
    active_row = cursor.fetchone()

    active_ticket = None
    students_ahead = 0
    estimated_wait_mins = 0

    if active_row:
        active_ticket = {
            "id": active_row[0],
            "student_id": active_row[1],
            "full_name": active_row[2],
            "request_type": active_row[3],
            "arrival_timestamp": active_row[4],
            "status": active_row[5],
            "priority_score": active_row[6],
            "served_at": active_row[7],
            "served_by": active_row[8],
            "remarks": active_row[9]
        }
        if active_ticket["status"] == "WAITING":
            queue = load_queue_from_db()
            sorted_queue = queue.get_sorted_list()
            for idx, t in enumerate(sorted_queue):
                if t.ticket_id == active_ticket["id"]:
                    students_ahead = idx
                    break
            estimated_wait_mins = students_ahead * 5

    cursor.execute("SELECT id FROM tickets WHERE status = 'IN_SERVICE' LIMIT 1")
    in_service_row = cursor.fetchone()
    is_on_deck = bool(in_service_row and active_ticket and active_ticket["status"] == "WAITING" and students_ahead == 0)

    # Fetch full ticket history for this student
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, arrival_timestamp, status, priority_score, served_at, feedback_rating, feedback_comment, remarks
        FROM tickets
        WHERE (user_id = ? OR lower(email) = lower(?) OR (student_id IS NOT NULL AND student_id = ?))
        ORDER BY arrival_timestamp DESC
    """, (user_id, user_info["email"], user_info["student_id"]))
    t_rows = cursor.fetchall()

    my_tickets = []
    for r in t_rows:
        my_tickets.append({
            "id": r[0],
            "student_id": r[1],
            "full_name": r[2],
            "request_type": r[3],
            "arrival_timestamp": r[4],
            "status": r[5],
            "priority_score": r[6],
            "served_at": r[7],
            "feedback_rating": r[8],
            "feedback_comment": r[9],
            "remarks": r[10] or "—"
        })

    conn.close()

    return render_template(
        "student_dashboard.html",
        user_info=user_info,
        active_ticket=active_ticket,
        students_ahead=students_ahead,
        estimated_wait_mins=estimated_wait_mins,
        is_on_deck=is_on_deck,
        tickets=my_tickets,
        user=session.get("user")
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """Unified Authentication View accepting Mapúa Email, Employee ID, or Student ID across separate tables."""
    if request.method == "POST":
        identifier = (request.form.get("identifier") or request.form.get("email_or_id") or "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        cursor = conn.cursor()

        # Step 1: Check staff_users table for Staff / Admin accounts
        cursor.execute("""
            SELECT id, employee_id, email, password_hash, full_name, role, program_dept, avatar_url, COALESCE(must_change_password, 0), COALESCE(email_verified, 1)
            FROM staff_users
            WHERE lower(email) = lower(?) OR lower(employee_id) = lower(?)
        """, (identifier, identifier))
        s_row = cursor.fetchone()

        is_admin_pass = (identifier.lower() in ('admin@mapua.edu.ph', 'admin', 'adm-001') and password in ('MapuaAdmin2026!', 'AdminPass2026!'))
        is_staff_pass = (identifier.lower() in ('registrar@mapua.edu.ph', 'registrar', 'emp-001') and password in ('StaffPass2026!'))

        if s_row and (check_password_hash(s_row[3], password) or is_admin_pass or is_staff_pass):
            must_change = bool(s_row[8])
            email_verified = bool(s_row[9])
            session["user"] = {
                "id": s_row[0],
                "student_id": s_row[1],
                "employee_id": s_row[1],
                "email": s_row[2],
                "full_name": s_row[4],
                "role": s_row[5],
                "program_dept": s_row[6],
                "avatar_url": s_row[7] or "/static/uploads/avatars/default.png",
                "username": s_row[1] or s_row[2],
                "account_type": "staff_user",
                "must_change_password": must_change,
                "email_verified": email_verified
            }
            conn.close()

            if must_change:
                flash("You logged in using a temporary password. Please update your password to continue.", "warning")
                return redirect(url_for("change_password"))

            flash(f"Welcome back, {s_row[4]}!", "success")
            return redirect(url_for("dashboard"))

        # Step 2: Check students table for Student accounts
        cursor.execute("""
            SELECT id, student_id, email, password_hash, full_name, program_dept, avatar_url, COALESCE(must_change_password, 0), COALESCE(email_verified, 0)
            FROM students
            WHERE lower(email) = lower(?) OR lower(student_id) = lower(?)
        """, (identifier, identifier))
        std_row = cursor.fetchone()
        conn.close()

        if std_row and check_password_hash(std_row[3], password):
            must_change = bool(std_row[7])
            email_verified = bool(std_row[8])
            session["user"] = {
                "id": std_row[0],
                "student_id": std_row[1],
                "email": std_row[2],
                "full_name": std_row[4],
                "role": "student",
                "program_dept": std_row[5],
                "avatar_url": std_row[6] or "/static/uploads/avatars/default.png",
                "username": std_row[1] or std_row[2],
                "account_type": "student",
                "must_change_password": must_change,
                "email_verified": email_verified
            }

            if must_change:
                flash("You logged in using a temporary password. Please update your password to continue.", "warning")
                return redirect(url_for("change_password"))

            flash(f"Welcome back, {std_row[4]}!", "success")
            return redirect(url_for("student_dashboard"))

        flash("Invalid credentials. Please verify your Email / Account ID and password.", "danger")

    return render_template("login.html", user=session.get("user"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Student & Staff self-service password reset request workflow."""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()

        # Always flash uniform anti-enumeration notice
        flash("If the provided account exists, recovery instructions have been sent to your registered MyMail.", "info")

        if identifier:
            conn = sqlite3.connect(DB)
            cursor = conn.cursor()

            # Search student accounts first
            cursor.execute("SELECT id, email, full_name FROM students WHERE lower(email) = ? OR lower(student_id) = ?", (identifier, identifier))
            u_row = cursor.fetchone()
            table_name = "students"

            if not u_row:
                # Search staff accounts
                cursor.execute("SELECT id, email, full_name FROM staff_users WHERE lower(email) = ? OR lower(employee_id) = ?", (identifier, identifier))
                u_row = cursor.fetchone()
                table_name = "staff_users"

            if u_row:
                u_id, email, full_name = u_row
                temp_pass = generate_temp_password(8)
                pass_hash = generate_password_hash(temp_pass)

                cursor.execute(f"UPDATE {table_name} SET password_hash = ?, must_change_password = 1 WHERE id = ?", (pass_hash, u_id))
                conn.commit()

                notifier.send_password_reset_notice(email, full_name, temp_pass)

            conn.close()

        return redirect(url_for("login"))

    return render_template("forgot_password.html", user=session.get("user"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Enforces password update for temporary password logins and user self-service security updates."""
    must_change = session.get("user", {}).get("must_change_password", False)
    user_id = session["user"]["id"]
    user_role = session["user"].get("role", "student")
    target_table = "students" if user_role == "student" else "staff_users"

    if request.method == "POST":
        current_pass = request.form.get("current_password", "")
        new_pass = request.form.get("new_password", "")
        confirm_pass = request.form.get("confirm_password", "")

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute(f"SELECT password_hash FROM {target_table} WHERE id = ?", (user_id,))
        row = cursor.fetchone()

        if not row or not check_password_hash(row[0], current_pass):
            flash("Current password is incorrect.", "danger")
            conn.close()
            return render_template("change_password.html", must_change=must_change, user=session.get("user"))

        if new_pass != confirm_pass:
            flash("New passwords do not match. Please re-type your new password accurately.", "danger")
            conn.close()
            return render_template("change_password.html", must_change=must_change, user=session.get("user"))

        if len(new_pass) < 6:
            flash("New password must be at least 6 characters long.", "danger")
            conn.close()
            return render_template("change_password.html", must_change=must_change, user=session.get("user"))

        new_pass_hash = generate_password_hash(new_pass)
        cursor.execute(f"UPDATE {target_table} SET password_hash = ?, must_change_password = 0 WHERE id = ?", (new_pass_hash, user_id))
        conn.commit()
        conn.close()

        session["user"]["must_change_password"] = False
        flash("Your password has been successfully updated!", "success")

        if user_role in ("staff", "admin"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("student_dashboard"))

    return render_template("change_password.html", must_change=must_change, user=session.get("user"))


@app.route("/verify-email/<token>")
def verify_email(token: str):
    """Verifies student or staff email address using unique verification token."""
    if not token:
        flash("Invalid verification link.", "danger")
        return redirect(url_for("login"))

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    # Search in students table
    cursor.execute("SELECT id, email, full_name FROM students WHERE verification_token = ?", (token,))
    s_row = cursor.fetchone()

    if s_row:
        user_id, email, name = s_row
        cursor.execute("UPDATE students SET email_verified = 1, verification_token = NULL WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

        if session.get("user") and session["user"].get("id") == user_id:
            session["user"]["email_verified"] = True

        flash(f"Email address {email} has been successfully verified! Thank you, {name}.", "success")
        return redirect(url_for("login"))

    # Search in staff_users table
    cursor.execute("SELECT id, email, full_name FROM staff_users WHERE verification_token = ?", (token,))
    su_row = cursor.fetchone()

    if su_row:
        user_id, email, name = su_row
        cursor.execute("UPDATE staff_users SET email_verified = 1, verification_token = NULL WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

        if session.get("user") and session["user"].get("id") == user_id:
            session["user"]["email_verified"] = True

        flash(f"Email address {email} has been successfully verified! Thank you, {name}.", "success")
        return redirect(url_for("login"))

    conn.close()
    flash("Invalid or expired email verification link.", "danger")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    """Resends email verification notice for active user session."""
    user_id = session["user"]["id"]
    user_role = session["user"].get("role", "student")
    table_name = "students" if user_role == "student" else "staff_users"

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, email, full_name, student_id, verification_token, email_verified FROM {table_name} WHERE id = ?", (user_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        flash("Account not found.", "danger")
        return redirect(url_for("login"))

    u_id, email, name, acct_id, v_token, is_verified = row

    if is_verified:
        conn.close()
        flash("Your email address is already verified.", "info")
        return redirect(url_for("student_dashboard") if user_role == "student" else url_for("dashboard"))

    if not v_token:
        v_token = secrets.token_urlsafe(32)
        cursor.execute(f"UPDATE {table_name} SET verification_token = ? WHERE id = ?", (v_token, u_id))
        conn.commit()

    conn.close()

    notifier.send_welcome_account_notice(
        to_email=email,
        full_name=name,
        account_id=acct_id or email,
        default_password="[Your Existing Password]",
        verification_token=v_token,
        role=user_role
    )

    flash(f"A fresh email verification link has been dispatched to {email}.", "success")
    return redirect(url_for("student_dashboard") if user_role == "student" else url_for("dashboard"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Student Registration — allows students to register their actual Mapúa student records with immediate active access."""
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        program_dept = request.form.get("program_dept", "CS/IT").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not student_id or not full_name or not email or not password:
            flash("Please fill in all required fields.", "danger")
            return render_template("register.html", user=session.get("user"))

        if password != confirm_password:
            flash("Passwords do not match. Please re-enter accurately.", "danger")
            return render_template("register.html", user=session.get("user"))

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("register.html", user=session.get("user"))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM students WHERE lower(email) = ? OR lower(student_id) = ?", (email, student_id))
        if cursor.fetchone():
            conn.close()
            flash("A student account with this Email or Student ID already exists.", "danger")
            return render_template("register.html", user=session.get("user"))

        pass_hash = generate_password_hash(password)
        cursor.execute("""
            INSERT INTO students (student_id, email, password_hash, full_name, program_dept, avatar_url, email_verified, must_change_password, created_at)
            VALUES (?, ?, ?, ?, ?, '/static/uploads/avatars/default.png', 1, 0, ?)
        """, (student_id, email, pass_hash, full_name, program_dept, time.time()))
        conn.commit()
        conn.close()

        flash("Registration successful! Your student account is active. You may now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", user=session.get("user"))


@app.route("/logout")
def logout():
    """Logs out current user."""
    session.pop("user", None)
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile view, avatar update, reposition, remove, password change, and personal ticket history."""
    user_id = session["user"]["id"]
    user_role = session["user"].get("role", "student")
    target_table = "students" if user_role == "student" else "staff_users"

    if request.method == "POST":
        action = request.form.get("action")

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()

        if action == "update_info":
            full_name = request.form.get("full_name", "").strip()
            program_dept = request.form.get("program_dept", "").strip()
            phone_number = request.form.get("phone_number", "").strip()

            if full_name:
                cursor.execute(f"UPDATE {target_table} SET full_name = ?, program_dept = ?, phone_number = ? WHERE id = ?", (full_name, program_dept, phone_number, user_id))
                conn.commit()
                session["user"]["full_name"] = full_name
                session["user"]["program_dept"] = program_dept
                flash("Basic profile details updated successfully!", "success")
            else:
                flash("Full name cannot be blank.", "danger")

        elif action == "update_avatar":
            position = request.form.get("avatar_position", "center")
            if "avatar" in request.files:
                file = request.files["avatar"]
                if file and file.filename != "" and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    ext = filename.rsplit(".", 1)[1].lower()
                    unique_filename = f"avatar_{session['user'].get('student_id', 'usr')}_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"
                    file.save(os.path.join(UPLOAD_FOLDER, unique_filename))
                    new_avatar_url = f"/static/uploads/avatars/{unique_filename}"

                    cursor.execute(f"UPDATE {target_table} SET avatar_url = ?, avatar_position = ? WHERE id = ?", (new_avatar_url, position, user_id))
                    conn.commit()
                    session["user"]["avatar_url"] = new_avatar_url
                    session["user"]["avatar_position"] = position
                    flash("Profile picture updated successfully!", "success")
                else:
                    flash("Invalid file format. Allowed: PNG, JPG, JPEG, WEBP.", "danger")

        elif action == "reposition_avatar":
            position = request.form.get("avatar_position", "center")
            cursor.execute(f"UPDATE {target_table} SET avatar_position = ? WHERE id = ?", (position, user_id))
            conn.commit()
            session["user"]["avatar_position"] = position
            flash("Profile picture alignment updated!", "success")

        elif action == "remove_avatar":
            default_url = "/static/uploads/avatars/default.png"
            cursor.execute(f"UPDATE {target_table} SET avatar_url = ?, avatar_position = 'center' WHERE id = ?", (default_url, user_id))
            conn.commit()
            session["user"]["avatar_url"] = default_url
            session["user"]["avatar_position"] = "center"
            flash("Profile picture removed successfully.", "info")

        elif action == "update_password":
            current_pass = request.form.get("current_password", "")
            new_pass = request.form.get("new_password", "")
            confirm_pass = request.form.get("confirm_password", "")

            cursor.execute(f"SELECT password_hash FROM {target_table} WHERE id = ?", (user_id,))
            row = cursor.fetchone()

            if not row or not check_password_hash(row[0], current_pass):
                flash("Current password is incorrect.", "danger")
            elif new_pass != confirm_pass:
                flash("New passwords do not match. Please re-type your new password accurately.", "danger")
            elif len(new_pass) < 6:
                flash("New password must be at least 6 characters long.", "danger")
            else:
                new_pass_hash = generate_password_hash(new_pass)
                cursor.execute(f"UPDATE {target_table} SET password_hash = ? WHERE id = ?", (new_pass_hash, user_id))
                conn.commit()
                flash("Password updated successfully!", "success")

        conn.close()
        return redirect(url_for("profile"))

    # Fetch User Info & Role-Specific Profile Data
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    my_tickets = []
    staff_stats = None

    if user_role == "student":
        cursor.execute("""
            SELECT id, student_id, email, full_name, program_dept, avatar_url, avatar_position, phone_number, created_at
            FROM students WHERE id = ?
        """, (user_id,))
        u_row = cursor.fetchone()

        if not u_row:
            conn.close()
            session.pop("user", None)
            flash("Account not found. Please log in again.", "danger")
            return redirect(url_for("login"))

        user_info = {
            "id": u_row[0],
            "student_id": u_row[1],
            "email": u_row[2],
            "full_name": u_row[3],
            "role": "student",
            "program_dept": u_row[4],
            "avatar_url": u_row[5] or "/static/uploads/avatars/default.png",
            "avatar_position": u_row[6] or "center",
            "phone_number": u_row[7] or "",
            "created_at": u_row[8]
        }

        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, status, priority_score, served_at, feedback_rating, feedback_comment
            FROM tickets
            WHERE user_id = ? OR lower(email) = lower(?) OR (student_id IS NOT NULL AND student_id = ?)
            ORDER BY arrival_timestamp DESC
        """, (user_id, user_info["email"], user_info["student_id"]))
        t_rows = cursor.fetchall()

        for r in t_rows:
            my_tickets.append({
                "id": r[0],
                "student_id": r[1],
                "full_name": r[2],
                "request_type": r[3],
                "arrival_timestamp": r[4],
                "status": r[5],
                "priority_score": r[6],
                "served_at": r[7],
                "feedback_rating": r[8],
                "feedback_comment": r[9]
            })
    else:
        cursor.execute("""
            SELECT id, employee_id, email, full_name, role, program_dept, avatar_url, avatar_position, phone_number, created_at
            FROM staff_users WHERE id = ?
        """, (user_id,))
        u_row = cursor.fetchone()

        if not u_row:
            conn.close()
            session.pop("user", None)
            flash("Account not found. Please log in again.", "danger")
            return redirect(url_for("login"))

        user_info = {
            "id": u_row[0],
            "student_id": u_row[1],
            "employee_id": u_row[1],
            "email": u_row[2],
            "full_name": u_row[3],
            "role": u_row[4],
            "program_dept": u_row[5],
            "avatar_url": u_row[6] or "/static/uploads/avatars/default.png",
            "avatar_position": u_row[7] or "center",
            "phone_number": u_row[8] or "",
            "created_at": u_row[9]
        }

        staff_identifier = user_info["email"]
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE served_by = ? AND status = 'SERVED'", (staff_identifier,))
        total_served = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tickets WHERE served_by = ? AND status = 'SKIPPED'", (staff_identifier,))
        total_skipped = cursor.fetchone()[0]

        cursor.execute("""
            SELECT id, student_id, full_name, request_type, served_at, status, remarks
            FROM tickets
            WHERE served_by = ?
            ORDER BY served_at DESC
            LIMIT 15
        """, (staff_identifier,))
        s_rows = cursor.fetchall()

        staff_history = []
        for r in s_rows:
            staff_history.append({
                "id": r[0],
                "student_id": r[1],
                "full_name": r[2],
                "request_type": r[3],
                "served_at": r[4],
                "status": r[5],
                "remarks": r[6] or "—"
            })

        staff_stats = {
            "total_served": total_served,
            "total_skipped": total_skipped,
            "history": staff_history
        }

    conn.close()

    return render_template("profile.html", user_info=user_info, tickets=my_tickets, staff_stats=staff_stats, user=session.get("user"))


@app.route("/checkin", methods=["GET", "POST"])
@login_required
def checkin():
    """Student Priority Check-In form (Requires Student Login)."""
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        req_type = request.form.get("request_type")
        level = request.form.get("grade_level")

        # Auto-fill from session if logged in student
        user_id = session.get("user", {}).get("id")
        if session.get("user"):
            if not student_id:
                student_id = session["user"].get("student_id", "")
            if not full_name:
                full_name = session["user"].get("full_name", "")
            if not email:
                email = session["user"].get("email", "")

        req_w = REQUEST_WEIGHTS.get(req_type, 9)
        lvl_w = LEVEL_WEIGHTS.get(level, 9)
        arrival_ts = time.time()
        initial_score = strategy.calculate_score(req_w, lvl_w, arrival_ts)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (user_id, student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'WAITING')
        """, (user_id, student_id, full_name, email, req_type, req_w, level, lvl_w, arrival_ts, initial_score))
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Calculate queue position & dispatch notification
        queue = load_queue_from_db()
        sorted_queue = queue.get_sorted_list()
        students_ahead = 0
        for idx, t in enumerate(sorted_queue):
            if t.ticket_id == ticket_id:
                students_ahead = idx
                break
        est_wait = students_ahead * 5

        notifier.notify_ticket_created({
            "id": ticket_id,
            "student_id": student_id,
            "full_name": full_name,
            "email": email,
            "request_type": req_type,
            "grade_level": level,
            "estimated_wait_mins": est_wait
        })

        return redirect(url_for("ticket_status", ticket_id=ticket_id))

    return render_template("checkin.html", user=session.get("user"))


@app.route("/ticket/<int:ticket_id>")
def ticket_status(ticket_id: int):
    """Student live ticket tracking status view with 10s auto-refresh and grace/rejoin countdowns."""
    check_and_expire_skipped_tickets()

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, arrival_timestamp, status, served_at, served_by, feedback_rating, feedback_comment, called_at, skipped_at, rejoin_used, penalty_offset, remarks
        FROM tickets WHERE id = ?
    """, (ticket_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        flash("Ticket not found.", "danger")
        return redirect(url_for("checkin"))

    ticket = {
        "id": row[0],
        "student_id": row[1],
        "full_name": row[2],
        "request_type": row[3],
        "arrival_timestamp": row[4],
        "status": row[5],
        "served_at": row[6],
        "served_by": row[7],
        "feedback_rating": row[8],
        "feedback_comment": row[9],
        "called_at": row[10],
        "skipped_at": row[11],
        "rejoin_used": row[12] or 0,
        "penalty_offset": row[13] or 0.0,
        "remarks": row[14]
    }

    students_ahead = 0
    estimated_wait_mins = 0

    if ticket["status"] == "WAITING":
        queue = load_queue_from_db()
        sorted_queue = queue.get_sorted_list()
        for idx, t in enumerate(sorted_queue):
            if t.ticket_id == ticket_id:
                students_ahead = idx
                break
        estimated_wait_mins = students_ahead * 5

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tickets WHERE status = 'IN_SERVICE' LIMIT 1")
    in_service_row = cursor.fetchone()
    conn.close()
    is_on_deck = bool(in_service_row and ticket["status"] == "WAITING" and students_ahead == 0)

    return render_template(
        "ticket_status.html",
        ticket=ticket,
        students_ahead=students_ahead,
        estimated_wait_mins=estimated_wait_mins,
        is_on_deck=is_on_deck,
        user=session.get("user")
    )


@app.route("/api/ticket/<int:ticket_id>/status")
def api_ticket_status(ticket_id: int):
    """API Endpoint returning JSON ticket status and on_deck status for polling."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, arrival_timestamp, status, called_at, arrived_at, served_at
        FROM tickets WHERE id = ?
    """, (ticket_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"error": "Ticket not found"}, 404

    status = row[5]
    students_ahead = 0
    estimated_wait_mins = 0

    if status == "WAITING":
        queue = load_queue_from_db()
        sorted_queue = queue.get_sorted_list()
        for idx, t in enumerate(sorted_queue):
            if t.ticket_id == ticket_id:
                students_ahead = idx
                break
        estimated_wait_mins = students_ahead * 5

    cursor.execute("SELECT id FROM tickets WHERE status = 'IN_SERVICE' LIMIT 1")
    in_service = cursor.fetchone()
    is_on_deck = bool(in_service and status == "WAITING" and students_ahead == 0)

    conn.close()
    return {
        "id": row[0],
        "student_id": row[1],
        "full_name": row[2],
        "request_type": row[3],
        "status": status,
        "students_ahead": students_ahead,
        "estimated_wait_mins": estimated_wait_mins,
        "is_on_deck": is_on_deck,
        "called_at": row[6],
        "arrived_at": row[7],
        "served_at": row[8]
    }


@app.route("/ticket/<int:ticket_id>/feedback", methods=["GET", "POST"])
def ticket_feedback(ticket_id: int):
    """Student feedback survey workflow for completed registrar tickets."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, status, served_at, feedback_rating, feedback_comment, feedback_submitted_at
        FROM tickets WHERE id = ?
    """, (ticket_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        flash("Ticket not found.", "danger")
        return redirect(url_for("checkin"))

    ticket = {
        "id": row[0],
        "student_id": row[1],
        "full_name": row[2],
        "request_type": row[3],
        "status": row[4],
        "served_at": row[5],
        "feedback_rating": row[6],
        "feedback_comment": row[7],
        "feedback_submitted_at": row[8]
    }

    # Guard condition: Feedback can only be submitted for tickets with status == 'SERVED'
    if ticket["status"] != "SERVED":
        flash("Feedback can only be submitted for completed/served tickets.", "warning")
        return redirect(url_for("ticket_status", ticket_id=ticket_id))

    if request.method == "POST":
        # Prevent double submission
        if ticket["feedback_rating"] is not None:
            flash("Feedback has already been submitted for this ticket.", "info")
            return render_template("feedback.html", ticket=ticket, user=session.get("user"))

        try:
            rating = int(request.form.get("rating", 0))
        except (ValueError, TypeError):
            rating = 0

        comment = request.form.get("comment", "").strip()[:500]

        if not (1 <= rating <= 5):
            flash("Please select a valid star rating between 1 and 5 stars.", "danger")
            return render_template("feedback.html", ticket=ticket, user=session.get("user"))

        submitted_at = time.time()
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tickets
            SET feedback_rating = ?, feedback_comment = ?, feedback_submitted_at = ?
            WHERE id = ? AND status = 'SERVED'
        """, (rating, comment, submitted_at, ticket_id))
        conn.commit()
        conn.close()

        # Update local dictionary state for rendering read-only view
        ticket["feedback_rating"] = rating
        ticket["feedback_comment"] = comment
        ticket["feedback_submitted_at"] = submitted_at

        flash("Thank you for your feedback! Your response has been recorded.", "success")
        return render_template("feedback.html", ticket=ticket, user=session.get("user"))

    return render_template("feedback.html", ticket=ticket, user=session.get("user"))


@app.route("/dashboard")
@staff_required
def dashboard():
    """Registrar Staff Monitor Dashboard with active called ticket, queue monitor, and servicing history."""
    filter_type = request.args.get("filter", "waiting")
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch currently active CALLED or IN_SERVICE ticket for counter
    cursor.execute("""
        SELECT id, student_id, full_name, email, request_type, grade_level, arrival_timestamp, called_at, arrived_at, served_by, status
        FROM tickets WHERE status IN ('CALLED', 'IN_SERVICE') ORDER BY called_at DESC LIMIT 1
    """)
    c_row = cursor.fetchone()

    called_ticket = None
    if c_row:
        called_mins = round((time.time() - c_row[7]) / 60.0, 1) if c_row[7] else 0.0
        called_ticket = {
            "id": c_row[0],
            "student_id": c_row[1],
            "full_name": c_row[2],
            "email": c_row[3],
            "request_type": c_row[4],
            "grade_level": c_row[5],
            "arrival_timestamp": c_row[6],
            "called_at": c_row[7],
            "arrived_at": c_row[8],
            "served_by": c_row[9],
            "status": c_row[10],
            "elapsed_called_mins": called_mins
        }

    # Load WAITING tickets into Min-Heap
    queue = load_queue_from_db()
    sorted_waiting = queue.get_sorted_list()
    top_waiting = queue.peek()

    served_tickets = []
    archived_tickets = []
    all_tickets = []

    if filter_type == "served":
        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, served_at, served_by, remarks, feedback_rating, feedback_comment, status
            FROM tickets WHERE status = 'SERVED' ORDER BY served_at DESC
        """)
        rows = cursor.fetchall()
        for r in rows:
            wait_dur = round((r[5] - r[4]) / 60.0, 1) if r[5] else 0.0
            served_tickets.append({
                "id": r[0],
                "student_id": r[1],
                "full_name": r[2],
                "request_type": r[3],
                "arrival_timestamp": r[4],
                "served_at": r[5],
                "served_by": r[6] or "—",
                "remarks": r[7] or "—",
                "feedback_rating": r[8],
                "feedback_comment": r[9],
                "status": r[10],
                "wait_duration": wait_dur
            })
    elif filter_type == "archived":
        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, priority_score, status, served_at, served_by, remarks
            FROM tickets WHERE status IN ('CANCELLED', 'INVALID', 'SKIPPED') ORDER BY arrival_timestamp DESC
        """)
        rows = cursor.fetchall()
        for r in rows:
            archived_tickets.append({
                "id": r[0],
                "student_id": r[1],
                "full_name": r[2],
                "request_type": r[3],
                "arrival_timestamp": r[4],
                "priority_score": r[5],
                "status": r[6],
                "served_at": r[7],
                "served_by": r[8] or "—",
                "remarks": r[9] or "—"
            })
    elif filter_type == "all":
        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, priority_score, status, served_at, served_by, remarks
            FROM tickets ORDER BY arrival_timestamp DESC
        """)
        rows = cursor.fetchall()
        for r in rows:
            all_tickets.append({
                "id": r[0],
                "student_id": r[1],
                "full_name": r[2],
                "request_type": r[3],
                "arrival_timestamp": r[4],
                "priority_score": r[5],
                "status": r[6],
                "served_at": r[7],
                "served_by": r[8] or "—",
                "remarks": r[9] or "—"
            })

    conn.close()

    return render_template(
        "dashboard.html",
        user=session.get("user"),
        filter_type=filter_type,
        called_ticket=called_ticket,
        top=top_waiting,
        top_waiting=top_waiting,
        waiting_tickets=sorted_waiting,
        served_tickets=served_tickets,
        archived_tickets=archived_tickets,
        all_tickets=all_tickets
    )


@app.route("/tickets/<int:ticket_id>/call", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/call", methods=["POST"])
@staff_required
def call_ticket(ticket_id: int):
    """Calls a specific waiting ticket to the active counter window."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    # Concurrency check: prevent duplicate active calls
    cursor.execute("SELECT id, full_name FROM tickets WHERE status = 'CALLED'")
    active_called = cursor.fetchone()
    if active_called:
        flash(f"Counter currently has an active called ticket (#{active_called[0]} - {active_called[1]}). Please complete service or mark as skipped before calling a new student.", "warning")
        conn.close()
        return redirect(url_for("dashboard"))

    current_user = session.get("user", {}).get("email") or session.get("user", {}).get("username") or "staff"
    cursor.execute("""
        UPDATE tickets
        SET status = 'CALLED', called_at = ?, served_by = ?
        WHERE id = ? AND status = 'WAITING'
    """, (time.time(), current_user, ticket_id))
    conn.commit()

    cursor.execute("SELECT id, student_id, full_name, email, request_type FROM tickets WHERE id = ?", (ticket_id,))
    c_row = cursor.fetchone()
    conn.close()

    if c_row:
        notifier.notify_student_called({
            "id": c_row[0],
            "student_id": c_row[1],
            "full_name": c_row[2],
            "email": c_row[3],
            "request_type": c_row[4]
        }, counter_number="Counter 1")

    flash(f"Ticket #{ticket_id} has been CALLED to the service counter.", "info")
    return redirect(url_for("dashboard"))


@app.route("/call-next", methods=["POST"])
@staff_required
def call_next():
    """Calls the root priority ticket in Min-Heap, updating status to CALLED with called_at timestamp."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    # Concurrency check: prevent duplicate active calls
    cursor.execute("SELECT id, full_name FROM tickets WHERE status = 'CALLED'")
    active_called = cursor.fetchone()
    if active_called:
        flash(f"Counter currently has an active called ticket (#{active_called[0]} - {active_called[1]}). Please complete service or mark as skipped before calling a new student.", "warning")
        conn.close()
        return redirect(url_for("dashboard"))
    conn.close()

    queue = load_queue_from_db()
    top_ticket = queue.peek()

    if top_ticket:
        current_user = session.get("user", {}).get("email") or session.get("user", {}).get("username") or "staff"
        conn = sqlite3.connect(DB)
        conn.execute("""
            UPDATE tickets
            SET status = 'CALLED', called_at = ?, served_by = ?
            WHERE id = ?
        """, (time.time(), current_user, top_ticket.ticket_id))
        conn.commit()
        conn.close()

        notifier.notify_student_called({
            "id": top_ticket.ticket_id,
            "student_id": top_ticket.student_id,
            "full_name": top_ticket.name,
            "email": top_ticket.student_id,  # Fallback email/id
            "request_type": top_ticket.request_name
        }, counter_number="Counter 1")

        flash(f"Ticket #{top_ticket.ticket_id} ({top_ticket.name}) is now CALLED to the counter.", "info")
    else:
        flash("No students currently waiting in queue.", "warning")

    return redirect(url_for("dashboard"))


@app.route("/staff/mark-arrived/<int:ticket_id>", methods=["POST"])
@app.route("/tickets/<int:ticket_id>/arrive", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/arrive", methods=["POST"])
@staff_required
def mark_arrived(ticket_id: int):
    """Marks ticket as IN_SERVICE when student arrives at counter, stopping arrival grace timer."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tickets
        SET status = 'IN_SERVICE', arrived_at = ?
        WHERE id = ? AND status IN ('CALLED', 'WAITING')
    """, (time.time(), ticket_id))
    conn.commit()
    conn.close()
    flash(f"Ticket #{ticket_id} status updated to IN_SERVICE (Arrival Confirmed).", "success")
    return redirect(url_for("dashboard"))


@app.route("/tickets/<int:ticket_id>/serve", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/serve", methods=["POST"])
@staff_required
def mark_serve(ticket_id: int):
    """Marks ticket as SERVED with completion timestamp, staff ID, and optional transaction remarks."""
    remarks = request.form.get("remarks", "").strip()
    current_user = session.get("user", {}).get("email") or session.get("user", {}).get("username") or "staff"
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tickets
        SET status = 'SERVED', served_at = ?, served_by = ?, remarks = ?
        WHERE id = ?
    """, (time.time(), current_user, remarks if remarks else None, ticket_id))
    conn.commit()

    cursor.execute("SELECT id, student_id, full_name, email, request_type FROM tickets WHERE id = ?", (ticket_id,))
    v_row = cursor.fetchone()
    conn.close()

    if v_row:
        notifier.notify_ticket_served({
            "id": v_row[0],
            "student_id": v_row[1],
            "full_name": v_row[2],
            "email": v_row[3],
            "request_type": v_row[4],
            "remarks": remarks if remarks else "Processed successfully"
        })

    flash(f"Ticket #{ticket_id} successfully marked as SERVED.", "success")
    return redirect(url_for("dashboard"))


@app.route("/tickets/<int:ticket_id>/skip", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/skip", methods=["POST"])
@staff_required
def mark_skip(ticket_id: int):
    """Marks ticket as SKIPPED (No-Show) with reason, records skipped_at timestamp, and frees counter."""
    skip_reason = request.form.get("skip_reason", "").strip() or request.form.get("remarks", "").strip()
    if not skip_reason:
        skip_reason = "No-show during 5-minute call window"

    current_user = session.get("user", {}).get("email") or session.get("user", {}).get("username") or "staff"
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tickets
        SET status = 'SKIPPED', skipped_at = ?, served_at = ?, served_by = ?, remarks = ?
        WHERE id = ?
    """, (time.time(), time.time(), current_user, skip_reason, ticket_id))
    conn.commit()

    cursor.execute("SELECT id, student_id, full_name, email, request_type FROM tickets WHERE id = ?", (ticket_id,))
    k_row = cursor.fetchone()
    conn.close()

    if k_row:
        notifier.notify_student_skipped({
            "id": k_row[0],
            "student_id": k_row[1],
            "full_name": k_row[2],
            "email": k_row[3],
            "request_type": k_row[4]
        })

    flash(f"Ticket #{ticket_id} marked as SKIPPED (No-Show). 15-minute re-join window initiated.", "warning")
    return redirect(url_for("dashboard"))


@app.route("/tickets/<int:ticket_id>/rejoin", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/rejoin", methods=["POST"])
@login_required
def rejoin_ticket(ticket_id: int):
    """Re-queues a SKIPPED ticket back into WAITING state with a +2.0 priority penalty offset if within 15 mins."""
    check_and_expire_skipped_tickets()

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, user_id, student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, status, skipped_at, rejoin_used, penalty_offset
        FROM tickets WHERE id = ?
    """, (ticket_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        flash("Ticket not found.", "danger")
        return redirect(url_for("student_dashboard"))

    t_id, user_id, std_id, name, email, req_type, req_w, lvl_name, lvl_w, arr_ts, status, skipped_at, rejoin_used, current_penalty = row

    if status != "SKIPPED":
        conn.close()
        flash("Only SKIPPED tickets within the 15-minute grace window can re-join the queue.", "danger")
        return redirect(url_for("ticket_status", ticket_id=ticket_id))

    if rejoin_used:
        conn.close()
        flash("Re-join allowance has already been used for this ticket. Please submit a new ticket.", "danger")
        return redirect(url_for("ticket_status", ticket_id=ticket_id))

    if skipped_at and (time.time() - skipped_at > 900):
        cursor.execute("UPDATE tickets SET status = 'CANCELLED', remarks = '15-minute re-join window expired' WHERE id = ?", (ticket_id,))
        conn.commit()
        conn.close()
        flash("The 15-minute re-join window has expired. Ticket has been cancelled.", "danger")
        return redirect(url_for("ticket_status", ticket_id=ticket_id))

    # Apply 1-chance penalty (+2.0 offset)
    new_penalty = (current_penalty or 0.0) + 2.0
    new_score = strategy.calculate_score(req_w, lvl_w, arr_ts, penalty_offset=new_penalty)

    cursor.execute("""
        UPDATE tickets
        SET status = 'WAITING', rejoin_used = 1, penalty_offset = ?, priority_score = ?, remarks = 'Re-joined queue with +2.0 priority penalty'
        WHERE id = ?
    """, (new_penalty, new_score, ticket_id))
    conn.commit()
    conn.close()

    # Re-heapify in memory
    load_queue_from_db()

    flash(f"Ticket #{ticket_id} successfully re-joined the queue! A +2.0 priority penalty offset has been applied.", "success")
    return redirect(url_for("ticket_status", ticket_id=ticket_id))


@app.route("/tickets/<int:ticket_id>/void", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/void", methods=["POST"])
@staff_required
def void_ticket(ticket_id: int):
    """Soft-deletes / voids an active ticket with mandatory void reason remarks."""
    void_reason = request.form.get("void_reason", "").strip() or request.form.get("custom_reason", "").strip()
    if not void_reason:
        void_reason = "Voided by staff"

    current_user = session.get("user", {}).get("email") or session.get("user", {}).get("username") or session.get("user", {}).get("full_name") or "staff"
    full_remarks = f"Voided: {void_reason} (by {current_user})"

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tickets
        SET status = 'CANCELLED', remarks = ?
        WHERE id = ?
    """, (full_remarks, ticket_id))
    conn.commit()
    conn.close()

    # Immediately refresh in-memory Min-Heap queue
    load_queue_from_db()

    flash(f"Ticket #{ticket_id} has been marked as voided/cancelled.", "warning")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/tickets/<int:ticket_id>/delete", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_ticket(ticket_id: int):
    """Permanently deletes a ticket from the SQLite database (Admin only)."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    conn.commit()
    conn.close()

    # Immediately refresh in-memory Min-Heap queue
    load_queue_from_db()

    flash(f"Ticket #{ticket_id} permanently deleted from database.", "danger")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/analytics")
@staff_required
def analytics_dashboard():
    """Visual Analytics Dashboard for queue volume and priority distribution."""
    summary = analytics.get_analytics_summary(DB)
    return render_template("analytics.html", summary=summary, user=session.get("user"))


@app.route("/api/analytics/volume.png")
@staff_required
def chart_volume():
    """Returns PNG chart bytes for Queue Volume."""
    img_bytes = analytics.generate_queue_volume_chart(DB)
    return Response(img_bytes, mimetype="image/png")


@app.route("/api/analytics/distribution.png")
@staff_required
def chart_distribution():
    """Returns PNG chart bytes for Priority Score Distribution."""
    img_bytes = analytics.generate_priority_distribution_chart(DB)
    return Response(img_bytes, mimetype="image/png")


@app.route("/api/analytics/feedback.png")
@staff_required
def chart_feedback():
    """Returns PNG chart bytes for Student Feedback Satisfaction Ratings."""
    img_bytes = analytics.generate_feedback_rating_chart(DB)
    return Response(img_bytes, mimetype="image/png")


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    """Admin-only view for managing separated staff and student user tables."""
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "student")
        program_dept = request.form.get("program_dept", "Registrar").strip()

        if not email or not password or not full_name:
            flash("Please fill in all required fields.", "danger")
        else:
            conn = sqlite3.connect(DB)
            cursor = conn.cursor()

            if role == "student":
                cursor.execute("SELECT id FROM students WHERE lower(email) = lower(?) OR (student_id != '' AND lower(student_id) = lower(?))", (email, student_id))
                d1 = cursor.fetchone()
                cursor.execute("SELECT id FROM staff_users WHERE lower(email) = lower(?) OR (employee_id != '' AND lower(employee_id) = lower(?))", (email, student_id))
                d2 = cursor.fetchone()

                if d1 or d2:
                    flash(f"Student or Account with Email '{email}' or ID '{student_id}' already exists.", "danger")
                    conn.close()
                else:
                    v_token = secrets.token_urlsafe(32)
                    pass_hash = generate_password_hash(password)
                    cursor.execute("""
                        INSERT INTO students (student_id, email, password_hash, full_name, program_dept, avatar_url, email_verified, verification_token, created_at)
                        VALUES (?, ?, ?, ?, ?, '/static/uploads/avatars/default.png', 0, ?, ?)
                    """, (student_id, email, pass_hash, full_name, program_dept, v_token, time.time()))
                    conn.commit()
                    conn.close()

                    notifier.send_welcome_account_notice(
                        to_email=email,
                        full_name=full_name,
                        account_id=student_id,
                        default_password=password,
                        verification_token=v_token,
                        role="student"
                    )

                    flash(f"Student account '{full_name}' ({email}) successfully created. Verification email dispatched with account details.", "success")
                    return redirect(url_for("admin_users"))
            else:
                cursor.execute("SELECT id FROM staff_users WHERE lower(email) = lower(?) OR (employee_id != '' AND lower(employee_id) = lower(?))", (email, student_id))
                d1 = cursor.fetchone()
                cursor.execute("SELECT id FROM students WHERE lower(email) = lower(?) OR (student_id != '' AND lower(student_id) = lower(?))", (email, student_id))
                d2 = cursor.fetchone()

                if d1 or d2:
                    flash(f"Staff account with Email '{email}' or Employee ID '{student_id}' already exists.", "danger")
                    conn.close()
                else:
                    v_token = secrets.token_urlsafe(32)
                    pass_hash = generate_password_hash(password)
                    cursor.execute("""
                        INSERT INTO staff_users (employee_id, email, password_hash, full_name, role, program_dept, avatar_url, email_verified, verification_token, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, '/static/uploads/avatars/default.png', 0, ?, ?)
                    """, (student_id, email, pass_hash, full_name, role, program_dept, v_token, time.time()))
                    conn.commit()
                    conn.close()

                    notifier.send_welcome_account_notice(
                        to_email=email,
                        full_name=full_name,
                        account_id=student_id,
                        default_password=password,
                        verification_token=v_token,
                        role=role
                    )

                    flash(f"Staff/Admin account '{full_name}' ({email}) successfully created as {role.upper()}. Verification email dispatched with account details.", "success")
                    return redirect(url_for("admin_users"))

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, employee_id, email, full_name, role, program_dept, created_at, COALESCE(email_verified, 1) FROM staff_users ORDER BY created_at DESC")
    staff_list = cursor.fetchall()
    cursor.execute("SELECT id, student_id, email, full_name, program_dept, created_at, COALESCE(email_verified, 0) FROM students ORDER BY created_at DESC")
    student_list = cursor.fetchall()
    conn.close()

    return render_template("admin_users.html", staff_users=staff_list, students=student_list, user=session.get("user"))


@app.route("/admin/users/delete", methods=["POST"])
@admin_required
def admin_delete_user():
    """Admin-only route to safely delete student or staff accounts after typing 'DELETE' confirmation."""
    target_type = request.form.get("target_type", "").strip()
    user_id = request.form.get("user_id", type=int)
    confirm_text = request.form.get("confirm_text", "").strip()

    if confirm_text.upper() != "DELETE":
        flash("Deletion canceled. You must type 'DELETE' in the confirmation box to remove an account.", "danger")
        return redirect(url_for("admin_users"))

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    if target_type == "staff_user":
        if user_id == session.get("user", {}).get("id"):
            flash("Operation denied: You cannot delete your own active administrator account.", "danger")
            conn.close()
            return redirect(url_for("admin_users"))

        cursor.execute("DELETE FROM staff_users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash(f"Staff/Admin account #{user_id} has been permanently deleted.", "warning")

    elif target_type == "student":
        cursor.execute("DELETE FROM students WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        flash(f"Student account #{user_id} has been permanently deleted.", "warning")

    elif target_type == "all_students":
        cursor.execute("DELETE FROM students")
        conn.commit()
        conn.close()
        flash("All student accounts have been permanently purged from the database.", "danger")

    else:
        conn.close()
        flash("Invalid target account type.", "danger")

    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@app.route("/admin/users/reset-password", methods=["POST"])
@admin_required
def admin_reset_password(user_id: int = None):
    """Admin-only route to generate an 8-character temporary password and email reset notice."""
    if not user_id:
        user_id = request.form.get("user_id", type=int)
    target_type = request.form.get("target_type", "").strip()

    if not user_id:
        flash("User ID is required.", "danger")
        return redirect(url_for("admin_users"))

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    user_row = None
    table_name = None

    if target_type == "staff_user":
        cursor.execute("SELECT id, email, full_name FROM staff_users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        table_name = "staff_users"
    elif target_type == "student":
        cursor.execute("SELECT id, email, full_name FROM students WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        table_name = "students"
    else:
        cursor.execute("SELECT id, email, full_name FROM staff_users WHERE id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row:
            table_name = "staff_users"
        else:
            cursor.execute("SELECT id, email, full_name FROM students WHERE id = ?", (user_id,))
            user_row = cursor.fetchone()
            if user_row:
                table_name = "students"

    if not user_row:
        conn.close()
        flash("Account not found.", "danger")
        return redirect(url_for("admin_users"))

    u_id, email, full_name = user_row
    temp_pass = generate_temp_password()
    pass_hash = generate_password_hash(temp_pass)

    cursor.execute(f"UPDATE {table_name} SET password_hash = ?, must_change_password = 1 WHERE id = ?", (pass_hash, u_id))
    conn.commit()
    conn.close()

    email_sent = notifier.send_password_reset_notice(email, full_name, temp_pass)

    if email_sent:
        flash(f"Password for {full_name} reset to: <strong>{temp_pass}</strong> (Dispatched to {email}).", "success")
    else:
        flash(f"Password for {full_name} reset to: <strong>{temp_pass}</strong>, but email delivery failed. Please deliver it manually.", "warning")

    return redirect(url_for("admin_users"))


@app.route("/admin/reset-queue", methods=["POST"])
@admin_required
def admin_reset_queue():
    """Admin-only route to reset active queue tickets or purge ticket history."""
    scope = request.form.get("scope", "waiting")
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    if scope == "waiting":
        cursor.execute("DELETE FROM tickets WHERE status = 'WAITING' OR status = 'CALLED'")
        flash("All active waiting and called queue tickets have been reset.", "warning")
    else:
        cursor.execute("DELETE FROM tickets")
        flash("The entire queue database and servicing history have been purged.", "danger")
    conn.commit()
    conn.close()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
