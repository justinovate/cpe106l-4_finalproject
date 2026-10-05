"""
MapuaQ Analytics Module
Generates queue volume analytics, priority distribution visualizations, and student feedback satisfaction metrics using Matplotlib.
Configured for headless web server rendering (matplotlib.use('Agg')).
"""

import matplotlib
matplotlib.use('Agg')  # Headless backend MUST be configured before importing pyplot
import matplotlib.pyplot as plt

import io
import sqlite3
from config import Config


def _resolve_db_path(db_path: str = None) -> str:
    """Resolves database path to absolute Config.DB_NAME if default or relative path provided."""
    if not db_path or db_path == "students_queue.db":
        return Config.DB_NAME
    return db_path


def _get_db_conn(db_path: str = None):
    """Returns sqlite3 connection with WAL mode and 5000ms busy timeout enabled."""
    target_db = _resolve_db_path(db_path)
    conn = sqlite3.connect(target_db, timeout=20.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def get_analytics_summary(db_path: str = None) -> dict:
    """Returns key queue metrics and student feedback satisfaction statistics from SQLite database."""
    conn = _get_db_conn(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tickets")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'WAITING'")
        waiting = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'SERVED'")
        served = cursor.fetchone()[0]

        cursor.execute("SELECT request_type, COUNT(*) FROM tickets GROUP BY request_type")
        by_request = dict(cursor.fetchall())

        cursor.execute("SELECT grade_level, COUNT(*) FROM tickets GROUP BY grade_level")
        by_level = dict(cursor.fetchall())

        # Feedback Satisfaction Metrics
        cursor.execute("SELECT COUNT(*), AVG(feedback_rating) FROM tickets WHERE feedback_rating IS NOT NULL")
        fb_row = cursor.fetchone()
        total_feedback = fb_row[0] if fb_row and fb_row[0] else 0
        avg_satisfaction = round(fb_row[1], 2) if (fb_row and fb_row[1] is not None) else 0.0

        response_rate = round((total_feedback / served * 100), 1) if served > 0 else 0.0

        cursor.execute("SELECT feedback_rating, COUNT(*) FROM tickets WHERE feedback_rating IS NOT NULL GROUP BY feedback_rating")
        rating_dist = {i: 0 for i in range(1, 6)}
        for r, count in cursor.fetchall():
            if r in rating_dist:
                rating_dist[r] = count
    finally:
        conn.close()

    return {
        "total_tickets": total,
        "waiting_tickets": waiting,
        "served_tickets": served,
        "by_request": by_request,
        "by_level": by_level,
        "total_feedback_count": total_feedback,
        "average_satisfaction": avg_satisfaction,
        "satisfaction_response_rate": response_rate,
        "rating_distribution": rating_dist,
    }


def generate_queue_volume_chart(db_path: str = None) -> bytes:
    """Generates a PNG bar chart of queue volume by Request Type and Status."""
    conn = _get_db_conn(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT request_type, 
                   SUM(CASE WHEN status = 'WAITING' THEN 1 ELSE 0 END) as waiting_count,
                   SUM(CASE WHEN status = 'SERVED' THEN 1 ELSE 0 END) as served_count
            FROM tickets
            GROUP BY request_type
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    categories = [r[0] for r in rows] if rows else ["No Data"]
    waiting_counts = [r[1] for r in rows] if rows else [0]
    served_counts = [r[2] for r in rows] if rows else [0]

    short_cats = [c[:25] + "..." if len(c) > 28 else c for c in categories]

    fig, ax = plt.subplots(figsize=(9, 5), dpi=120)
    x = range(len(categories))
    width = 0.35

    rects1 = ax.bar([i - width/2 for i in x], waiting_counts, width, label='Waiting', color='#800000')  # Mapúa Cardinal
    rects2 = ax.bar([i + width/2 for i in x], served_counts, width, label='Served', color='#002B49')   # Mapúa Navy

    ax.set_ylabel('Number of Tickets', fontsize=11, fontweight='bold')
    ax.set_title('MapuaQ Queue Volume by Request Type', fontsize=13, fontweight='bold', pad=15)
    ax.set_xticks(list(x))
    ax.set_xticklabels(short_cats, rotation=35, ha='right', fontsize=8)
    ax.legend(frameon=True, facecolor='#f8f9fa')
    ax.grid(axis='y', linestyle='--', alpha=0.5)

    ax.bar_label(rects1, padding=3)
    ax.bar_label(rects2, padding=3)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_priority_distribution_chart(db_path: str = None) -> bytes:
    """Generates a PNG histogram of priority score distribution."""
    conn = _get_db_conn(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT priority_score FROM tickets")
        scores = [r[0] for r in cursor.fetchall()]
    finally:
        conn.close()

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    if scores:
        n, bins, patches = ax.hist(scores, bins=10, color='#800000', edgecolor='white', alpha=0.85)
        ax.set_xlabel('Priority Score (Lower = Higher Service Priority)', fontsize=11, fontweight='bold')
        ax.set_ylabel('Ticket Frequency', fontsize=11, fontweight='bold')
        ax.set_title('MapuaQ Priority Score Distribution', fontsize=13, fontweight='bold', pad=15)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
    else:
        ax.text(0.5, 0.5, 'No Ticket Data Available', horizontalalignment='center',
                verticalalignment='center', transform=ax.transAxes, fontsize=12, color='gray')
        ax.set_title('MapuaQ Priority Score Distribution', fontsize=13, fontweight='bold', pad=15)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_feedback_rating_chart(db_path: str = None) -> bytes:
    """Generates a PNG bar chart of Student Feedback Satisfaction Star Ratings (1-5 Stars)."""
    conn = _get_db_conn(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT feedback_rating, COUNT(*)
            FROM tickets
            WHERE feedback_rating IS NOT NULL
            GROUP BY feedback_rating
        """)
        rows = dict(cursor.fetchall())
    finally:
        conn.close()

    labels = ['1 Star', '2 Stars', '3 Stars', '4 Stars', '5 Stars']
    counts = [rows.get(i, 0) for i in range(1, 6)]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)

    if any(counts):
        rects = ax.bar(labels, counts, color='#F1B82D', edgecolor='#800000', linewidth=1.5, alpha=0.9)
        ax.set_xlabel('Satisfaction Star Rating', fontsize=11, fontweight='bold')
        ax.set_ylabel('Number of Student Ratings', fontsize=11, fontweight='bold')
        ax.set_title('MapuaQ Student Satisfaction Ratings', fontsize=13, fontweight='bold', pad=15)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        ax.bar_label(rects, padding=3, fontweight='bold')
    else:
        ax.text(0.5, 0.5, 'No Student Feedback Recorded Yet', horizontalalignment='center',
                verticalalignment='center', transform=ax.transAxes, fontsize=12, color='gray')
        ax.set_title('MapuaQ Student Satisfaction Ratings', fontsize=13, fontweight='bold', pad=15)

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
