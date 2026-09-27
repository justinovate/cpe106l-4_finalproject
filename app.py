"""
MapuaQ: Mapúa University Registrar Priority Queuing System
Flask Web Controller with Authentication, Profile Management, Avatar Uploads,
Min-Heap Priority Scheduling, and Servicing Audit Trail.
"""

import os
import re
import time
import uuid
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

app = Flask(__name__)
app.secret_key = "mapuaq_registrar_secret_key_2026_super_secure"
DB = "students_queue.db"
strategy = StandardRegistrarStrategy()

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
    """Initializes SQLite tables, performs migrations, and seeds default Admin & Staff accounts."""
    conn = sqlite3.connect(DB)
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.commit()

    cursor = conn.cursor()

    # Schema migration checks for tickets table
    cursor.execute("PRAGMA table_info(tickets)")
    t_cols = [row[1] for row in cursor.fetchall()]
    if "user_id" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN user_id INTEGER NULL")
    if "email" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    if "called_at" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN called_at REAL NULL")
    if "served_at" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN served_at REAL NULL")
    if "served_by" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN served_by TEXT NULL")
    if "remarks" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN remarks TEXT NULL")
    if "feedback_rating" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN feedback_rating INTEGER NULL")
    if "feedback_comment" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN feedback_comment TEXT NULL")
    if "feedback_submitted_at" not in t_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN feedback_submitted_at REAL NULL")

    # Schema migration checks for users table
    cursor.execute("PRAGMA table_info(users)")
    u_cols = [row[1] for row in cursor.fetchall()]
    if "student_id" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN student_id TEXT UNIQUE NULL")
    if "email" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT UNIQUE NOT NULL DEFAULT ''")
    if "program_dept" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN program_dept TEXT NULL")
    if "avatar_url" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT '/static/uploads/avatars/default.png'")

    conn.commit()

    # Seed default Admin account if missing
    cursor.execute("SELECT id FROM users WHERE email = 'admin@mapua.edu.ph' OR student_id = 'admin'")
    if not cursor.fetchone():
        admin_pass_hash = generate_password_hash("MapuaAdmin2026!")
        cursor.execute("""
            INSERT INTO users (student_id, email, password_hash, full_name, role, program_dept, avatar_url, created_at)
            VALUES ('admin', 'admin@mapua.edu.ph', ?, 'Lead Registrar Admin', 'admin', 'Registrar Administration', '/static/uploads/avatars/default.png', ?)
        """, (admin_pass_hash, time.time()))
        conn.commit()

    # Seed default Staff account if missing
    cursor.execute("SELECT id FROM users WHERE email = 'registrar@mapua.edu.ph' OR student_id = 'registrar'")
    if not cursor.fetchone():
        staff_pass_hash = generate_password_hash("StaffPass2026!")
        cursor.execute("""
            INSERT INTO users (student_id, email, password_hash, full_name, role, program_dept, avatar_url, created_at)
            VALUES ('registrar', 'registrar@mapua.edu.ph', ?, 'Registrar Staff Officer', 'staff', 'Registrar Counter', '/static/uploads/avatars/default.png', ?)
        """, (staff_pass_hash, time.time()))
        conn.commit()

    # Seed default Student accounts if missing
    default_students = [
        ("2024000101", "student1@mymail.mapua.edu.ph", "Juan Dela Cruz", "BS Computer Engineering"),
        ("2024000102", "student2@mymail.mapua.edu.ph", "Maria Clara Santos", "BS Information Technology"),
        ("2024000103", "student3@mymail.mapua.edu.ph", "Jose Rizal System", "BS Computer Science"),
    ]

    for std_id, std_email, std_name, std_prog in default_students:
        cursor.execute("SELECT id FROM users WHERE email = ? OR student_id = ?", (std_email, std_id))
        if not cursor.fetchone():
            std_pass_hash = generate_password_hash("StudentPass2026!")
            cursor.execute("""
                INSERT INTO users (student_id, email, password_hash, full_name, role, program_dept, avatar_url, created_at)
                VALUES (?, ?, ?, ?, 'student', ?, '/static/uploads/avatars/default.png', ?)
            """, (std_id, std_email, std_pass_hash, std_name, std_prog, time.time()))
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
    """Loads active waiting tickets from SQLite, calculates dynamic aging, and returns Min-Heap Queue."""
    queue = RegistrarMinHeapQueue(strategy)
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp
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
            arrival_timestamp=r[7]
        )
        queue.push(ticket)
    
    queue.refresh_scores()
    return queue


@app.route("/")
def index():
    """Main Entry Point — Redirects unauthenticated users directly to unified /login."""
    if "user" in session:
        role = session["user"].get("role")
        if role in ("staff", "admin"):
            return redirect(url_for("dashboard"))
        return redirect(url_for("checkin"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Unified Authentication View accepting Mapúa Email, Employee ID, or Student ID."""
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, student_id, email, password_hash, full_name, role, program_dept, avatar_url
            FROM users
            WHERE email = ? OR student_id = ?
        """, (identifier, identifier))
        row = cursor.fetchone()
        conn.close()

        if row and check_password_hash(row[3], password):
            session["user"] = {
                "id": row[0],
                "student_id": row[1],
                "email": row[2],
                "full_name": row[4],
                "role": row[5],
                "program_dept": row[6],
                "avatar_url": row[7] or "/static/uploads/avatars/default.png",
                "username": row[1] or row[2]
            }
            flash(f"Welcome back, {row[4]}!", "success")
            if row[5] in ("staff", "admin"):
                return redirect(url_for("dashboard"))
            return redirect(url_for("checkin"))
        else:
            flash("Invalid credentials. Please verify your Email / Account ID and password.", "danger")

    return render_template("login.html", user=session.get("user"))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Public registration disabled — Account access is provisioned by Registrar Administration."""
    flash("Account access is managed by Mapúa Registrar Administration. Please log in with your provisioned credentials.", "info")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    """Logs out current user."""
    session.pop("user", None)
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("index"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile view, avatar update, password change, and personal ticket history."""
    user_id = session["user"]["id"]

    if request.method == "POST":
        action = request.form.get("action")

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()

        if action == "update_avatar":
            if "avatar" in request.files:
                file = request.files["avatar"]
                if file and file.filename != "" and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    ext = filename.rsplit(".", 1)[1].lower()
                    unique_filename = f"avatar_{session['user'].get('student_id', 'usr')}_{int(time.time())}_{uuid.uuid4().hex[:6]}.{ext}"
                    file.save(os.path.join(UPLOAD_FOLDER, unique_filename))
                    new_avatar_url = f"/static/uploads/avatars/{unique_filename}"

                    cursor.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (new_avatar_url, user_id))
                    conn.commit()
                    session["user"]["avatar_url"] = new_avatar_url
                    flash("Profile picture updated successfully!", "success")
                else:
                    flash("Invalid file format. Allowed: PNG, JPG, JPEG, WEBP.", "danger")

        elif action == "update_password":
            current_pass = request.form.get("current_password", "")
            new_pass = request.form.get("new_password", "")
            confirm_pass = request.form.get("confirm_password", "")

            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()

            if not row or not check_password_hash(row[0], current_pass):
                flash("Current password is incorrect.", "danger")
            elif new_pass != confirm_pass:
                flash("New passwords do not match.", "danger")
            elif len(new_pass) < 6:
                flash("New password must be at least 6 characters long.", "danger")
            else:
                new_pass_hash = generate_password_hash(new_pass)
                cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_pass_hash, user_id))
                conn.commit()
                flash("Password updated successfully!", "success")

        conn.close()
        return redirect(url_for("profile"))

    # Fetch User Info & Role-Specific Profile Data
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, email, full_name, role, program_dept, avatar_url, created_at
        FROM users WHERE id = ?
    """, (user_id,))
    u_row = cursor.fetchone()

    user_info = {
        "id": u_row[0],
        "student_id": u_row[1],
        "email": u_row[2],
        "full_name": u_row[3],
        "role": u_row[4],
        "program_dept": u_row[5],
        "avatar_url": u_row[6] or "/static/uploads/avatars/default.png",
        "created_at": u_row[7]
    }

    my_tickets = []
    staff_stats = None

    if user_info["role"] == "student":
        # Student Profile: Fetch student's queued tickets and ratings
        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, status, priority_score, served_at, feedback_rating, feedback_comment
            FROM tickets
            WHERE user_id = ? OR email = ? OR (student_id IS NOT NULL AND student_id = ?)
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
        # Staff / Admin Profile: Fetch staff servicing statistics and audit records
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

        return redirect(url_for("ticket_status", ticket_id=ticket_id))

    return render_template("checkin.html", user=session.get("user"))


@app.route("/ticket/<int:ticket_id>")
def ticket_status(ticket_id: int):
    """Student live ticket tracking status view with 10s auto-refresh."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, arrival_timestamp, status, served_at, served_by, feedback_rating, feedback_comment
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
        "feedback_comment": row[9]
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

    return render_template(
        "ticket_status.html",
        ticket=ticket,
        students_ahead=students_ahead,
        estimated_wait_mins=estimated_wait_mins,
        user=session.get("user")
    )


@app.route("/ticket/<int:ticket_id>/feedback", methods=["POST"])
def ticket_feedback(ticket_id: int):
    """Submits student feedback rating (1-5 stars) and comment for completed ticket."""
    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "").strip()

    if rating and 1 <= rating <= 5:
        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tickets
            SET feedback_rating = ?, feedback_comment = ?, feedback_submitted_at = ?
            WHERE id = ? AND status = 'SERVED'
        """, (rating, comment, time.time(), ticket_id))
        conn.commit()
        conn.close()
        flash("Thank you for your feedback!", "success")

    return redirect(url_for("ticket_status", ticket_id=ticket_id))


@app.route("/dashboard")
@staff_required
def dashboard():
    """Registrar Staff Monitor Dashboard with active called ticket, queue monitor, and servicing history."""
    filter_type = request.args.get("filter", "waiting")
    
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    # Fetch currently active CALLED ticket for counter
    cursor.execute("""
        SELECT id, student_id, full_name, email, request_type, grade_level, arrival_timestamp, called_at, served_by
        FROM tickets WHERE status = 'CALLED' ORDER BY called_at DESC LIMIT 1
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
            "served_by": c_row[8],
            "elapsed_called_mins": called_mins
        }

    # Load WAITING tickets into Min-Heap
    queue = load_queue_from_db()
    sorted_waiting = queue.get_sorted_list()
    top_waiting = queue.peek()

    served_tickets = []
    all_tickets = []

    if filter_type == "served":
        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, served_at, served_by, remarks, feedback_rating, feedback_comment, status
            FROM tickets WHERE status IN ('SERVED', 'SKIPPED') ORDER BY served_at DESC
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
    conn.close()

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
        flash(f"Ticket #{top_ticket.ticket_id} ({top_ticket.name}) is now CALLED to the counter.", "info")
    else:
        flash("No students currently waiting in queue.", "warning")

    return redirect(url_for("dashboard"))


@app.route("/tickets/<int:ticket_id>/serve", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/serve", methods=["POST"])
@staff_required
def mark_serve(ticket_id: int):
    """Marks ticket as SERVED with completion timestamp, staff ID, and optional transaction remarks."""
    remarks = request.form.get("remarks", "").strip()
    current_user = session.get("user", {}).get("email") or session.get("user", {}).get("username") or "staff"
    conn = sqlite3.connect(DB)
    conn.execute("""
        UPDATE tickets
        SET status = 'SERVED', served_at = ?, served_by = ?, remarks = ?
        WHERE id = ?
    """, (time.time(), current_user, remarks if remarks else None, ticket_id))
    conn.commit()
    conn.close()
    flash(f"Ticket #{ticket_id} successfully marked as SERVED.", "success")
    return redirect(url_for("dashboard"))


@app.route("/tickets/<int:ticket_id>/skip", methods=["POST"])
@app.route("/ticket/<int:ticket_id>/skip", methods=["POST"])
@staff_required
def mark_skip(ticket_id: int):
    """Marks ticket as SKIPPED (No-Show) with reason and frees counter."""
    skip_reason = request.form.get("skip_reason", "").strip() or request.form.get("remarks", "").strip()
    if not skip_reason:
        skip_reason = "No-show during 5-minute call window"

    current_user = session.get("user", {}).get("email") or session.get("user", {}).get("username") or "staff"
    conn = sqlite3.connect(DB)
    conn.execute("""
        UPDATE tickets
        SET status = 'SKIPPED', served_at = ?, served_by = ?, remarks = ?
        WHERE id = ?
    """, (time.time(), current_user, skip_reason, ticket_id))
    conn.commit()
    conn.close()
    flash(f"Ticket #{ticket_id} marked as SKIPPED (No-Show).", "warning")
    return redirect(url_for("dashboard"))


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


@app.route("/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    """Admin-only view for user management and staff provisioning."""
    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "staff")
        program_dept = request.form.get("program_dept", "Registrar Staff").strip()

        if not email or not password or not full_name:
            flash("Please fill in all required fields.", "danger")
        else:
            conn = sqlite3.connect(DB)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ? OR (student_id IS NOT NULL AND student_id = ? AND student_id != '')", (email, student_id))
            if cursor.fetchone():
                flash(f"User with Email '{email}' or Student ID '{student_id}' already exists.", "danger")
                conn.close()
            else:
                pass_hash = generate_password_hash(password)
                cursor.execute("""
                    INSERT INTO users (student_id, email, password_hash, full_name, role, program_dept, avatar_url, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, '/static/uploads/avatars/default.png', ?)
                """, (student_id if student_id else None, email, pass_hash, full_name, role, program_dept, time.time()))
                conn.commit()
                conn.close()
                flash(f"User '{full_name}' ({email}) successfully created as {role.upper()}.", "success")
                return redirect(url_for("admin_users"))

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, student_id, email, full_name, role, program_dept, created_at FROM users ORDER BY created_at DESC")
    users_list = cursor.fetchall()
    conn.close()

    return render_template("admin_users.html", users=users_list, user=session.get("user"))


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
    init_db()
    app.run(debug=True)