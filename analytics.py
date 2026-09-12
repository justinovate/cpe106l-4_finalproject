"""
MapuaQ Analytics Module
Generates queue volume analytics and priority distribution visualizations using Matplotlib.
"""

import io
import sqlite3
import matplotlib
matplotlib.use('Agg')  # Headless backend for web server rendering
import matplotlib.pyplot as plt


def get_analytics_summary(db_path: str = "students_queue.db") -> dict:
    """Returns key queue metrics from SQLite database."""
    conn = sqlite3.connect(db_path)
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

    conn.close()

    return {
        "total_tickets": total,
        "waiting_tickets": waiting,
        "served_tickets": served,
        "by_request": by_request,
        "by_level": by_level,
    }


def generate_queue_volume_chart(db_path: str = "students_queue.db") -> bytes:
    """Generates a PNG bar chart of queue volume by Request Type and Status."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT request_type, 
               SUM(CASE WHEN status = 'WAITING' THEN 1 ELSE 0 END) as waiting_count,
               SUM(CASE WHEN status = 'SERVED' THEN 1 ELSE 0 END) as served_count
        FROM tickets
        GROUP BY request_type
    """)
    rows = cursor.fetchall()
    conn.close()

    categories = [r[0] for r in rows] if rows else ["No Data"]
    waiting_counts = [r[1] for r in rows] if rows else [0]
    served_counts = [r[2] for r in rows] if rows else [0]

    short_cats = [c.split(" / ")[0] for c in categories]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=120)
    x = range(len(categories))
    width = 0.35

    rects1 = ax.bar([i - width/2 for i in x], waiting_counts, width, label='Waiting', color='#800000')  # Mapúa Cardinal
    rects2 = ax.bar([i + width/2 for i in x], served_counts, width, label='Served', color='#002B49')   # Mapúa Navy

    ax.set_ylabel('Number of Tickets', fontsize=11, fontweight='bold')
    ax.set_title('MapuaQ Queue Volume by Request Type', fontsize=13, fontweight='bold', pad=15)
    ax.set_xticks(list(x))
    ax.set_xticklabels(short_cats, rotation=15, ha='right', fontsize=9)
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


def generate_priority_distribution_chart(db_path: str = "students_queue.db") -> bytes:
    """Generates a PNG histogram of priority score distribution."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT priority_score FROM tickets")
    scores = [r[0] for r in cursor.fetchall()]
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
