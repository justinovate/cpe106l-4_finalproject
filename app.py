"""
MapuaQ: Mapúa University Registrar Priority Queuing System
Flask Web Controller for Sprint 4 Local Deployment.
"""

import os
import sqlite3
import time
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config['DB_NAME'] = os.path.join(app.root_path, 'students_queue.db')
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

REQUEST_WEIGHTS = {
    "Official Transcript of Records (TOR)": 3.0,
    "Diploma / Graduation Certificate": 3.0,
    "Certification of Grades / Enrollment": 2.0,
    "Honorable Dismissal": 2.0,
    "ID Replacement / Validation": 1.0,
    "General Inquiry": 1.0
}

LEVEL_WEIGHTS = {
    "4th Year / Graduating": 0.5,
    "3rd Year": 0.7,
    "2nd Year": 0.85,
    "1st Year": 1.0
}


def get_db_connection():
    """Establishes SQLite connection with WAL mode and 5s busy timeout to prevent database locks."""
    db_name = app.config.get('DB_NAME') or Config.DB_NAME
    conn = sqlite3.connect(db_name, timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db():
    """Initializes schema and runs automatic table migration if IN_SERVICE is missing from tickets table."""
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    schema_path = os.path.join(app.root_path, 'schema.sql')

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
        if not cur.fetchone():
            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    conn.executescript(f.read())
                conn.commit()
            seed_default_users(conn)
        else:
            cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tickets';")
            row = cur.fetchone()
            if row and row['sql'] and 'IN_SERVICE' not in row['sql']:
                conn.execute("PRAGMA foreign_keys=off;")
                conn.execute("BEGIN TRANSACTION;")
                conn.execute("ALTER TABLE tickets RENAME TO tickets_old;")
                conn.execute("""
                CREATE TABLE tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    student_id TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    request_weight REAL NOT NULL DEFAULT 1.0,
                    grade_level TEXT NOT NULL,
                    level_weight REAL NOT NULL DEFAULT 1.0,
                    arrival_timestamp REAL NOT NULL,
                    priority_score REAL NOT NULL,
                    penalty_offset REAL DEFAULT 0.0,
                    status TEXT CHECK(status IN ('WAITING', 'CALLED', 'IN_SERVICE', 'SERVED', 'SKIPPED', 'CANCELLED', 'INVALID')) DEFAULT 'WAITING',
                    called_at REAL NULL,
                    arrived_at REAL NULL,
                    skipped_at REAL NULL,
                    served_at REAL NULL,
                    served_by INTEGER NULL,
                    rejoin_used INTEGER DEFAULT 0,
                    remarks TEXT,
                    feedback_rating INTEGER,
                    feedback_comment TEXT,
                    feedback_submitted_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                """)
                conn.execute("""
                INSERT INTO tickets (id, user_id, student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, penalty_offset, status, called_at, arrived_at, skipped_at, served_at, served_by, rejoin_used, remarks, feedback_rating, feedback_comment, feedback_submitted_at)
                SELECT id, user_id, student_id, full_name, email, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, penalty_offset, status, called_at, NULL, skipped_at, served_at, served_by, rejoin_used, remarks, feedback_rating, feedback_comment, feedback_submitted_at FROM tickets_old;
                """)
                conn.execute("DROP TABLE tickets_old;")
                conn.commit()
                conn.execute("PRAGMA foreign_keys=on;")
            seed_default_users(conn)
    finally:
        conn.close()


def seed_default_users(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email = ?", ('staff@mapua.edu.ph',))
    if not cur.fetchone():
        pass_hash = generate_password_hash('staff123')
        cur.execute(
            "INSERT INTO users (student_id, full_name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
            ('STAFF-001', 'Registrar Staff', 'staff@mapua.edu.ph', pass_hash, 'STAFF')
        )
        conn.commit()


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') not in ('STAFF', 'ADMIN'):
            flash("Staff privileges required.", "danger")
            return redirect(url_for('student_portal'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') in ('STAFF', 'ADMIN'):
            return redirect(url_for('dashboard'))
        return redirect(url_for('student_portal'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not student_id or not full_name or not email or not password:
            flash("All fields are required.", "danger")
            return render_template('register.html')

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template('register.html')

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE student_id = ? OR email = ?", (student_id, email))
            if cur.fetchone():
                flash("Student ID or Email is already registered.", "danger")
                return render_template('register.html')

            pass_hash = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (student_id, full_name, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                (student_id, full_name, email, pass_hash, 'STUDENT')
            )
            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for('login'))
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email_or_id = request.form.get('email_or_id', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM users WHERE LOWER(email) = ? OR LOWER(student_id) = ?",
                (email_or_id, email_or_id)
            )
            user = cur.fetchone()

            if user and check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['student_id'] = user['student_id']
                session['full_name'] = user['full_name']
                session['email'] = user['email']
                session['role'] = user['role']
                session['avatar_url'] = user['avatar_url']
                flash(f"Welcome back, {user['full_name']}!", "success")
                
                if user['role'] in ('STAFF', 'ADMIN'):
                    return redirect(url_for('dashboard'))
                return redirect(url_for('student_portal'))
            else:
                flash("Invalid credentials. Please try again.", "danger")
        finally:
            conn.close()

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))


@app.route('/student_portal')
@login_required
def student_portal():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tickets WHERE user_id = ? ORDER BY id DESC",
            (session['user_id'],)
        )
        user_tickets = cur.fetchall()
        
        cur.execute("SELECT COUNT(*) as count FROM tickets WHERE status = 'WAITING'")
        waiting_count = cur.fetchone()['count']
        
        cur.execute("SELECT * FROM tickets WHERE status IN ('CALLED', 'IN_SERVICE') ORDER BY id ASC LIMIT 1")
        active_serving = cur.fetchone()
        
        return render_template(
            'student_portal.html',
            user_tickets=user_tickets,
            waiting_count=waiting_count,
            active_serving=active_serving
        )
    finally:
        conn.close()


@app.route('/checkin', methods=['GET', 'POST'])
@login_required
def checkin():
    if request.method == 'POST':
        request_type = request.form.get('request_type')
        grade_level = request.form.get('grade_level')
        
        if request_type not in REQUEST_WEIGHTS or grade_level not in LEVEL_WEIGHTS:
            flash("Invalid request options selected.", "danger")
            return redirect(url_for('checkin'))
            
        req_weight = REQUEST_WEIGHTS[request_type]
        lvl_weight = LEVEL_WEIGHTS[grade_level]
        arr_time = time.time()
        
        priority_score = arr_time * req_weight * lvl_weight
        
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM tickets WHERE user_id = ? AND status IN ('WAITING', 'CALLED', 'IN_SERVICE')",
                (session['user_id'],)
            )
            if cur.fetchone():
                flash("You already have an active ticket in the queue.", "warning")
                return redirect(url_for('student_portal'))
                
            cur.execute("""
                INSERT INTO tickets (
                    user_id, student_id, full_name, email, request_type, request_weight,
                    grade_level, level_weight, arrival_timestamp, priority_score, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'WAITING')
            """, (
                session['user_id'], session['student_id'], session['full_name'], session['email'],
                request_type, req_weight, grade_level, lvl_weight, arr_time, priority_score
            ))
            conn.commit()
            ticket_id = cur.lastrowid
            flash("Ticket issued successfully!", "success")
            return redirect(url_for('ticket_status', ticket_id=ticket_id))
        finally:
            conn.close()
            
    return render_template(
        'checkin.html',
        request_weights=REQUEST_WEIGHTS,
        level_weights=LEVEL_WEIGHTS
    )


@app.route('/ticket/<int:ticket_id>')
@login_required
def ticket_status(ticket_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        
        if not ticket:
            flash("Ticket not found.", "danger")
            return redirect(url_for('student_portal'))
            
        if session.get('role') not in ('STAFF', 'ADMIN') and ticket['user_id'] != session['user_id']:
            flash("Access denied.", "danger")
            return redirect(url_for('student_portal'))
            
        position = None
        if ticket['status'] == 'WAITING':
            cur.execute("""
                SELECT COUNT(*) as count FROM tickets 
                WHERE status = 'WAITING' AND priority_score < ?
            """, (ticket['priority_score'],))
            position = cur.fetchone()['count'] + 1
            
        cur.execute("SELECT COUNT(*) as count FROM tickets WHERE status = 'IN_SERVICE'")
        in_service_count = cur.fetchone()['count']
        
        is_rank_1 = False
        if ticket['status'] == 'WAITING':
            cur.execute("SELECT id FROM tickets WHERE status = 'WAITING' ORDER BY priority_score ASC LIMIT 1")
            top_ticket = cur.fetchone()
            if top_ticket and top_ticket['id'] == ticket['id']:
                is_rank_1 = True
                
        notify_prepare = bool(in_service_count > 0 and is_rank_1)
        
        return render_template(
            'ticket_status.html',
            ticket=ticket,
            position=position,
            notify_prepare=notify_prepare
        )
    finally:
        conn.close()


@app.route('/api/ticket/<int:ticket_id>/status')
@login_required
def api_ticket_status(ticket_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        
        if not ticket:
            return jsonify({'error': 'Ticket not found'}), 404
            
        position = None
        if ticket['status'] == 'WAITING':
            cur.execute("""
                SELECT COUNT(*) as count FROM tickets 
                WHERE status = 'WAITING' AND priority_score < ?
            """, (ticket['priority_score'],))
            position = cur.fetchone()['count'] + 1
            
        cur.execute("SELECT COUNT(*) as count FROM tickets WHERE status = 'IN_SERVICE'")
        in_service_count = cur.fetchone()['count']
        
        is_rank_1 = False
        if ticket['status'] == 'WAITING':
            cur.execute("SELECT id FROM tickets WHERE status = 'WAITING' ORDER BY priority_score ASC LIMIT 1")
            top_ticket = cur.fetchone()
            if top_ticket and top_ticket['id'] == ticket['id']:
                is_rank_1 = True
                
        notify_prepare = bool(in_service_count > 0 and is_rank_1)
        
        return jsonify({
            'id': ticket['id'],
            'status': ticket['status'],
            'position': position,
            'notify_prepare': notify_prepare,
            'called_at': ticket['called_at'],
            'arrived_at': ticket['arrived_at'],
            'served_at': ticket['served_at']
        })
    finally:
        conn.close()


@app.route('/ticket/rejoin/<int:ticket_id>', methods=['POST'])
@login_required
def rejoin_queue(ticket_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        
        if not ticket:
            flash("Ticket not found.", "danger")
            return redirect(url_for('student_portal'))
            
        if ticket['user_id'] != session['user_id'] and session.get('role') not in ('STAFF', 'ADMIN'):
            flash("Access denied.", "danger")
            return redirect(url_for('student_portal'))
            
        if ticket['status'] == 'SKIPPED' and ticket['rejoin_used'] == 0:
            new_arrival = time.time()
            new_priority = new_arrival * ticket['request_weight'] * ticket['level_weight']
            cur.execute("""
                UPDATE tickets 
                SET status = 'WAITING', arrival_timestamp = ?, priority_score = ?, rejoin_used = 1
                WHERE id = ?
            """, (new_arrival, new_priority, ticket_id))
            conn.commit()
            flash("Successfully rejoined the queue!", "success")
        else:
            flash("Unable to rejoin queue. Ticket is either not skipped or rejoin has already been used.", "warning")
            
        return redirect(url_for('ticket_status', ticket_id=ticket_id))
    finally:
        conn.close()


@app.route('/dashboard')
@staff_required
def dashboard():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM tickets WHERE status = 'IN_SERVICE' ORDER BY arrived_at ASC")
        in_service_tickets = cur.fetchall()
        
        cur.execute("SELECT * FROM tickets WHERE status = 'CALLED' ORDER BY called_at ASC")
        called_tickets = cur.fetchall()
        
        cur.execute("SELECT * FROM tickets WHERE status = 'WAITING' ORDER BY priority_score ASC")
        waiting_tickets = cur.fetchall()
        
        cur.execute("SELECT * FROM tickets WHERE status = 'SKIPPED' ORDER BY skipped_at DESC")
        skipped_tickets = cur.fetchall()
        
        cur.execute("SELECT * FROM tickets WHERE status = 'SERVED' ORDER BY served_at DESC LIMIT 20")
        served_tickets = cur.fetchall()
        
        return render_template(
            'dashboard.html',
            in_service_tickets=in_service_tickets,
            called_tickets=called_tickets,
            waiting_tickets=waiting_tickets,
            skipped_tickets=skipped_tickets,
            served_tickets=served_tickets
        )
    finally:
        conn.close()


@app.route('/staff/call-next', methods=['POST'])
@staff_required
def call_next():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE status = 'WAITING' ORDER BY priority_score ASC LIMIT 1")
        next_ticket = cur.fetchone()
        
        if not next_ticket:
            flash("No waiting tickets in the queue.", "info")
            return redirect(url_for('dashboard'))
            
        now = time.time()
        cur.execute(
            "UPDATE tickets SET status = 'CALLED', called_at = ? WHERE id = ?",
            (now, next_ticket['id'])
        )
        conn.commit()
        flash(f"Ticket #{next_ticket['id']} ({next_ticket['full_name']}) has been CALLED.", "success")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


@app.route('/staff/mark-arrived/<int:ticket_id>', methods=['POST'])
@staff_required
def mark_arrived(ticket_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        
        if not ticket:
            flash("Ticket not found.", "danger")
            return redirect(url_for('dashboard'))
            
        now = time.time()
        cur.execute(
            "UPDATE tickets SET status = 'IN_SERVICE', arrived_at = ? WHERE id = ?",
            (now, ticket_id)
        )
        conn.commit()
        flash(f"Ticket #{ticket_id} marked as ARRIVED and is now IN SERVICE.", "success")
        return redirect(url_for('dashboard'))
    except Exception as e:
        conn.rollback()
        flash(f"Error marking ticket arrived: {str(e)}", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


@app.route('/staff/complete-service/<int:ticket_id>', methods=['POST'])
@staff_required
def complete_service(ticket_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        
        if not ticket:
            flash("Ticket not found.", "danger")
            return redirect(url_for('dashboard'))
            
        now = time.time()
        cur.execute(
            "UPDATE tickets SET status = 'SERVED', served_at = ?, served_by = ? WHERE id = ?",
            (now, session['user_id'], ticket_id)
        )
        conn.commit()
        flash(f"Ticket #{ticket_id} marked as SERVED.", "success")
        return redirect(url_for('dashboard'))
    except Exception as e:
        conn.rollback()
        flash(f"Error completing ticket: {str(e)}", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


@app.route('/staff/skip/<int:ticket_id>', methods=['POST'])
@staff_required
def skip_ticket(ticket_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket = cur.fetchone()
        
        if not ticket:
            flash("Ticket not found.", "danger")
            return redirect(url_for('dashboard'))
            
        now = time.time()
        cur.execute(
            "UPDATE tickets SET status = 'SKIPPED', skipped_at = ? WHERE id = ?",
            (now, ticket_id)
        )
        conn.commit()
        flash(f"Ticket #{ticket_id} marked as SKIPPED.", "warning")
        return redirect(url_for('dashboard'))
    except Exception as e:
        conn.rollback()
        flash(f"Error skipping ticket: {str(e)}", "danger")
        return redirect(url_for('dashboard'))
    finally:
        conn.close()


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        if request.method == 'POST':
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip().lower()
            
            if not full_name or not email:
                flash("Full name and email are required.", "danger")
                return redirect(url_for('profile'))
                
            cur.execute("UPDATE users SET full_name = ?, email = ? WHERE id = ?", (full_name, email, session['user_id']))
            conn.commit()
            session['full_name'] = full_name
            session['email'] = email
            flash("Profile details updated successfully.", "success")
            return redirect(url_for('profile'))
            
        cur.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],))
        user = cur.fetchone()
        return render_template('profile.html', user=user)
    finally:
        conn.close()


@app.route('/profile/avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        flash("No image file provided.", "danger")
        return redirect(url_for('profile'))
        
    file = request.files['avatar']
    if file.filename == '':
        flash("No file selected.", "danger")
        return redirect(url_for('profile'))
        
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in app.config['ALLOWED_EXTENSIONS']:
        flash("Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP.", "danger")
        return redirect(url_for('profile'))
        
    filename = f"avatar_user_{session['user_id']}_{int(time.time())}.{ext}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    avatar_url = url_for('static', filename=f'uploads/{filename}')
    
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, session['user_id']))
        conn.commit()
        session['avatar_url'] = avatar_url
        flash("Profile photo updated successfully!", "success")
    finally:
        conn.close()
        
    return redirect(url_for('profile'))


if __name__ == '__main__':
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)
