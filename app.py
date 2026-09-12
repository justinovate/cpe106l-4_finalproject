"""
MapuaQ: Mapúa University Registrar Priority Queuing System
Flask Web Controller
"""

import time
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, Response
from heap_queue import (
    StandardRegistrarStrategy,
    RegistrarMinHeapQueue,
    StudentTicket
)
import analytics

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


@app.route("/", methods=["GET", "POST"])
def checkin():
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
        conn.execute("""
            INSERT INTO tickets (student_id, full_name, request_type, request_weight, grade_level, level_weight, arrival_timestamp, priority_score, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'WAITING')
        """, (student_id, full_name, req_type, req_w, level, lvl_w, arrival_ts, initial_score))
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


@app.route("/analytics")
def analytics_dashboard():
    summary = analytics.get_analytics_summary(DB)
    return render_template("analytics.html", summary=summary)


@app.route("/api/analytics/volume.png")
def chart_volume():
    img_bytes = analytics.generate_queue_volume_chart(DB)
    return Response(img_bytes, mimetype="image/png")


@app.route("/api/analytics/distribution.png")
def chart_distribution():
    img_bytes = analytics.generate_priority_distribution_chart(DB)
    return Response(img_bytes, mimetype="image/png")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)