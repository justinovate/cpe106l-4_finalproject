"""
Flask Web Application for Registrar Priority Queuing System
"""

import sqlite3
from flask import Flask, render_template, request, redirect, url_for
from heap_queue import (
    StandardRegistrarStrategy,
    RegistrarMinHeapQueue,
    StudentTicket
)

app = Flask(__name__)
DB = "students_queue.db"
strategy = StandardRegistrarStrategy()

REQUEST_WEIGHTS = {
    "Graduation Clearance / Drop Deadline": 1,
    "Prerequisite Override / Grade Dispute": 3,
    "Transcript (TOR) Pickup": 6,
    "Certificate of Enrollment / Inquiry": 9,
}

LEVEL_WEIGHTS = {
    "Graduating Senior": 1,
    "Non-Graduating Senior": 3,
    "Junior": 5,
    "Sophomore": 7,
    "Freshman": 9,
}


def init_db():
    conn = sqlite3.connect(DB)
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def load_queue_from_db() -> RegistrarMinHeapQueue:
    queue = RegistrarMinHeapQueue(strategy)
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, student_id, full_name, request_type, request_weight, grade_level, level_weight
        FROM tickets WHERE status = 'WAITING'
    """)
    rows = cursor.fetchall()
    conn.close()

    for r in rows:
        ticket = StudentTicket(r[0], r[1], r[2], r[3], r[4], r[5], r[6])
        queue.push(ticket)
    return queue


@app.route("/", methods=["GET", "POST"])
def checkin():
    if request.method == "POST":
        student_id = request.form.get("student_id").strip()
        full_name = request.form.get("full_name").strip()
        req_type = request.form.get("request_type")
        level = request.form.get("grade_level")

        req_w = REQUEST_WEIGHTS.get(req_type, 9)
        lvl_w = LEVEL_WEIGHTS.get(level, 9)
        initial_score = round((req_w * 0.6) + (lvl_w * 0.4), 2)

        conn = sqlite3.connect(DB)
        conn.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, priority_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'WAITING')
        """, (student_id, full_name, req_type, req_w, level, lvl_w, initial_score))
        conn.commit()
        conn.close()

        return render_template("checkin.html", success=True, name=full_name)

    return render_template("checkin.html", success=False)


@app.route("/dashboard")
def dashboard():
    queue = load_queue_from_db()
    sorted_tickets = queue.get_sorted_list()
    top_ticket = queue.peek()
    return render_template("dashboard.html", tickets=sorted_tickets, top=top_ticket)


@app.route("/call-next", methods=["POST"])
def call_next():
    queue = load_queue_from_db()
    top_ticket = queue.peek()

    if top_ticket:
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE tickets SET status = 'SERVED' WHERE id = ?", (top_ticket.ticket_id,))
        conn.commit()
        conn.close()

    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)