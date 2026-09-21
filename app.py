"""
MapuaQ: Mapúa University Registrar Priority Queuing System
Flask Web Controller with Role-Based Access Control, Session Authentication,
and Servicing Audit Trail.
"""

import time
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, Response, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

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


def init_db():
    """Initializes SQLite tables and seeds default Lead Registrar Admin account if empty."""
    conn = sqlite3.connect(DB)
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.commit()

    # Schema migration check for tickets table
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(tickets)")
    columns = [row[1] for row in cursor.fetchall()]
    if "served_at" not in columns:
        cursor.execute("ALTER TABLE tickets ADD COLUMN served_at REAL NULL")
    if "served_by" not in columns:
        cursor.execute("ALTER TABLE tickets ADD COLUMN served_by TEXT NULL")
    conn.commit()

    # Seed default Admin account if no users exist
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_count == 0:
        admin_pass_hash = generate_password_hash("MapuaAdmin2026!")
        cursor.execute("""
            INSERT INTO users (username, password_hash, full_name, role, created_at)
            VALUES (?, ?, ?, 'admin', ?)
        """, ("admin", admin_pass_hash, "Lead Registrar Admin", time.time()))
        conn.commit()

    conn.close()


def login_required(f):
    """Decorator to require authenticated staff/admin session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access the Registrar Employee Portal.", "warning")
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
    
    # Apply dynamic priority score aging calculation across all queued tickets
    queue.refresh_scores()
    return queue


@app.route("/")
def index():
    """Main Landing Portal offering Student Kiosk and Staff Login pathways."""
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Staff and Admin authentication view."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password_hash, full_name, role FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()

        if row and check_password_hash(row[2], password):
            session["user"] = {
                "id": row[0],
                "username": row[1],
                "full_name": row[3],
                "role": row[4]
            }
            flash(f"Welcome back, {row[3]}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid username or password. Please try again.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Logs out current staff/admin user."""
    session.pop("user", None)
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("index"))


@app.route("/checkin", methods=["GET", "POST"])
def checkin():
    """Student Priority Check-In form."""
    if request.method == "POST":
        student_id = request.form.get("student_id").strip()
        full_name = request.form.get("full_name").strip()
        req_type = request.form.get("request_type")
        level = request.form.get("grade_level")

        req_w = REQUEST_WEIGHTS.get(req_type, 9)
        lvl_w = LEVEL_WEIGHTS.get(level, 9)
        arrival_ts = time.time()
        initial_score = strategy.calculate_score(req_w, lvl_w, arrival_ts)

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'WAITING')
        """, (student_id, full_name, req_type, req_w, level, lvl_w, arrival_ts, initial_score))
        ticket_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return redirect(url_for("ticket_status", ticket_id=ticket_id))

    return render_template("checkin.html")


@app.route("/ticket/<int:ticket_id>")
def ticket_status(ticket_id: int):
    """Student live ticket tracking status view with 10s auto-refresh."""
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, arrival_timestamp, status, served_at, served_by
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
        "served_by": row[7]
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
        estimated_wait_mins=estimated_wait_mins
    )


@app.route("/dashboard")
@login_required
def dashboard():
    """Registrar Staff Monitor Dashboard with filter tabs and servicing history."""
    filter_type = request.args.get("filter", "waiting")
    queue = load_queue_from_db()
    sorted_waiting = queue.get_sorted_list()
    top_ticket = queue.peek()

    served_tickets = []
    all_tickets = []

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    if filter_type == "served":
        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, served_at, served_by
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
                "served_by": r[6],
                "wait_duration": wait_dur
            })
    elif filter_type == "all":
        cursor.execute("""
            SELECT id, student_id, full_name, request_type, arrival_timestamp, priority_score, status, served_at, served_by
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
                "served_by": r[8]
            })

    conn.close()

    return render_template(
        "dashboard.html",
        user=session.get("user"),
        filter_type=filter_type,
        top=top_ticket,
        waiting_tickets=sorted_waiting,
        served_tickets=served_tickets,
        all_tickets=all_tickets
    )


@app.route("/call-next", methods=["POST"])
@login_required
def call_next():
    """Calls the root ticket in Min-Heap, updates status to SERVED with audit timestamp and username."""
    queue = load_queue_from_db()
    top_ticket = queue.peek()

    if top_ticket:
        current_user = session.get("user", {}).get("username", "staff")
        conn = sqlite3.connect(DB)
        conn.execute("""
            UPDATE tickets
            SET status = 'SERVED', served_at = ?, served_by = ?
            WHERE id = ?
        """, (time.time(), current_user, top_ticket.ticket_id))
        conn.commit()
        conn.close()
        flash(f"Ticket #{top_ticket.ticket_id} ({top_ticket.name}) marked as SERVED by {current_user}.", "success")

    return redirect(url_for("dashboard"))


@app.route("/analytics")
@login_required
def analytics_dashboard():
    """Visual Analytics Dashboard for queue volume and priority distribution."""
    summary = analytics.get_analytics_summary(DB)
    return render_template("analytics.html", summary=summary, user=session.get("user"))


@app.route("/api/analytics/volume.png")
@login_required
def chart_volume():
    """Returns PNG chart bytes for Queue Volume."""
    img_bytes = analytics.generate_queue_volume_chart(DB)
    return Response(img_bytes, mimetype="image/png")


@app.route("/api/analytics/distribution.png")
@login_required
def chart_distribution():
    """Returns PNG chart bytes for Priority Score Distribution."""
    img_bytes = analytics.generate_priority_distribution_chart(DB)
    return Response(img_bytes, mimetype="image/png")


@app.route("/admin/users", methods=["GET", "POST"])
@login_required
@admin_required
def admin_users():
    """Admin-only view for user management and staff provisioning."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "staff")

        if not username or not password or not full_name:
            flash("All fields are required.", "danger")
        else:
            conn = sqlite3.connect(DB)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                flash(f"Username '{username}' is already taken.", "danger")
                conn.close()
            else:
                pass_hash = generate_password_hash(password)
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (username, pass_hash, full_name, role, time.time()))
                conn.commit()
                conn.close()
                flash(f"User '{full_name}' ({username}) successfully created as {role.upper()}.", "success")
                return redirect(url_for("admin_users"))

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, role, created_at FROM users ORDER BY created_at DESC")
    users_list = cursor.fetchall()
    conn.close()

    return render_template("admin_users.html", users=users_list, user=session.get("user"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)